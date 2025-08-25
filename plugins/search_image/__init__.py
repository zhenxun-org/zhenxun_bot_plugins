from pathlib import Path

from httpx import HTTPStatusError
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    At,
    Image,
    Match,
    UniMsg,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyMergeExtension
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_waiter import waiter

from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.depends import CheckConfig
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .saucenao import get_saucenao_image

__plugin_meta__ = PluginMetadata(
    name="识图",
    description="以图搜图，看破本源",
    usage="""
    识别图片 [二次元图片]
    指令：
        识图 [图片]
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        menu_type="一些工具",
        commands=[Command(command="识图 [图片]")],
        configs=[
            RegisterConfig(
                key="MAX_FIND_IMAGE_COUNT",
                value=3,
                help="搜索图片返回的最大数量",
                default_value=3,
                type=int,
            ),
            RegisterConfig(
                key="API_KEY",
                value=None,
                help="Saucenao的API_KEY，通过"
                " https://saucenao.com/user.php?page=search-api 注册获取",
            ),
        ],
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna("识图", Args["data?", [Image, At]]),
    block=True,
    priority=5,
    extensions=[ReplyMergeExtension()],
)


async def get_image_info(mod: str, url: str) -> str | list[str | Path] | None:
    if mod == "saucenao":
        return await get_saucenao_image(url)


async def get_image_data() -> str:
    @waiter(waits=["message"], keep_session=True)
    async def check(message: UniMsg):
        return message[Image]

    resp = await check.wait("请发送需要识别的图片！", timeout=60)
    if resp is None:
        await MessageUtils.build_message("等待超时...").finish()
    if not resp:
        await MessageUtils.build_message(
            "未获取需要操作的图片，请重新发送命令！"
        ).finish()
    if not resp[0].url:
        await MessageUtils.build_message("获取图片失败，请重新发送命令！").finish()
    return resp[0].url


@_matcher.handle(parameterless=[CheckConfig(config="API_KEY")])
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    data: Match[Image | At],
):
    image_url = None
    group_id = session.group.id if session.group else None
    if data.available:
        if isinstance(data.result, At):
            if not session.user.avatar:
                await MessageUtils.build_message("没拿到图图,请找管理员吧").finish()
            platform = PlatformUtils.get_platform(session)
            image_url = PlatformUtils.get_user_avatar_url(
                data.result.target, platform, session.self_id
            )
        else:
            image_url = data.result.url
    if not image_url:
        image_url = await get_image_data()
    if not image_url:
        await MessageUtils.build_message("获取图片链接失败...").finish(reply_to=True)
    await MessageUtils.build_message("开始处理图片...").send()
    info_list = None
    try:
        info_list = await get_image_info("saucenao", image_url)
    except HTTPStatusError as e:
        logger.error("识图请求失败", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message(
            f"请求失败了哦，code: {e.response.status_code}"
        ).send(reply_to=True)
    except Exception as e:
        logger.error("识图请求失败", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("请求失败了哦，请稍后再试~").send(
            reply_to=True
        )
        return
    if isinstance(info_list, str):
        await MessageUtils.build_message(info_list).finish(at_sender=True)
    if not info_list:
        await MessageUtils.build_message("未查询到...").finish()
    platform = PlatformUtils.get_platform(bot)
    if PlatformUtils.is_forward_merge_supported(session) and group_id:
        forward = MessageUtils.template2forward(info_list[1:], bot.self_id)  # type: ignore
        await bot.send_group_forward_msg(
            group_id=int(group_id),
            messages=forward,  # type: ignore
        )
    else:
        for info in info_list[1:]:
            await MessageUtils.build_message(info).send()
    logger.info(f" 识图: {image_url}", arparma.header_result, session=session)
