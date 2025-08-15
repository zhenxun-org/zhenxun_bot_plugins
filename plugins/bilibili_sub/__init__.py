import asyncio
from datetime import datetime
from io import BytesIO
import time

from arclet.alconna.typing import CommandMeta
from bilireq.login import Login
import nonebot
from nonebot.adapters import Bot
from nonebot.drivers import Driver
from nonebot.matcher import Matcher
from nonebot.params import ArgStr
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_session import EventSession
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.models.group_console import GroupConsole
from zhenxun.services.log import logger
from zhenxun.utils.image_utils import text2image
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .auth import AuthManager
from .config import LOG_COMMAND
from .data_source import (
    BilibiliSub,
    SubManager,
    add_live_sub,
    add_season_sub,
    add_up_sub,
    delete_sub,  # noqa: F401
    get_media_id,
    get_sub_status,
)
from .utils import calc_time_total

base_config = Config.get("bilibili_sub")

__plugin_meta__ = PluginMetadata(
    name="B站订阅",
    description="非常便利的B站订阅通知",
    usage="""
        usage：
            B站直播，番剧，UP动态开播等提醒
            主播订阅相当于 直播间订阅 + UP订阅
            指令：
                添加订阅 ['主播'/'UP'/'番剧'] [id/链接/番名]
                删除订阅 ['主播'/'UP'/'id'] [id]
                查看订阅
            示例：   
                添加订阅主播 2345344 <-(直播房间id)
                添加订阅UP 2355543 <-(个人主页id)
                添加订阅番剧 史莱姆 <-(支持模糊搜索)
                添加订阅番剧 125344 <-(番剧id)
                删除订阅id 2324344 <-(任意id，通过查看订阅获取)
        """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.8",
        superuser_help="""
    登录b站获取cookie防止风控：
            bil_check/检测b站
            bil_login/登录b站
            bil_logout/退出b站 uid
            示例:
                登录b站 
                检测b站
                bil_logout 12345<-(退出登录的b站uid，通过检测b站获取)
        """,
        configs=[
            RegisterConfig(
                module="bilibili_sub",
                key="LIVE_MSG_AT_ALL",
                value=False,
                help="直播提醒是否AT全体（仅在真寻是管理员时生效）",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="UP_MSG_AT_ALL",
                value=False,
                help="UP动态投稿提醒是否AT全体（仅在真寻是管理员时生效）",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="CHECK_TIME",
                value=60,
                help="b站检测时间间隔(秒)",
                default_value=60,
                type=int,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="ENABLE_SLEEP_MODE",
                value=True,
                help="是否开启固定时间段内休眠",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="SLEEP_START_TIME",
                value="01:00",
                help="开启休眠时间",
                default_value="01:00",
                type=str,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="SLEEP_END_TIME",
                value="07:30",
                help="关闭休眠时间",
                default_value="07:30",
                type=str,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="ENABLE_AD_FILTER",
                value=True,
                help="是否开启广告过滤",
                default_value=True,
                type=bool,
            ),
        ],
        admin_level=base_config.get("GROUP_BILIBILI_SUB_LEVEL"),
    ).to_dict(),
)

Config.add_plugin_config(
    "bilibili_sub",
    "GROUP_BILIBILI_SUB_LEVEL",
    5,
    help="群内bilibili订阅需要管理的权限",
    default_value=5,
    type=int,
)

add_sub = on_alconna(
    Alconna(
        "添加订阅",
        Args["sub_type", str]["sub_msg", str],
        meta=CommandMeta(compact=True),
    ),
    aliases={"d", "添加订阅"},
    priority=5,
    block=True,
)
del_sub = on_alconna(
    Alconna(
        "删除订阅",
        Args["sub_type", str]["sub_msg", str],
        meta=CommandMeta(compact=True),
    ),
    aliases={"td", "取消订阅"},
    priority=5,
    block=True,
)
show_sub_info = on_alconna("查看订阅", priority=5, block=True)

blive_check = on_alconna(
    Alconna("bil_check"),
    aliases={"检测b站", "检测b站登录", "b站登录检测"},
    permission=SUPERUSER,
    priority=5,
    block=True,
)
blive_login = on_alconna(
    Alconna("bil_login"),
    aliases={"登录b站", "b站登录"},
    permission=SUPERUSER,
    priority=5,
    block=True,
)
blive_logout = on_alconna(
    Alconna("bil_logout", Args["uid", int]),
    aliases={"退出b站", "退出b站登录", "b站登录退出"},
    permission=SUPERUSER,
    priority=5,
    block=True,
)

driver: Driver = nonebot.get_driver()

sub_manager: SubManager | None = None


@driver.on_startup
async def _():
    global sub_manager
    sub_manager = SubManager()


@add_sub.handle()
@del_sub.handle()
async def _(session: Uninfo, state: T_State, sub_type: str, sub_msg: str):
    group_id = session.group.id if session.group else None
    if group_id:
        sub_user = f"{session.user.id}:{group_id}"
    else:
        sub_user = f"{session.user.id}"
    state["sub_type"] = sub_type
    state["sub_user"] = sub_user
    if "http" in sub_msg:
        sub_msg = sub_msg.split("?")[0]
        sub_msg = sub_msg[:-1] if sub_msg[-1] == "/" else sub_msg
        sub_msg = sub_msg.split("/")[-1]
    sub_id = sub_msg[2:] if sub_msg.startswith("md") else sub_msg
    if sub_id.isdigit():
        state["sub_id"] = int(sub_id)

    elif sub_type in {"season", "动漫", "番剧"}:
        rst = "*以为您找到以下番剧，请输入Id选择：*\n"
        state["season_data"] = await get_media_id(sub_id)
        if not state["season_data"]:
            await MessageUtils.build_message(f"未找到番剧：{sub_msg}").finish()
        if len(state["season_data"]) == 0:
            await MessageUtils.build_message(f"未找到番剧：{sub_msg}").finish()
        for i, x in enumerate(state["season_data"]):
            rst += f"{i + 1}.{state['season_data'][x]['title']}\n----------\n"
        await MessageUtils.build_message("\n".join(rst.split("\n")[:-1])).send()
    else:
        await MessageUtils.build_message("Id 必须为全数字！").finish()


@add_sub.got("sub_type")
@add_sub.got("sub_user")
@add_sub.got("id")
async def _(
    session: Uninfo,
    state: T_State,
    sub_id: str = ArgStr("sub_id"),
    sub_type: str = ArgStr("sub_type"),
    sub_user: str = ArgStr("sub_user"),
):
    if sub_type in {"season", "动漫", "番剧"} and state.get("season_data"):
        season_data = state["season_data"]
        if not sub_id.isdigit() or int(sub_id) < 1 or int(sub_id) > len(season_data):
            await add_sub.reject_arg("id", "Id必须为数字且在范围内！请重新输入...")
        sub_id = season_data[int(sub_id) - 1]["media_id"]
    id_data = int(sub_id)
    if sub_type in {"主播", "直播"}:
        await MessageUtils.build_message(
            await add_live_sub(session, id_data, sub_user)
        ).send()
    elif sub_type.lower() in {"up", "用户"}:
        await MessageUtils.build_message(
            await add_up_sub(session, id_data, sub_user)
        ).send()
    elif sub_type in {"season", "动漫", "番剧"}:
        await MessageUtils.build_message(
            await add_season_sub(session, id_data, sub_user)
        ).send()
    else:
        await MessageUtils.build_message(
            "参数错误，第一参数必须为：主播/up/番剧！"
        ).finish()
    logger.info(
        f"添加订阅：{sub_type} -> {sub_user} -> {id_data}", LOG_COMMAND, session=session
    )


@del_sub.got("sub_type")
@del_sub.got("sub_user")
@del_sub.got("id")
async def _(
    session: EventSession,
    id_: str = ArgStr("id"),
    sub_type: str = ArgStr("sub_type"),
    sub_user: str = ArgStr("sub_user"),
):
    if sub_type in {"主播", "直播"}:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user, "live")
    elif sub_type.lower() in {"up", "用户"}:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user, "up")
    else:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user)
    if result:
        await MessageUtils.build_message(f"删除订阅id：{id_} 成功...").send()
        logger.info(f"删除订阅 {id_}", session=session)
    else:
        await MessageUtils.build_message(f"删除订阅id：{id_} 失败...").send()


@show_sub_info.handle()
async def _(session: EventSession):
    gid = session.id3 or session.id2
    id_ = gid if gid else session.id1
    data = await BilibiliSub.filter(sub_users__contains=id_).all()
    live_rst = ""
    up_rst = ""
    season_rst = ""
    for x in data:
        if x.sub_type == "live":
            live_rst += (
                f"\t直播间id：{x.sub_id}\n\t名称：{x.uname}\n------------------\n"
            )
        elif x.sub_type == "season":
            season_rst += (
                f"\t番剧id：{x.sub_id}\n"
                f"\t番名：{x.season_name}\n"
                f"\t当前集数：{x.season_current_episode}\n"
                f"------------------\n"
            )
        elif x.sub_type == "up":
            up_rst += f"\tUP：{x.uname}\n\tuid：{x.uid}\n------------------\n"
    live_rst = "当前订阅的直播：\n" + live_rst if live_rst else live_rst
    up_rst = "当前订阅的UP：\n" + up_rst if up_rst else up_rst
    season_rst = "当前订阅的番剧：\n" + season_rst if season_rst else season_rst
    if not live_rst and not up_rst and not season_rst:
        live_rst = "该群目前没有任何订阅..." if gid else "您目前没有任何订阅..."

    img = await text2image(live_rst + up_rst + season_rst, padding=10, color="#f9f6f2")
    await MessageUtils.build_message(img).finish()


@blive_check.handle()
async def _():
    if not AuthManager.grpc_auths:
        await MessageUtils.build_message("没有缓存的登录信息").finish()
    msgs = []
    for auth in AuthManager.grpc_auths:
        token_time = calc_time_total(auth.tokens_expired - int(time.time()))
        cookie_time = calc_time_total(auth.cookies_expired - int(time.time()))
        msg = (
            f"账号uid: {auth.uid}\n"
            f"token有效期: {token_time}\n"
            f"cookie有效期: {cookie_time}"
        )
        msgs.append(msg)
    await MessageUtils.build_message("\n----------\n".join(msgs)).finish()


@blive_login.handle()
async def _(matcher: Matcher):
    login = Login()
    qr_url = await login.get_qrcode_url()
    logger.debug(f"qrcode login url: {qr_url}")
    img = await login.get_qrcode(qr_url)
    if not img:
        await MessageUtils.build_message("获取二维码失败").finish()
    if isinstance(img, str):
        await MessageUtils.build_message(img).finish()
    buffered = BytesIO()
    img.save(buffered)
    img_data = buffered.getvalue()
    await MessageUtils.build_message(img_data).send()
    try:
        auth = await login.qrcode_login(interval=5)
        assert auth, "登录失败，返回数据为空"
        AuthManager.add_auth(auth)
    except Exception as e:
        await MessageUtils.build_message(f"登录失败: {e}").finish()
    await MessageUtils.build_message("登录成功，已将验证信息缓存至文件").finish()


@blive_logout.handle()
async def _(uid: int):
    if msg := AuthManager.remove_auth(uid):
        await MessageUtils.build_message(msg).finish()
    await MessageUtils.build_message(f"账号 {uid} 已退出登录").finish()


def should_run():
    """判断当前时间是否在运行时间段内（7点30到次日1点）"""
    now = datetime.now().time()
    # 如果当前时间在 7:30 到 23:59:59 之间，或者 0:00 到 1:00 之间，则运行
    return (
        now >= datetime.strptime(base_config.get("SLEEP_END_TIME"), "%H:%M").time()
    ) or (now < datetime.strptime(base_config.get("SLEEP_START_TIME"), "%H:%M").time())


# 信号量，限制并发任务数
semaphore = asyncio.Semaphore(200)


# 推送
@scheduler.scheduled_job(
    "interval",
    seconds=base_config.get("CHECK_TIME") or 30,
    max_instances=500,
    misfire_grace_time=40,
)
async def check_subscriptions():
    """
    定时任务：检查订阅并发送消息
    """
    if not sub_manager:
        return
    async with semaphore:  # 限制并发任务数
        if base_config.get("ENABLE_SLEEP_MODE") and not should_run():
            return

        bots = nonebot.get_bots()
        if not bots:
            logger.warning("No available bots found.")
            return

        for bot in bots.values():
            if not bot:
                continue

            # 获取随机订阅数据
            sub = await sub_manager.random_sub_data()
            if not sub:
                logger.debug("没有获取可用的订阅数据", LOG_COMMAND)
                continue
            try:
                logger.info(
                    f"Bilibili订阅开始检测：{sub.sub_id}，类型：{sub.sub_type}",
                    LOG_COMMAND,
                )

                # 获取订阅状态，设置超时时间为30秒
                msg_list = await asyncio.wait_for(
                    get_sub_status(None, int(sub.sub_id), sub.sub_type), timeout=30
                )

                if msg_list:
                    await send_sub_msg(msg_list, sub, bot)

                    # 如果是直播订阅，额外检测UP主动态
                    if sub.sub_type == "live":
                        msg_list = await asyncio.wait_for(
                            get_sub_status(None, int(sub.sub_id), "up"), timeout=30
                        )
                        if msg_list:
                            await send_sub_msg(msg_list, sub, bot)

            except asyncio.TimeoutError:
                logger.error(f"任务超时：检测订阅 {sub.sub_id} 时超时", LOG_COMMAND)
            except Exception as e:
                logger.error(
                    f"任务异常：检测订阅 {sub.sub_id} 时出错", LOG_COMMAND, e=e
                )


async def send_sub_msg(msg_list: list, sub: BilibiliSub, bot: Bot):
    """推送信息

    参数:
        msg_list: 消息列表
        sub: BilibiliSub
        bot: Bot
    """
    if not msg_list:
        return
    temp_group = []
    for x in sub.sub_users.split(",")[:-1]:
        try:
            if ":" in x and x.split(":")[1] not in temp_group:
                group_id = x.split(":")[1]
                temp_group.append(group_id)
                if (
                    await bot.get_group_member_info(
                        group_id=int(group_id),
                        user_id=int(bot.self_id),
                        no_cache=True,
                    )
                )["role"] in ["owner", "admin"] and (
                    (
                        sub.sub_type == "live"
                        and Config.get_config("bilibili_sub", "LIVE_MSG_AT_ALL")
                    )
                    or (
                        sub.sub_type == "up"
                        and Config.get_config("bilibili_sub", "UP_MSG_AT_ALL")
                    )
                ):
                    msg_list.insert(0, UniMessage.at_all() + "\n")
                if not await GroupConsole.is_block_plugin(group_id, "bilibili_sub"):
                    await PlatformUtils.send_message(
                        bot,
                        user_id=None,
                        group_id=group_id,
                        message=MessageUtils.build_message(msg_list),
                    )

            else:
                await PlatformUtils.send_message(
                    bot,
                    user_id=x,
                    group_id=None,
                    message=MessageUtils.build_message(msg_list),
                )
        except Exception as e:
            logger.error(f"B站订阅推送发生错误 sub_id：{sub.sub_id}", LOG_COMMAND, e=e)
