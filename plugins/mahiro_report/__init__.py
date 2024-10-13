import shutil
from pathlib import Path

from nonebot.plugin import PluginMetadata
from nonebot_plugin_session import EventSession
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna

from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.plugin_init import PluginInit
from zhenxun.configs.path_config import TEMPLATE_PATH

from .data_source import Report

__plugin_meta__ = PluginMetadata(
    name="真寻日报",
    description="嗨嗨，这里是小记者真寻哦",
    usage="""
    指令：
        真寻日报
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1").dict(),
)


RESOURCE_PATH = TEMPLATE_PATH / "mahiro_report"

_matcher = on_alconna(Alconna("真寻日报"), priority=5, block=True, use_origin=True)


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    await MessageUtils.build_message(await Report.get_report_image()).send()
    logger.info("查看真寻日报", arparma.header_result, session=session)


class MyPluginInit(PluginInit):
    async def install(self):
        res = Path(__file__).parent / "mahiro_report"
        if res.exists():
            if RESOURCE_PATH.exists():
                shutil.rmtree(RESOURCE_PATH)
            shutil.move(res, RESOURCE_PATH)
            logger.info(f"移动 真寻日报 资源文件夹成功 {res} -> {RESOURCE_PATH}")

    async def remove(self):
        if RESOURCE_PATH.exists():
            shutil.rmtree(RESOURCE_PATH)
            logger.info(f"删除 真寻日报 资源文件夹成功 {RESOURCE_PATH}")
