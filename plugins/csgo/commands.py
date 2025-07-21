from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    Field,
    Option,
    on_alconna,
    store_true,
)

__all__ = [
    "_ban_stat_matcher",
    "_bind_steam_id_matcher",
    "_map_rate_matcher",
    "_match_detail_matcher",
    "_match_list_matcher",
    "_match_matcher",
    "_official_data_matcher",
    "_rank_matcher",
    "_refresh_matcher",
    "_unbind_steam_id_matcher",
    "_user_data_matcher",
    "_video_download_matcher",
    "_video_matcher",
    "_watch_play_matcher",
    "_weapon_data_matcher",
]

_bind_steam_id_matcher = on_alconna(
    Alconna(
        "绑定steam",
        Args["steam_id", str],
        Field(
            missing_tips=lambda: "请在命令后跟随Steam Id！",
        ),
    ),
    priority=5,
    block=True,
    skip_for_unmatch=False,
)

_unbind_steam_id_matcher = on_alconna(
    Alconna("解绑steam"),
    priority=5,
    block=True,
)

_map_rate_matcher = on_alconna(
    Alconna("完美地图数据", Args["target?", At | str]["season?", str]),
    priority=5,
    block=True,
)

_user_data_matcher = on_alconna(
    Alconna("完美数据", Args["target?", At | str]["season?", str]),
    priority=5,
    block=True,
)

_watch_play_matcher = on_alconna(
    Alconna("完美监控", Args["target?", At | str]),
    priority=5,
    block=True,
)

_video_matcher = on_alconna(
    Alconna("完美时刻", Args["target?", At | str]),
    priority=5,
    block=True,
)

_video_download_matcher = on_alconna(
    Alconna(
        "完美时刻下载",
        Args["video_id", str],
        Field(
            missing_tips=lambda: "请在命令后跟随视频id前四位！",
        ),
    ),
    skip_for_unmatch=False,
    priority=5,
    block=True,
)

_official_data_matcher = on_alconna(
    Alconna("官匹数据", Args["target?", At | str]),
    priority=5,
    block=True,
)


_weapon_data_matcher = on_alconna(
    Alconna("完美武器数据", Args["target?", At | str]["season?", str]),
    priority=5,
    block=True,
)

_ban_stat_matcher = on_alconna(Alconna("完美封禁统计"), priority=5, block=True)

_match_matcher = on_alconna(
    Alconna("赛事查看", Args["target?", At]), priority=5, block=True
)


_rank_matcher = on_alconna(
    Alconna("pw-rank", Args["num?", int], Option("-t", Args["type", str])),
    priority=5,
    block=True,
)

_rank_matcher.shortcut(
    r"完美天梯排行\s*(?P<num>\d*)",
    command="pw-rank",
    arguments=["{num}", "-t", "score"],
    prefix=True,
)

_rank_matcher.shortcut(
    r"完美rt排行\s*(?P<num>\d*)",
    command="pw-rank",
    arguments=["{num}", "-t", "rt"],
    prefix=True,
)

_refresh_matcher = on_alconna(
    Alconna(
        "csgo刷新数据", Option("--all", action=store_true, help_text="刷新所有数据")
    ),
    priority=5,
    block=True,
)

_match_list_matcher = on_alconna(
    Alconna("完美战绩", Args["target?", At | str], Option("-p", Args["page", int])),
    priority=5,
    block=True,
)

_match_detail_matcher = on_alconna(
    Alconna("完美战绩详情", Args["match_id", str]),
    priority=5,
    block=True,
)
