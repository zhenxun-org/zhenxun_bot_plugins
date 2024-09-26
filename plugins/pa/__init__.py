import os
from pathlib import Path
import random
import shutil

from nonebot import on_regex
from nonebot.plugin import PluginMetadata
from nonebot_plugin_session import EventSession

from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.services.plugin_service import PluginService
from zhenxun.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="给我爬",
    description="给我爬吧表情包",
    usage="""
    爬爬爬爬爬爬
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1").dict(),
)

RESOUCE_PATH = IMAGE_PATH / "pa"

_matcher = on_regex(r".{0,3}爬.{0,3}", priority=5, block=True)


@_matcher.handle()
async def _(session: EventSession):
    if not RESOUCE_PATH.exists():
        await MessageUtils.build_message("爬不出去了...").finish()
    file_list = os.listdir(RESOUCE_PATH)
    if not file_list:
        await MessageUtils.build_message("爬不出去了...").finish()
    file = random.choice(file_list)
    await MessageUtils.build_message(RESOUCE_PATH / file).send()
    logger.info("触发爬爬爬爬爬", "给我爬", session=session)


class PluginInit(PluginService):
    async def install(self):
        res = Path(__file__).parent / "pa"
        if res.exists():
            if RESOUCE_PATH.exists():
                shutil.rmtree(RESOUCE_PATH)
            shutil.move(res, RESOUCE_PATH)
            logger.info(f"移动 爬 资源文件夹成功 {res} -> {RESOUCE_PATH}")
