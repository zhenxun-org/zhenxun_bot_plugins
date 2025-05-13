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
    Query,
    UniMsg,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyMergeExtension
from nonebot_plugin_alconna.uniseg.tools import image_fetch
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_waiter import waiter

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import Command, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .data_source import AnimeManage

__plugin_meta__ = PluginMetadata(
    name="角色识别",
    description="动漫以及gal游戏的角色识别",
    usage="""
    指令：
        角色识别 ?[-t [1, 2, 3, 4](识别类型，默认2)] [图片]

        1: 高级动画识别模型①
        2: 高级动画识别模型②（默认）
        3: 普通动画识别模型
        4: 高级Gal识别模型

        示例:
            角色识别 [图片]
            角色识别 -t 1 [图片]
            角色识别 @user
            [引用消息] 角色识别
            [引用消息] 角色识别 -t 2

    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.3",
        menu_type="一些工具",
        commands=[
            Command(command="角色识别 ?[-t [1, 2, 3, 4](识别类型，默认2)] [图片]")
        ],
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna(
        "角色识别",
        Args["data?", Image | At],
        Option("-t|--type", Args["search_type", int], help_text="识别类型"),
    ),
    block=True,
    priority=5,
    extensions=[ReplyMergeExtension()],
)


async def get_image_data() -> bytes:
    @waiter(waits=["message"], keep_session=True)
    async def check(message: UniMsg):
        return message.get(Image, 1)

    await MessageUtils.build_message("请发送需要识别的角色图片！").send()
    resp = await check.wait(timeout=60)
    if resp is None:
        await MessageUtils.build_message("等待超时...").finish()
    if not resp:
        await MessageUtils.build_message(
            "未获取需要识别的图片，请重新发送命令！"
        ).finish()
    return await AsyncHttpx.get_content(resp[0].url)


@_matcher.handle()
async def _(
    bot: Bot,
    event: Event,
    state: T_State,
    data: Match[Image | At],
    arparma: Arparma,
    session: Uninfo,
    search_type: Query[int] = Query("search_type", 2),
):
    if search_type.result not in [1, 2, 3, 4]:
        await MessageUtils.build_message("识别类型错误，请输入1-4...").finish()

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
    await MessageUtils.build_message("开始识别了哦，请稍等...").send()
    try:
        result_list, image, file = await AnimeManage.search(
            image_data, search_type.result
        )
    except HTTPStatusError as e:
        logger.error(
            f"识别请求失败 code: {e.response.status_code}",
            arparma.header_result,
            session=session,
            e=e,
        )
        return await MessageUtils.build_message(
            f"识别请求失败 code: {e.response.status_code}"
        ).send()
    except Exception as e:
        logger.error("角色识别错误", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("识别失败，请稍后再试...").finish()
    if not file or isinstance(result_list, str):
        await MessageUtils.build_message(str(result_list)).finish()
    await MessageUtils.build_message(image).send()
    if PlatformUtils.is_forward_merge_supported(session):
        # 非qq时不发送消息避免刷屏
        await MessageUtils.alc_forward_msg(
            [[file], *result_list], session.self_id, BotConfig.self_nickname
        ).send()
    logger.info("角色识别", arparma.header_result, session=session)
