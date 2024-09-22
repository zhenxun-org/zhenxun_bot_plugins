from nonebot import on_regex
from nonebot_plugin_alconna import Alconna, Args, Option, on_alconna, store_true

from zhenxun.utils.rules import admin_check

_add_matcher = on_regex(
    r"^(全局|私聊)?添加词条\s*?(模糊|正则|图片)?问(\S*\s?\S*)",
    priority=5,
    block=True,
    rule=admin_check("word_bank", "WORD_BANK_LEVEL"),
)


_del_matcher = on_alconna(
    Alconna(
        "删除词条",
        Args["problem?", str],
        Option("--all", action=store_true, help_text="所有词条"),
        Option("--id", Args["index", int], help_text="下标id"),
        Option("--aid", Args["answer_id", int], help_text="回答下标id"),
    ),
    priority=5,
    block=True,
)


_update_matcher = on_alconna(
    Alconna(
        "修改词条",
        Args["replace", str]["problem?", str],
        Option("--id", Args["index", int], help_text="词条id"),
        Option("--all", action=store_true, help_text="全局词条"),
    )
)
