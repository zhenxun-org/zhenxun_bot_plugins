from nonebot.plugin import PluginMetadata

from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.utils.enum import PluginType

from . import command  # noqa: F401

__plugin_meta__ = PluginMetadata(
    name="词云",
    description="看看自己说了什么话",
    usage="""\
### ✨ 获取词云
**基础用法**
- **按时间范围**: `今日词云`, `昨日词云`, `本周词云`, `上周词云`, `本月词云`, `上月词云`, `本季词云`, `年度词云`
- **个人词云**: 在上述命令前添加 `我的`，如 `我的今日词云`。
- **快捷指令**: `我的词云` (等同于 `我的今日词云`)

**历史词云**
- **查询单日**: `历史词云 <日期>`
  - 日期格式: `YYYY-MM-DD` 或 `MM-DD` (年份默认为当前年份)。
- **查询范围**: `历史词云 <开始日期>~<结束日期>`

**附加选项 (仅超级用户)**
- **跨群查询**: 在任意获取词云的命令后追加 `-g <群号>`。

**示例**
> `本周词云`
> `我的词云`
> `历史词云 2024-01-15`
> `历史词云 03-01~03-15 -g 123456`

---
### ⚙️ 定时发送 (仅超级用户)
**命令列表**
- `定时词云 开启 <时间>` - 开启定时任务，时间格式为 `HH:MM` 或 `HHMM`。
- `定时词云 关闭` - 关闭定时任务。
- `定时词云 查看` - 查看定时任务状态。
- `定时词云 暂停` - 暂停定时任务。
- `定时词云 恢复` - 恢复已暂停的任务。
- `定时词云 清空` - 清空所有词云定时任务。

**目标范围**
- **默认**: 操作当前群聊。
- **指定群聊**: 在命令后追加 `-g <群号>`。
- **所有群聊**: 在命令后追加 `-all` (全局任务)。

**示例**
> `定时词云 开启 22:00`
> `定时词云 关闭 -g 123456`
> `定时词云 查看 -all`\
""".strip(),
    extra=PluginExtraData(
        author="yajiwa",
        version="1.5.0",
        plugin_type=PluginType.NORMAL,
        commands=[
            Command(command="今日词云"),
            Command(command="我的词云"),
            Command(command="昨日词云"),
            Command(command="本周词云"),
            Command(command="本月词云"),
            Command(command="年度词云"),
            Command(command="我的年度词云"),
        ],
        configs=[
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_TEMPLATE",
                value=1,
                help="词云模板 参1：图片生成，默认使用真寻图片，可在项目路径resources/image/wordcloud下配置图片，多张则随机 "
                     "| 参2/其他：黑底图片",
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
                type=list[str],
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
                type=list[str],
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
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_WHITE_BG_MAX_BRIGHTNESS",
                value=0.7,
                help="白底文字最高亮度阈值，超过这个值的字体颜色会被调暗以确保清晰可见",
                type=float,
            ),
            RegisterConfig(
                module="word_clouds",
                key="WORD_CLOUDS_BLACK_BG_MIN_BRIGHTNESS",
                value=0.3,
                help="黑底文字最低亮度阈值，低于这个值的字体颜色会被调亮以确保清晰可见",
                type=float,
            ),
        ],
    ).to_dict(),
)
