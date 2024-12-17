from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

from ..config import KwType
from .data_source import InfoManage

__plugin_meta__ = PluginMetadata(
    name="PIX收录",
    description="PIX关键词/UID/PID添加管理",
    usage="""
    指令：
        pix图库 ?[tags](使用空格分隔)
        pix查看 ?["u", "p", "k", "a"]
            u: uid
            p: pid
            k: 关键词
            a: 全部(默认)
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        plugin_type=PluginType.SUPERUSER,
        version="0.1",
    ).dict(),
)

_gallery_matcher = on_alconna(
    Alconna(
        "pix图库",
        Args["tags?", str] / "\n",
    ),
    priority=5,
    block=True,
)

_matcher = on_alconna(
    Alconna(
        "pix查看",
        Args["seek_type?", ["u", "p", "k", "a"]],
    ),
    priority=1,
    block=True,
    permission=SUPERUSER,
)


@_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    seek_type: Match[str],
):
    kw_type = None
    if seek_type.available:
        if seek_type.result == "u":
            kw_type = KwType.UID
        elif seek_type.result == "p":
            kw_type = KwType.PID
        elif seek_type.result == "k":
            kw_type = KwType.KEYWORD
    result = await InfoManage.get_seek_info(kw_type)
    await MessageUtils.build_message(result).send(reply_to=True)
    logger.info(
        f"PIX 查看PIX收录 seek_type: {seek_type.result}",
        arparma.header_result,
        session=session,
    )


@_gallery_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    tags: Match[str],
):
    tags_list = []
    if tags.available and tags.result.strip():
        tags_list = tags.result.strip().split()
    result = await InfoManage.get_pix_gallery(tags_list)
    await MessageUtils.build_message(result).send(reply_to=True)
    logger.info(
        f"PIX 查看PIX图库 tags: {tags_list}", arparma.header_result, session=session
    )
