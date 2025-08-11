import re

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Arparma
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from ..commands import _bind_steam_id_matcher, _unbind_steam_id_matcher
from .data_source import BindManager

__plugin_meta__ = PluginMetadata(
    name="绑定SteamID",
    description="绑定和解绑Steam ID",
    usage="""
    指令：
        绑定steam [steamId]
        解绑steam

        示例：
        绑定steam 123123123123
        解绑steam
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1", menu_type="CSGO").to_dict(),
)


@_bind_steam_id_matcher.handle()
async def _(session: Uninfo, steam_id: str, arparma: Arparma):
    if not steam_id:
        await MessageUtils.build_message("Steam ID不能为空").finish(reply_to=True)
    if not re.fullmatch(r"^\d{17}$", steam_id):
        await MessageUtils.build_message("Steam ID格式错误，需要64位Id").finish(
            reply_to=True
        )

    result = await BindManager.bind_steam_id(session, session.user.id, steam_id)

    logger.info(
        f"尝试绑定Steam ID {steam_id}",
        arparma.header_result,
        session=session,
    )
    await MessageUtils.build_message(result).send(reply_to=True)


@_unbind_steam_id_matcher.handle()
async def _(session: Uninfo, arparma: Arparma):
    result = await BindManager.unbind_steam_id(session.user.id)

    logger.info(
        "尝试解绑Steam ID",
        arparma.header_result,
        session=session,
    )

    await MessageUtils.build_message(result).send(reply_to=True)
