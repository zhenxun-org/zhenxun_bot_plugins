import os
from pathlib import Path
import random
import shutil

from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Arparma, UniMessage, Voice, on_alconna
from nonebot_plugin_session import EventSession
import ujson as json

from zhenxun.configs.config import BotConfig
from zhenxun.configs.path_config import RECORD_PATH
from zhenxun.configs.utils import Command, PluginCdBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.services.plugin_init import PluginInit
from zhenxun.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="钉宫骂我",
    description="请狠狠的骂我一次！",
    usage="""
    多骂我一点，球球了
    指令：
        骂老子
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        commands=[Command(command=f"{BotConfig.self_nickname}骂我")],
        limits=[PluginCdBlock(cd=3, result="就...就算求我骂你也得慢慢来...")],
    ).to_dict(),
)

_matcher = on_alconna(Alconna("ma-wo"), priority=5, block=True, rule=to_me())

_matcher.shortcut(
    r".{0,5}骂.{0,5}(我|劳资|老子).{0,5}",
    command="ma-wo",
    arguments=[],
    prefix=True,
)

RESOURCE_PATH = RECORD_PATH / "dinggong"

text_data = {}


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    global text_data
    if not RESOURCE_PATH.exists():
        await MessageUtils.build_message("钉宫语音文件夹不存在...").finish()
    files = os.listdir(RESOURCE_PATH)
    if not files:
        await MessageUtils.build_message("钉宫语音文件夹为空...").finish()
    if not text_data:
        text_file = RESOURCE_PATH / "data.json"
        text_data = json.load(text_file.open("r", encoding="utf-8"))
    voice = random.choice(files)
    index = voice.split(".")[0]
    text = text_data.get(index, "")
    await UniMessage([Voice(raw=(RESOURCE_PATH / voice).read_bytes())]).send()
    if text:
        await MessageUtils.build_message(text).send()
    logger.info(f"发送钉宫骂人: {voice}", arparma.header_result, session=session)


class MyPluginInit(PluginInit):
    async def install(self):
        res = Path(__file__).parent / "dinggong"
        if res.exists():
            if RESOURCE_PATH.exists():
                shutil.rmtree(RESOURCE_PATH)
            shutil.move(res, RESOURCE_PATH)
            logger.info(f"移动 钉宫语音 资源文件夹成功 {res} -> {RESOURCE_PATH}")

    async def remove(self):
        if RESOURCE_PATH.exists():
            shutil.rmtree(RESOURCE_PATH)
            logger.info(f"删除 钉宫语音 资源文件夹成功 {RESOURCE_PATH}")
