from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
    Arparma,
    Match,
    Query,
    Subcommand,
    UniMsg,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from zhenxun.services.log import logger
from zhenxun.utils._image_template import ImageTemplate
from zhenxun.utils.depends import UserName
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from ..models.bym_gift_store import GiftStore
from ..models.bym_user import BymUser
from .data_source import ICON_PATH, use_gift

_matcher = on_alconna(
    Alconna(
        "bym-gift",
        Subcommand("user-gift"),
        Subcommand("use-gift", Args["name?", str]["num?", int]),
    ),
    priority=5,
    block=True,
)


_matcher.shortcut(
    r"我的礼物",
    command="bym-gift",
    arguments=["user-gift"],
    prefix=True,
)

_matcher.shortcut(
    r"使用礼物(?P<name>.*?)",
    command="bym-gift",
    arguments=["use-gift", "{name}"],
    prefix=True,
)


@_matcher.assign("user-gift")
async def _(session: Uninfo, uname: str = UserName()):
    user = await BymUser.get_user(session.user.id, PlatformUtils.get_platform(session))
    result = await GiftStore.filter(uuid__in=user.props.keys()).all()
    column_name = ["-", "使用ID", "名称", "数量", "简介"]
    data_list = []
    uuid2goods = {item.uuid: item for item in result}
    for i, p in enumerate(user.props.copy()):
        if prop := uuid2goods.get(p):
            icon = ""
            icon_path = ICON_PATH / prop.icon
            if icon_path.exists():
                icon = (icon_path, 33, 33)
            if user.props[p] <= 0:
                del user.props[p]
                continue
            data_list.append(
                [
                    icon,
                    i,
                    prop.name,
                    user.props[p],
                    prop.description,
                ]
            )
    await user.save(update_fields=["props"])
    result = await ImageTemplate.table_page(
        f"{uname}的礼物仓库",
        "通过 使用礼物 [ID/名称] 使礼物生效",
        column_name,
        data_list,
    )
    await MessageUtils.build_message(result).send(reply_to=True)
    logger.info(f"{uname} 查看礼物仓库", "我的礼物", session=session)


@_matcher.assign("use-gift")
async def _(
    bot: Bot,
    event: Event,
    message: UniMsg,
    session: Uninfo,
    arparma: Arparma,
    name: Match[str],
    num: Query[int] = AlconnaQuery("num", 1),
):
    if not name.available:
        await MessageUtils.build_message(
            "请在指令后跟需要使用的礼物名称或id..."
        ).finish(reply_to=True)
    result = await use_gift(bot, event, session, message, name.result, num.result)
    logger.info(
        f"使用礼物 {name.result}, 数量: {num.result}",
        arparma.header_result,
        session=session,
    )
    await MessageUtils.build_message(result).send(reply_to=True)
