import asyncio

from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Option,
    Query,
    Reply,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg import Receipt
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import BaseBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from ..config import InfoManage
from .data_source import PixManage, base_config

__plugin_meta__ = PluginMetadata(
    name="PIX",
    description="这里是PIX图库！",
    usage="""
    指令：
        pix ?*[tags] ?[-n 1]: 通过 tag 获取相似图片，不含tag时随机抽取,
                -n表示数量, -r表示查看r18, -noai表示过滤ai

            示例：pix 萝莉 白丝
            示例：pix 萝莉 白丝 -n 10  （10为数量）

        pix图库 ?[tags](使用空格分隔)

        引用消息 /original                  : 获取原图
        引用消息 /info                      : 查看图片信息

        示例：pix 萝莉 白丝
        示例：pix 萝莉 白丝 -n 10  （10为数量）

    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        superuser_help="""
        指令：
            pix -s ?*[tags]: 通过tag获取色图，不含tag时随机
            pix -r ?*[tags]: 通过tag获取r18图，不含tag时随机
        """,
        menu_type="来点好康的",
        limits=[BaseBlock(result="您有PIX图片正在处理，请稍等...")],
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


_matcher = on_alconna(
    Alconna(
        "pix",
        Args["tags?", str] / "\n",
        Option("-n|--num", Args["num", int]),
    ),
    priority=5,
    block=True,
)

_original_matcher = on_alconna(
    Alconna(["/"], "original"),
    priority=5,
    block=True,
    use_cmd_start=False,
    rule=reply_check(),
)

_info_matcher = on_alconna(
    Alconna(["/"], "info"),
    priority=5,
    block=True,
    use_cmd_start=False,
    rule=reply_check(),
)


@_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    tags: Query[tuple[str, ...]] = Query("tags", ()),
    num: Query[int] = Query("num", 1),
):
    if num.result > 10:
        await MessageUtils.build_message("最多一次10张哦...").finish()
    allow_group_r18 = base_config.get("ALLOW_GROUP_R18")
    is_r18 = arparma.find("r18")
    if (
        not allow_group_r18
        and session.group
        and is_r18
        and session.user.id not in bot.config.superusers
    ):
        await MessageUtils.build_message("给我滚出克私聊啊变态！").finish()
    is_ai = arparma.find("noai") or None
    result = await PixManage.get_pix(tags.result, num.result, is_r18, is_ai)
    if not result:
        await MessageUtils.build_message("没有找到相关tag/pix/uid的图片...").finish()
    task_list = [asyncio.create_task(PixManage.get_pix_result(r)) for r in result]
    result_list = await asyncio.gather(*task_list)
    max_once_num2forward = base_config.get("MAX_ONCE_NUM2FORWARD")
    if max_once_num2forward and max_once_num2forward <= len(result) and session.group:
        await MessageUtils.alc_forward_msg(
            [r[0] for r in result_list], bot.self_id, BotConfig.self_nickname
        ).send()
    else:
        for r, pix in result_list:
            receipt = await MessageUtils.build_message(r).send()
            msg_id = receipt.msg_ids[0]["message_id"]
            InfoManage.add(str(msg_id), pix)
    logger.info(f"pix tags: {tags.result}", arparma.header_result, session=session)


@_original_matcher.handle()
async def _(bot: Bot, event: Event, arparma: Arparma, session: Uninfo):
    reply: Reply | None = await reply_fetch(event, bot)
    if reply and (pix_model := InfoManage.get(str(reply.id))):
        result = await PixManage.get_image(pix_model, True)
        if not result:
            await MessageUtils.build_message("下载图片数据失败...").finish()
        receipt: Receipt = await MessageUtils.build_message(result).send(reply_to=True)
        msg_id = receipt.msg_ids[0]["message_id"]
        InfoManage.add(str(msg_id), pix_model)
    else:
        await MessageUtils.build_message(
            "没有找到该图片相关信息或数据已过期..."
        ).finish(reply_to=True)


@_info_matcher.handle()
async def _(bot: Bot, event: Event):
    reply: Reply | None = await reply_fetch(event, bot)
    if reply and (pix_model := InfoManage.get(str(reply.id))):
        result = f"""title: {pix_model.title}
author: {pix_model.author}
pid: {pix_model.pid}-{pix_model.img_p}
uid: {pix_model.uid}
nsfw: {pix_model.nsfw_tag}
tags: {pix_model.tags}""".strip()
        await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message("没有找到该图片相关信息或数据已过期...").finish(
        reply_to=True
    )
