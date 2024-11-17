from nonebot import on_message
from nonebot.matcher import Matcher
from nonebot.adapters import Bot, Event
from nonebot_plugin_uninfo import Uninfo
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import UniMsg
from nonebot.message import run_preprocessor

from zhenxun.services.log import logger
from zhenxun.configs.config import Config
from zhenxun.utils.enum import PluginType
from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.ban_console import BanConsole
from zhenxun.models.group_console import GroupConsole

from .utils import black_word_manager

__plugin_meta__ = PluginMetadata(
    name="敏感词文本监听",
    description="敏感词文本监听",
    usage="".strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        menu_type="其他",
        plugin_type=PluginType.DEPENDANT,
    ).dict(),
)

base_config = Config.get("black_word")

_matcher = on_message(priority=5, block=False)


async def check(
    matcher: Matcher, event: Event, session: Uninfo, bot: Bot, msg: str
) -> bool:
    user_id = session.user.id
    group_id = session.group.id if session.group else None
    if not matcher.plugin:
        return False
    if not event.is_tome() or matcher.plugin.name != "black_watch":
        return False
    if user_id in bot.config.superusers:
        logger.debug(f"超级用户跳过黑名单词汇检查 Message: {msg}", session=session)
        return False
    if group_id:
        if await BanConsole.is_ban(None, group_id):
            logger.debug("群组处于黑名单中...", "敏感词警察")
            return False
        if g := await GroupConsole.get_group(group_id):
            if g.level < 0:
                logger.debug("群黑名单, 群权限-1...", "敏感词警察")
                return False
    return not await BanConsole.is_ban(user_id, group_id)


# 黑名单词汇检测
@run_preprocessor
async def _(bot: Bot, message: UniMsg, matcher: Matcher, event: Event, session: Uninfo):
    msg = message.extract_plain_text()
    if not await check(matcher, event, session, bot, msg):
        return
    if await black_word_manager.check(bot, session, msg) and base_config.get(
        "CONTAIN_BLACK_STOP_PROPAGATION"
    ):
        matcher.stop_propagation()
