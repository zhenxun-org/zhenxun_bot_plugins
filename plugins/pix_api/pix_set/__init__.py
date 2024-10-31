from nonebot.rule import Rule
from httpx import HTTPStatusError
from nonebot_plugin_uninfo import Uninfo
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Args,
    Reply,
    Option,
    UniMsg,
    Alconna,
    Arparma,
    on_alconna,
    store_true,
)

from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.utils import PluginExtraData

from .._config import InfoManage
from .data_source import PixManage

__plugin_meta__ = PluginMetadata(
    name="PIX修改",
    description="这里是PIX图库！",
    usage="""
    指令：
        引用消息 /info
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

    async def _rule(message: UniMsg):
        return bool(message and isinstance(message[0], Reply))

    return Rule(_rule)


_info_matcher = on_alconna(
    Alconna(["/"], "info"),
    priority=5,
    block=True,
    use_cmd_start=False,
    rule=reply_check(),
)

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


@_info_matcher.handle()
async def _(message: UniMsg):
    reply: Reply = message.pop(0)
    if pix_model := InfoManage.get(str(reply.id)):
        result = f"""title: {pix_model.title}
author: {pix_model.author}
pid: {pix_model.pid}
uid: {pix_model.uid}
nsfw: {pix_model.nsfw_tag}
tags: {pix_model.tags}""".strip()
        await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message("没有找到该图片相关信息...").finish(reply_to=True)


@_block_matcher.handle()
async def _(message: UniMsg, arparma: Arparma, session: Uninfo):
    reply: Reply = message.pop(0)
    if pix_model := InfoManage.get(str(reply.id)):
        try:
            result = await PixManage.block_pix(pix_model, arparma.find("u"))
        except HTTPStatusError as e:
            logger.error(
                "pix图库API出错...", arparma.header_result, session=session, e=e
            )
            await MessageUtils.build_message(
                f"pix图库API出错啦！ code: {e.response.status_code}"
            ).finish()
        await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message("没有找到该图片相关信息...").finish(reply_to=True)


@_nsfw_matcher.handle()
async def _(message: UniMsg, arparma: Arparma, n: int, session: Uninfo):
    reply: Reply = message.pop(0)
    if pix_model := InfoManage.get(str(reply.id)):
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
    await MessageUtils.build_message("没有找到该图片相关信息...").finish(reply_to=True)
