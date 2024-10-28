from nonebot_plugin_uninfo import Uninfo
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Args, Alconna, Arparma, on_alconna

from zhenxun.services.log import logger
from zhenxun.utils.depends import CheckConfig
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.utils import PluginExtraData

from .._enum import KwType
from .data_source import KeywordManage

__plugin_meta__ = PluginMetadata(
    name="PIX添加",
    description="PIX关键词/UID/PID添加管理",
    usage="""
    指令：
        pix添加 ['u', 'p', 'k'] [content]
            u: uid
            p: pid
            k: 关键词
        示例:
            pix添加 u 123456789
            pix添加 p 123456789
            pix添加 k 真寻
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        menu_type="PIX图库",
        superuser_help="""
        pix处理 ['a', 'f', 'i'] [id]
        """.strip(),
        version="0.1",
    ).dict(),
)


_add_matcher = on_alconna(
    Alconna(
        "pix添加",
        Args["add_type", ["u", "p", "k"]]["content", str],
    ),
    priority=5,
    block=True,
)


@_add_matcher.handle(parameterless=[CheckConfig("pix", "pix_api")])
async def _(
    session: Uninfo,
    arparma: Arparma,
    add_type: str,
    content: str,
):
    if add_type == "u":
        result = await KeywordManage.add_content(content, KwType.UID)
    elif add_type == "p":
        result = await KeywordManage.add_content(content, KwType.PID)
    else:
        result = await KeywordManage.add_content(content, KwType.KEYWORD)
    await MessageUtils.build_message(result).send()
    logger.info(f"PIX 添加结果: {result}", arparma.header_result, session=session)
