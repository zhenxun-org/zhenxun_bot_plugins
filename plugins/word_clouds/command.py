from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    Option,
    on_alconna,
    store_true,
    Match,
    Arparma,
    AlconnaMatch,
    Query,
    AlconnaQuery,
)
from nonebot.typing import T_State
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.adapters.onebot.v11 import Bot
from nonebot.permission import SUPERUSER
from nonebot.exception import FinishedException
from zhenxun.builtin_plugins.scheduler_admin.commands import schedule_cmd
from zhenxun.utils.rules import ensure_group
from zhenxun.services import scheduler_manager
from zhenxun.services.scheduler import ScheduleContext
from zhenxun.services.log import logger

from .handlers import CloudHandler, dispatch_wordcloud_task
from .services import TimeService

from .models import WordCloudTaskParams


async def scheduled_wordcloud_job(context: ScheduleContext, **kwargs):
    """
    一个包装函数，作为暴露给 scheduler_manager 的任务入口。
    """
    group_id = context.group_id
    if not group_id:
        logger.warning("定时词云任务执行失败：group_id 为空")
        return

    gid = int(group_id)
    time_service = TimeService()
    start, stop = time_service.get_time_range("今日")

    params = WordCloudTaskParams(
        start_time=start,
        end_time=stop,
        group_id=gid,
        destination_group_id=gid,
        is_scheduled_task=True,
        date_type="今日",
        is_today=True,
    )
    await dispatch_wordcloud_task(params)


scheduler_manager.register(
    "word_clouds",
    default_permission=5,
    default_jitter=60,
    default_spread=180,
)(scheduled_wordcloud_job)

_matcher = on_alconna(
    Alconna(
        "wordcloud",
        Args[
            "date?",
            ["今日", "昨日", "本周", "上周", "本月", "上月", "本季", "年度", "历史"],
        ]["at_user?", At],
        Option("-m|--my", action=store_true, help_text="个人词云"),
        Option("-d|--a_date", Args["z_date", str], help_text="指定日期"),
        Option(
            "-g|--group",
            Args["target_group_id", int],
            help_text="指定群聊 (仅超级用户)",
        ),
    ),
    priority=5,
    block=True,
    rule=ensure_group,
)

cloud_handler = CloudHandler()


_matcher.shortcut(
    r"^我的(?P<date>今日|昨日|本周|上周|本月|上月|本季|年度)词云$",
    command="wordcloud",
    arguments=["{date}", "--my"],
    prefix=True,
)

_matcher.shortcut(
    r"^我的(?P<date>今日|昨日|本周|上周|本月|上月|本季|年度)词云\s+-g\s+(?P<group_id>\d+)$",
    command="wordcloud",
    arguments=["{date}", "--my", "-g", "{group_id}"],
    prefix=True,
)

_matcher.shortcut(
    r"^我的词云$",
    command="wordcloud",
    arguments=["今日", "--my"],
    prefix=True,
)

_matcher.shortcut(
    r"^我的词云\s+-g\s+(?P<group_id>\d+)$",
    command="wordcloud",
    arguments=["今日", "--my", "-g", "{group_id}"],
    prefix=True,
)

_matcher.shortcut(
    r"^历史词云\s+(?P<date>.+)$",
    command="wordcloud",
    arguments=["历史", "--a_date", "{date}"],
    prefix=True,
)

_matcher.shortcut(
    r"^历史词云\s+(?P<date>.+?)\s+-g\s+(?P<group_id>\d+)$",
    command="wordcloud",
    arguments=["历史", "--a_date", "{date}", "-g", "{group_id}"],
    prefix=True,
)

_matcher.shortcut(
    r"(?P<date>今日|昨日|本周|上周|本月|上月|本季|年度)词云$",
    command="wordcloud",
    arguments=["{date}"],
    prefix=True,
)

_matcher.shortcut(
    r"(?P<date>今日|昨日|本周|上周|本月|上月|本季|年度)词云\s+-g\s+(?P<group_id>\d+)",
    command="wordcloud",
    arguments=["{date}", "-g", "{group_id}"],
    prefix=True,
)


@_matcher.handle()
async def handle_first_receive(
    bot: Bot,
    event: GroupMessageEvent,
    state: T_State,
    date: Match[str],
    arparma: Arparma,
    z_date: Match[str] = AlconnaMatch("z_date"),
    target_group: Query[int] = AlconnaQuery("group.target_group_id", 0),
):
    logger.debug(f"target_group: {target_group}")
    if target_group.available and target_group.result:
        is_superuser = await SUPERUSER(bot, event)
        if not is_superuser:
            await _matcher.finish("需要超级用户权限才能查看指定群组的词云。")
            return
        state["target_group_id"] = target_group.result

    await cloud_handler.handle_first_receive(state, date, arparma, z_date)

    if "start" in state and "stop" in state:
        start = state["start"]
        stop = state["stop"]
        my = state["my"]
        target_group_id = state.get("target_group_id")

        try:
            await cloud_handler.handle_message(
                event, state, start, stop, my, target_group_id
            )
        except FinishedException:
            raise


schedule_cmd.shortcut(
    r"^定时词云 开启 (?P<time>\S+)(?:\s+(?P<target>-g\s+[\d\s]+|-t\s+\S+))?$",
    command="定时任务",
    arguments=["设置", "word_clouds", "{target}", "--daily", "{time}"],
    prefix=True,
)

schedule_cmd.shortcut(
    r"^定时词云 (?P<action>关闭|删除)(?:\s+(?P<target>--all|-g\s+[\d\s]+|-t\s+\S+))?$",
    command="定时任务",
    arguments=["{action}", "{target}", "-p", "word_clouds"],
    prefix=True,
)

schedule_cmd.shortcut(
    r"^定时词云 (?P<action>暂停|恢复|查看)(?:\s+(?P<target>--all|-g\s+[\d\s]+|-t\s+\S+))?$",
    command="定时任务",
    arguments=["{action}", "{target}", "-p", "word_clouds"],
    prefix=True,
)

schedule_cmd.shortcut(
    r"^全局定时词云 (?P<action>开启) (?P<time>\S+)$",
    command="定时任务",
    arguments=["设置", "word_clouds", "--global", "--daily", "{time}"],
    prefix=True,
)

schedule_cmd.shortcut(
    r"^全局定时词云 (?P<action>关闭|删除|暂停|恢复|查看)$",
    command="定时任务",
    arguments=["{action}", "--global", "-p", "word_clouds"],
    prefix=True,
)
