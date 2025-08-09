import ast
import json
import os
from typing import Any
import datetime
import base64
from openai import AsyncOpenAI
import asyncio
from dotenv import load_dotenv
load_dotenv()

from nonebot import require
require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import md_to_pic

from zhenxun.models.sign_user import SignUser
from zhenxun.models.user_console import UserConsole
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.enum import GoldHandle

from .dlc.draw_picture import get_image
from .dlc.run_python import CodeExecutor
from .dlc.search import search


# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

save_path = f"{TEMP_PATH}\\see_picture.png"
class DEEKSEEKSession:
    def __init__(
        self,
        model_name="deepseek-reasoner",#'TIG-3.6-Mirage',#"deepseek-reasoner",  # "deepseek-chat",# "Pro/deepseek-ai/DeepSeek-R1"  # noqa: E501
        prompt="",
        max_code_executions=5,
        max_chat_turns=10,
        request_delay=1,
    ):
        self.model_name = model_name
        self.prompt = prompt
        self.max_code_executions = max_code_executions
        self.code_execution_count = 0
        self.max_chat_turns = max_chat_turns
        self.chat_history: list[dict[str, Any]] = []
        self.request_delay = request_delay
        self.code_executor = CodeExecutor(
            max_code_executions=max_code_executions
        )  # 创建 CodeExecutor 实例
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = 'https://api.deepseek.com/'


    async def send_message(self, message: Any, user_id,image_url:str = '',question:str='',reply_text:str='') -> str:
        tool_use, message = message
        
        """发送消息，处理代码执行，并进行滑动窗口式历史记录管理"""
        # logger.info(str(message.split(":")[1].split("[")[0]))
        sign_user = await SignUser.get_or_none(user_id=user_id)
        gold_user = await UserConsole.get_user(user_id)
        if not question:
            question = message
        if reply_text:
            self.chat_history.append({"role": "assistant", "content": f"用户引用了一条消息:\n{reply_text}"})#仅支持文字图片暂不支持
        if image_url:
            iamge_read=await self.see_picture(image_url)
            self.chat_history.append({"role": "assistant", "content": f"用户发来了一张图片其内容为{iamge_read}"})

        self.chat_history = self.chat_history[-self.max_chat_turns * 2:] 
        if tool_use:
            messages = message
        else:
            if  message.split(":")[1].split("[")[0] == '/deepseek':
                self.api_key = os.getenv("DEEPSEEK_API_KEY")#从deepseek官网获取
                self.base_url = 'https://api.deepseek.com/'
                self.model_name = 'deepseek-reasoner'
                await MessageUtils.build_message(f'已切换模型至{self.model_name}').finish()
                return f'已切换模型至{self.model_name}'

            elif message.split(":")[1].split("[")[0] == '/gemini':
                self.api_key = os.getenv("GOOGLE_API_KEY")#从gemini官网获取
                self.base_url = 'https://generativelanguage.googleapis.com/v1beta/openai/'
                self.model_name = 'gemini-2.5-flash'
                await MessageUtils.build_message(f'已切换模型至{self.model_name}').finish()
                return f'已切换模型至{self.model_name}'
            elif message.split(":")[1].split("[")[0] == '/幻宙':
                self.api_key = os.getenv("HUANZOU_API_KEY")#从幻宙官网获取效果不佳但有不稳定免费模型可白嫖https://phapi.furina.junmatec.cn
                self.base_url = 'https://phapi.furina.junmatec.cn/v1/'
                self.model_name = 'TIG-3.6-VL-Lite'#免费模型需要改名称
                await MessageUtils.build_message(f'已切换模型至{self.model_name}').finish()
                return f'已切换模型至{self.model_name}'
            elif message.split(":")[1].split("[")[0] in ["清除对话记录", "-clear", "遗忘"]:
                self.chat_history = []
                await MessageUtils.build_message("对话历史已清空").finish()
                return '对话历史已清空'
           
            messages = [
                {"role": "system", "content": self.prompt},
                {
                    "role": "assistant",
                    "content": f"用户基础信息：好感度：{sign_user.impression}，金币数量{gold_user.gold}",
                },
                *self.chat_history,
                {"role": "user", "content": question},
            ]
        logger.info(str(messages))
        client = AsyncOpenAI(api_key=self.api_key, base_url= self.base_url)
        response = await client.chat.completions.create(
            model=self.model_name, messages=messages, stream=True,stop=["?~~>"]
        )

        # 状态跟踪变量
        in_code_block = False
        code_block_type = ""
        code_block_buffer = ""
        text_buffer = ""
        paragraph_count = 0
        answer = ""

        #try:
        async for chunk in response:
            if (
                    not chunk.choices
                    or not chunk.choices[0].delta
                    or not chunk.choices[0].delta.content
                ):
                continue

            chunk_content = chunk.choices[0].delta.content
            

            if in_code_block:
                    # 代码块模式：专用缓冲区累积
                code_block_buffer += chunk_content

                    # 实时检测结束标记
                if "```" in code_block_buffer:
                    parts = code_block_buffer.split("```", 1)
                    #logger.info(parts)
                    true_content = parts[0]
                    trailing_text = parts[1] if len(parts) > 1 else ""
                    idx = true_content.find('\n')
                    #logger.info(idx)
                    try:
                        code_block_type = true_content[:4]
                        if code_block_type in ['json', 'jso']:
                            code_block_json = ast.literal_eval(true_content[4:])
                            if code_block_json["type"] == "python":
                                await self.run_python(
                                    code=code_block_json["source"], user_id=user_id,question=question,answer=answer
                                )
                            elif code_block_json["type"] == "search":
                                await self.search_from_web(
                                    search_information=code_block_json["source"], user_id=user_id,answer=answer,question=question
                                )
                            elif code_block_json["type"] == "draw":
                                await self.draw_picture(code=code_block_json["source"],question=question)
                                return code_block_json["source"]
                            elif code_block_json["type"] == "gold":
                                await self.gold(gold=float(code_block_json["source"]),user_id=user_id,answer=answer,question=question)
                        else:
                            answer += f"```\n{true_content}\n```"
                            await MessageUtils.build_message(f"base64://{base64.b64encode(await md_to_pic(f'```{true_content}```',screenshot_timeout=9999999)).decode('utf-8')}").send()
                        #print(code_block_json["type"])
                        #print(code_block_json["source"])
                    except:
                        if code_block_type in ['json', 'jso']:
                            pass
                        else:
                            answer += f"```\n{true_content}\n```"
                            await MessageUtils.build_message(f"```\n{true_content}\n```").send()

                    # 输出完整代码块
                    print(
                            "\n"
                            + "-" * 20
                            + f" CODE BLOCK ({code_block_type}) "
                            + "-" * 20
                        )
                    print(true_content)
                    print("-" * 50 + "\n")
                    # 退出代码块状态
                    in_code_block = False
                    code_block_type = ""
                    # 结束标记后的文本转入普通缓冲区
                    text_buffer += trailing_text  # 关键修复：使用 += 而不是 =
            else:
                # 普通文本模式
                text_buffer += chunk_content

                # 检测代码块开始
                if "```" in text_buffer:
                    parts = text_buffer.split("```", 1)
                    # 输出代码块前的文本（如果有）
                    if parts[0].strip():  # 关键修复：检查是否有实际内容
                        paragraph_count += 1
                        '''print(
                                "\n"
                                + "-" * 10
                                + f" PARAGRAPH {paragraph_count} "
                                + "-" * 10
                            )'''
                        #print(parts[0].strip())
                        answer += parts[0].strip()
                        await MessageUtils.build_message(parts[0].strip()).send()

                        # 准备进入代码块状态
                    in_code_block = True
                    code_block_buffer = parts[1] if len(parts) > 1 else ""
                    text_buffer = ""  # 清空文本缓冲区
                    continue

                    # 处理段落分割（改进版）
                while "\n\n" in text_buffer:
                    idx = text_buffer.index("\n\n")
                    paragraph = text_buffer[:idx].strip()  # 获取并清理段落内容
                    text_buffer = text_buffer[idx + 2 :]  # 移除已处理部分

                        # 只输出非空段落
                    if paragraph and paragraph !='---':
                        paragraph_count += 1
                            # print("\n" + "-"*10 + f" PARAGRAPH {paragraph_count} " + "-"*10)
                            # print(paragraph)
                        answer += paragraph
                        await MessageUtils.build_message(paragraph).send()

            # 循环结束后处理剩余内容（关键修复）
        if in_code_block:
            # 处理未结束的代码块
            if code_block_type in ['json', 'jso']:
                true_content = parts[0]
                idx = 4
                code_block_json = ast.literal_eval(true_content[idx:])
                if code_block_json["type"] == "python":
                   
                    await self.run_python(
                        code=code_block_json["source"], user_id=user_id,question=question,answer=answer
                    )
                elif code_block_json["type"] == "search":
                    await self.search_from_web(
                    search_information=code_block_json["source"], user_id=user_id,answer=answer,question=question
                        )
                elif code_block_json["type"] == "draw":
                    await self.draw_picture(code=code_block_json["source"],question=question)
                    return code_block_json["source"]
            else:
                true_content = parts[0]
                # 添加deepseek回复到历史记录
                answer += f"```\n{true_content}\n```"
                self.chat_history.append({"role": "user", "content": question})
                self.chat_history.append({"role": "assistant", "content": answer})
                self.code_execution_count = 0
               
                await MessageUtils.build_message(true_content).finish()
            #print("\n" + "-" * 20 + f" CODE BLOCK ({code_block_type}) " + "-" * 20)
            #print(code_block_buffer)
            #print("-" * 50 + "\n")
        elif text_buffer.strip():
            # 处理剩余的文本内容
            paragraphs = [p.strip() for p in text_buffer.split("\n\n") if p.strip()]
            for i, p in enumerate(paragraphs):
                paragraph_count += 1
                #print("\n" + "-" * 10 + f" PARAGRAPH {paragraph_count} " + "-" * 10)
                #print(p)
                # 添加deepseek回复到历史记录
                answer += p
                self.chat_history.append({"role": "user", "content": question})
                self.chat_history.append({"role": "assistant", "content": answer})
                self.code_execution_count = 0
                
                await MessageUtils.build_message(p).finish()

        '''except Exception as e:
            print(f"\nError occurred: {e!s}")
            # 确保在出错时也输出已收集的内容
            if in_code_block and code_block_buffer:
                print("\n" + "-" * 20 + f" CODE BLOCK ({code_block_type}) " + "-" * 20)
                print(code_block_buffer)
                print("-" * 50 + "\n")
            elif text_buffer.strip():
                print("\n" + "-" * 10 + " FINAL TEXT " + "-" * 10)
                print(text_buffer.strip())'''

        
        
        return answer  # type: ignore
    async def see_picture(self,image_url):
        await AsyncHttpx.download_file(image_url,save_path)
        with open(save_path,'rb') as file:
            byte_data = file.read()
            image_base64 =base64.b64encode(byte_data).decode("utf-8")
            client = AsyncOpenAI(api_key=os.getenv("SILICONFLOW_API_KEY"),base_url= "https://api.siliconflow.cn/v1/")
            message = [{"role":"system","content":"你需要描述你所看到的图像描述要简短清晰如果是文字类图片直接返回所有文字，注意不要加你的见解！！！！"},
                       {"role":"user","content":[{"type": "image_url","image_url": {"url": f"data:image/png;base64,{image_base64}"}}]}]
            response = await client.chat.completions.create(model='Qwen/Qwen2.5-VL-32B-Instruct',messages=message)
            return response.choices[0].message.content
    async def run_python(self, code, user_id,question,answer):
        logger.info("正在尝试运行python代码")
        logger.info(str(code))
        sign_user = await SignUser.get_or_none(user_id=user_id)
        gold_user = await UserConsole.get_user(user_id)
        code_output = await self.code_executor.execute_python_code(
            code
        )  # 使用 CodeExecutor 执行代码
        if "代码执行次数已达上限" not in code_output:
            response_text = f"{code_output}"
            messages = (
                True,
                (
                    [
                        {"role": "system", "content": self.prompt},
                        {
                            "role": "assistant",
                            "content": f"用户基础信息：好感度：{sign_user.impression}，金币数量{gold_user.gold}",
                        },
                        {"role":"assistant","content":answer},
                        {"role":"user","content":question},
                        {"role": "assistant", "content": response_text},
                        {
                            "role": "user",
                            "content": "系统消息:如果运行失败就尝试修复代码，如果运行成功就给用户回复",
                        },
                    ]
                ),
            )
            logger.info(response_text)
            await self.send_message(message=messages, user_id=user_id,question=question)
        else:
            await MessageUtils.build_message(
                f"代码运行上限请重新提问{code_output}"
            ).finish()

    async def search_from_web(self, question, user_id,answer,search_information):
        if self.model_name.find('gemini'):
            asyncio.sleep(1)
        sign_user = await SignUser.get_or_none(user_id=user_id)
        gold_user = await UserConsole.get_user(user_id)
        response = await search(search_information)
        messages = (
            True,
            (
                [
                    {"role": "system", "content": self.prompt},
                    {
                        "role": "assistant",
                        "content": f"用户基础信息：好感度：{sign_user.impression}，金币数量{gold_user.gold}",
                    },
                    {"role":"user","content":question},
                    {"role":"assistant","content":answer},
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": "系统消息:请根据搜索内容给用户回复"},
                ]
            ),
        )
        logger.info(response)
        await self.send_message(message=messages, user_id=user_id,question=question)

    async def draw_picture(self, code,question):
        image = await get_image(code)
        logger.info(code)
        self.chat_history.append({"role": "user", "content": question})
        self.chat_history.append({"role": "assistant", "content": f"绘图命令:{code}"})

        await MessageUtils.build_message(image).finish()
    async def gold(self,gold,user_id,question,answer):
        sign_user = await SignUser.get_or_none(user_id=user_id)
        gold_user = await UserConsole.get_user(user_id)
        if gold > 0:
            await UserConsole.add_gold(user_id, gold, 'ai')
            end ='添加'
        elif gold <0:
            await UserConsole.reduce_gold(user_id,gold, GoldHandle.BUY , 'ai')
            end = '减少'
        messages = (True,([
                {"role": "system", "content": self.prompt},
                {
                    "role": "assistant",
                    "content": f"用户基础信息：好感度：{sign_user.impression}，金币数量{gold_user.gold}",
                },
                {"role":"user","content":question},
                {"role":"assistant","content":answer},
                {"role":"assistant","content":f"已成功{end}{gold}金币"},
                {"role": "user", "content": "系统消息:请根据特殊能力返回给用户回复"},
            ]))
        await self.send_message(message=messages, user_id=user_id,question=question)


class DEEPSEEKManager:
    def __init__(self):
        self.sessions: dict[str, DEEKSEEKSession] = {}

    def create_session(
        self,
        session_id: str,
        prompt: str = "",
        max_code_executions: int = 5,
        max_chat_turns: int = 10,
        request_delay: int = 1,
    ) -> None:
        """创建新的会话"""
        if session_id in self.sessions:
            raise ValueError(f"Session ID '{session_id}' already exists.")
        self.sessions[session_id] = DEEKSEEKSession(
            prompt=prompt,
            max_code_executions=max_code_executions,
            max_chat_turns=max_chat_turns,
            request_delay=request_delay,
        )

    def get_session(self, session_id: str) -> DEEKSEEKSession:
        """获取指定会话"""
        if session_id not in self.sessions:
            raise ValueError(f"Session ID '{session_id}' not found.")
        return self.sessions[session_id]

    def delete_session(self, session_id: str) -> None:
        """删除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        else:
            raise ValueError(f"Session ID '{session_id}' not found.")