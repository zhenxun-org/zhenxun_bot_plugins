from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_uninfo import Uninfo
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna.uniseg.tools import image_fetch
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyMergeExtension
from nonebot_plugin_alconna import (
    Args,
    At,
    Image,
    Match,
    Query,
    Option,
    Alconna,
    Arparma,
    on_alconna,
)

from zhenxun.services.log import logger
from zhenxun.configs.config import BotConfig
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.configs.utils import PluginExtraData

from .data_source import AnimeManage

__plugin_meta__ = PluginMetadata(
    name="角色识别",
    description="动漫以及gal游戏的角色识别",
    usage="""
    指令：
        角色识别 ?[-t [1, 2, 3, 4, 5](识别类型，默认1)] [图片]

        1: 高级动画识别模型①（默认）
        2: 高级动画识别模型②
        3: 普通动画识别模型
        4: 普通Gal识别模型
        5: 高级Gal识别模型

        示例:
            角色识别 [图片]
            角色识别 -t 1 [图片]
            角色识别 @user
            [引用消息] 角色识别
            [引用消息] 角色识别 -t 2

    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1", menu_type="一些工具"
    ).dict(),
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


@_matcher.handle()
async def _(
    data: Match[Image | At],
    search_type: Query[int] = Query("search_type", 1),
):
    if data.available:
        _matcher.set_path_arg("data", data.result)
    if search_type.result not in [1, 2, 3, 4, 5]:
        await MessageUtils.build_message("识别类型错误，请输入1-5...").finish()
    _matcher.set_path_arg("search_type", search_type.result)


@_matcher.got_path("data", prompt="图来！")
async def _(
    bot: Bot,
    event: Event,
    state: T_State,
    session: Uninfo,
    arparma: Arparma,
    data: Image | At,
    search_type: int,
):
    image_data = None
    if isinstance(data, At):
        if session.user.avatar:
            platform = PlatformUtils.get_platform(session)
            image_data = await PlatformUtils.get_user_avatar(
                data.target, platform, session.self_id
            )
    else:
        image_data = await image_fetch(event, bot, state, data)
    if not image_data:
        await MessageUtils.build_message("图片获取失败...").finish()
    await MessageUtils.build_message("开始识别了哦，请稍等...").send()
    try:
        result_list, file = await AnimeManage.search(image_data, search_type)
    except Exception as e:
        logger.error("角色识别错误", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("识别失败，请稍后再试...").finish()
    if not file or isinstance(result_list, str):
        await MessageUtils.build_message(str(result_list)).finish()
    if PlatformUtils.get_platform(session) == "qq":
        await MessageUtils.alc_forward_msg(
            [[file], *result_list], session.self_id, BotConfig.self_nickname
        ).send()
    else:
        await MessageUtils.build_message(file).send()
        for result in result_list:
            await MessageUtils.build_message(result).send()
    logger.info("角色识别", arparma.header_result, session=session)
