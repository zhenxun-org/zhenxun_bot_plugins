from nonebot.adapters.onebot.v11 import Bot
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import BaseBlock, PluginCdBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .data_source import JmDownload

__plugin_meta__ = PluginMetadata(
    name="Jm下载器",
    description="懂的都懂，密码是id号",
    usage="""
    指令：
        jm [本子id]
    示例：
        jm 114514
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        menu_type="一些工具",
        limits=[
            BaseBlock(result="当前有本子正在下载，请稍等..."),
            PluginCdBlock(result="Jm下载器冷却中（5s）..."),
        ],
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna("jm", Args["album_id", str]), priority=5, block=True, rule=to_me()
)


@_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma, album_id: str):
    await MessageUtils.build_message("正在下载中，请稍后...").send(reply_to=True)
    group_id = session.group.id if session.group else None
    await JmDownload.download_album(bot, session.user.id, group_id, album_id)
    logger.info(f"下载了本子 {album_id}", arparma.header_result, session=session)
