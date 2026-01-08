from datetime import datetime

import nonebot
from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_session import EventSession
from playwright.async_api import TimeoutError

from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig, Task
from zhenxun.services.log import logger
from zhenxun.utils.common_utils import CommonUtils
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import broadcast_group

from .config import REPORT_PATH
from .data_source import Report

__plugin_meta__ = PluginMetadata(
    name="真寻日报",
    description="嗨嗨，这里是小记者真寻哦",
    usage="""
    指令：
        真寻日报
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.7",
        superuser_help="""重置真寻日报""",
        commands=[Command(command="真寻日报")],
        tasks=[Task(module="mahiro_report", name="真寻日报")],
        configs=[
            RegisterConfig(
                module="alapi",
                key="ALAPI_TOKEN",
                value=None,
                help="在https://admin.alapi.cn/user/login登录后获取token",
            ),
            RegisterConfig(
                key="FULL_SHOW",
                value=False,
                help="完全显示it资讯和60s",
                default_value=False,
                type=bool,
            ),
        ],
    ).to_dict(),
)


_matcher = on_alconna(Alconna("真寻日报"), priority=5, block=True, use_origin=True)

_reset_matcher = on_alconna(
    Alconna("重置真寻日报"), priority=5, block=True, permission=SUPERUSER
)


@_reset_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    file = REPORT_PATH / f"{datetime.now().date()}.png"
    if file.exists():
        file.unlink()
        logger.info("重置真寻日报", arparma.header_result, session=session)
    await MessageUtils.build_message("真寻日报已重置!").send()


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    try:
        await MessageUtils.build_message(await Report.get_report_image()).send()
        logger.info("查看真寻日报", arparma.header_result, session=session)
    except TimeoutError:
        await MessageUtils.build_message("真寻日报生成超时...").send(at_sender=True)
        logger.error("真寻日报生成超时", arparma.header_result, session=session)


driver = nonebot.get_driver()


async def check(bot: Bot, group_id: str) -> bool:
    return not await CommonUtils.task_is_block(bot, "mahiro_report", group_id)


@scheduler.scheduled_job(
    "cron",
    hour=0,
    minute=1,
)
async def _():
    for _ in range(3):
        try:
            await Report.get_report_image()
            logger.info("自动生成日报成功...")
            break
        except TimeoutError:
            logger.warning("自动生成日报失败...")


@scheduler.scheduled_job(
    "cron",
    hour=9,
    minute=1,
)
async def _():
    file = await Report.get_report_image()
    message = MessageUtils.build_message(file)
    await broadcast_group(message, log_cmd="真寻日报", check_func=check)
    logger.info("每日真寻日报发送...")
