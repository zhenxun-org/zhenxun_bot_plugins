import asyncio
from datetime import datetime, timedelta
import random

import nonebot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Arparma, Match
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_session import EventSession

from zhenxun.configs.utils import (
    Command,
    PluginCdBlock,
    PluginExtraData,
    RegisterConfig,
    Task,
)
from zhenxun.services.log import logger
from zhenxun.utils.common_utils import CommonUtils
from zhenxun.utils.depends import UserName
from zhenxun.utils.image_utils import text2image
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import broadcast_group

from .buff import BuffUpdateManager, CaseManager
from .build_image import build_case_image, build_skin_trends
from .command import (
    _group_open_matcher,
    _knifes_matcher,
    _multiple_matcher,
    _my_open_matcher,
    _open_matcher,
    _price_matcher,
    _reload_matcher,
    _show_case_matcher,
    _update_matcher,
)
from .config import CASE2ID, KNIFE2ID
from .data_source import OpenCaseManager, auto_update, reset_count_daily
from .exception import NotLoginRequired

__plugin_meta__ = PluginMetadata(
    name="CSGO开箱",
    description="csgo模拟开箱[戒赌]",
    usage="""
    指令：
        开箱 ?[武器箱]
        [1-30]连开箱 ?[武器箱]
        我的开箱
        我的金色
        群开箱统计
        查看武器箱?[武器箱]
        * 不包含[武器箱]时随机开箱 *
        示例: 查看武器箱
        示例: 查看武器箱英勇
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1-eb2b7db",
        superuser_help="""
        更新皮肤指令
        重置开箱： 重置今日开箱所有次数
        指令：
            更新武器箱 ?[武器箱/ALL]
            更新皮肤 ?[名称/ALL1]
            更新皮肤 ?[名称/ALL1]
            更新武器箱图片
        * 不指定武器箱时则全部更新 *
        * 过多的爬取会导致账号API被封 *
        """.strip(),
        menu_type="抽卡相关",
        commands=[
            Command(command="开箱"),
            Command(command="[1-30]连开箱"),
            Command(command="我的开箱"),
            Command(command="我的金色"),
            Command(command="群开箱统计"),
            Command(command="查看武器箱 ?[武器箱]"),
        ],
        tasks=[Task(module="open_case_reset_remind", name="每日开箱重置提醒")],
        limits=[PluginCdBlock(result="着什么急啊，慢慢来！")],
        configs=[
            RegisterConfig(
                key="INITIAL_OPEN_CASE_COUNT",
                value=20,
                help="初始每日开箱次数",
                default_value=20,
                type=int,
            ),
            RegisterConfig(
                key="EACH_IMPRESSION_ADD_COUNT",
                value=3,
                help="每 * 点好感度额外增加开箱次数",
                default_value=3,
                type=int,
            ),
            RegisterConfig(key="COOKIE", value=None, help="BUFF的cookie"),
            RegisterConfig(
                key="DAILY_UPDATE",
                value=None,
                help="每日自动更新的武器箱，存在'ALL'时则更新全部武器箱",
                type=list[str],
            ),
            RegisterConfig(
                key="DEFAULT_OPEN_CASE_RESET_REMIND",
                module="_task",
                value=True,
                help="被动 每日开箱重置提醒 进群默认开关状态",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="BUFF_PROXY",
                value=None,
                help="buff请求代理",
                default_value=None,
            ),
        ],
    ).to_dict(),
)


@_price_matcher.handle()
async def _(
    session: EventSession,
    arparma: Arparma,
    name: str,
    skin: str,
    abrasion: str,
    day: Match[int],
):
    name = name.replace("武器箱", "").strip()
    _day = day.result if day.available else 7
    if _day > 180 or _day <= 0:
        await MessageUtils.build_message("天数必须大于0且小于180").finish()
    result = await build_skin_trends(name, skin, abrasion, _day)
    if not result:
        await MessageUtils.build_message("未查询到数据...").finish(reply_to=True)
    await MessageUtils.build_message(result).send()
    logger.info(
        f"查看 [{name}:{skin}({abrasion})] 价格趋势",
        arparma.header_result,
        session=session,
    )


@_open_matcher.handle()
async def _(session: EventSession, arparma: Arparma, name: Match[str]):
    gid = session.id3 or session.id2
    if not session.id1:
        await MessageUtils.build_message("用户id为空...").finish()
    if not gid:
        await MessageUtils.build_message("群组id为空...").finish()
    case_name = name.result.replace("武器箱", "").strip() if name.available else None
    result = await OpenCaseManager.open_case(session.id1, gid, case_name, 1, session)
    await result.finish(reply_to=True)


@_multiple_matcher.handle()
async def _(session: EventSession, arparma: Arparma, num: int, name: Match[str]):
    gid = session.id3 or session.id2
    if not session.id1:
        await MessageUtils.build_message("用户id为空...").finish()
    if not gid:
        await MessageUtils.build_message("群组id为空...").finish()
    if num > 30:
        await MessageUtils.build_message("开箱次数不要超过30啊笨蛋！").finish()
    if num < 0:
        await MessageUtils.build_message("再负开箱就扣你明天开箱数了！").finish()
    case_name = name.result.replace("武器箱", "").strip() if name.available else None
    result = await OpenCaseManager.open_case(session.id1, gid, case_name, num, session)
    await result.send(reply_to=True)
    logger.info(f"{num}连开箱", arparma.header_result, session=session)


@_reload_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    try:
        await reset_count_daily(session.id3 or session.id2)
        logger.info("重置开箱次数", arparma.header_result, session=session)
        await MessageUtils.build_message("重置开箱次数成功!").send()
    except Exception:
        logger.error("重置开箱发生错误...", arparma.header_result, session=session)
        await MessageUtils.build_message("重置开箱次数失败...").finish()


@_my_open_matcher.handle()
async def _(session: EventSession, arparma: Arparma, uname: str = UserName()):
    gid = session.id3 or session.id2
    user_id = session.id1
    if not user_id:
        await MessageUtils.build_message("用户id为空...").finish()
    if not gid:
        await MessageUtils.build_message("群组id为空...").finish()
    await MessageUtils.build_message(
        await OpenCaseManager.get_user_data(uname, user_id, gid),
    ).send(reply_to=True)
    logger.info("查询我的开箱", arparma.header_result, session=session)


@_knifes_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    gid = session.id3 or session.id2
    if not session.id1:
        await MessageUtils.build_message("用户id为空...").finish()
    if not gid:
        await MessageUtils.build_message("群组id为空...").finish()
    result = await OpenCaseManager.get_my_knifes(session.id1, gid)
    await result.send(reply_to=True)
    logger.info("查询我的金色", arparma.header_result, session=session)


@_group_open_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    gid = session.id3 or session.id2
    if not gid:
        await MessageUtils.build_message("群组id为空...").finish()
    result = await OpenCaseManager.get_group_data(gid)
    await MessageUtils.build_message(result).send(reply_to=True)
    logger.info("查询群开箱统计", arparma.header_result, session=session)


@_show_case_matcher.handle()
async def _(session: EventSession, arparma: Arparma, name: Match[str]):
    case_name = name.result.strip() if name.available else None
    await MessageUtils.build_message("正在构建武器箱图片，请稍等...").send()
    result = await build_case_image(case_name)
    if isinstance(result, str):
        await MessageUtils.build_message(result).send()
    else:
        await MessageUtils.build_message(result).send()
        logger.info("查看武器箱", arparma.header_result, session=session)


@_update_matcher.handle()
async def _(session: EventSession, arparma: Arparma, name: Match[str]):
    # sourcery skip: low-code-quality
    case_name = None
    if name.available:
        case_name = name.result.strip()
    if not case_name:
        case_list = []
        skin_list = []
        for i, case_name in enumerate(CASE2ID):
            if case_name in CaseManager.CURRENT_CASES:
                case_list.append(f"{i+1}.{case_name} [已更新]")
            else:
                case_list.append(f"{i+1}.{case_name}")
        for skin_name in KNIFE2ID:
            skin_list.append(f"{skin_name}")
        text = "武器箱:\n" + "\n".join(case_list) + "\n皮肤:\n" + ", ".join(skin_list)
        img = await text2image(text, padding=20, color="#f9f6f2")
        await MessageUtils.build_message(
            ["未指定武器箱, 当前已包含武器箱/皮肤\n", img]
        ).finish()
    if case_name in ["ALL", "ALL1"]:
        if case_name == "ALL":
            case_list = list(CASE2ID.keys())
            type_ = "武器箱"
        else:
            case_list = list(KNIFE2ID.keys())
            type_ = "罕见皮肤"
        await MessageUtils.build_message(f"即将更新所有{type_}, 请稍等").send()
        for i, case_name in enumerate(case_list):
            try:
                info = await BuffUpdateManager.update_skin(case_name)
                rand = random.randint(300, 500)
                result = f"更新全部{type_}完成"
                if i < len(case_list) - 1:
                    next_case = case_list[i + 1]
                    result = f"将在 {rand} 秒后更新下一{type_}: {next_case}"
                await MessageUtils.build_message(f"{info}, {result}").send()
                logger.info(f"info, {result}", "更新武器箱", session=session)
                await asyncio.sleep(rand)
            except NotLoginRequired:
                await MessageUtils.build_message(
                    f"更新{type_}: {case_name} 需要登录, 请先登录"
                ).finish()
            except Exception as e:
                logger.error(f"更新{type_}: {case_name}", session=session, e=e)
                await MessageUtils.build_message(
                    f"更新{type_}: {case_name} 发生错误: {type(e)}: {e}"
                ).send()
        await MessageUtils.build_message(f"更新全部{type_}完成").send()
    else:
        await MessageUtils.build_message(
            f"开始{arparma.header_result}: {case_name}, 请稍等"
        ).send()
        try:
            await MessageUtils.build_message(
                await BuffUpdateManager.update_skin(case_name)
            ).send(at_sender=True)
        except Exception as e:
            logger.error(f"{arparma.header_result}: {case_name}", session=session, e=e)
            await MessageUtils.build_message(
                f"成功{arparma.header_result}: {case_name} 发生错误: {type(e)}: {e}"
            ).send()


driver = nonebot.get_driver()


@driver.on_startup
async def _():
    await CaseManager.reload()


async def check(bot, group_id: str) -> bool:
    return not await CommonUtils.task_is_block(bot, "open_case_reset_remind", group_id)


@scheduler.scheduled_job(
    "cron",
    hour=0,
    minute=1,
)
async def _():
    await reset_count_daily()
    await broadcast_group("每日开箱重置成功!", log_cmd="每日开箱重置", check_func=check)


@scheduler.scheduled_job(
    "cron",
    hour=0,
    minute=10,
)
async def _():
    now = datetime.now()
    hour = random.choice([0, 1, 2, 3])
    date = now + timedelta(hours=hour)
    logger.debug(f"将在 {date} 时自动更新武器箱...", "更新武器箱")
    scheduler.add_job(
        auto_update,
        "date",
        run_date=date.replace(microsecond=0),
        id="auto_update_csgo_cases",
    )
