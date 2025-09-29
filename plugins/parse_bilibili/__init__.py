import traceback
import asyncio
from typing import Optional, Any
from nonebot import on_message, get_driver
from nonebot.plugin import PluginMetadata
from bilibili_api import session as bili_session

from nonebot.adapters import Bot, Event

from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_session import EventSession
from nonebot_plugin_alconna import UniMsg, UniMessage, Text, Image

from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType

from zhenxun.utils.common_utils import CommonUtils
from zhenxun.configs.utils import Task, RegisterConfig, PluginExtraData

from .config import (
    base_config,
    MODULE_NAME,
    load_credential_from_file,
    check_and_refresh_credential,
)
from .services.network_service import ParserService
from .services.cache_service import CacheService
from .services.utility_service import AutoDownloadManager
from .utils.message import (
    MessageBuilder,
    render_video_info_to_image,
    render_season_info_to_image,
)
from .utils.exceptions import (
    UrlParseError,
    UnsupportedUrlError,
    ResourceNotFoundError,
)
from .model import VideoInfo, LiveInfo, ArticleInfo, SeasonInfo, UserInfo
from .utils.url_parser import UrlParserRegistry, extract_bilibili_url_from_message
from .utils.exceptions import BilibiliBaseException

from .services.download_manager import DownloadTask, download_manager
from .commands import (
    login_matcher,
    bili_download_matcher,
    auto_download_matcher,
    bili_cover_matcher,
)
from .commands.login import credential_status_matcher

_ = (  # type: ignore
    login_matcher,
    bili_download_matcher,
    auto_download_matcher,
    bili_cover_matcher,
    credential_status_matcher,
)


async def _handle_auto_download(bot: Bot, event: Event, video_info: VideoInfo):
    """处理自动下载请求"""
    session_id = event.get_session_id()
    logger.info(f"为会话 {session_id} 触发自动下载: {video_info.title}")

    task = DownloadTask(bot=bot, event=event, info_model=video_info, is_manual=False)
    await download_manager.add_task(task)


async def _initialize_services():
    await CacheService.initialize()
    await AutoDownloadManager.load_config()
    await load_credential_from_file()
    download_manager.initialize()

    asyncio.create_task(check_and_refresh_credential())


driver = get_driver()


@driver.on_startup
async def _startup():
    await _initialize_services()


@driver.on_shutdown
async def _shutdown():
    await bili_session.close()  # type: ignore


__plugin_meta__ = PluginMetadata(
    name="B站内容解析",
    description="B站内容解析（视频、直播、专栏/动态、番剧），支持被动解析、命令下载和自动下载。",
    usage="""
### 插件功能

**1. 被动解析**

> 自动监听消息中的 B 站链接，并发送解析结果。

- **支持类型**: 视频(av/BV)、直播、专栏(cv)、动态(t.bili/opus)、番剧/影视(ss/ep)、用户空间(space)。
- **智能识别**: 支持短链(b23.tv)及小程序/JSON卡片（需在配置中开启）。
- **防刷屏**: 默认5分钟内同一链接在同一会话中不重复解析（可通过 `CACHE_TTL` 配置修改）。
- **开关控制**:
    - 命令: `开启群被动b站解析` / `关闭群被动b站解析`
    - WebUI: 在bot后台的「群组」->「群功能」中修改「b站解析」状态。

**2. 手动视频下载**

- **命令**: `bili下载 [链接/ID]` (别名: `b站下载`)

> 用于下载 B 站视频。支持视频链接、av/BV号、或引用包含视频链接的消息/卡片。

- **功能**:
    - 下载过程中会发送进度提示。
    - 支持视频缓存，重复下载会直接发送缓存文件。
    - 可通过 `VIDEO_DOWNLOAD_QUALITY` 配置项设置下载画质。

**3. 获取封面**

- **命令**: `bili封面` (别名: `b站封面`)

> 获取 B 站视频或番剧的原始封面图片。

- **使用方式**: 必须通过**引用**包含 B 站视频(av/BV)或番剧(ss/ep)链接的消息来触发。

**4. 自动下载控制 (需要**管理员**权限)**

- **命令**: 
    - `bili自动下载 on`: 为当前群聊开启视频自动下载。
    - `bili自动下载 off`: 为当前群聊关闭视频自动下载。

> 开启后，被动解析到视频链接时，会自动下载并发送视频文件。

**5. B站账号登录 (仅限**超级用户**)**

- **命令**: `bili登录`

> 生成二维码进行 B 站账号登录，以解析需要登录才能查看的内容和获取更高清晰度的视频。支持凭证自动刷新。

**6. B站账号状态查询 (仅限**超级用户**)**

- **命令**: `bili状态`

> 查询当前 B 站账号的登录凭证状态，如是否有效、是否需要刷新等。
    """.strip(),
    extra=PluginExtraData(
        author="leekooyo (Refactored by Assistant)",
        version="1.5.1",
        plugin_type=PluginType.DEPENDANT,
        menu_type="其他",
        configs=[
            RegisterConfig(
                module=MODULE_NAME,
                key="PROXY",
                value=None,
                default_value=None,
                help="下载代理",
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="CACHE_TTL",
                value=5,
                default_value=5,
                help="被动解析缓存时间（分钟），同一链接在此时间内同一会话不重复解析，设为0关闭缓存",
                type=int,
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="ENABLE_MINIAPP_PARSE",
                value=True,
                default_value=True,
                help="是否在被动解析中解析QQ小程序/JSON卡片中的B站链接（不影响 bili解析 命令）",
                type=bool,
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="RENDER_AS_IMAGE",
                value=True,
                default_value=True,
                help="是否将被动解析结果渲染成图片发送",
                type=bool,
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="CACHE_CLEAN_INTERVAL_HOURS",
                value=24,
                default_value=24,
                help="缓存清理间隔（小时），控制所有类型缓存的清理间隔",
                type=int,
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="AUTO_DOWNLOAD_MAX_DURATION",
                value=10,
                default_value=10,
                help="自动下载最大时长(分钟), 超过此值不下载，设为0关闭时长限制",
                type=int,
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="MANUAL_DOWNLOAD_MAX_DURATION",
                value=20,
                default_value=20,
                help="手动下载最大时长(分钟), 超过此值不下载，设为0关闭时长限制，超级用户不受影响",
                type=int,
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="CACHE_EXPIRY_DAYS",
                value=7,
                default_value=7,
                help="缓存过期时间(天), 临时文件默认1天, 视频缓存默认7天",
                type=int,
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="MAX_VIDEO_CACHE_SIZE_MB",
                value=1024,
                default_value=1024,
                help="视频缓存最大大小(MB), 超过此大小自动清理最旧的缓存",
                type=int,
            ),
            RegisterConfig(
                module=MODULE_NAME,
                key="VIDEO_DOWNLOAD_QUALITY",
                value=64,
                default_value=64,
                help="视频下载质量(16=360P, 32=480P, 64=720P, 80=1080P)",
                type=int,
            ),
            RegisterConfig(
                module="BiliBili",
                key="COOKIES",
                value="",
                default_value="",
                help="B站cookies数据，由系统自动管理，请勿手动修改",
            ),
        ],
        tasks=[Task(module="parse_bilibili", name="b站解析")],
    ).dict(),
)


async def _rule(uninfo: Uninfo, message: UniMsg) -> bool:
    plain_text = message.extract_plain_text().strip()
    if await CommonUtils.task_is_block(uninfo, "parse_bilibili"):
        return False
    if plain_text.startswith(("bili下载", "b站下载")):
        logger.debug("消息被识别为 bili下载 命令，被动解析跳过", "B站解析")
        return False

    plain_text = message.extract_plain_text().strip()
    if (
        plain_text.startswith("bili下载")
        or plain_text.startswith("b站下载")
        or plain_text.startswith("bili封面")
        or plain_text.startswith("b站封面")
    ):
        logger.debug(f"消息文本以命令开头，被动解析跳过: {plain_text}", "B站解析")
        return False

    check_hyper = base_config.get("ENABLE_MINIAPP_PARSE", True)
    if not check_hyper:
        logger.debug("小程序/卡片解析已禁用，跳过 Hyper 检查", "B站解析")

    url = extract_bilibili_url_from_message(message, check_hyper=check_hyper)

    if url:
        logger.debug(f"从消息中提取到B站URL: {url}", "B站解析")
        return True

    plain_text_for_check = message.extract_plain_text().strip()
    if plain_text_for_check:
        logger.debug(f"检查文本内容: '{plain_text_for_check[:100]}...'", "B站解析")
        parser_found = UrlParserRegistry.get_parser(plain_text_for_check)
        if (
            parser_found
            and parser_found.__name__ == "PureVideoIdParser"
            and hasattr(parser_found, "PATTERN")
        ):
            if parser_found.PATTERN.fullmatch(plain_text_for_check):  # type: ignore
                logger.debug("文本内容匹配到纯视频ID，符合规则", "B站解析")
                return True

    logger.debug("消息不符合被动解析规则", "B站解析")
    return False


async def _build_video_message(
    video_info: VideoInfo, render_enabled: bool
) -> Optional[UniMsg]:
    if render_enabled:
        logger.debug(
            f"渲染视频消息 (style_blue): {video_info.title} (BV: {video_info.bvid})",
            "B站解析",
        )
        try:
            image_bytes = await render_video_info_to_image(video_info)
            if image_bytes:
                return UniMessage(
                    [Image(raw=image_bytes), Text(f"链接: {video_info.parsed_url}")]
                )
            else:
                logger.warning("VideoInfo 渲染函数返回空，尝试原始消息", "B站解析")
                return await MessageBuilder.build_video_message(video_info)
        except Exception as render_err:
            logger.error("渲染失败，将使用原始消息", "B站解析", e=render_err)
            return await MessageBuilder.build_video_message(video_info)
    else:
        logger.debug(
            f"构建视频消息: {video_info.title} (BV: {video_info.bvid})",
            "B站解析",
        )
        return await MessageBuilder.build_video_message(video_info)


async def _build_live_message(live_info: LiveInfo, render_enabled: bool) -> UniMsg:
    if render_enabled:
        logger.warning("LiveInfo 渲染暂未实现，将发送原始消息", "B站解析")

    logger.debug(
        f"构建直播间消息: {live_info.title} (Room: {live_info.room_id})",
        "B站解析",
    )
    return await MessageBuilder.build_live_message(live_info)


async def _build_article_message(
    article_info: ArticleInfo, render_enabled: bool
) -> Optional[UniMsg]:
    logger.debug(
        f"构建文章/动态消息: {article_info.type} {article_info.id}, 渲染模式: {render_enabled}",
        "B站解析",
    )
    article_message = await MessageBuilder.build_article_message(
        article_info, render_enabled=render_enabled
    )

    if article_message and article_info.url:
        image_segment: Image | None = None
        for seg in article_message:
            if isinstance(seg, Image):
                image_segment = seg
                break

        if image_segment:
            return UniMessage([image_segment, Text(f"\n链接: {article_info.url}")])
        else:
            return article_message
    else:
        return article_message


async def _build_season_message(
    season_info: SeasonInfo, render_enabled: bool
) -> Optional[UniMsg]:
    if render_enabled:
        logger.debug(f"渲染番剧消息 (style_blue): {season_info.title}", "B站解析")
        try:
            image_bytes = await render_season_info_to_image(season_info)
            if image_bytes:
                return UniMessage(
                    [Image(raw=image_bytes), Text(f"\n链接: {season_info.parsed_url}")]
                )
            else:
                logger.warning("SeasonInfo 渲染函数返回空，尝试原始消息", "B站解析")
                return await MessageBuilder.build_season_message(season_info)
        except Exception as render_err:
            logger.error("渲染失败，将使用原始消息", "B站解析", e=render_err)
            return await MessageBuilder.build_season_message(season_info)
    else:
        logger.debug(f"构建番剧消息: {season_info.title}", "B站解析")
        return await MessageBuilder.build_season_message(season_info)


async def _build_user_message(
    user_info: UserInfo, render_enabled: bool
) -> Optional[UniMsg]:
    if render_enabled:
        logger.warning("UserInfo 渲染暂未实现，将发送原始消息", "B站解析")
        return await MessageBuilder.build_user_message(user_info)
    else:
        logger.debug(
            f"构建用户消息: {user_info.name} (Mid: {user_info.mid})", "B站解析"
        )
        return await MessageBuilder.build_user_message(user_info)


async def _build_message_for_content(
    content: Any, render_enabled: bool
) -> Optional[UniMsg]:
    """根据解析内容的类型，分发到相应的消息构建函数"""
    build_mapping = {
        VideoInfo: _build_video_message,
        LiveInfo: _build_live_message,
        ArticleInfo: _build_article_message,
        SeasonInfo: _build_season_message,
        UserInfo: _build_user_message,
    }

    for content_type, builder_func in build_mapping.items():
        if isinstance(content, content_type):
            type_name = content_type.__name__.replace("Info", "").upper()
            if base_config.get(f"ENABLE_{type_name}_PARSE", True):
                return await builder_func(content, render_enabled)
            else:
                logger.warning(f"{type_name} 解析已在配置中禁用，跳过消息构建。")
                return None

    logger.warning(f"内容类型 {type(content).__name__} 没有匹配的消息构建器或已禁用。")
    return None


_matcher = on_message(priority=50, block=False, rule=_rule)


@_matcher.handle()
async def _(
    bot: Bot,
    event: Event,
    session: EventSession,
    message: UniMsg,
):
    check_hyper = base_config.get("ENABLE_MINIAPP_PARSE", True)
    target_url = extract_bilibili_url_from_message(message, check_hyper=check_hyper)

    if not target_url:
        logger.debug("被动解析：在消息中未找到有效的B站URL/ID，退出处理。")  # type: ignore
        return

    if not await CacheService.should_parse_url(target_url, session):
        logger.debug(f"被动解析：URL在缓存中且TTL未过期，跳过: {target_url}")
        return

    try:
        logger.info(f"被动解析：开始解析URL: {target_url}", session=session)
        parsed_content = await ParserService.parse(target_url)

        if not parsed_content:
            return

        render_enabled = base_config.get("RENDER_AS_IMAGE", True)
        final_message = await _build_message_for_content(parsed_content, render_enabled)

        if final_message:
            await final_message.send()  # type: ignore
            await CacheService.add_url_to_cache(target_url, session)
            logger.info(f"被动解析：成功解析并发送: {target_url}", session=session)

            if isinstance(
                parsed_content, VideoInfo
            ) and await AutoDownloadManager.is_enabled(session):
                await _handle_auto_download(bot, event, parsed_content)
        else:
            logger.info(
                f"被动解析：最终消息为空或未构建 (URL: {target_url})", session=session
            )
            await CacheService.add_url_to_cache(target_url, session)

    except ResourceNotFoundError as e:
        logger.info(
            f"被动解析：资源不存在: {target_url}, 错误: {e.message}", session=session
        )
    except (UrlParseError, UnsupportedUrlError) as e:
        logger.warning(
            f"被动解析：URL解析失败: {target_url}. 原因: {e.message}", session=session
        )
    except BilibiliBaseException as e:
        logger.error(
            f"被动解析：API或处理错误: {target_url}. 类型: {type(e).__name__}, 原因: {e.message}",
            session=session,
        )
    except Exception as e:
        logger.error(
            f"被动解析：处理URL时发生意外错误: {target_url}", session=session, e=e
        )
        logger.error(traceback.format_exc())
