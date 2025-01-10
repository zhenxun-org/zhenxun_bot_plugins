import contextlib
from datetime import datetime, timedelta
import time
import uuid

from apscheduler.jobstores.base import JobLookupError
from nonebot.adapters import Bot
from nonebot.exception import ActionFailed
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
    Arparma,
    At,
    Field,
    Match,
    Option,
    Query,
    on_alconna,
)
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_session import EventSession
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import (
    Command,
    PluginCdBlock,
    PluginExtraData,
    RegisterConfig,
)
from zhenxun.services.log import logger
from zhenxun.utils.depends import GetConfig, UserName
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.rules import ensure_group

from .config import FESTIVE_KEY, FestiveRedBagManage
from .data_source import RedBagManager

__plugin_meta__ = PluginMetadata(
    name="金币红包",
    description="运气项目又来了",
    usage="""
    塞红包 [金币数] ?[红包数=5] ?[at指定人]: 塞入红包
    开/抢: 打开红包
    退回红包: 退回未开完的红包，必须在一分钟后使用

    * 不同群组同一个节日红包用户只能开一次

    示例:
        塞红包 1000
        塞红包 1000 10
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1-89d294e",
        superuser_help="""
        节日红包 [金额] [红包数] ?[指定主题文字] ? -g [群id] [群id] ...

        * 不同群组同一个节日红包用户只能开一次

        示例:
            节日红包 10000 20 今日出道贺金
            节日红包 10000 20 明日出道贺金 -g 123123123

        """,
        commands=[
            Command(command="塞红包 [金币数] ?[红包数=5] ?[at指定人]"),
            Command(command="开红包"),
            Command(command="退回红包"),
        ],
        configs=[
            RegisterConfig(
                key="DEFAULT_TIMEOUT",
                value=600,
                help="普通红包默认超时时间",
                default_value=600,
                type=int,
            ),
            RegisterConfig(
                key="DEFAULT_INTERVAL",
                value=60,
                help="用户发送普通红包最小间隔时间",
                default_value=60,
                type=int,
            ),
            RegisterConfig(
                key="RANK_NUM",
                value=10,
                help="结算排行显示前N位",
                default_value=10,
                type=int,
            ),
        ],
        limits=[PluginCdBlock(result="急什么急什么，待会再发！")],
    ).to_dict(),
)


_red_bag_matcher = on_alconna(
    Alconna(
        "塞红包",
        Args[
            "amount",
            int,
            Field(
                missing_tips=lambda: "请在命令后跟随金币数量！",
                unmatch_tips=lambda _: "金币数量必须为数字！",
            ),
        ]["num", int, 5]["user?", At],
    ),
    aliases={"金币红包"},
    skip_for_unmatch=False,
    priority=5,
    block=True,
    rule=ensure_group,
)

_open_matcher = on_alconna(
    Alconna("开"),
    aliases={"抢", "开红包", "抢红包"},
    priority=5,
    block=True,
    rule=ensure_group,
)

_return_matcher = on_alconna(
    Alconna("退回红包"), aliases={"退还红包"}, priority=5, block=True, rule=ensure_group
)

_festive_matcher = on_alconna(
    Alconna(
        "节日红包",
        Args["amount", int]["num", int]["text?", str],
        Option("-g|--group", Args["groups", str] / "\n", help_text="指定群"),
    ),
    priority=1,
    block=True,
    permission=SUPERUSER,
    rule=to_me(),
)


@_red_bag_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    amount: int,
    user: Match[At],
    num: Query[int] = AlconnaQuery("num", 5),
    default_interval: int = GetConfig(config="DEFAULT_INTERVAL"),
    user_name: str = UserName(),
):
    at_user = user.result.target if user.available else None
    group_id = session.group.id if session.group else None
    """以频道id为键"""
    if not group_id:
        await MessageUtils.build_message("群组id为空").finish()
    group_red_bag = RedBagManager.get_group_data(group_id)
    # 剩余过期时间
    time_remaining = group_red_bag.check_timeout(session.user.id)
    if time_remaining != -1:
        # 判断用户红包是否存在且是否过时覆盖
        if user_red_bag := group_red_bag.get_user_red_bag(session.user.id):
            now = time.time()
            if now < user_red_bag.start_time + default_interval:
                await MessageUtils.build_message(
                    "你的红包还没消化完捏..."
                    f"还剩下 {user_red_bag.num - len(user_red_bag.open_user)} 个! "
                    f"请等待红包领取完毕...(或等待{time_remaining}秒红包cd)"
                ).finish()
    platform = PlatformUtils.get_platform(session)
    result = await RedBagManager.check_gold(
        session.user.id, num.result, amount, platform
    )
    if result:
        await MessageUtils.build_message(result).finish(at_sender=True)
    await group_red_bag.add_red_bag(
        f"{user_name}的红包",
        amount,
        1 if at_user else num.result,
        user_name,
        session.user.id,
        assigner=at_user,
        platform=platform,
    )
    image = await RedBagManager.random_red_bag_background(session)
    message_list: list = [
        f"{user_name}发起了金币红包\n金额: {amount}\n数量: {num.result}\n"
    ]
    if at_user:
        message_list.append("指定人: ")
        message_list.extend((At(flag="user", target=at_user), "\n"))
    message_list.append(image)
    await MessageUtils.build_message(message_list).send()
    logger.info(
        f"塞入 {num.result} 个红包，共 {amount} 金币",
        arparma.header_result,
        session=session,
    )


@_open_matcher.handle()
async def _(
    session: Uninfo,
    rank_num: int = GetConfig(config="RANK_NUM"),
):
    # group_id = session.id3 or session.id2
    group_id = session.group.id if session.group else None
    """以频道id为键"""
    if not group_id:
        await MessageUtils.build_message("群组id为空").finish()
    platform = PlatformUtils.get_platform(session)
    if group_red_bag := RedBagManager.get_group_data(group_id):
        open_data, settlement_list = await group_red_bag.open(session.user.id, platform)
        # send_msg = Text("没有红包给你开！")
        send_msg = []
        for _, item in open_data.items():
            amount, red_bag = item
            result_image = await RedBagManager.build_open_result_image(
                red_bag, session, amount
            )
            send_msg.extend(
                (
                    f"开启了 {red_bag.promoter} 的红包, 获取 {amount} 个金币\n",
                    result_image,
                    "\n",
                )
            )
            logger.info(
                f"抢到了 {red_bag.promoter}({red_bag.promoter_id})"
                f" 的红包，获取了{amount}个金币",
                "开红包",
                session=session,
            )
        send_msg = (
            MessageUtils.build_message(send_msg[:-1])
            if send_msg
            else MessageUtils.build_message("没有红包给你开！")
        )
        await send_msg.send(reply_to=True)
        if settlement_list:
            for red_bag in settlement_list:
                result_image = await red_bag.build_amount_rank(rank_num, platform)
                await MessageUtils.build_message(
                    [f"{red_bag.name}已结算\n", result_image]
                ).send()


@_return_matcher.handle()
async def _(
    session: EventSession,
    default_interval: int = GetConfig(config="DEFAULT_INTERVAL"),
    rank_num: int = GetConfig(config="RANK_NUM"),
):
    group_id = session.id3 or session.id2
    user_id = session.id1
    if not user_id:
        await MessageUtils.build_message("用户id为空").finish()
    if not group_id:
        await MessageUtils.build_message("群组id为空").finish()
    if group_red_bag := RedBagManager.get_group_data(group_id):
        if user_red_bag := group_red_bag.get_user_red_bag(user_id):
            now = time.time()
            if now - user_red_bag.start_time < default_interval:
                await MessageUtils.build_message(
                    "你的红包还没有过时, "
                    f"在 {int(default_interval - now + user_red_bag.start_time)} "
                    "秒后可以退回..."
                ).finish(reply_to=True)
            user_red_bag = group_red_bag.get_user_red_bag(user_id)
            if user_red_bag and (
                data := await group_red_bag.settlement(user_id, session.platform)
            ):
                image_result = await user_red_bag.build_amount_rank(
                    rank_num, session.platform
                )
                logger.info(f"退回了红包 {data[0]} 金币", "红包退回", session=session)
                await MessageUtils.build_message(
                    [
                        f"已成功退还了 " f"{data[0]} 金币\n",
                        image_result,
                    ]
                ).finish(reply_to=True)
    await MessageUtils.build_message("目前没有红包可以退回...").finish(reply_to=True)


@_festive_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    amount: int,
    num: int,
    text: Match[str],
    groups: Match[str],
):
    greetings = text.result if text.available else "恭喜发财 大吉大利"
    gl = []
    if groups.available:
        gl = groups.result.strip().split()
    else:
        g_l, _ = await PlatformUtils.get_group_list(bot)
        gl = [g.channel_id or g.group_id for g in g_l]
    _uuid = str(uuid.uuid1())
    FestiveRedBagManage.add(_uuid)
    _suc_cnt = 0
    platform = PlatformUtils.get_platform(session)
    for g in gl:
        if target := PlatformUtils.get_target(group_id=g):
            group_red_bag = RedBagManager.get_group_data(g)
            if festive_red_bag := group_red_bag.get_festive_red_bag():
                group_red_bag.remove_festive_red_bag()
                if festive_red_bag.uuid:
                    FestiveRedBagManage.remove(festive_red_bag.uuid)
                rank_image = await festive_red_bag.build_amount_rank(10, platform)
                with contextlib.suppress(ActionFailed):
                    await MessageUtils.build_message(
                        [
                            f"{BotConfig.self_nickname}的节日红包过时了，一共开启了 "
                            f"{len(festive_red_bag.open_user)}"
                            f"个红包，共{sum(festive_red_bag.open_user.values())}金币\n",
                            rank_image,
                        ]
                    ).send(target=target, bot=bot)
            with contextlib.suppress(JobLookupError):
                scheduler.remove_job(f"{FESTIVE_KEY}_{g}")
                await RedBagManager.end_red_bag(g, is_festive=True, platform=platform)
            await group_red_bag.add_red_bag(
                f"{BotConfig.self_nickname}的红包",
                amount,
                num,
                BotConfig.self_nickname,
                FESTIVE_KEY,
                _uuid,
                platform=platform,
            )
            scheduler.add_job(
                RedBagManager._auto_end_festive_red_bag,
                "date",
                run_date=(datetime.now() + timedelta(hours=24)).replace(microsecond=0),
                id=f"{FESTIVE_KEY}_{g}",
                args=[bot, g, session.platform],
            )
            try:
                image_result = await RedBagManager.random_red_bag_background(
                    session, greetings, True
                )
                await MessageUtils.build_message(
                    [
                        f"{BotConfig.self_nickname}发起了节日金币红包\n"
                        f"金额: {amount}\n数量: {num}\n",
                        image_result,
                    ]
                ).send(target=target, bot=bot)
                _suc_cnt += 1
                logger.debug("节日红包图片信息发送成功...", "节日红包", group_id=g)
            except ActionFailed:
                logger.warning("节日红包图片信息发送失败...", "节日红包", group_id=g)
    if gl:
        await MessageUtils.build_message(
            f"节日红包发送成功，累计成功发送 {_suc_cnt} 个群组!"
        ).send()
