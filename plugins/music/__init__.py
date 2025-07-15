from pathlib import Path
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, on_alconna
from nonebot_plugin_htmlrender import template_to_pic
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.utils import (
    AICallableParam,
    AICallableProperties,
    AICallableTag,
    Command,
    PluginExtraData,
    RegisterConfig,
)
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .model_ncm import MusicHelper163, MusicMetaData

_matcher = on_alconna(
    Alconna("点歌", Args["name?", str] / "\n"), priority=5, block=True
)


@_matcher.handle()
async def handle_first_receive(name: Match[str]):
    if name.available:
        _matcher.set_path_arg("name", name.result)


@_matcher.got_path("name", prompt="歌名是？")
async def call_music(session: Uninfo, arparma: Arparma, name: str):
    meta_data = await MusicHelper163.meta_data(name)
    if not meta_data:
        await MessageUtils.build_message("没有找到这首歌！").finish(reply_to=True)

    if Config.get_config("music", "type") == "zhenxun":
        await build_zhenxun(meta_data)
    else:
        await build_normal(meta_data)
    logger.info(f"点歌 :{name}", arparma.header_result, session=session)


async def build_zhenxun(meta_data: MusicMetaData):
    data = {
        "self_nickname": BotConfig.self_nickname,
        **dict(meta_data),
    }
    result = await template_to_pic(
        template_path=str((Path(__file__).parent / "templates").absolute()),
        template_name="info.html",
        templates={"data": data},
        pages={
            "viewport": {"width": 600, "height": 220},
            "base_url": f"file://{Path(__file__).parent}",
        },
        wait=2,
    )
    message = [
        result,
        meta_data.url,
    ]
    await MessageUtils.build_message(message).send()


async def build_normal(meta_data: MusicMetaData):
    await _matcher.send(MessageSegment.music(meta_data.type_, int(meta_data.id)))


__plugin_meta__ = PluginMetadata(
    name="点歌",
    description="为你点播了一首简单的歌",
    usage="""
    在线点歌
    指令：
        点歌 [歌名]
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="1.0",
        commands=[Command(command="点歌 [歌名]")],
        configs=[
            RegisterConfig(
                key="type",
                value="zhenxun",
                help="显示样式，normal, zhenxun",
                default_value="zhenxun",
            )
        ],
        smart_tools=[
            AICallableTag(
                name="call_music",
                description="如果你想为某人点歌，调用此方法",
                parameters=AICallableParam(
                    type="object",
                    properties={
                        "name": AICallableProperties(
                            type="string", description="用户想要听的歌曲名称"
                        ),
                    },
                    required=["name"],
                ),
                func=call_music,
            )
        ],
    ).to_dict(),
)
