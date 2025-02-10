import asyncio
import os
import random
import re
from typing import ClassVar

from nonebot.compat import model_dump
from nonebot_plugin_alconna import Text, UniMessage, UniMsg
from pydantic import BaseModel

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

from .config import (
    BYM_CONTENT,
    NO_RESULT,
    NO_RESULT_IMAGE,
    NORMAL_CONTENT,
    PROMPT_FILE,
    OpenAiResult,
)

base_config = Config.get("bym_ai")

semaphore = asyncio.Semaphore(3)


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
    content: str | list
    """消息内容"""

    class Config:
        arbitrary_types_allowed = True


def split_text(text: str) -> list[tuple[str, float]]:
    """文本切割"""
    results = []
    split_list = [
        s for s in __split_text(text, r"(?<!\?)[。？\n](?!\?)", 3) if s.strip()
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
        if len(result) < limit - 1:
            result.append(text[last_index : match.start()])
            last_index = match.end()
        else:
            break

    result.append(text[last_index:])
    return result


class Conversation:
    """预设存储"""

    history_data: ClassVar[dict[str, list[ChatMessage]]] = {}

    chat_prompt: str = ""

    @classmethod
    def get_conversation(cls, user_id: str) -> list[ChatMessage]:
        """获取预设

        参数:
            user_id: 用户id

        返回:
            list[ChatMessage]: 预设数据
        """
        conversation = []
        if not cls.chat_prompt:
            cls.chat_prompt = PROMPT_FILE.open(encoding="utf8").read()
        if user_id in conversation:
            conversation = cls.history_data[user_id]
        elif cls.chat_prompt:
            conversation.append(ChatMessage(role="system", content=cls.chat_prompt))
        return conversation

    @classmethod
    def set_history(cls, user_id: str, conversation: list[ChatMessage]):
        """设置历史预设

        参数:
            user_id: 用户id
            conversation: 消息记录
        """
        if len(conversation) > 20:
            conversation = conversation[-20:]
        cls.history_data[user_id] = conversation


class CallApi:
    def __init__(self):
        self.chat_url = base_config.get("BYM_AI_CHAT_URL")
        self.chat_token = base_config.get("BYM_AI_CHAT_TOKEN")
        self.chat_model = base_config.get("BYM_AI_CHAT_MODEL")

        self.tts_url = Config.get_config("bym_ai", "BYM_AI_TTS_URL")
        self.tts_token = Config.get_config("bym_ai", "BYM_AI_TTS_TOKEN")
        self.tts_voice = Config.get_config("bym_ai", "BYM_AI_TTS_VOICE")

    async def fetch_chat(self, user_id: str, content: list):
        conversation = Conversation.get_conversation(user_id)
        conversation.append(ChatMessage(role="user", content=content))

        response = await AsyncHttpx.post(
            self.chat_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.chat_token}",
            },
            json={
                "messages": [model_dump(c) for c in conversation],
                "stream": False,
                "model": self.chat_model,
                "temperature": 0.7,
            },
        )
        response.raise_for_status()
        result = OpenAiResult(**response.json())
        assistant_reply = None
        if result.choices and (message := result.choices[0].message):
            assistant_reply = message.content.strip()
        if assistant_reply:
            conversation.append(
                ChatMessage(role="assistant", content=[assistant_reply])
            )
            Conversation.set_history(user_id, conversation)
        return assistant_reply

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
                    else:
                        logger.warning(
                            f"fetch_tts 请求失败: {response.content}", "BYM_AI"
                        )
                        await asyncio.sleep(delay)

                except Exception as e:
                    logger.error("fetch_tts 请求失败", "BYM_AI", e=e)

        return None


class ChatManager:
    group_cache: ClassVar[dict[str, list[MessageCache]]] = {}

    @classmethod
    def format(cls, data: str) -> dict[str, str]:
        """格式化数据

        参数:
            data: 文本

        返回:
            dict[str, str]: 格式化字典文本
        """
        return {
            "type": "text",
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
        return [cls.format(seg.text) for seg in message if isinstance(seg, Text)]

    @classmethod
    def __get_normal_content(
        cls, nickname: str, message: UniMsg
    ) -> list[dict[str, str]]:
        """获取普通回答文本内容

        参数:
            nickname: 用户昵称
            message: 消息内容

        返回:
            list[dict[str, str]]: 文本序列
        """
        content = cls.__build_content(message)
        content.insert(0, cls.format(NORMAL_CONTENT.format(nickname=nickname)))
        return content

    @classmethod
    def __get_bym_content(
        cls, user_id: str, group_id: str, nickname: str
    ) -> list[dict[str, str]]:
        """获取伪人回答文本内容

        参数:
            user_id: 用户id
            group_id: 群组id
            nickname: 用户昵称

        返回:
            list[dict[str, str]]: 文本序列
        """
        content = [
            cls.format(
                BYM_CONTENT.format(
                    user_id=user_id, group_id=group_id, nickname=nickname
                )
            )
        ]
        if group_message := cls.group_cache.get(group_id):
            for message in group_message:
                content.append(cls.format(f"{message.nickname} {message.user_id}"))
                content.extend(cls.__build_content(message.message))

        return content

    @classmethod
    async def add_cache(
        cls, user_id: str, group_id: str, nickname: str, message: UniMsg
    ):
        """添加消息缓存

        参数:
            user_id: 用户id
            group_id: 群组id
            nickname: 用户昵称
            message: 消息内容
        """
        if group_id not in cls.group_cache:
            cls.group_cache[group_id] = []
        cls.group_cache[group_id].append(
            MessageCache(user_id=user_id, nickname=nickname, message=message)
        )
        if len(cls.group_cache[group_id]) >= 20:
            cls.group_cache[group_id].pop(0)

    @classmethod
    async def get_result(
        cls,
        user_id: str,
        group_id: str,
        nickname: str,
        message: UniMsg,
        is_bym: bool,
    ) -> str | None:
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
        if is_bym:
            content = cls.__get_bym_content(user_id, nickname, group_id)
            result = await CallApi().fetch_chat(user_id, content)
            result = None if result == "<EMPTY>" else result
        else:
            content = cls.__get_normal_content(nickname, message)
            result = await CallApi().fetch_chat(user_id, content)
        return result

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
