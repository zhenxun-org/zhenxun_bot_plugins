import time

from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

from .data_source import PixSeekManage

__plugin_meta__ = PluginMetadata(
    name="PIX收录",
    description="PIX关键词/UID/PID添加管理",
    usage="""
    指令：
        pix收录 ?["u", "p", "k", "a"] ?[num]
            u: uid
            p: pid
            k: 关键词
            a: 全部(默认)
        示例:
            pix收录
            pix收录 u 10
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        plugin_type=PluginType.SUPERUSER,
        version="0.1",
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna(
        "pix收录",
        Args["seek_type?", ["u", "p", "k", "a"]]["num?", int],
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
    num: Match[int],
):
    st = seek_type.result if seek_type.available else "a"
    n = num.result if num.available else None
    try:
        start = time.time()
        result = await PixSeekManage.start_seek(st, n)  # type: ignore
        end = time.time()
        await MessageUtils.build_message(
            f"累计耗时: {int(end - start)} 秒\n共保存 {result[0]} 条数据!"
            f"\n已存在数据: {result[1]} 条!"
        ).send()
        logger.info(f"PIX 添加结果: {result}", arparma.header_result, session=session)
    except ValueError:
        await MessageUtils.build_message("没有需要收录的数据...").send()
