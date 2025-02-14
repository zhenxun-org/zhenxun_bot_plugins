import asyncio
import ujson as json
import os
import random
import re
import time
from typing import ClassVar, Literal, Sequence, AsyncGenerator
from inspect import signature, Parameter
import uuid

from nonebot import require, get_bot
from nonebot_plugin_alconna import Text, UniMessage, UniMsg
from nonebot.plugin import get_loaded_plugins
from nonebot.compat import model_dump
from nonebot.adapters import Event, Bot
from pydantic import BaseModel

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.models.sign_user import SignUser
from zhenxun.services.log import logger
from zhenxun.utils.decorator.retry import Retry
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.utils import AICallableTag, PluginExtraData

from .model import BymChat

require("sign_in")

from zhenxun.builtin_plugins.sign_in.utils import (
    get_level_and_next_impression,
    level2attitude,
)

from .config import (
    BYM_CONTENT,
    DEFAULT_GROUP,
    NO_RESULT,
    NO_RESULT_IMAGE,
    NORMAL_CONTENT,
    NORMAL_IMPRESSION_CONTENT,
    PROMPT_FILE,
    TIP_CONTENT,
    Tool,
    OpenAiResult,
    base_config,
)

semaphore = asyncio.Semaphore(3)

total_tools_registry: dict[str, AICallableTag] = {}

class MessageCache(BaseModel):
    user_id: str
    """用户id"""
    nickname: str
    """用户昵称"""
    message: UniMsg
    """消息"""

    class Config:
        arbitrary_types_allowed = True


class ChatMessage(BaseModel):
    role: str
    """角色"""
    content: str | list | None = None
    """消息内容"""
    tool_call_id: str | None = None
    """工具回调id"""
    tool_calls: list[Tool] | None = None
    """工具回调信息"""

    class Config:
        arbitrary_types_allowed = True


def split_text(text: str) -> list[tuple[str, float]]:
    """文本切割"""
    results = []
    split_list = [
        s for s in __split_text(text, r"(?<!\?)[。？\n](?!\?)", 3) if s.strip() and s != "<EMPTY>"
    ]
    for r in split_list:
        next_char_index = text.find(r) + len(r)
        if next_char_index < len(text) and text[next_char_index] == "？":
            r += "？"
        results.append((r, min(len(r) * 0.2, 3.0)))
    return results


def __split_text(text: str, regex: str, limit: int) -> list[str]:
    """文本切割"""
    result = []
    last_index = 0
    global_regex = re.compile(regex)

    for match in global_regex.finditer(text):
        if len(result) >= limit - 1:
            break

        result.append(text[last_index : match.start()])
        last_index = match.end()
    result.append(text[last_index:])
    return result

def _filter_result(result: str | None):
    if not result:
        return result
    
    result = result.replace('<EMPTY>', '')
    
    # 去掉首尾的空白字符
    result = result.strip()
    
    # 如果过滤后的结果为空字符串，则返回 None
    if not result:
        return None
    
    return result


class TokenCounter:
    def __init__(self):
        if tokens := base_config.get("BYM_AI_CHAT_TOKEN"):
            if isinstance(tokens, str):
                tokens = [tokens]
            self.tokens = {t: 0 for t in tokens}

    def get_token(self) -> str:
        """获取token，将时间最小的token返回"""
        token_list = sorted(self.tokens.keys(), key=lambda x: self.tokens[x])
        result_token = token_list[0]
        self.tokens[result_token] = int(time.time())
        return token_list[0]

    def delay(self, token: str):
        """延迟token"""
        if token in self.tokens:
            """等待15分钟"""
            self.tokens[token] = int(time.time()) + 60 * 15


token_counter = TokenCounter()


class Conversation:
    """预设存储"""

    history_data: ClassVar[dict[str, list[ChatMessage]]] = {}

    chat_prompt: str = ""

    @classmethod
    def add_system(cls) -> ChatMessage:
        """添加系统预设"""
        if not cls.chat_prompt:
            cls.chat_prompt = PROMPT_FILE.open(encoding="utf8").read()
        return ChatMessage(role="system", content=cls.chat_prompt)

    @classmethod
    async def get_db_data(cls, user_id: str) -> list[ChatMessage]:
        """从数据库获取记录

        参数:
            user_id: 用户id

        返回:
            list[ChatMessage]: 记录列表
        """
        conversation = []
        for db_data in (
            await BymChat.filter(user_id=user_id).order_by("-id").limit(40).all()
        ):
            if db_data.is_reset:
                break
            conversation.extend(
                (
                    ChatMessage(role="assistant", content=db_data.result),
                    ChatMessage(role="user", content=db_data.plain_text),
                )
            )
        conversation.reverse()
        return conversation

    @classmethod
    async def get_conversation(cls, user_id: str) -> list[ChatMessage]:
        """获取预设

        参数:
            user_id: 用户id

        返回:
            list[ChatMessage]: 预设数据
        """
        conversation = []
        if user_id in cls.history_data:
            conversation = cls.history_data[user_id]
        else:
            # 尝试从数据库中获取历史对话
            conversation = await cls.get_db_data(user_id)
        if not conversation or conversation[0].role != "system":
            conversation.insert(0, cls.add_system())
        return conversation

    @classmethod
    def set_history(cls, user_id: str, conversation: list[ChatMessage]):
        """设置历史预设

        参数:
            user_id: 用户id
            conversation: 消息记录
        """
        if len(conversation) > 40:
            conversation = [conversation[0]] + conversation[-39:]
        cls.history_data[user_id] = conversation

    @classmethod
    async def reset(cls, user_id: str):
        """重置预设

        参数:
            user_id: 用户id
        """
        if db_data := await BymChat.filter(user_id=user_id).order_by("-id").first():
            db_data.is_reset = True
            await db_data.save(update_fields=["is_reset"])
        if user_id in cls.history_data:
            del cls.history_data[user_id]


class CallApi:
    def __init__(self):
        self.chat_url = base_config.get("BYM_AI_CHAT_URL")
        self.chat_model = base_config.get("BYM_AI_CHAT_MODEL")
        self.chat_token = token_counter.get_token()

        self.tts_url = Config.get_config("bym_ai", "BYM_AI_TTS_URL")
        self.tts_token = Config.get_config("bym_ai", "BYM_AI_TTS_TOKEN")
        self.tts_voice = Config.get_config("bym_ai", "BYM_AI_TTS_VOICE")

    @Retry.api()
    async def fetch_chat(self, user_id: str, conversation: list[ChatMessage], tools: Sequence[AICallableTag]) -> OpenAiResult:
        send_json = {
            "messages": [model_dump(model=c, exclude_none=True) for c in conversation],
            "stream": False,
            "model": self.chat_model,
            "tools": [{"type": "function", "function": tool.to_dict()} for tool in tools],
            "tool_choice": "auto",
            "temperature": 0.7,
        }
                
        response = await AsyncHttpx.post(
            self.chat_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.chat_token}",
            },
            json=send_json,
            verify=False
        )

        if response.status_code == 429:
            logger.debug(
                f"fetch_chat 请求失败: 限速, token: {self.chat_token} 延迟 15 分钟",
                "BYM_AI",
                session=user_id,
            )
            token_counter.delay(self.chat_token)

        response.raise_for_status()
        return OpenAiResult(**response.json())

    @Retry.api()
    async def fetch_tts(
        self, content: str, retry_count: int = 3, delay: int = 5
    ) -> bytes | None:
        """获取tts语音

        参数:
            content: 内容
            retry_count: 重试次数.
            delay: 重试延迟.

        返回:
            bytes | None: 语音数据
        """
        if not self.tts_url or not self.tts_token or not self.tts_voice:
            return None

        headers = {"Authorization": f"Bearer {self.tts_token}"}
        payload = {"model": "hailuo", "input": content, "voice": self.tts_voice}

        async with semaphore:
            for _ in range(retry_count):
                try:
                    response = await AsyncHttpx.post(
                        self.tts_url, headers=headers, json=payload
                    )
                    response.raise_for_status()
                    if "audio/mpeg" in response.headers.get("Content-Type", ""):
                        return response.content
                    logger.warning(f"fetch_tts 请求失败: {response.content}", "BYM_AI")
                    await asyncio.sleep(delay)

                except Exception as e:
                    logger.error("fetch_tts 请求失败", "BYM_AI", e=e)

        return None


class ChatManager:
    group_cache: ClassVar[dict[str, list[MessageCache]]] = {}
    user_impression: ClassVar[dict[str, float]] = {}
    event: Event
    bot: Bot

    @classmethod
    def format(
        cls, type: Literal["system", "user", "text"], data: str
    ) -> dict[str, str]:
        """格式化数据

        参数:
            data: 文本

        返回:
            dict[str, str]: 格式化字典文本
        """
        return {
            "type": type,
            "text": data,
        }

    @classmethod
    def __build_content(cls, message: UniMsg) -> list[dict[str, str]]:
        """获取消息文本内容

        参数:
            message: 消息内容

        返回:
            list[dict[str, str]]: 文本列表
        """
        return [
            cls.format("text", seg.text) for seg in message if isinstance(seg, Text)
        ]

    @classmethod
    async def __get_normal_content(
        cls, user_id: str, nickname: str, message: UniMsg
    ) -> list[dict[str, str]]:
        """获取普通回答文本内容

        参数:
            user_id: 用户id
            nickname: 用户昵称
            message: 消息内容

        返回:
            list[dict[str, str]]: 文本序列
        """
        content = cls.__build_content(message)
        if user_id not in cls.user_impression:
            sign_user = await SignUser.get_user(user_id)
            cls.user_impression[user_id] = float(sign_user.impression)
        level, _, _ = get_level_and_next_impression(cls.user_impression[user_id])
        level = "1" if level == "0" else level
        content.insert(
            0,
            cls.format(
                "text",
                NORMAL_IMPRESSION_CONTENT.format(
                    nickname=nickname,
                    impression=cls.user_impression[user_id],
                    attitude=level2attitude[level],
                )
                if base_config.get("ENABLE_IMPRESSION")
                else NORMAL_CONTENT.format(
                    nickname=nickname,
                ),
            ),
        )
        return content

    @classmethod
    def __get_bym_content(
        cls, user_id: str, group_id: str | None, nickname: str
    ) -> list[dict[str, str]]:
        """获取伪人回答文本内容

        参数:
            user_id: 用户id
            group_id: 群组id
            nickname: 用户昵称

        返回:
            list[dict[str, str]]: 文本序列
        """
        if not group_id:
            group_id = DEFAULT_GROUP
        content = [
            cls.format(
                "text",
                BYM_CONTENT.format(
                    user_id=user_id, group_id=group_id, nickname=nickname, self_id=cls.bot.self_id
                ),
            )
        ]
        if group_message := cls.group_cache.get(group_id):
            for message in group_message:
                content.append(
                    cls.format("text", f"用户昵称：{message.nickname} 用户ID：{message.user_id}")
                )
                content.extend(cls.__build_content(message.message))
        content.append(cls.format("text", TIP_CONTENT))
        return content

    @classmethod
    def add_cache(
        cls, user_id: str, group_id: str | None, nickname: str, message: UniMsg
    ):
        """添加消息缓存

        参数:
            user_id: 用户id
            group_id: 群组id
            nickname: 用户昵称
            message: 消息内容
        """
        if not group_id:
            group_id = DEFAULT_GROUP
        message_cache = MessageCache(
            user_id=user_id, nickname=nickname, message=message
        )
        if group_id not in cls.group_cache:
            cls.group_cache[group_id] = [message_cache]
        else:
            cls.group_cache[group_id].append(message_cache)
        if len(cls.group_cache[group_id]) >= 30:
            cls.group_cache[group_id].pop(0)

    @classmethod
    async def get_result(
        cls,
        bot: Bot,
        event: Event,
        user_id: str,
        group_id: str | None,
        nickname: str,
        message: UniMsg,
        is_bym: bool,
    ) -> AsyncGenerator[str | None, None]:
        """获取回答结果

        参数:
            user_id: 用户id
            group_id: 群组id
            nickname: 用户昵称
            message: 消息内容
            is_bym: 是否伪人

        返回:
            str | None: 消息内容
        """
        cls.add_cache(user_id, group_id, nickname, message)
        cls.event = event
        cls.bot = bot
        if is_bym:
            content = cls.__get_bym_content(user_id, group_id, nickname)
            conversation = []            
        else:
            content = await cls.__get_normal_content(user_id, nickname, message)
            conversation = Conversation.get_conversation(user_id)
        conversation.append(ChatMessage(role="user", content=content))

        # 加载工具集
        if base_config.get("BYM_AI_CHAT_SMART"):
            tools = cls._load_tools()
        else:
            tools = []

        result = await CallApi().fetch_chat(user_id, conversation, tools)
        async for res in cls._handle_result(user_id, conversation, result, tools):
            res = _filter_result(res)
            if res:
                cls.add_cache(cls.bot.self_id, group_id, BotConfig.self_nickname, MessageUtils.build_message(res))
            yield res

    @classmethod
    def _load_tools(cls) -> list[AICallableTag]:
        """加载可用的工具

        加载的工具分为两部分：
            tools目录下所有继承了 AbstractTool 类的工具
            bot中所有带有属性 smart_tools 的插件
        """
        tools = []
        loaded_plugins = get_loaded_plugins()
        
        for plugin in loaded_plugins:
            if not plugin or not plugin.metadata or not plugin.metadata.extra:
                continue
            extra_data = PluginExtraData.model_validate(plugin.metadata.extra)
            if extra_data.smart_tools:
                smart_tools = [
                    tool for tool in extra_data.smart_tools
                    if tool.name and tool.description and tool.func
                ]
                tools.extend(smart_tools)
        
        total_tools_registry.update({tool.name: tool for tool in tools if tool.name})
        
        return tools
        

    @classmethod
    async def _handle_result(
        cls,
        user_id: str,
        conversation: list[ChatMessage],
        result: OpenAiResult,
        tools: Sequence[AICallableTag]
    ) -> AsyncGenerator[str | None, None]:
        """处理API响应并处理工具回调

        参数:
            user_id: 用户id
            conversation: 当前对话
            result: API响应结果
            tools: 可用的工具列表

        返回:
            str | None: 处理后的消息内容
        """
        assistant_reply = None
        if result.choices and (msg := result.choices[0].message):
            if msg.content:
                assistant_reply = msg.content.strip()

            conversation.append(ChatMessage(role="assistant", content=assistant_reply, tool_calls=msg.tool_calls))
            Conversation.set_history(user_id, conversation)

            yield assistant_reply

            # 处理工具回调
            if msg.tool_calls:
                temp_conversation = conversation
                for tool_call in msg.tool_calls:
                    if not tool_call.id:
                        tool_call.id = str(uuid.uuid4())
                    func = tool_call.function
                    tool = total_tools_registry.get(func.name)
                    args = func.arguments
                    if tool and tool.func and args:
                        func_sign = signature(tool.func)
                        parsed_args = json.loads(args)
                        parsed_args['event'] = cls.event
                        parsed_args['bot'] = cls.bot
                        func_params = {
                            key: parsed_args[key] for key, param in func_sign.parameters.items()
                            if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY) and key in parsed_args
                        }
                        try:
                            tool_result = await tool.func(**func_params)
                        except Exception as e:
                            tool_result = str(e)
                        temp_conversation.append(
                            ChatMessage(role="tool", tool_call_id=tool_call.id, content=str(tool_result))
                        )
                rst = await CallApi().fetch_chat(user_id, temp_conversation, tools)
                async for res in cls._handle_result(user_id, conversation, rst, tools):
                    yield res

    @classmethod
    async def tts(cls, content: str) -> bytes | None:
        """获取tts语音

        参数:
            content: 文本数据

        返回:
            bytes | None: 语音数据
        """
        return await CallApi().fetch_tts(content)

    @classmethod
    def no_result(cls) -> UniMessage:
        """
        没有回答时的回复
        """
        return MessageUtils.build_message(
            [
                random.choice(NO_RESULT),
                IMAGE_PATH / "noresult" / random.choice(NO_RESULT_IMAGE),
            ]
        )

    @classmethod
    def hello(cls) -> UniMessage:
        """一些打招呼的内容"""
        result = random.choice(
            (
                "哦豁？！",
                "你好！Ov<",
                f"库库库，呼唤{BotConfig.self_nickname}做什么呢",
                "我在呢！",
                "呼呼，叫俺干嘛",
            )
        )
        img = random.choice(os.listdir(IMAGE_PATH / "zai"))
        return MessageUtils.build_message([IMAGE_PATH / "zai" / img, result])
