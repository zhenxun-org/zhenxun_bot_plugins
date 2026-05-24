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
from .data_source import PixManager, base_config

__plugin_meta__ = PluginMetadata(
    name="PIX",
    description="PIX 图片检索与发送",
    usage=r"""
        指令:
        pix ?*[tags] ?[-n 1] ?*[--nsfw [0, 1, 2]] ?[--ratio r1,r2]
        功能: 通过标签获取相似图片，不带标签时随机抽取。
        -n 表示数量
        -r 表示查看R18内容
        -noai 表示过滤AI生成的图片
        --nsfw 表示获取的NSFW标签，取值：0 普通，1 色图，2 R18
        --ratio 表示获取的图片比例，示例: 0.5,1.5 表示长宽比大于0.5小于1.5

        特别地，当tag中包含 >数字 时，会获取P站收藏数大于该数字的图片。
        示例: pix 萝莉 白丝 >1000
        示例: pix 萝莉 白丝
        示例: pix 萝莉 白丝 -n 10 （10为数量）

        pix图库 ?[tags](使用空格分隔)

        引用消息命令:
        /star                      : 收藏图片
        /unstar                    : 取消收藏图片
        /original                  : 获取原图
        /info                      : 查看图片信息
        /block ?[level] ?[--all]   : block该uid
            默认level为0，可选[1, 2]，1程度较轻，含有all时block该uid下所有图片
        /block -u                  : block该uid下的所有图片
        /nsfw n                    : 设置nsfw等级 n = [0, 1, 2] 其中
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

        pixtag ?[10] : 查看排名前10的tag，最大不能超过100
            示例:
                pixtag 20
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        menu_type="PIX鍥惧簱",
        superuser_help="""
        鎸囦护锛?
            pix -s ?*[tags]: 閫氳繃tag鑾峰彇鑹插浘锛屼笉鍚玹ag鏃堕殢鏈?
        """,
        commands=[
            Command(command="pix ?*[tags] ?[-n 1]"),
            Command(command="[寮曠敤娑堟伅] /original"),
            Command(command="[寮曠敤娑堟伅] /info"),
        ],
        limits=[BaseBlock(result="鎮ㄦ湁PIX鍥剧墖姝ｅ湪澶勭悊锛岃绋嶇瓑...")],
    ).to_dict(),
)


def reply_check() -> Rule:
    """
    妫€鏌ユ槸鍚﹀瓨鍦ㄥ洖澶嶆秷鎭?

    杩斿洖:
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
        Option("-r|--r18", action=store_true, help_text="鏄惁鏄痳18"),
        Option("-noai", action=store_true, help_text="鏄惁鏄繃婊i"),
        Option(
            "--nsfw",
            Args["nsfw_tag", MultiVar(int)],
            help_text="nsfw_tag锛孾0, 1, 2]",
        ),
        Option(
            "--ratio", Args["ratio", str], help_text="鍥剧墖姣斾緥锛屼緥濡? 0.5,1.2"
        ),
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
    if not 1 <= num.result <= 10:
        await MessageUtils.build_message("数量必须在 1 到 10 之间...").finish()
    allow_group_r18 = base_config.get("ALLOW_GROUP_R18")
    is_r18 = bool(arparma.find("r18"))
    if (
        not allow_group_r18
        and session.group
        and (is_r18 or 2 in nsfw.result)
        and session.user.id not in bot.config.superusers
    ):
        await MessageUtils.build_message("缁欐垜婊氬嚭鍏嬬鑱婂晩鍙樻€侊紒").finish()
    is_ai = False if arparma.find("noai") else None
    ratio_tuple = None
    ratio_text = ratio.result.strip().replace("，", ",")
    if ratio_text:
        ratio_tuple_split = [x.strip() for x in ratio_text.split(",") if x.strip()]
        if len(ratio_tuple_split) != 2:
            return await MessageUtils.build_message("比例格式错误，请输入 x,y").finish()
        try:
            ratio_tuple = [float(ratio_tuple_split[0]), float(ratio_tuple_split[1])]
        except ValueError:
            return await MessageUtils.build_message(
                "比例格式错误，请输入数字，例如 0.5,1.5"
            ).finish()
        if (
            ratio_tuple[0] <= 0
            or ratio_tuple[1] <= 0
            or ratio_tuple[0] > ratio_tuple[1]
        ):
            return await MessageUtils.build_message(
                "比例范围错误，请确保 0 < x <= y"
            ).finish()
    if nsfw.result:
        for n in nsfw.result:
            if n not in [0, 1, 2]:
                return await MessageUtils.build_message(
                    "nsfw_tag鏍煎紡閿欒锛岃杈撳叆0,1,2"
                ).finish()
    try:
        result = await PixManager.get_pix(
            tags.result,
            num.result,
            is_r18,
            is_ai,
            nsfw.result,
            ratio_tuple,
        )
        if not result.suc:
            await MessageUtils.build_message(result.info).finish()
    except HTTPStatusError as e:
        logger.debug(
            "pix鍥惧簱API鍑洪敊...", arparma.header_result, session=session, e=e
        )
        await MessageUtils.build_message(
            f"pix鍥惧簱API鍑洪敊鍟︼紒code: {e.response.status_code}"
        ).finish()
    except Exception as e:
        logger.error(
            "pix鍥惧簱API鍑洪敊...", arparma.header_result, session=session, e=e
        )
        await MessageUtils.build_message(
            "pix鍥惧簱API鍑洪敊鍟︼紝璇风◢鍚庡啀璇?.."
        ).finish()
    if not result.data:
        await MessageUtils.build_message(
            "娌℃湁鎵惧埌鐩稿叧tag/pix/uid鐨勫浘鐗?.."
        ).finish()
    task_list = [asyncio.create_task(PixManager.get_pix_result(r)) for r in result.data]
    result_list = await asyncio.gather(*task_list)
    max_once_num2forward = base_config.get("MAX_ONCE_NUM2FORWARD")
    if (
        max_once_num2forward
        and max_once_num2forward <= len(result.data)
        and session.group
    ):
        if not base_config.get("SHOW_INFO"):
            result_list = [[f"pid: {r[1].pid}\n", r[0][-1]] for r in result_list]
        else:
            result_list = [r[0] for r in result_list]
        await MessageUtils.alc_forward_msg(
            result_list, bot.self_id, BotConfig.self_nickname
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
            result = await PixManager.get_image(pix_model, True)
            if not result:
                await MessageUtils.build_message("涓嬭浇鍥剧墖鏁版嵁澶辫触...").finish()
        except HTTPStatusError as e:
            logger.error(
                "pix鍥惧簱API鍑洪敊...", arparma.header_result, session=session, e=e
            )
            await MessageUtils.build_message(
                f"pix鍥惧簱API鍑洪敊鍟︼紒 code: {e.response.status_code}"
            ).finish()
        receipt: Receipt = await MessageUtils.build_message(result).send(reply_to=True)
        msg_id = receipt.msg_ids[0]["message_id"]
        InfoManage.add(str(msg_id), pix_model)
    else:
        await MessageUtils.build_message(
            "娌℃湁鎵惧埌璇ュ浘鐗囩浉鍏充俊鎭垨鏁版嵁宸茶繃鏈?.."
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
        return await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message(
        "娌℃湁鎵惧埌璇ュ浘鐗囩浉鍏充俊鎭垨鏁版嵁宸茶繃鏈?.."
    ).finish(reply_to=True)
