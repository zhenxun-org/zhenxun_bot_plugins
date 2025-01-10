from datetime import datetime, timedelta
import re

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Arg, Depends
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot_plugin_alconna import Arparma, Match
import pytz

from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

from .command import _matcher
from .data_source import draw_word_cloud, get_list_msg

__plugin_meta__ = PluginMetadata(
    name="词云",
    description="看看自己说了什么话",
    usage="""
    usage：
        词云
        指令：
            今日词云：获取今天的词云
            昨日词云：获取昨天的词云
            本周词云：获取本周词云
            本月词云：获取本月词云
            年度词云：获取年度词云

            历史词云(支持 ISO8601 格式的日期与时间，如 2022-02-22T22:22:22)
            获取某日的词云
            历史词云 2022-01-01
            获取指定时间段的词云
            历史词云
            示例：历史词云 2022-01-01~2022-02-22
            示例：历史词云 2022-02-22T11:11:11~2022-02-22T22:22:22

            如果想要获取自己的发言，可在命令前添加 我的
            示例：我的今日词云
    """.strip(),
    extra=PluginExtraData(
        author="yajiwa",
        version="0.1-89d294e",
        plugin_type=PluginType.NORMAL,
        commands=[
            Command(command="今日词云"),
            Command(command="昨日词云"),
            Command(command="本周词云"),
            Command(command="本月词云"),
            Command(command="年度词云"),
            Command(command="历史词云"),
        ],
        configs=[
            RegisterConfig(
                key="WORD_CLOUDS_TEMPLATE",
                value=1,
                help="词云模板 参1：图片生成，默认使用真寻图片，可在项目路径resources/image/wordcloud下配置图片，多张则随机 | 参2/其他：黑底图片",
                type=int,
            )
        ],
    ).to_dict(),
)


def parse_datetime(key: str):
    """解析数字，并将结果存入 state 中"""

    async def _key_parser(
        matcher: Matcher,
        state: T_State,
        input_: datetime | Message = Arg(key),
    ):
        if isinstance(input_, datetime):
            return

        plaintext = input_.extract_plain_text()
        try:
            state[key] = get_datetime_fromisoformat_with_timezone(plaintext)
        except ValueError:
            await matcher.reject_arg(key, "请输入正确的日期，不然我没法理解呢！")

    return _key_parser


def get_datetime_now_with_timezone() -> datetime:
    """获取当前时间，并包含时区信息"""
    return datetime.now().astimezone()


def get_datetime_fromisoformat_with_timezone(date_string: str) -> datetime:
    """从 iso8601 格式字符串中获取时间，并包含时区信息"""
    return datetime.fromisoformat(date_string).astimezone()


@_matcher.handle()
async def handle_first_receive(
    state: T_State,
    date: Match[str],
    arparma: Arparma,
    z_date: Match[str],
):
    state["my"] = arparma.find("my")
    select_data = date.result if date.available else "今日"

    if select_data == "今日":
        dt = get_datetime_now_with_timezone()
        state["start"] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        state["stop"] = dt
    elif select_data == "昨日":
        dt = get_datetime_now_with_timezone()
        state["stop"] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        state["start"] = state["stop"] - timedelta(days=1)
    elif select_data == "本周":
        dt = get_datetime_now_with_timezone()
        state["start"] = dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=dt.weekday())
        state["stop"] = dt
    elif select_data == "本月":
        dt = get_datetime_now_with_timezone()
        state["start"] = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        state["stop"] = dt
    elif select_data == "年度":
        dt = get_datetime_now_with_timezone()
        state["start"] = dt.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        state["stop"] = dt
    elif select_data == "历史":
        # if not z_date.available:
        #     await MessageUtils.build_message("历史词云需要输入日期！").finish(
        #         reply_to=True
        #     )
        if z_date.available:
            if match := re.match(r"^(.+?)(?:~(.+))?$", z_date.result):
                start = match[1]
                stop = match[2]
                try:
                    state["start"] = get_datetime_fromisoformat_with_timezone(start)
                    if stop:
                        state["stop"] = get_datetime_fromisoformat_with_timezone(stop)
                    else:
                        # 如果没有指定结束日期，则认为是指查询这一天的词云
                        state["start"] = state["start"].replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        state["stop"] = state["start"] + timedelta(days=1)
                except ValueError:
                    await MessageUtils.build_message(
                        "请输入正确的日期，不然我没法理解呢！"
                    ).finish(reply_to=True)


@_matcher.got(
    "start",
    prompt="请输入你要查询的起始日期（如 2022-01-01）",
    parameterless=[Depends(parse_datetime("start"))],
)
@_matcher.got(
    "stop",
    prompt="请输入你要查询的结束日期（如 2022-02-22）",
    parameterless=[Depends(parse_datetime("stop"))],
)
async def handle_message(
    event: GroupMessageEvent,
    start: datetime = Arg(),
    stop: datetime = Arg(),
    my: bool = Arg(),
):
    # 是否只查询自己的记录
    user_id = int(event.user_id) if my else None
    # 将时间转换到 东八 时区
    messages = await get_list_msg(
        user_id,
        int(event.group_id),
        days=(
            start.astimezone(pytz.timezone("Asia/Shanghai")),
            stop.astimezone(pytz.timezone("Asia/Shanghai")),
        ),
    )
    if messages:
        image_bytes = await draw_word_cloud(messages, get_driver().config)
        if image_bytes:
            await MessageUtils.build_message(image_bytes).finish(at_sender=my)
        else:
            await MessageUtils.build_message("生成词云失败").finish(at_sender=my)
    else:
        await MessageUtils.build_message("没有获取到词云数据").finish(at_sender=my)
