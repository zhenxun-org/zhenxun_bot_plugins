from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.utils import Command, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .music_163 import get_song_id


def music(type_: str, id_: int) -> MessageSegment:
    return MessageSegment.music(type_, id_)


__plugin_meta__ = PluginMetadata(
    name="点歌",
    description="为你点播了一首简单的歌",
    usage="""
    在线点歌
    指令：
        点歌 [歌名]
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.2", commands=[Command(command="点歌 [歌名]")]
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("点歌", Args["name?", str] / "\n"), priority=5, block=True
)


@_matcher.handle()
async def handle_first_receive(name: Match[str]):
    if name.available:
        _matcher.set_path_arg("name", name.result)


@_matcher.got_path("name", prompt="歌名是？")
async def _(session: Uninfo, arparma: Arparma, name: str):
    song_id = await get_song_id(name)
    if not song_id:
        await MessageUtils.build_message("没有找到这首歌！").finish(reply_to=True)
    await _matcher.send(music("163", song_id))
    logger.info(f"点歌 :{name}", arparma.header_result, session=session)
