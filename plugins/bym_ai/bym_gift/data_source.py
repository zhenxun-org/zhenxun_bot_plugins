import asyncio
from collections.abc import Callable
from datetime import datetime
import inspect
import random
from types import MappingProxyType

from nonebot.adapters import Bot, Event
from nonebot.utils import is_coroutine_callable
from nonebot_plugin_alconna import UniMessage, UniMsg
from nonebot_plugin_uninfo import Uninfo
from tortoise.expressions import F

from zhenxun.configs.config import BotConfig
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.utils.platform import PlatformUtils

from ..exception import GiftRepeatSendException
from ..models.bym_gift_log import GiftLog
from ..models.bym_gift_store import GiftStore
from ..models.bym_user import BymUser
from .gift_register import gift_register

ICON_PATH = IMAGE_PATH / "gift_icon"
ICON_PATH.mkdir(parents=True, exist_ok=True)

gift_list = []


async def send_gift(user_id: str, session: Uninfo) -> str:
    global gift_list
    if (
        await GiftLog.filter(
            user_id=session.user.id, create_time__gte=datetime.now().date(), type=0
        ).count()
        > 2
    ):
        raise GiftRepeatSendException
    if not gift_list:
        gift_list = await GiftStore.all()
    gift = random.choice(gift_list)
    user = await BymUser.get_user(user_id, PlatformUtils.get_platform(session))
    if gift.uuid not in user.props:
        user.props[gift.uuid] = 0
    user.props[gift.uuid] += 1
    await asyncio.gather(
        *[
            user.save(update_fields=["props"]),
            GiftLog.create(user_id=user_id, uuid=gift.uuid, type=0),
            GiftStore.filter(uuid=gift.uuid).update(count=F("count") + 1),
        ]
    )
    return f"{BotConfig.self_nickname}赠送了{gift.name}作为礼物。"


def __build_params(
    bot: Bot,
    event: Event,
    session: Uninfo,
    message: UniMsg,
    gift: GiftStore,
    num: int,
):
    group_id = None
    if session.group:
        group_id = session.group.parent.id if session.group.parent else session.group.id
    return {
        "_bot": bot,
        "event": event,
        "user_id": session.user.id,
        "group_id": group_id,
        "num": num,
        "name": gift.name,
        "message": message,
    }


def __parse_args(
    args: MappingProxyType,
    **kwargs,
) -> dict:
    """解析参数

    参数:
        args: MappingProxyType

    返回:
        list[Any]: 参数
    """
    _kwargs = kwargs.copy()
    for key in kwargs:
        if key not in args:
            del _kwargs[key]
    return _kwargs


async def __run(
    func: Callable,
    **kwargs,
) -> str | UniMessage | None:
    """运行道具函数

    参数:
        goods: Goods
        param: ShopParam

    返回:
        str | MessageFactory | None: 使用完成后返回信息
    """
    args = inspect.signature(func).parameters  # type: ignore
    if args and next(iter(args.keys())) != "kwargs":
        return (
            await func(**__parse_args(args, **kwargs))
            if is_coroutine_callable(func)
            else func(**__parse_args(args, **kwargs))
        )
    if is_coroutine_callable(func):
        return await func()
    else:
        return func()


async def use_gift(
    bot: Bot,
    event: Event,
    session: Uninfo,
    message: UniMsg,
    name: str,
    num: int,
) -> str | UniMessage:
    """使用道具

    参数:
        bot: Bot
        event: Event
        session: Session
        message: 消息
        name: 礼物名称
        num: 使用数量
        text: 其他信息

    返回:
        str | MessageFactory: 使用完成后返回信息
    """
    user = await BymUser.get_user(user_id=session.user.id)
    if name.isdigit():
        try:
            uuid = list(user.props.keys())[int(name)]
            gift_info = await GiftStore.get_or_none(uuid=uuid)
        except IndexError:
            return "仓库中礼物不存在..."
    else:
        gift_info = await GiftStore.get_or_none(goods_name=name)
    if not gift_info:
        return f"{name} 不存在..."
    func = gift_register.get_func(gift_info.name)
    if not func:
        return f"{gift_info.name} 未注册使用函数, 无法使用..."
    if user.props[gift_info.uuid] < num:
        return f"你的 {gift_info.name} 数量不足 {num} 个..."
    kwargs = __build_params(bot, event, session, message, gift_info, num)
    result = await __run(func, **kwargs)
    if gift_info.uuid not in user.usage_count:
        user.usage_count[gift_info.uuid] = 0
    user.usage_count[gift_info.uuid] += num
    user.props[gift_info.uuid] -= num
    if user.props[gift_info.uuid] < 0:
        del user.props[gift_info.uuid]
    await user.save(update_fields=["props", "usage_count"])
    await GiftLog.create(user_id=session.user.id, uuid=gift_info.uuid, type=1)
    if not result:
        result = f"使用道具 {gift_info.name} {num} 次成功！"
    return result
