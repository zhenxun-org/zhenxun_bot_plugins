from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    Option,
    Subcommand,
    Field,
    on_alconna,
    store_true,
    Match,
    Arparma,
    AlconnaMatch,
    Query,
    AlconnaQuery,
)
from nonebot.params import Arg, Depends
from nonebot.typing import T_State
from datetime import datetime
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.adapters.onebot.v11 import Bot
from nonebot.permission import SUPERUSER

from zhenxun.utils.rules import ensure_group, admin_check

from .handlers.cloud_handler import CloudHandler
from . import schedule_manage

cloud_handler = CloudHandler()

_matcher = on_alconna(
    Alconna(
        "wordcloud",
        Args["date?", ["今日", "昨日", "本周", "上周", "本月", "上月", "本季", "年度", "历史"]][
            "at_user?", At
        ],
        Option("-m|--my", action=store_true, help_text="个人词云"),
        Option("-d|--a_date", Args["z_date", str]),
        Option(
            "-g|--group",
            Args["target_group_id", int, Field(completion="指定群号 (SUPERUSER)")],
            help_text="指定群聊 (仅超级用户)",
        ),
    ),
    priority=5,
    block=True,
    rule=ensure_group,
)


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
    r"^我的词云(?:\s+-g\s+(?P<group_id>\d+))?$",
    command="wordcloud",
    arguments=lambda match: ["今日", "--my"]
    + (["-g", match.group("group_id")] if match.group("group_id") else []),
    prefix=True,
)


_matcher.shortcut(
    r"历史词云\S?(?P<date>.*?)(?:\s+-g\s+(?P<group_id>\d+))?$",
    command="wordcloud",
    arguments=lambda match: ["--a_date", match.group("date").strip()]
    + (["-g", match.group("group_id")] if match.group("group_id") else []),
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
    z_date: Match[str],
    target_group: Query[int] = AlconnaQuery("group.target_group_id"),
):
    if target_group.available:
        is_superuser = await SUPERUSER(bot, event)
        if not is_superuser:
            await _matcher.finish("需要超级用户权限才能查看指定群组的词云。")
            return
        state["target_group_id"] = target_group.result

    await cloud_handler.handle_first_receive(state, date, arparma, z_date)


@_matcher.got(
    "start",
    prompt="请输入你要查询的起始日期（如 2022-01-01）",
    parameterless=[Depends(cloud_handler.parse_datetime("start"))],
)
@_matcher.got(
    "stop",
    prompt="请输入你要查询的结束日期（如 2022-02-22）",
    parameterless=[Depends(cloud_handler.parse_datetime("stop"))],
)
async def handle_message(
    event: GroupMessageEvent,
    state: T_State,
    start: datetime = Arg(),
    stop: datetime = Arg(),
    my: bool = Arg(),
):
    target_group_id = state.get("target_group_id")

    await cloud_handler.handle_message(event, state, start, stop, my, target_group_id)


schedule_alconna = Alconna(
    "定时词云",
    Subcommand(
        "开启",
        Args["time_str", str, Field(completion="输入时间 (HH:MM 或 HHMM)")],
        Option(
            "-g",
            Args["target_group_id", int, Field(completion="指定群号 (SUPERUSER)")],
            help_text="指定群聊",
        ),
        Option("-all", help_text="所有群聊 (SUPERUSER)"),
    ),
    Subcommand(
        "关闭",
        Option(
            "-g",
            Args["target_group_id", int, Field(completion="指定群号 (SUPERUSER)")],
            help_text="指定群聊",
        ),
        Option("-all", help_text="所有群聊 (SUPERUSER)"),
    ),
    Subcommand(
        "状态",
        Option(
            "-g",
            Args["target_group_id", int, Field(completion="指定群号 (SUPERUSER)")],
            help_text="指定群聊",
        ),
        Option("-all", help_text="所有群聊 (SUPERUSER)"),
    ),
)

schedule_matcher = on_alconna(schedule_alconna, priority=4, block=True)


@schedule_matcher.assign("开启")
async def handle_schedule_on(
    bot: Bot,
    event: GroupMessageEvent,
    state: T_State,
    time_str: Match[str] = AlconnaMatch("time_str"),
    target_group: Query[int] = AlconnaQuery("开启.g.target_group_id"),
    all_groups: Query[bool] = AlconnaQuery("开启.all.value", default=False),
):
    if not time_str.available:
        await schedule_matcher.finish("请提供定时时间 (HH:MM 或 HHMM 格式)。")
        return

    current_group_id = str(event.group_id)
    is_superuser = await SUPERUSER(bot, event)
    is_admin = await admin_check("word_clouds", None)(bot=bot, event=event, state=state)

    time_to_set = time_str.result

    if all_groups.result:
        if not is_superuser:
            await schedule_matcher.finish("需要超级用户权限才能对所有群组操作。")
            return
        added, failed, message = await schedule_manage.add_schedule_for_all(time_to_set)
        await schedule_matcher.finish(message)
    elif target_group.available:
        if not is_superuser:
            await schedule_matcher.finish("需要超级用户权限才能指定群组。")
            return
        target_gid = str(target_group.result)
        success, message = await schedule_manage.add_schedule(target_gid, time_to_set)
        await schedule_matcher.finish(message)
    else:
        if not is_admin and not is_superuser:
            await schedule_matcher.finish("需要管理员权限才能设置当前群的定时词云。")
            return
        success, message = await schedule_manage.add_schedule(
            current_group_id, time_to_set
        )
        await schedule_matcher.finish(message)


@schedule_matcher.assign("关闭")
async def handle_schedule_off(
    bot: Bot,
    event: GroupMessageEvent,
    state: T_State,
    target_group: Query[int] = AlconnaQuery("关闭.g.target_group_id"),
    all_groups: Query[bool] = AlconnaQuery("关闭.all.value", default=False),
):
    current_group_id = str(event.group_id)
    is_superuser = await SUPERUSER(bot, event)
    is_admin = await admin_check("word_clouds", None)(bot=bot, event=event, state=state)

    if all_groups.result:
        if not is_superuser:
            await schedule_matcher.finish("需要超级用户权限才能对所有群组操作。")
            return
        removed_count, message = await schedule_manage.remove_schedule_for_all()
        await schedule_matcher.finish(message)
    elif target_group.available:
        if not is_superuser:
            await schedule_matcher.finish("需要超级用户权限才能指定群组。")
            return
        target_gid = str(target_group.result)
        success, message = await schedule_manage.remove_schedule(target_gid)
        await schedule_matcher.finish(message)
    else:
        if not is_admin and not is_superuser:
            await schedule_matcher.finish("需要管理员权限才能取消当前群的定时词云。")
            return
        success, message = await schedule_manage.remove_schedule(current_group_id)
        await schedule_matcher.finish(message)


@schedule_matcher.assign("状态")
async def handle_schedule_status(
    bot: Bot,
    event: GroupMessageEvent,
    state: T_State,
    target_group: Query[int] = AlconnaQuery("状态.g.target_group_id"),
    all_groups: Query[bool] = AlconnaQuery("状态.all.value", default=False),
):
    current_group_id = str(event.group_id)
    is_superuser = await SUPERUSER(bot, event)
    is_admin = await admin_check("word_clouds", None)(bot=bot, event=event, state=state)

    if all_groups.result:
        if not is_superuser:
            await schedule_matcher.finish("需要超级用户权限才能查看所有群组的状态。")
            return

        all_schedules = await schedule_manage.get_all_schedules()
        if not all_schedules:
            await schedule_matcher.finish("当前没有任何群组设置了定时词云。")
            return

        status_lines = ["当前定时词云设置状态："]
        for group_id, time_str in all_schedules.items():
            status_lines.append(f"群 {group_id}: 每天 {time_str}")

        status_message = "\n".join(status_lines)
        if len(status_lines) > 20:
            status_message = (
                f"共有 {len(all_schedules)} 个群组设置了定时词云。\n" + status_message
            )

        await schedule_matcher.finish(status_message)
        return

    gid_to_check = current_group_id
    if target_group.available:
        if not is_superuser:
            await schedule_matcher.finish("需要超级用户权限才能查看指定群组的状态。")
            return
        gid_to_check = str(target_group.result)
    else:
        if not is_admin and not is_superuser:
            await schedule_matcher.finish(
                "需要管理员权限才能查看当前群的定时词云状态。"
            )
            return

    schedule_time = await schedule_manage.get_schedule_time(gid_to_check)
    if schedule_time:
        await schedule_matcher.finish(
            f"群 {gid_to_check} 的定时词云已开启，时间为每天 {schedule_time}。"
        )
    else:
        await schedule_matcher.finish(f"群 {gid_to_check} 未设置定时词云。")
