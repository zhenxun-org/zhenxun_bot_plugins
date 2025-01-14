import asyncio

from httpx import HTTPStatusError
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    MultiVar,
    Option,
    Query,
    Reply,
    on_alconna,
    store_true,
)
from nonebot_plugin_alconna.uniseg import Receipt
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import BaseBlock, Command, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.depends import CheckConfig
from zhenxun.utils.message import MessageUtils

from .._config import InfoManage
from .data_source import PixManage, base_config

__plugin_meta__ = PluginMetadata(
    name="PIX",
    description="这里是PIX图库！",
    usage="""
    指令：
        pix ?*[tags] ?[-n 1] ?*[--nsfw [0, 1, 2]] ?[--ratio r1,r2]
                : 通过 tag 获取相似图片，不含tag时随机抽取,
                -n表示数量, -r表示查看r18, -noai表示过滤ai
                --nsfw 表示获取的 nsfw-tag，0: 普通, 1: 色图, 2: R18
                --ratio 表示获取的图片比例，示例: 0.5,1.5 表示长宽比大于0.5小于1.5

            示例：pix 萝莉 白丝
            示例：pix 萝莉 白丝 -n 10  （10为数量）

        pix图库 ?[tags](使用空格分隔)

        引用消息 /star                      : 收藏图片
        引用消息 /unatar                    : 取消收藏图片
        引用消息 /original                  : 获取原图
        引用消息 /info                      : 查看图片信息
        引用消息 /block ?[level] ?[--all]   : block该pid
            默认level为2，可选[1, 2], 1程度较轻，含有all时block该pid下所有图片
        引用消息 /block -u                  : block该uid下的所有图片
        引用消息 / nsfw n                   : 设置nsfw等级 n = [0, 1, 2] 其中
            0: 普通
            1: 色图
            2: R18

        pix添加 ['u', 'p'] [*content]: 可同时添加多个pid和uid
            u: uid
            p: pid
            示例:
                pix添加 u 123456789
                pix添加 p 123456789
                pix添加 u 123456789 12312332

        pix收藏           : 查看个人收藏
        pix排行 ?[10] -r: 查看收藏排行, 默认获取前10，包含-r时会获取包括r18在内的排行

        pixtag ?[10] : 查看排名前10的tag，最大不能超过30
            示例:
                pixtag 20
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        menu_type="PIX图库",
        superuser_help="""
        指令：
            pix -s ?*[tags]: 通过tag获取色图，不含tag时随机
        """,
        commands=[
            Command(command="pix ?*[tags] ?[-n 1]"),
            Command(command="[引用消息] /original"),
            Command(command="[引用消息] /info"),
        ],
        limits=[BaseBlock(result="您有PIX图片正在处理，请稍等...")],
    ).to_dict(),
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
        Args["tags?", MultiVar(str)],
        Option("-n|--num", Args["num", int]),
        Option("-r|--r18", action=store_true, help_text="是否是r18"),
        Option("-noai", action=store_true, help_text="是否是过滤ai"),
        Option(
            "--nsfw",
            Args["nsfw_tag", MultiVar(int)],
            help_text="nsfw_tag，[0, 1, 2]",
        ),
        Option("--ratio", Args["ratio", str], help_text="图片比例，例如: 0.5,1.2"),
    ),
    aliases={"PIX"},
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


@_matcher.handle(parameterless=[CheckConfig("pix", "pix_api")])
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    tags: Query[tuple[str, ...]] = Query("tags", ()),
    num: Query[int] = Query("num", 1),
    nsfw: Query[tuple[int, ...]] = Query("nsfw_tag", ()),
    ratio: Query[str] = Query("ratio", ""),
):
    if num.result > 10:
        await MessageUtils.build_message("最多一次10张哦...").finish()
    allow_group_r18 = base_config.get("ALLOW_GROUP_R18")
    is_r18 = arparma.find("r18")
    if (
        not allow_group_r18
        and session.group
        and (is_r18 or 2 in nsfw.result)
        and session.user.id not in bot.config.superusers
    ):
        await MessageUtils.build_message("给我滚出克私聊啊变态！").finish()
    is_ai = False if arparma.find("noai") else None
    ratio_tuple = None
    if "," in ratio.result:
        ratio_tuple = ratio.result.split(",")
    elif "，" in ratio.result:
        ratio_tuple = ratio.result.split("，")
    if ratio_tuple and len(ratio_tuple) < 2:
        return await MessageUtils.build_message("比例格式错误，请输入x,y").finish()
    if ratio_tuple:
        ratio_tuple = [float(ratio_tuple[0]), float(ratio_tuple[1])]
    if nsfw.result:
        for n in nsfw.result:
            if n not in [0, 1, 2]:
                return await MessageUtils.build_message(
                    "nsfw_tag格式错误，请输入0,1,2"
                ).finish()
    try:
        result = await PixManage.get_pix(
            tags.result,
            num.result,
            is_r18,
            is_ai,
            nsfw.result,
            ratio_tuple,
        )
        if not result.suc:
            await MessageUtils.build_message(result.info).send()
    except HTTPStatusError as e:
        logger.debug("pix图库API出错...", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message(
            f"pix图库API出错啦！code: {e.response.status_code}"
        ).finish()
    if not result.data:
        await MessageUtils.build_message("没有找到相关tag/pix/uid的图片...").finish()
    task_list = [asyncio.create_task(PixManage.get_pix_result(r)) for r in result.data]
    result_list = await asyncio.gather(*task_list)
    max_once_num2forward = base_config.get("MAX_ONCE_NUM2FORWARD")
    if (
        max_once_num2forward
        and max_once_num2forward <= len(result.data)
        and session.group
    ):
        await MessageUtils.alc_forward_msg(
            [r[0] for r in result_list], bot.self_id, BotConfig.self_nickname
        ).send()
    else:
        for r, pix in result_list:
            receipt: Receipt = await MessageUtils.build_message(r).send()
            msg_id = receipt.msg_ids[0]["message_id"]
            InfoManage.add(str(msg_id), pix)
    logger.info(f"pix tags: {tags.result}", arparma.header_result, session=session)


@_original_matcher.handle()
async def _(bot: Bot, event: Event, arparma: Arparma, session: Uninfo):
    reply: Reply | None = await reply_fetch(event, bot)
    if reply and (pix_model := InfoManage.get(str(reply.id))):
        try:
            result = await PixManage.get_image(pix_model, True)
            if not result:
                await MessageUtils.build_message("下载图片数据失败...").finish()
        except HTTPStatusError as e:
            logger.error(
                "pix图库API出错...", arparma.header_result, session=session, e=e
            )
            await MessageUtils.build_message(
                f"pix图库API出错啦！ code: {e.response.status_code}"
            ).finish()
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
