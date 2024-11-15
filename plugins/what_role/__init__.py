from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Image,
    Match,
    Option,
    Query,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

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

    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1", menu_type="一些工具"
    ).dict(),
)


_matcher = on_alconna(
    Alconna(
        "角色识别",
        Args["image?", Image],
        Option("-t|--type", Args["search_type", int], help_text="识别类型"),
    ),
    block=True,
    priority=5,
)


@_matcher.handle()
async def _(image: Match[Image], search_type: Query[int] = Query("search_type", 1)):
    if image.available:
        _matcher.set_path_arg("image", image.result)
    if search_type.result not in [1, 2, 3, 4, 5]:
        await MessageUtils.build_message("识别类型错误，请输入1-5...").finish()
    _matcher.set_path_arg("search_type", search_type.result)


@_matcher.got_path("image", prompt="图来！")
async def _(
    session: Uninfo,
    arparma: Arparma,
    image: Image,
    search_type: int,
):
    if not image.url:
        await MessageUtils.build_message("图片url为空...").finish()
    await MessageUtils.build_message("开始识别了哦，请稍等...").send()
    try:
        result_list, file = await AnimeManage.search(image.url, search_type)
    except Exception as e:
        logger.error("角色识别错误", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("识别失败，请稍后再试...").finish()
    if not file:
        await MessageUtils.build_message(str(result_list)).finish()
    if PlatformUtils.get_platform(session) == "qq":
        await MessageUtils.alc_forward_msg(
            [[file], result_list], session.self_id, BotConfig.self_nickname
        ).send()
    else:
        await MessageUtils.build_message(file).send()
        for result in result_list:
            await MessageUtils.build_message(result).send()
    logger.info("角色识别", arparma.header_result, session=session)
