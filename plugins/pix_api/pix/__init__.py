from nonebot.adapters import Bot
from httpx import HTTPStatusError
from nonebot_plugin_uninfo import Uninfo
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Args,
    Match,
    Query,
    Option,
    Alconna,
    Arparma,
    MultiVar,
    on_alconna,
    store_true,
)

from zhenxun.services.log import logger
from zhenxun.configs.config import BotConfig
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.utils import BaseBlock, RegisterConfig, PluginExtraData

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
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        menu_type="PIX图库",
        superuser_help="""
        指令：
            pix -s ?*[tags]: 通过tag获取色图，不含tag时随机
        """,
        limits=[BaseBlock(result="您有PIX图片正在处理，请稍等...")],
        configs=[
            RegisterConfig(
                key="MAX_ONCE_NUM2FORWARD",
                value=None,
                help="单次发送的图片数量达到指定值时转发为合并消息",
                default_value=None,
                type=int,
            ),
            RegisterConfig(
                key="ALLOW_GROUP_R18",
                value=False,
                help="允许非超级用户使用-r参数",
                default_value=False,
                type=bool,
            ),
        ],
    ).dict(),
)

_matcher = on_alconna(
    Alconna(
        "pix",
        Args["tags?", MultiVar(str)],
        Option("-n|--num", Args["num", int]),
        Option("-r|--r18", action=store_true, help_text="是否是r18"),
        Option("-noai", action=store_true, help_text="是否是过滤ai"),
    ),
    aliases={"PIX"},
    priority=5,
    block=True,
)


@_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    tags: Query[tuple[str, ...]] = Query("tags", ()),
    num: Query[int] = Query("num", 1),
    r18: Query[bool] = Query("r18", False),
):
    allow_group_r18 = base_config.get("ALLOW_GROUP_R18")
    if (
        not allow_group_r18
        and session.group
        and r18.result
        and session.user.id not in bot.config.superusers
    ):
        await MessageUtils.build_message("给我滚出克私聊啊变态！").finish()
    is_ai = arparma.find("noai") or None
    try:
        result = await PixManage.get_pix(tags.result, num.result, r18.result, is_ai)
        if not result.suc:
            await MessageUtils.build_message(result.info).send()
    except HTTPStatusError as e:
        logger.debug("pix图库API出错...", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("pix图库API出错啦！").finish()
    if not result.data:
        await MessageUtils.build_message("没有找到相关tag/pix/uid的图片...").finish()
    max_once_num2forward = base_config.get("MAX_ONCE_NUM2FORWARD")
    if (
        max_once_num2forward
        and max_once_num2forward <= len(result.data)
        and session.group
    ):
        message_list = []
        for r in result.data:
            message_list.append(await PixManage.get_pix_result(r))
        await MessageUtils.alc_forward_msg(
            message_list, session.user.id, BotConfig.self_nickname
        ).send()
    else:
        for r in result.data:
            message = await PixManage.get_pix_result(r)
            await MessageUtils.build_message(message).send()
    logger.info(f"pix tags: {tags.result}", arparma.header_result, session=session)
