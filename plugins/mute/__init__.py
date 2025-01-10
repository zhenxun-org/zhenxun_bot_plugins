from pathlib import Path

import nonebot
from nonebot.plugin import PluginMetadata

from zhenxun.configs.utils import PluginExtraData
from zhenxun.utils.enum import PluginType

__plugin_meta__ = PluginMetadata(
    name="刷屏禁言检测",
    description="",
    usage="",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1-473ecd8",
        plugin_type=PluginType.PARENT,
    ).to_dict(),
)

nonebot.load_plugins(str(Path(__file__).parent.resolve()))
