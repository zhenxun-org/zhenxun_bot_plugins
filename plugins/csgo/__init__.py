from pathlib import Path
import shutil

import nonebot

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import TEMPLATE_PATH
from zhenxun.services.log import logger
from zhenxun.services.plugin_init import PluginInit

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

RESOURCE_PATH = TEMPLATE_PATH / "csgo"


class MyPluginInit(PluginInit):
    async def install(self):
        res = Path(__file__).parent / "csgo"
        if res.exists():
            if RESOURCE_PATH.exists():
                shutil.rmtree(RESOURCE_PATH)
            shutil.move(res, RESOURCE_PATH)
            logger.info(f"移动 csgo 资源文件夹成功 {res} -> {RESOURCE_PATH}")

    async def remove(self):
        if RESOURCE_PATH.exists():
            shutil.rmtree(RESOURCE_PATH)
            logger.info(f"删除 csgo 资源文件夹成功 {RESOURCE_PATH}")
