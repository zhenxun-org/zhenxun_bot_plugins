from nonebot.permission import SUPERUSER
from nonebot_plugin_uninfo import Uninfo
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Args,
    Match,
    Query,
    Alconna,
    Arparma,
    MultiVar,
    on_alconna,
)

from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.depends import CheckConfig
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.utils import PluginExtraData

from .data_source import InfoManage

__plugin_meta__ = PluginMetadata(
    name="PIX图库",
    description="查看pix图库数量",
    usage="""
    指令：
        pix图库 ?[tags](使用空格分隔)
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        menu_type="PIX图库",
        superuser_help="""
        pix查看 ?["u", "p", "k", "a"]
            u: uid
            p: pid
            k: 关键词
            a: 全部(默认)
            """.strip(),
        version="0.1",
    ).dict(),
)

_matcher = on_alconna(
    Alconna(
        "pix图库",
        Args["tags?", MultiVar(str)],
    ),
    priority=5,
    block=True,
)


@_matcher.handle(parameterless=[CheckConfig("pix", "pix_api")])
async def _(
    session: Uninfo,
    arparma: Arparma,
    tags: Query[tuple[str, ...]] = Query("tags", ()),
):
    result = await InfoManage.get_pix_gallery(tags.result)
    await MessageUtils.build_message(result).send(reply_to=True)
    logger.info(
        f"PIX 查看PIX图库 tags: {tags.result}", arparma.header_result, session=session
    )