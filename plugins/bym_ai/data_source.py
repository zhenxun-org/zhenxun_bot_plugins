import asyncio
from datetime import datetime
import os
import random
import re
from typing import ClassVar, Literal

from nonebot.adapters import Bot
from nonebot_plugin_alconna import UniMessage, UniMsg
from nonebot_plugin_uninfo import Uninfo

from zhenxun.builtin_plugins.sign_in.utils import (
    get_level_and_next_impression,
    level2attitude,
)
from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.models.group_console import GroupConsole
from zhenxun.models.sign_user import SignUser
from zhenxun.services.llm import AI, LLMContentPart, LLMResponse
from zhenxun.services.llm.tools import RunContext, ToolInvoker, tool_provider_manager
from zhenxun.services.llm.utils import extract_text_from_content, unimsg_to_llm_parts
from zhenxun.services.log import logger
from zhenxun.utils.decorator.retry import Retry
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

from .config import (
    BYM_CONTENT,
    DEEP_SEEK_SPLIT,
    DEFAULT_GROUP,
    GROUP_CONTENT,
    NO_RESULT,
    NO_RESULT_IMAGE,
    NORMAL_CONTENT,
    NORMAL_IMPRESSION_CONTENT,
    TIP_CONTENT,
    FunctionParam,
    MessageCache,
    base_config,
)
from .exception import NotResultException
from .memory_backend import BymMemory
from .models.bym_gift_log import GiftLog

semaphore = asyncio.Semaphore(3)


GROUP_NAME_CACHE = {}


def split_text(text: str) -> list[tuple[str, float]]:
    """文本切割"""
    results = []
    split_list = [
        s
        for s in __split_text(text, r"(?<!\?)[。？\n](?!\?)", 3)
        if s.strip() and s != "<EMPTY>"
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


def _filter_result(result: str) -> str:
    result = result.replace("<EMPTY>", "").strip()
    return re.sub(r"(.)\1{5,}", r"\1" * 5, result)


def _strip_noise(text: str) -> str:
    for pattern in (
        r"```tool_code([\s\S]*?)```",
        r"```json([\s\S]*?)```",
        r"</?思考过程>([\s\S]*?)</?思考过程>",
        r"</?thought>([\s\S]*?)</?thought>",
    ):
        text = re.sub(pattern, "", text).strip()
    return text


def remove_deep_seek(text: str, is_tool: bool) -> str:
    """去除深度探索"""
    logger.debug(f"去除深度思考前原文：{text}", "BYM_AI")
    if "```" in text.strip() and not text.strip().endswith("```"):
        text += "```"

    def _extract(text_value: str) -> str | None:
        patterns = (
            ("findall", r"</?content>([\s\S]*?)</?content>"),
            ("findall", r"```<content>([\s\S]*?)```"),
            ("findall", r"```xml([\s\S]*?)```"),
            ("findall", r"```content([\s\S]*?)```"),
            ("search", r"instruction[:,：](.*)<\/code>"),
            ("findall", r"<think>\n(.*?)\n</think>"),
            ("search", r"Response[:,：]\*?\*?(.*)"),
        )
        for mode, pattern in patterns:
            if mode == "findall":
                match = re.findall(pattern, text_value, re.DOTALL)
                if match:
                    return match[-1]
            else:
                match = re.search(pattern, text_value, re.DOTALL)
                if match:
                    return match[1]
        if len(re.split(r"最终(回复|结果)[：,:]", text_value, re.DOTALL)) > 1:
            return re.split(r"最终(回复|结果)[：,:]", text_value, re.DOTALL)[-1]
        if "回复用户" in text_value:
            return re.split("回复用户.{0,1}", text_value)[-1]
        if "最终回复" in text_value:
            return re.split("最终回复.{0,1}", text_value)[-1]
        if "Response text:" in text_value:
            return re.split("Response text[:,：]", text_value)[-1]
        return None

    match_text = _extract(text)
    if match_text:
        return _extracted_from_remove_deep_seek_30(match_text)

    text = _strip_noise(text)
    if is_tool:
        if DEEP_SEEK_SPLIT in text:
            return text.split(DEEP_SEEK_SPLIT, 1)[-1].strip()
        if match := re.search(r"```text\n([\s\S]*?)\n```", text, re.DOTALL):
            text = match[1]
        if text.endswith("```"):
            text = text[:-3].strip()
        if match := re.search(r"<content>\n([\s\S]*?)\n</content>", text, re.DOTALL):
            text = match[1]
        elif match := re.search(r"<think>\n([\s\S]*?)\n</think>", text, re.DOTALL):
            text = match[1]
        elif "think" in text:
            if text.count("think") == 2:
                text = re.split("<.{0,1}think.*>", text)[1]
            else:
                text = re.split("<.{0,1}think.*>", text)[-1]
        else:
            arr = text.split("\n")
            index = next((i for i, a in enumerate(arr) if not a.strip()), 0)
            if index != 0:
                text = "\n".join(arr[index + 1 :])
            text = re.sub(r"^[\s\S]*?结果[:,：]\n", "", text)
        return (
            re.sub(r"深度思考：[\s\S]*?\n\s*\n", "", text)
            .replace("深度思考结束。", "")
            .strip()
        )
    else:
        text = text.strip().split("\n")[-1]
        text = re.sub(r"^[\s\S]*?结果[:,：]\n", "", text)
    return re.sub(r"<\/?content>", "", text).replace("深度思考结束。", "").strip()


def _extracted_from_remove_deep_seek_30(match_text):
    match_text = re.sub(r"```tool_code([\s\S]*?)```", "", match_text).strip()
    match_text = re.sub(r"```json([\s\S]*?)```", "", match_text).strip()
    match_text = re.sub(r"</?思考过程>([\s\S]*?)</?思考过程>", "", match_text).strip()
    match_text = re.sub(
        r"\[\/?instruction\]([\s\S]*?)\[\/?instruction\]", "", match_text
    ).strip()
    match_text = re.sub(r"</?thought>([\s\S]*?)</?thought>", "", match_text).strip()
    return re.sub(r"<\/?content>", "", match_text)


class CallApi:
    def __init__(self):
        # tts 语音相关配置仍使用原有实现
        self.tts_url = Config.get_config("bym_ai", "BYM_AI_TTS_URL")
        self.tts_token = Config.get_config("bym_ai", "BYM_AI_TTS_TOKEN")
        self.tts_voice = Config.get_config("bym_ai", "BYM_AI_TTS_VOICE")

    @Retry.api(exception=(NotResultException,))
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
    user_impression: ClassVar[dict[str, tuple[float, float]]] = {}
    user_impression_ttl = 6 * 60 * 60

    @classmethod
    def format(
        cls, type: Literal["system", "user", "text", "image_url"], data: str
    ) -> dict[str, str | dict[str, str]]:
        """格式化数据

        参数:
            data: 数据

        返回:
            dict[str, str]: 格式化字典文本
        """

        if type == "image_url":
            return {"type": type, "image_url": {"url": data}}
        else:
            return {
                "type": type,
                "text": data,
            }

    @classmethod
    async def __build_content(cls, message: UniMsg) -> list[LLMContentPart]:
        """
        获取消息内容

        参数:
            message: 消息内容

        返回:
            list[LLMContentPart]: 消息内容片段列表
        """
        # 完全交给 LLM 的 UniMessage → LLMContentPart 转换逻辑处理
        return await unimsg_to_llm_parts(message)

    @classmethod
    async def __get_normal_content(
        cls, user_id: str, group_id: str | None, nickname: str, message: UniMsg
    ) -> list[LLMContentPart]:
        """获取普通回答文本内容

        参数:
            user_id: 用户id
            nickname: 用户昵称
            message: 消息内容

        返回:
            list[LLMContentPart]: 文本序列（多模态）
        """
        content_parts = await cls.__build_content(message)
        now_ts = datetime.now().timestamp()
        impression_cache = cls.user_impression.get(user_id)
        if (
            not impression_cache
            or now_ts - impression_cache[1] > cls.user_impression_ttl
        ):
            sign_user = await SignUser.get_user(user_id)
            cls.user_impression[user_id] = (float(sign_user.impression), now_ts)
        impression_value = cls.user_impression[user_id][0]
        gift_count = await GiftLog.filter(
            user_id=user_id, create_time__gte=datetime.now().date()
        ).count()
        level, _, _ = get_level_and_next_impression(impression_value)
        level = "1" if level in ["0"] else level
        content_result = (
            NORMAL_IMPRESSION_CONTENT.format(
                time=datetime.now(),
                nickname=nickname,
                user_id=user_id,
                impression=impression_value,
                max_impression=impression_value + 30,
                attitude=level2attitude[str(level)],
                gift_count=gift_count,
            )
            if base_config.get("ENABLE_IMPRESSION")
            else NORMAL_CONTENT.format(
                nickname=nickname,
                user_id=user_id,
            )
        )
        if group_id and base_config.get("ENABLE_GROUP_CHAT"):
            if group_id not in GROUP_NAME_CACHE:
                if group := await GroupConsole.get_group(group_id):
                    GROUP_NAME_CACHE[group_id] = group.group_name
            content_result = (
                GROUP_CONTENT.format(
                    group_id=group_id, group_name=GROUP_NAME_CACHE.get(group_id, "")
                )
                + content_result
            )
        # 将前置的描述拼到最前面
        parts: list[LLMContentPart] = [LLMContentPart.text_part(content_result)]
        parts.extend(content_parts)
        return parts

    @classmethod
    async def __get_bym_content(
        cls, bot: Bot, user_id: str, group_id: str | None, nickname: str
    ) -> list[LLMContentPart]:
        """获取伪人回答文本内容

        参数:
            user_id: 用户id
            group_id: 群组id
            nickname: 用户昵称

        返回:
            list[LLMContentPart]: 文本序列（纯文本）
        """
        if not group_id:
            group_id = DEFAULT_GROUP
        base_text = BYM_CONTENT.format(
            user_id=user_id,
            group_id=group_id,
            nickname=nickname,
            self_id=bot.self_id,
        )
        content: list[LLMContentPart] = [LLMContentPart.text_part(base_text)]
        if group_message := cls.group_cache.get(group_id):
            for message in group_message:
                content.append(
                    LLMContentPart.text_part(
                        f"用户昵称：{message.nickname} 用户ID：{message.user_id}"
                    )
                )
                content.extend(await cls.__build_content(message.message))
        content.append(LLMContentPart.text_part(TIP_CONTENT))
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
        cache_size = base_config.get("GROUP_CACHE_SIZE") or 30
        if len(cls.group_cache[group_id]) >= cache_size:
            cls.group_cache[group_id].pop(0)

    @classmethod
    async def _run_tools(
        cls,
        tool_calls: list,
        tool_names: list[str],
        session_key: str,
        func_param: FunctionParam,
    ) -> list:
        if not tool_calls:
            return []
        resolved_tools = await tool_provider_manager.resolve_specific_tools(tool_names)
        if not resolved_tools:
            return []
        context = RunContext(
            session_id=session_key,
            scope={
                "bot": func_param.bot,
                "event": func_param.event,
                "session": func_param.session,
                "message": func_param.message,
            },
            extra={
                "arparma": func_param.arparma,
            },
        )
        invoker = ToolInvoker()
        return await invoker.execute_batch(tool_calls, resolved_tools, context=context)

    @classmethod
    @Retry.api(exception=(NotResultException,))
    async def get_result(
        cls,
        bot: Bot,
        session: Uninfo,
        group_id: str | None,
        nickname: str,
        message: UniMsg,
        is_bym: bool,
        func_param: FunctionParam,
    ) -> str:
        """获取回答结果（使用统一 LLM 服务的实现）"""
        user_id = session.user.id
        cls.add_cache(user_id, group_id, nickname, message)

        # 构建当前轮输入（不再手动维护完整对话列表，交给 AI 会话管理）
        if is_bym:
            content_parts = await cls.__get_bym_content(
                bot, user_id, group_id, nickname
            )
        else:
            content_parts = await cls.__get_normal_content(
                user_id, group_id, nickname, message
            )

        # 使用 AI 会话客户端，按 bym:user_id[:group_id] 作为 session_id 进行历史管理
        session_key = f"bym:{user_id}:{group_id}" if group_id else f"bym:{user_id}"
        model_name = base_config.get("BYM_AI_CHAT_MODEL")
        ai = AI(session_id=session_key, memory=BymMemory())

        # 智能模式下允许 LLM 使用已注册的智能工具（来自 smart_tools）
        tools_param = None
        tool_names: list[str] = []
        if base_config.get("BYM_AI_CHAT_SMART"):
            resolved_tools = await tool_provider_manager.get_resolved_tools()
            tool_names = list(resolved_tools.keys())
            tools_param = tool_names or None

        llm_response = await ai.chat(
            content_parts,
            model=model_name,
            tools=tools_param,
        )

        final_result_text = llm_response.text or extract_text_from_content(
            llm_response.content_parts
        )

        if base_config.get("BYM_AI_CHAT_SMART") and llm_response.tool_calls:
            tool_messages = await cls._run_tools(
                llm_response.tool_calls,
                tool_names,
                session_key,
                func_param,
            )
            if tool_messages:
                await ai.memory.add_messages(session_key, tool_messages)
                if tool_result_text := "\n".join(
                    extract_text_from_content(msg.content)
                    for msg in tool_messages
                    if msg.content
                ).strip():
                    final_result_text = tool_result_text

        if res := _filter_result(final_result_text):
            cls.add_cache(
                bot.self_id,
                group_id,
                BotConfig.self_nickname,
                MessageUtils.build_message(res),
            )
        return res

    @classmethod
    def _get_base_data(
        cls, session: Uninfo, result: LLMResponse, is_tools: bool
    ) -> tuple[str | None, str]:
        group_id = None
        if session.group:
            group_id = (
                session.group.parent.id if session.group.parent else session.group.id
            )
        assistant_reply = (result.text or "").strip()
        if not assistant_reply and (not result.content_parts):
            raise NotResultException()
        return group_id, remove_deep_seek(assistant_reply, is_tools)

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
