from nonebot import get_driver
from nonebot.plugin import PluginMetadata

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import PluginExtraData
from . import data_source, main

__all__ = ["data_source", "main"]

__plugin_meta__ = PluginMetadata(
    name="三角洲小助手",
    description=f"{BotConfig.self_nickname}帮你获取三角洲信息！",
    usage="指令：洲 / 粥",
    extra=PluginExtraData(author="The_elevenFD", version="0.2").to_dict(),
)

driver = get_driver()
delta_service = data_source.DeltaService()

@driver.on_startup
async def _():
    try:
        await delta_service._ensure_cookies()
    except Exception:
        pass

