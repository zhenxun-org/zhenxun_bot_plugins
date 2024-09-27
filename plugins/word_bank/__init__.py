from pathlib import Path

import nonebot
from nonebot.plugin import PluginMetadata

from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.utils.enum import PluginType

__plugin_meta__ = PluginMetadata(
    name="词库",
    description="",
    usage="",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.5-ea238a0",
        plugin_type=PluginType.PARENT,
        configs=[
            RegisterConfig(
                key="WORD_BANK_LEVEL",
                value=5,
                default_value=5,
                type=int,
                help="设置增删词库的权限等级",
            )
        ],
    ).dict(),
)

nonebot.load_plugins(str(Path(__file__).parent.resolve()))
