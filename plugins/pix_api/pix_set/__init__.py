from httpx import HTTPStatusError
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Option,
    Reply,
    on_alconna,
    store_true,
)
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .._config import InfoManage
from .data_source import PixManage

__plugin_meta__ = PluginMetadata(
    name="PIX修改",
    description="这里是PIX图库！",
    usage="""
    指令：
        引用消息 /block    : block该pid
        引用消息 /block -u : block该uid下的所有图片
        引用消息 / nsfw n : 设置nsfw等级 n = [0, 1, 2] 其中
            0: 普通
            1: 色图
            2: R18
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        menu_type="PIX图库",
        superuser_help="""
        指令：
            pix -s ?*[tags]: 通过tag获取色图，不含tag时随机
        """,
    ).dict(),
)


def reply_check() -> Rule:
    """
    检查是否存在回复消息

    返回:
        Rule: Rule
    """

    async def _rule(bot: Bot, event: Event):
        if event.get_type() == "message":
            return bool(await reply_fetch(event, bot))
        return False

    return Rule(_rule)


_block_matcher = on_alconna(
    Alconna(
        ["/"], "block", Option("-u|--uid", action=store_true, help_text="是否是uid")
    ),
    priority=5,
    block=True,
    use_cmd_start=False,
    rule=reply_check(),
)

_nsfw_matcher = on_alconna(
    Alconna(["/"], "nsfw", Args["n", int]),
    priority=5,
    block=True,
    use_cmd_start=False,
    rule=reply_check(),
)


@_block_matcher.handle()
async def _(bot: Bot, event: Event, arparma: Arparma, session: Uninfo):
    reply: Reply | None = await reply_fetch(event, bot)
    if reply and (pix_model := InfoManage.get(str(reply.id))):
        try:
            result = await PixManage.block_pix(pix_model, arparma.find("uid"))
        except HTTPStatusError as e:
            logger.error(
                "pix图库API出错...", arparma.header_result, session=session, e=e
            )
            await MessageUtils.build_message(
                f"pix图库API出错啦！ code: {e.response.status_code}"
            ).finish()
        await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message("没有找到该图片相关信息或数据已过期...").finish(
        reply_to=True
    )


@_nsfw_matcher.handle()
async def _(bot: Bot, event: Event, arparma: Arparma, n: int, session: Uninfo):
    reply: Reply | None = await reply_fetch(event, bot)
    if reply and (pix_model := InfoManage.get(str(reply.id))):
        if n not in [0, 1, 2]:
            await MessageUtils.build_message(
                "nsfw参数错误，必须在 [0, 1, 2] 之间..."
            ).finish(reply_to=True)
        try:
            result = await PixManage.set_nsfw(pix_model, n)
        except HTTPStatusError as e:
            logger.error(
                "pix图库API出错...", arparma.header_result, session=session, e=e
            )
            await MessageUtils.build_message(
                f"pix图库API出错啦！ code: {e.response.status_code}"
            ).finish()
        await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message("没有找到该图片相关信息或数据已过期...").finish(
        reply_to=True
    )


@scheduler.scheduled_job(
    "interval",
    hours=3,
)
async def _():
    InfoManage.remove()
    logger.debug("自动移除过期图片数据...")
