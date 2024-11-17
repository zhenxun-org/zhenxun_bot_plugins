from httpx import HTTPStatusError
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from nonebot.plugin import PluginMetadata
from zhenxun.configs.config import BotConfig
from nonebot_plugin_alconna import (
    Args,
    Option,
    Query,
    Reply,
    Alconna,
    Arparma,
    on_alconna,
    store_true,
)

from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.utils import PluginExtraData
from zhenxun.utils.platform import PlatformUtils

from .._config import InfoManage
from .data_source import StarManage

__plugin_meta__ = PluginMetadata(
    name="PIX收藏",
    description="这里是PIX图库！",
    usage="""
    指令：
        引用消息 /star     : 收藏图片
        引用消息 /unatar   : 取消收藏图片
        pix收藏           : 查看个人收藏
        pix排行 ?[10] -r: 查看收藏排行, 默认获取前10，包含-r时会获取包括r18在内的排行
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


_star_matcher = on_alconna(
    Alconna(["/"], "star"),
    priority=5,
    block=True,
    use_cmd_start=False,
    rule=reply_check(),
)

_unstar_matcher = on_alconna(
    Alconna(["/"], "unstar"),
    priority=5,
    block=True,
    use_cmd_start=False,
    rule=reply_check(),
)

_my_matcher = on_alconna(
    Alconna("pix收藏"),
    priority=5,
    block=True,
)

_rank_matcher = on_alconna(
    Alconna(
        "pix排行",
        Args["num?", int],
        Option("-r|--r18", action=store_true, help_text="是否包含r18"),
    ),
    priority=5,
    block=True,
)


@_star_matcher.handle()
async def _(bot: Bot, event: Event, session: Uninfo, arparma: Arparma):
    reply: Reply | None = await reply_fetch(event, bot)
    if reply and (pix_model := InfoManage.get(str(reply.id))):
        platform = PlatformUtils.get_platform(session)
        try:
            result = await StarManage.star_set(
                pix_model, f"{platform}-{session.user.id}", True
            )
        except HTTPStatusError as e:
            logger.error(
                "pix图库API出错...", arparma.header_result, session=session, e=e
            )
            await MessageUtils.build_message(
                f"pix图库API出错啦！ code: {e.response.status_code}"
            ).finish()
        logger.info(
            f"pix收藏图片: {pix_model.pid}", arparma.header_result, session=session
        )
        await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message("没有找到该图片相关信息或数据已过期...").finish(
        reply_to=True
    )


@_unstar_matcher.handle()
async def _(bot: Bot, event: Event, session: Uninfo, arparma: Arparma):
    reply: Reply | None = await reply_fetch(event, bot)
    if reply and (pix_model := InfoManage.get(str(reply.id))):
        platform = PlatformUtils.get_platform(session)
        try:
            result = await StarManage.star_set(
                pix_model, f"{platform}-{session.user.id}", False
            )
        except HTTPStatusError as e:
            logger.error(
                "pix图库API出错...", arparma.header_result, session=session, e=e
            )
            await MessageUtils.build_message(
                f"pix图库API出错啦！ code: {e.response.status_code}"
            ).finish()
        logger.info(
            f"pix取消收藏图片: {pix_model.pid}", arparma.header_result, session=session
        )
        await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message("没有找到该图片相关信息或数据已过期...").finish(
        reply_to=True
    )


@_my_matcher.handle()
async def _(session: Uninfo, arparma: Arparma):
    platform = PlatformUtils.get_platform(session)
    try:
        result = await StarManage.my_star(f"{platform}-{session.user.id}")
    except HTTPStatusError as e:
        logger.error("pix图库API出错...", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message(
            f"pix图库API出错啦！ code: {e.response.status_code}"
        ).finish()
    logger.info("pix查看收藏", arparma.header_result, session=session)
    await MessageUtils.build_message(result).finish(reply_to=True)


@_rank_matcher.handle()
async def _(session: Uninfo, arparma: Arparma, num: Query[int] = Query("num", 10)):
    try:
        result_list = await StarManage.star_rank(num.result, arparma.find("r18"))
    except HTTPStatusError as e:
        logger.error("pix图库API出错...", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message(
            f"pix图库API出错啦！ code: {e.response.status_code}"
        ).finish()
    if isinstance(result_list, str):
        await MessageUtils.build_message(result_list).finish(reply_to=True)
    if session.group:
        await MessageUtils.alc_forward_msg(
            result_list, session.user.id, BotConfig.self_nickname
        ).send()
    else:
        for r in result_list:
            await MessageUtils.build_message(r).send()
    logger.info("pix查看收藏排行", arparma.header_result, session=session)
