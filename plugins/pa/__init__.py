import os
from pathlib import Path
import random
import shutil

from nonebot import on_regex
from nonebot.plugin import PluginMetadata
from nonebot_plugin_session import EventSession

from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.configs.utils import Command, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.services.plugin_init import PluginInit
from zhenxun.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="爬爬爬",
    description="给我爬吧表情包",
    usage="""
    爬爬爬爬爬爬爬
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1", commands=[Command(command="爬")]
    ).to_dict(),
)

RESOURCE_PATH = IMAGE_PATH / "pa"

_matcher = on_regex(r".{0,3}爬.{0,3}", priority=5, block=True)


@_matcher.handle()
async def _(session: EventSession):
    if not RESOURCE_PATH.exists():
        await MessageUtils.build_message("爬不出去了...").finish()
    file_list = os.listdir(RESOURCE_PATH)
    if not file_list:
        await MessageUtils.build_message("爬不出去了...").finish()
    file = random.choice(file_list)
    await MessageUtils.build_message(RESOURCE_PATH / file).send()
    logger.info("触发爬爬爬爬爬", "给我爬", session=session)


class MyPluginInit(PluginInit):
    async def install(self):
        res = Path(__file__).parent / "pa"
        if res.exists():
            if RESOURCE_PATH.exists():
                shutil.rmtree(RESOURCE_PATH)
            shutil.move(res, RESOURCE_PATH)
            logger.info(f"移动 爬 资源文件夹成功 {res} -> {RESOURCE_PATH}")

    async def remove(self):
        if RESOURCE_PATH.exists():
            shutil.rmtree(RESOURCE_PATH)
            logger.info(f"删除 爬 资源文件夹成功 {RESOURCE_PATH}")
