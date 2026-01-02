from nonebot import on_message
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Image, UniMsg
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.ban_console import BanConsole
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.image_utils import get_download_image_hash
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import FreqLimiter, get_entity_ids

from ._data_source import mute_manager

__plugin_meta__ = PluginMetadata(
    name="刷屏监听",
    description="这是刷屏检测的监听器，用于检测用户是否在规定时间内发送了相同的消息",
    usage="无",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1-473ecd8",
        menu_type="其他",
        plugin_type=PluginType.DEPENDANT,
    ).to_dict(),
)


async def rule(session: Uninfo) -> bool:
    entity_ids = get_entity_ids(session)
    if not session.group:
        return False
    if mute_manager.get_group_data(entity_ids.group_id or "0").duration == 0:
        return False
    if await BanConsole.is_ban_cached(entity_ids.user_id, entity_ids.group_id):
        return False
    return True


_matcher = on_message(rule=rule, priority=1, block=False)

_flmt = FreqLimiter(30)


@_matcher.handle()
async def _(bot: Bot, session: Uninfo, message: UniMsg):
    entity_ids = get_entity_ids(session)
    plain_text = message.extract_plain_text()
    image_list = [m.url for m in message if isinstance(m, Image) and m.url]
    img_hash = ""
    for url in image_list:
        img_hash += await get_download_image_hash(url, "_mute_")
    _message = plain_text + img_hash
    if duration := mute_manager.add_message(
        entity_ids.user_id, entity_ids.group_id or "0", _message
    ):
        try:
            if _flmt.check(entity_ids.user_id):
                _flmt.start_cd(entity_ids.user_id)
                await PlatformUtils.ban_user(
                    bot, entity_ids.user_id, entity_ids.group_id or "0", duration
                )
                await MessageUtils.build_message(
                    f"检测到恶意刷屏，{BotConfig.self_nickname}要把你关进小黑屋！"
                ).send(at_sender=True)
                mute_manager.reset(entity_ids.user_id, entity_ids.group_id or "0")
                logger.info(
                    f"检测刷屏 被禁言 {duration} 分钟", "禁言检查", session=session
                )
        except Exception as e:
            logger.error("禁言发送错误", "禁言检测", session=session, e=e)
