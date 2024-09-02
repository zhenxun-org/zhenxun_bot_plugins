from nonebot_plugin_alconna import Alconna, Args, At, Option, on_alconna, store_true

from zhenxun.utils.rules import ensure_group

_matcher = on_alconna(
    Alconna(
        "wordcloud",
        Args["date?", ["今日", "昨日", "本周", "本月", "年度", "历史"]]["at_user?", At],
        Option("-m|--my", action=store_true, help_text="个人词云"),
        Option("-d|--a_date", Args["z_date", str]),
    ),
    priority=5,
    block=True,
    rule=ensure_group,
)


_matcher.shortcut(
    r"^我的(?P<date>今日|昨日|本周|本月|年度)?词云$",
    command="wordcloud",
    arguments=["{date}" "--my"],
    prefix=True,
)


_matcher.shortcut(
    r"历史词云\S?(?P<date>.*)?",
    command="wordcloud",
    arguments=["--a_date", "{date}"],
    prefix=True,
)

_matcher.shortcut(
    r"(?P<date>今日|昨日|本周|本月|年度)词云",
    command="wordcloud",
    arguments=["{date}"],
    prefix=True,
)
