import asyncio
from pathlib import Path
import random

from httpx import HTTPStatusError
from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, UniMsg, Voice, on_alconna
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.services.plugin_init import PluginInit
from zhenxun.utils.depends import CheckConfig, UserName
from zhenxun.utils.message import MessageUtils

from .config import FunctionParam
from .data_source import ChatManager, base_config, split_text
from .goods_register import driver  # noqa: F401
from .model import BymChat

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
        ignore_prompt=True,
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
                key="BYM_AI_CHAT_SMART",
                value=False,
                help="是否开启智能模式",
                default_value=False,
                type=bool,
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
            RegisterConfig(
                key="ENABLE_IMPRESSION",
                value=True,
                help="使用签到数据作为基础好感度",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="CACHE_SIZE",
                value=40,
                help="缓存聊天记录数据大小（每位用户）",
                default_value=40,
                type=int,
            ),
            RegisterConfig(
                key="ENABLE_GROUP_CHAT",
                value=True,
                help="在群组中时共用缓存",
                default_value=True,
                type=bool,
            ),
        ],
    ).to_dict(),
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


_matcher = on_alconna(Alconna("re:.*"), priority=998, rule=rule)


@_matcher.handle(parameterless=[CheckConfig(config="BYM_AI_CHAT_TOKEN")])
async def _(
    bot: Bot,
    event: Event,
    message: UniMsg,
    arparma: Arparma,
    session: Uninfo,
    uname: str = UserName(),
):
    if not message.extract_plain_text().strip():
        if event.is_tome():
            await MessageUtils.build_message(ChatManager.hello()).finish()
        return
    fun_param = FunctionParam(
        bot=bot, event=event, arparma=arparma, session=session, message=message
    )
    group_id = session.group.id if session.group else None
    is_bym = not event.is_tome()
    result = await ChatManager.get_result(
        bot, session, group_id, uname, message, is_bym, fun_param
    )
    if is_bym:
        """伪人回复，切割文本"""
        if result:
            for r, delay in split_text(result):
                await MessageUtils.build_message(r).send()
                await asyncio.sleep(delay)
    else:
        try:
            if result:
                await MessageUtils.build_message(result).send(reply_to=bool(group_id))
                if tts_data := await ChatManager.tts(result):
                    await MessageUtils.build_message(Voice(raw=tts_data)).send()
            elif not base_config.get("BYM_AI_CHAT_SMART"):
                await MessageUtils.build_message(ChatManager.no_result()).finish()
            if plain_text := message.extract_plain_text():
                await BymChat.create(
                    user_id=session.user.id,
                    group_id=group_id,
                    plain_text=plain_text,
                    result=result,
                )
            logger.info(
                f"BYM AI 问题: {message} | 回答: {result}", "BYM_AI", session=session
            )
        except HTTPStatusError as e:
            logger.error("BYM AI 请求失败", "BYM_AI", session=session, e=e)
            await MessageUtils.build_message(
                f"请求失败了哦，code: {e.response.status_code}"
            ).finish(reply_to=True)
        except Exception as e:
            logger.error("BYM AI 其他错误", "BYM_AI", session=session, e=e)
            await MessageUtils.build_message("发生了一些异常，想要休息一下...").finish(
                reply_to=True
            )


RESOURCE_FILE = IMAGE_PATH / "shop_icon" / "reload_ai_card.png"


class MyPluginInit(PluginInit):
    async def install(self):
        res = Path(__file__).parent / "reload_ai_card.png"
        if res.exists():
            if RESOURCE_FILE.exists():
                RESOURCE_FILE.unlink()
            res.rename(RESOURCE_FILE)
            logger.info(f"更新 BYM_AI 资源文件成功 {res} -> {RESOURCE_FILE}")

    async def remove(self):
        if RESOURCE_FILE.exists():
            RESOURCE_FILE.unlink()
            logger.info(f"删除 BYM_AI 资源文件成功 {RESOURCE_FILE}")
