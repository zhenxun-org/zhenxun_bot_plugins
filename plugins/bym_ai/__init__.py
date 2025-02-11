import asyncio
import random

from nonebot import on_message
from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import UniMsg, Voice
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.depends import UserName
from zhenxun.utils.message import MessageUtils

from .data_source import ChatManager, base_config, split_text

__plugin_meta__ = PluginMetadata(
    name="BYM_AI",
    description=f"{BotConfig.self_nickname}想成为人类...",
    usage=f"""
    你问小真寻的愿望？
    {BotConfig.self_nickname}说她想成为人类！
    """.strip(),
    extra=PluginExtraData(
        author="Chtholly",
        version="0.1",
        configs=[
            RegisterConfig(
                key="BYM_AI_CHAT_URL",
                value=None,
                help="ai聊天接口地址",
            ),
            RegisterConfig(
                key="BYM_AI_CHAT_TOKEN",
                value=None,
                help="ai聊天接口密钥，使用列表",
                type=list[str],
            ),
            RegisterConfig(
                key="BYM_AI_CHAT_MODEL",
                value=None,
                help="ai聊天接口模型",
            ),
            RegisterConfig(
                key="BYM_AI_CHAT",
                value=True,
                help="是否开启伪人回复",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="BYM_AI_CHAT_RATE",
                value=0.05,
                help="伪人回复概率 0-1",
                default_value=0.05,
                type=float,
            ),
            RegisterConfig(
                key="BYM_AI_TTS_URL",
                value=None,
                help="tts接口地址",
            ),
            RegisterConfig(
                key="BYM_AI_TTS_TOKEN",
                value=None,
                help="tts接口密钥",
            ),
            RegisterConfig(
                key="BYM_AI_TTS_VOICE",
                value=None,
                help="tts接口音色",
            ),
        ],
    ).dict(),
)


async def rule(event: Event, session: Uninfo) -> bool:
    if event.is_tome():
        """at自身必定回复"""
        return True
    if not base_config.get("BYM_AI_CHAT"):
        return False
    if event.is_tome() and not session.group:
        """私聊过滤"""
        return False
    rate = base_config.get("BYM_AI_CHAT_RATE") or 0
    return random.random() <= rate


_matcher = on_message(priority=998, rule=rule)


@_matcher.handle()
async def _(event: Event, message: UniMsg, session: Uninfo, uname: str = UserName()):
    if not message.extract_plain_text().strip():
        if event.is_tome():
            await MessageUtils.build_message(ChatManager.hello()).finish()
        return
    group_id = session.group.id if session.group else ""
    is_bym = not event.is_tome()
    result = await ChatManager.get_result(
        session.user.id, group_id, uname, message, is_bym
    )
    if is_bym:
        """伪人回复，切割文本"""
        if result:
            for r, delay in split_text(result):
                await MessageUtils.build_message(r).send()
                await asyncio.sleep(delay)
    else:
        if not result:
            return MessageUtils.build_message(ChatManager.no_result()).finish()
        await MessageUtils.build_message(result).send()
        if tts_data := await ChatManager.tts(result):
            await MessageUtils.build_message(Voice(raw=tts_data)).send()
    logger.info(f"BYM AI 问题: {message} | 回答: {result}", "BYM AI", session=session)
