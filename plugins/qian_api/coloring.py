from io import BytesIO

from httpx import HTTPStatusError
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    At,
    Image,
    Match,
    Option,
    on_alconna,
    store_true,
)
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyMergeExtension
from nonebot_plugin_alconna.uniseg.tools import image_fetch
from nonebot_plugin_uninfo import Uninfo
import ujson as json

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .data_source import get_image_data, parser

__plugin_meta__ = PluginMetadata(
    name="漫画上色",
    description="给图片或者漫画上色",
    usage="""
    指令：
        漫画上色 [图片/@]
        上色 [图片/@]
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1", menu_type="一些工具"
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna(
        "coloring",
        Args["data?", [Image, At]],
        Option("--comic", action=store_true, help_text="是否是漫画上色"),
    ),
    priority=5,
    block=True,
    extensions=[ReplyMergeExtension()],
)

_matcher.shortcut(
    r"上色",
    command="coloring",
    arguments=[],
    prefix=True,
)

_matcher.shortcut(
    r"漫画上色",
    command="coloring",
    arguments=["--comic"],
    prefix=True,
)


@_matcher.handle()
async def _(
    bot: Bot,
    event: Event,
    state: T_State,
    data: Match[Image | At],
    arparma: Arparma,
    session: Uninfo,
):
    image_data = None
    if data.available:
        if isinstance(data.result, At):
            if not session.user.avatar:
                await MessageUtils.build_message("没拿到图图,请找管理员吧").finish()
            platform = PlatformUtils.get_platform(session)
            image_data = await PlatformUtils.get_user_avatar(
                data.result.target, platform, session.self_id
            )
        else:
            image_data = await image_fetch(event, bot, state, data.result)
    if not image_data:
        image_data = await get_image_data()
    await MessageUtils.build_message("开始上色了哦，请稍等...").send()
    files = {"file": ("image.jpg", BytesIO(image_data), "image/jpeg")}
    try:
        if arparma.find("comic"):
            url = "https://api.3000y.ac.cn/v1/image-color"
        else:
            url = "https://api.3000y.ac.cn/v1/image-ddcolor"
        response = await AsyncHttpx.post(url, files=files)
        response.raise_for_status()
        image_url, result = parser(json.loads(response.text))
        if not image_url and result:
            await MessageUtils.build_message(result).send(reply_to=True)
        elif image_url:
            await MessageUtils.build_message(Image(url=image_url)).send(reply_to=True)
        else:
            await MessageUtils.build_message("上色失败...").send(reply_to=True)
    except HTTPStatusError as e:
        await MessageUtils.build_message(
            f"请求失败 code: {e.response.status_code}..."
        ).finish(reply_to=True)
    except Exception as e:
        logger.error("上色发生异常", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("发生了一些异常...").finish(reply_to=True)
