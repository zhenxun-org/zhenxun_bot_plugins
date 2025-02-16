import asyncio
from collections.abc import Sequence
import os
import random
import re
import time
from typing import ClassVar, Literal

from nonebot import require
from nonebot.adapters import Bot
from nonebot.compat import model_dump
from nonebot_plugin_alconna import Text, UniMessage, UniMsg
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.configs.utils import AICallableTag
from zhenxun.models.group_console import GroupConsole
from zhenxun.models.sign_user import SignUser
from zhenxun.services.log import logger
from zhenxun.utils.decorator.retry import Retry
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

from .call_tool import AiCallTool
from .model import BymChat

require("sign_in")

from zhenxun.builtin_plugins.sign_in.utils import (
    get_level_and_next_impression,
    level2attitude,
)

from .config import (
    BYM_CONTENT,
    DEEP_SEEK_SPLIT,
    DEFAULT_GROUP,
    GROUP_CONTENT,
    NO_RESULT,
    NO_RESULT_IMAGE,
    NORMAL_CONTENT,
    NORMAL_IMPRESSION_CONTENT,
    PROMPT_FILE,
    TIP_CONTENT,
    ChatMessage,
    FunctionParam,
    MessageCache,
    OpenAiResult,
    base_config,
)

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
    return result.replace("<EMPTY>", "").strip()


def remove_deep_seek(text: str) -> str:
    """去除深度探索"""
    if DEEP_SEEK_SPLIT in text:
        return text.split(DEEP_SEEK_SPLIT, 1)[-1].strip()
    if match := re.search(r"```text\n([\s\S]*?)\n```", text, re.DOTALL):
        text = match[1]
    if text.endswith("```"):
        text = text[:-3].strip()
    return re.sub(r"深度思考：[\s\S]*?\n\s*\n", "", text).strip()


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
    async def get_db_data(
        cls, user_id: str | None, group_id: str | None = None
    ) -> list[ChatMessage]:
        """从数据库获取记录

        参数:
            user_id: 用户id
            group_id: 群组id，获取群组内记录时使用

        返回:
            list[ChatMessage]: 记录列表
        """
        conversation = []
        enable_group_chat = base_config.get("ENABLE_GROUP_CHAT")
        if enable_group_chat and group_id:
            db_filter = BymChat.filter(group_id=group_id)
        elif enable_group_chat:
            db_filter = BymChat.filter(user_id=user_id, group_id=None)
        else:
            db_filter = BymChat.filter(user_id=user_id)
        db_data_list = (
            await db_filter.order_by("-id").limit(base_config.get("CACHE_SIZE")).all()
        )
        for db_data in db_data_list:
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
    async def get_conversation(
        cls, user_id: str | None, group_id: str | None
    ) -> list[ChatMessage]:
        """获取预设

        参数:
            user_id: 用户id

        返回:
            list[ChatMessage]: 预设数据
        """
        conversation = []
        if (
            base_config.get("ENABLE_GROUP_CHAT")
            and group_id
            and group_id in cls.history_data
        ):
            conversation = cls.history_data[group_id]
        elif user_id and user_id in cls.history_data:
            conversation = cls.history_data[user_id]
        # 尝试从数据库中获取历史对话
        if not conversation:
            conversation = await cls.get_db_data(user_id, group_id)
        # 必须带有人设
        conversation = [c for c in conversation if c.role != "system"]
        conversation.append(cls.add_system())
        return conversation

    @classmethod
    def set_history(
        cls, user_id: str, group_id: str | None, conversation: list[ChatMessage]
    ):
        """设置历史预设

        参数:
            user_id: 用户id
            conversation: 消息记录
        """
        cache_size = base_config.get("CACHE_SIZE")
        if len(conversation) > cache_size:
            conversation = conversation[-cache_size:]
        if base_config.get("ENABLE_GROUP_CHAT") and group_id:
            cls.history_data[group_id] = conversation
        else:
            cls.history_data[user_id] = conversation

    @classmethod
    async def reset(cls, user_id: str, group_id: str | None):
        """重置预设

        参数:
            user_id: 用户id
        """
        if base_config.get("ENABLE_GROUP_CHAT") and group_id:
            # 群组内重置
            if (
                db_data := await BymChat.filter(group_id=group_id)
                .order_by("-id")
                .first()
            ):
                db_data.is_reset = True
                await db_data.save(update_fields=["is_reset"])
            if group_id in cls.history_data:
                del cls.history_data[group_id]
        elif user_id:
            # 个人重置
            if (
                db_data := await BymChat.filter(user_id=user_id, group_id=None)
                .order_by("-id")
                .first()
            ):
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
    async def fetch_chat(
        self,
        user_id: str,
        conversation: list[ChatMessage],
        tools: Sequence[AICallableTag] | None,
    ) -> OpenAiResult:
        send_json = {
            "messages": [
                model_dump(model=c, exclude_none=True)
                for c in conversation
                if c.content
            ],
            "stream": False,
            "model": self.chat_model,
            "temperature": 0.7,
        }
        if tools:
            send_json["tools"] = [
                {"type": "function", "function": tool.to_dict()} for tool in tools
            ]
            send_json["tool_choice"] = "auto"

        response = await AsyncHttpx.post(
            self.chat_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.chat_token}",
            },
            json=send_json,
            verify=False,
        )

        if response.status_code == 429:
            logger.debug(
                f"fetch_chat 请求失败: 限速, token: {self.chat_token} 延迟 15 分钟",
                "BYM_AI",
                session=user_id,
            )
            token_counter.delay(self.chat_token)

        response.raise_for_status()
        result = OpenAiResult(**response.json())
        try:
            if content := result.choices[0].message.content:
                if match := re.search(r'"content":\s?"([^"]*)"', content, re.DOTALL):
                    result.choices[0].message.content = match[1]
        except Exception as e:
            logger.warning(
                f"fetch_chat 解析失败返回消息错误: {result.choices[0].message.content}",
                "BYM_AI",
                e=e,
            )
        return result

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
        cls, user_id: str, group_id: str | None, nickname: str, message: UniMsg
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
        level = "2" if level in ["0", "1"] else level
        content_result = (
            NORMAL_IMPRESSION_CONTENT.format(
                nickname=nickname,
                user_id=user_id,
                impression=cls.user_impression[user_id],
                attitude=level2attitude[level],
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
        content.insert(
            0,
            cls.format("text", content_result),
        )
        return content

    @classmethod
    def __get_bym_content(
        cls, bot: Bot, user_id: str, group_id: str | None, nickname: str
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
                    user_id=user_id,
                    group_id=group_id,
                    nickname=nickname,
                    self_id=bot.self_id,
                ),
            )
        ]
        if group_message := cls.group_cache.get(group_id):
            for message in group_message:
                content.append(
                    cls.format(
                        "text",
                        f"用户昵称：{message.nickname} 用户ID：{message.user_id}",
                    )
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
        session: Uninfo,
        group_id: str | None,
        nickname: str,
        message: UniMsg,
        is_bym: bool,
        func_param: FunctionParam,
    ) -> str:
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
        user_id = session.user.id
        cls.add_cache(user_id, group_id, nickname, message)
        if is_bym:
            content = cls.__get_bym_content(bot, user_id, group_id, nickname)
            conversation = await Conversation.get_conversation(None, group_id)
        else:
            content = await cls.__get_normal_content(
                user_id, group_id, nickname, message
            )
            conversation = await Conversation.get_conversation(user_id, group_id)
        conversation.append(ChatMessage(role="user", content=content))
        tools = list(AiCallTool.tools.values())
        result = await CallApi().fetch_chat(user_id, conversation, tools)
        if res := await cls._handle_result(
            bot, session, conversation, result, tools, func_param
        ):
            if res := _filter_result(res):
                cls.add_cache(
                    bot.self_id,
                    group_id,
                    BotConfig.self_nickname,
                    MessageUtils.build_message(res),
                )
        return res

    @classmethod
    async def _handle_result(
        cls,
        bot: Bot,
        session: Uninfo,
        conversation: list[ChatMessage],
        result: OpenAiResult,
        tools: Sequence[AICallableTag],
        func_param: FunctionParam,
    ) -> str:
        """处理API响应并处理工具回调

        参数:
            user_id: 用户id
            conversation: 当前对话
            result: API响应结果
            tools: 可用的工具列表
            func_param: 函数参数

        返回:
            str: 处理后的消息内容
        """
        group_id = None
        if session.group:
            group_id = (
                session.group.parent.id if session.group.parent else session.group.id
            )
        assistant_reply = ""
        if result.choices and (msg := result.choices[0].message):
            if msg.content:
                assistant_reply = msg.content.strip()

            conversation.append(
                ChatMessage(
                    role="assistant", content=assistant_reply, tool_calls=msg.tool_calls
                )
            )
            Conversation.set_history(session.user.id, group_id, conversation)

            # 处理工具回调
            if msg.tool_calls:
                temp_conversation = conversation.copy()
                temp_conversation.extend(
                    await AiCallTool.build_conversation(msg.tool_calls, func_param)
                )
                result = await CallApi().fetch_chat(
                    session.user.id, temp_conversation, tools
                )
                if res := await cls._handle_result(
                    bot, session, conversation, result, tools, func_param
                ):
                    if _filter_result(res):
                        assistant_reply = res
        return remove_deep_seek(assistant_reply)

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
