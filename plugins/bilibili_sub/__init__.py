import time
from io import BytesIO
from typing import Optional

import nonebot
from nonebot import Driver
from nonebot.log import logger
from bilireq.login import Login
from nonebot.params import ArgStr
from nonebot.typing import T_State
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import Bot
from arclet.alconna.typing import CommandMeta
from nonebot_plugin_session import EventSession
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_alconna import Args, Alconna, UniMessage, on_alconna

from zhenxun.configs.config import Config
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.image_utils import text2image
from zhenxun.utils.platform import PlatformUtils
from zhenxun.models.group_console import GroupConsole
from zhenxun.services.log import logger  # noqa: F811
from zhenxun.configs.utils import RegisterConfig, PluginExtraData

from .auth import AuthManager
from .utils import calc_time_total
from .data_source import delete_sub  # noqa: F401
from .data_source import (
    SubManager,
    BilibiliSub,
    add_up_sub,
    add_live_sub,
    get_media_id,
    add_season_sub,
    get_sub_status,
)

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
        version="0.2-f7511a1",
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
        ],
        admin_level=base_config.get("GROUP_BILIBILI_SUB_LEVEL"),
    ).dict(),
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
async def _(session: EventSession, state: T_State, sub_type: str, sub_msg: str):
    gid = session.id3 or session.id2
    if gid:
        sub_user = f"{session.id1}:{gid}"
    else:
        sub_user = f"{session.id1}"
    state["sub_type"] = sub_type
    state["sub_user"] = sub_user
    if "http" in sub_msg:
        sub_msg = sub_msg.split("?")[0]
        sub_msg = sub_msg[:-1] if sub_msg[-1] == "/" else sub_msg
        sub_msg = sub_msg.split("/")[-1]
    id_ = sub_msg[2:] if sub_msg.startswith("md") else sub_msg
    if not id_.isdigit():
        if sub_type in ["season", "动漫", "番剧"]:
            rst = "*以为您找到以下番剧，请输入Id选择：*\n"
            state["season_data"] = await get_media_id(id_)
            if len(state["season_data"]) == 0:
                await MessageUtils.build_message(f"未找到番剧：{sub_msg}").finish()
            for i, x in enumerate(state["season_data"]):
                rst += f'{i + 1}.{state["season_data"][x]["title"]}\n----------\n'
            await MessageUtils.build_message("\n".join(rst.split("\n")[:-1])).send()
        else:
            await MessageUtils.build_message("Id 必须为全数字！").finish()
    else:
        state["id"] = int(id_)


@add_sub.got("sub_type")
@add_sub.got("sub_user")
@add_sub.got("id")
async def _(
    session: EventSession,
    state: T_State,
    id_: str = ArgStr("id"),
    sub_type: str = ArgStr("sub_type"),
    sub_user: str = ArgStr("sub_user"),
):
    if sub_type in ["season", "动漫", "番剧"] and state.get("season_data"):
        season_data = state["season_data"]
        if not id_.isdigit() or int(id_) < 1 or int(id_) > len(season_data):
            await add_sub.reject_arg("id", "Id必须为数字且在范围内！请重新输入...")
        id_ = season_data[int(id_) - 1]["media_id"]
    id_ = int(id_)
    if sub_type in ["主播", "直播"]:
        await MessageUtils.build_message(await add_live_sub(id_, sub_user)).send()
    elif sub_type.lower() in ["up", "用户"]:
        await MessageUtils.build_message(await add_up_sub(id_, sub_user)).send()
    elif sub_type in ["season", "动漫", "番剧"]:
        await MessageUtils.build_message(await add_season_sub(id_, sub_user)).send()
    else:
        await MessageUtils.build_message(
            "参数错误，第一参数必须为：主播/up/番剧！"
        ).finish()
    gid = session.id3 or session.id2
    logger.info(
        f"(USER {session.id1}, GROUP "
        f"{gid if gid else 'private'})"
        f" 添加订阅：{sub_type} -> {sub_user} -> {id_}"
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
    if sub_type in ["主播", "直播"]:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user, "live")
    elif sub_type.lower() in ["up", "用户"]:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user, "up")
    else:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user)
    if result:
        await MessageUtils.build_message(f"删除订阅id：{id_} 成功...").send()
        gid = session.id3 or session.id2
        logger.info(
            f"(USER {session.id1}, GROUP "
            f"{gid if gid else 'private'})"
            f" 删除订阅 {id_}"
        )
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
                f"\t直播间id：{x.sub_id}\n"
                f"\t名称：{x.uname}\n"
                f"------------------\n"
            )
        if x.sub_type == "up":
            up_rst += f"\tUP：{x.uname}\n" f"\tuid：{x.uid}\n" f"------------------\n"
        if x.sub_type == "season":
            season_rst += (
                f"\t番剧id：{x.sub_id}\n"
                f"\t番名：{x.season_name}\n"
                f"\t当前集数：{x.season_current_episode}\n"
                f"------------------\n"
            )
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
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_data = buffered.getvalue()
    await MessageUtils.build_message(img_data).send()
    try:
        auth = await login.qrcode_login(interval=5)
        assert auth, "登录失败，返回数据为空"
        logger.debug(auth.data)
        AuthManager.add_auth(auth)
    except Exception as e:
        await MessageUtils.build_message(f"登录失败: {e}").finish()
    await MessageUtils.build_message("登录成功，已将验证信息缓存至文件").finish()


@blive_logout.handle()
async def _(uid: int):
    if msg := AuthManager.remove_auth(uid):
        await MessageUtils.build_message(msg).finish()
    await MessageUtils.build_message(f"账号 {uid} 已退出登录").finish()


# 推送
@scheduler.scheduled_job(
    "interval",
    seconds=base_config.get("CHECK_TIME") if base_config.get("CHECK_TIME") else 60,
    max_instances=100,
)
async def _():
    bots = nonebot.get_bots()
    for bot in bots.values():
        if bot:
            sub = await sub_manager.random_sub_data()
            if sub:
                logger.info(
                    f"Bilibili订阅开始检测：{sub.sub_id}， 类型：{sub.sub_type}"
                )
                msg_list = await get_sub_status(sub.sub_id, sub.sub_type)
                if msg_list:
                    await send_sub_msg(msg_list, sub, bot)
                    if sub.sub_type == "live":
                        msg_list = await get_sub_status(sub.sub_id, "up")
                        await send_sub_msg(msg_list, sub, bot)


async def send_sub_msg(msg_list: list, sub: BilibiliSub, bot: Bot):
    """
    推送信息
    :param msg_list: 消息列表
    :param sub: BilibiliSub
    :param bot: Bot
    """
    temp_group = []
    if msg_list:
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
                    )["role"] in ["owner", "admin"]:
                        if (
                            sub.sub_type == "live"
                            and Config.get_config("bilibili_sub", "LIVE_MSG_AT_ALL")
                        ) or (
                            sub.sub_type == "up"
                            and Config.get_config("bilibili_sub", "UP_MSG_AT_ALL")
                        ):
                            msg_list.append(UniMessage.at_all())
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
                logger.error(f"B站订阅推送发生错误 sub_id：{sub.sub_id} {type(e)}：{e}")
