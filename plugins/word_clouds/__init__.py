from nonebot import require

require("nonebot_plugin_apscheduler")

from nonebot.plugin import PluginMetadata

from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.utils.enum import PluginType
from pathlib import Path
from typing import List, Union

from . import command

__plugin_meta__ = PluginMetadata(
    name="词云",
    description="看看自己说了什么话",
    usage="""
    词云插件

    【获取词云】
    - 今日/昨日/本周/本月/年度词云
    - 我的今日/昨日/本周/本月/年度词云 - 获取自己的发言词云
    - 历史词云 [日期] - 获取某日词云 (例: 历史词云 2023-01-15)
    - 历史词云 [开始日期]~[结束日期] - 获取时间段词云 (例: 历史词云 2023-01-01~2023-01-31)
    - 历史词云 [开始时间]~[结束时间] - 精确时间段 (例: 历史词云 2023-01-15T10:00:00~2023-01-15T18:30:00)
    - 今日词云 -g <群号> - 获取指定群的词云 (仅超级用户)
    - 我的今日词云 -g <群号> - 获取自己在指定群的词云 (仅超级用户)
    - 历史词云 2023-01-01~2023-01-31 -g <群号> - 获取指定群的历史词云 (仅超级用户)

    【定时发送】(需要管理员权限, -g/-all 需要Superuser)
    - 定时词云 开启 <时间> - 设置当前群定时发送 (例: 定时词云 开启 22:00)
    - 定时词云 关闭 - 取消当前群定时发送
    - 定时词云 状态 - 查看当前群定时状态
    - 定时词云 [开启/关闭/状态] -g <群号> - 操作指定群聊
    - 定时词云 [开启/关闭/状态] -all - 操作所有群聊
    - 定时词云 队列 - 查看任务队列状态 (仅超级用户)
    - 定时词云 资源 - 查看资源池状态 (仅超级用户)

    【提示】
    - 时间格式为 HH:MM 或 HHMM
    - 日期/时间格式支持 ISO8601 标准
    """.strip(),
    extra=PluginExtraData(
        author="yajiwa",
        version="1.3.0",
        plugin_type=PluginType.NORMAL,
        commands=[
            Command(command="今日词云"),
            Command(command="昨日词云"),
            Command(command="本周词云"),
            Command(command="本月词云"),
            Command(command="年度词云"),
            Command(command="历史词云"),
            Command(command="定时词云 开启"),
            Command(command="定时词云 关闭"),
            Command(command="定时词云 状态"),
            Command(command="定时词云 队列"),
            Command(command="定时词云 资源"),
        ],
        configs=[
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_TEMPLATE",
                value=1,
                help="词云模板 参1：图片生成，默认使用真寻图片，可在项目路径resources/image/wordcloud下配置图片，多张则随机 | 参2/其他：黑底图片",
                type=int,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_MAX_WORDS",
                value=300,
                help="词云中显示的最大词数",
                type=int,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_MIN_FONT_SIZE",
                value=8,
                help="最小字体大小",
                type=int,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_MAX_FONT_SIZE",
                value=100,
                help="最大字体大小",
                type=int,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_WIDTH",
                value=1920,
                help="词云图片宽度",
                type=int,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_HEIGHT",
                value=1080,
                help="词云图片高度",
                type=int,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_BACKGROUND_COLOR",
                value=None,
                help="背景颜色，只能是'white'或'black'。当模板类型为1时默认为白色，否则为黑色。",
                type=str,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_COLORMAP_WHITE_BG",
                value=[
                    "viridis",
                    "plasma",
                    "inferno",
                    "magma",
                    "Blues",
                    "Greens",
                    "Reds",
                    "Purples",
                    "RdBu",
                    "coolwarm",
                    "PiYG",
                ],
                help="白色背景时使用的颜色映射列表，会随机选择其中之一",
                type=List[str],
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_COLORMAP_BLACK_BG",
                value=[
                    "plasma",
                    "hot",
                    "YlOrRd",
                    "YlOrBr",
                    "Oranges",
                    "OrRd",
                    "rainbow",
                    "jet",
                    "turbo",
                    "coolwarm",
                    "RdBu",
                    "Spectral",
                ],
                help="黑色背景时使用的颜色映射列表，会随机选择其中之一",
                type=List[str],
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_ADDITIONAL_OPTIONS",
                value={},
                help="额外的WordCloud选项，以字典形式提供",
                type=dict,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_RELATIVE_SCALING",
                value=0.3,
                help="相对缩放值，降低相对缩放使词云更均匀",
                type=float,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_PREFER_HORIZONTAL",
                value=0.7,
                help="水平词的比例，降低该值会增加垂直词的比例",
                type=float,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_COLLOCATIONS",
                value=True,
                help="是否检测词组",
                type=bool,
            ),
        ],
    ).to_dict(),
)
