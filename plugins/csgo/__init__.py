import nonebot
from pathlib import Path

from zhenxun.configs.config import Config

nonebot.load_plugins(str(Path(__file__).parent.resolve()))


Config.add_plugin_config(
    "csgo",
    "token",
    None,
    help="完美APP的token",
)

Config.add_plugin_config(
    "csgo",
    "token_steam_id",
    None,
    help="完美APP的token的steam_id",
)


Config.add_plugin_config(
    "csgo",
    "appversion",
    "3.6.0.185",
    help="完美APP的版本号",
)
