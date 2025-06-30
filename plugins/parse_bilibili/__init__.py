import asyncio
import traceback

from nonebot import get_driver, on_message
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Image, UniMessage, UniMsg
from nonebot_plugin_session import EventSession
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData, RegisterConfig, Task
from zhenxun.services.log import logger
from zhenxun.utils.common_utils import CommonUtils
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

from .commands import (
    _perform_video_download,
    auto_download_matcher,
    bili_cover_matcher,
    bili_download_matcher,
    login_matcher,
)
from .commands.login import credential_status_matcher
from .config import (
    MODULE_NAME,
    base_config,
    check_and_refresh_credential,
    load_credential_from_file,
)
from .model import ArticleInfo, LiveInfo, SeasonInfo, UserInfo, VideoInfo
from .services.cache_service import CacheService
from .services.network_service import NetworkService, ParserService
from .services.utility_service import AutoDownloadManager
from .utils.exceptions import (
    BilibiliRequestError,
    BilibiliResponseError,
    ResourceNotFoundError,
    ScreenshotError,
    UnsupportedUrlError,
    UrlParseError,
)
from .utils.message import (
    MessageBuilder,
    render_season_info_to_image,
    render_video_info_to_image,
)
from .utils.url_parser import UrlParserRegistry, extract_bilibili_url_from_message

__all__ = [
    "auto_download_matcher",
    "bili_cover_matcher",
    "bili_download_matcher",
    "credential_status_matcher",
    "login_matcher",
]


async def _initialize_services():
    await CacheService.initialize()
    await NetworkService.get_session()
    await AutoDownloadManager.load_config()
    await load_credential_from_file()

    asyncio.create_task(check_and_refresh_credential())  # noqa: RUF006


driver = get_driver()


@driver.on_startup
async def _startup():
    await _initialize_services()


@driver.on_shutdown
async def _shutdown():
    await NetworkService.close_session()


__plugin_meta__ = PluginMetadata(
    name="B站内容解析",
    description="B站内容解析（视频、直播、专栏/动态、番剧），支持被动解析、命令下载和自动下载。",
    usage="""
    插件功能：
    1. 被动解析：自动监听消息中的 B 站链接，并发送解析结果（可配置渲染成图片）。
       - 支持视频(av/BV)、直播、专栏、动态、番剧/影视、用户空间。
       - 支持短链(b23.tv)、小程序/卡片（需开启）。
       - 默认配置下，5分钟内同一链接在同一会话不重复解析。
       - 开启方式：
         方式一：使用命令「开启群被动b站解析」或「关闭群被动b站解析」
         方式二：在bot的Webui页面的「群组」中修改群被动状态「b站解析」

    2. 手动视频下载命令：
       bili/b站下载 [链接/ID]  # 专门用于下载 B 站视频

       - 支持视频链接、av/BV号、引用包含链接的消息或卡片。
       - 命令执行过程中会发送提示信息，并在下载完成后发送视频文件。
       - 支持视频缓存功能，已下载过的视频会被缓存，再次下载时直接从缓存发送。
       - 可通过配置项 VIDEO_DOWNLOAD_QUALITY
            设置下载视频的质量(16=360P, 32=480P, 64=720P, 80=1080P)。

    3. 获取封面命令：
       bili/b站封面  # 获取B站视频/番剧的原始封面图片

       - 只能通过引用包含B站链接的消息来触发，不支持直接传入链接参数。
       - 支持视频(av/BV)和番剧(ss/ep)的封面获取。
       - 返回原始大小的封面图片，不受尺寸限制。

    4. 自动下载控制命令 (需要管理员权限):
       bili/b站自动下载 on    # 为当前群聊开启视频自动下载
       bili/b站自动下载 off   # 为当前群聊关闭视频自动下载
       - 开启后，当被动解析到视频链接时，会自动执行下载并发送视频文件。

    5. B站账号登录命令 (仅超级用户):
       bili登录  # 生成二维码进行B站账号登录

       - 登录后可以获取更多需要登录才能查看的内容和更高清晰度的视频。
       - 支持凭证自动刷新，保持登录状态长期有效。

    6. B站账号状态查询命令 (仅超级用户):
       bili状态  # 查询当前B站账号登录状态

       - 可以查看当前凭证的有效性和是否需要刷新等信息。
       - 显示sessdata等重要凭证的状态。
    """.strip(),
    extra=PluginExtraData(
        author="leekooyo (Refactored by Assistant)",
        version="1.4.5",
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
                help="是否在被动解析中解析QQ小程序/JSON卡片中的B站链接"
                "（不影响 bili解析 命令）",
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
                help="手动下载最大时长(分钟), 超过此值不下载，"
                "设为0关闭时长限制，超级用户不受影响",
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
    ).to_dict(),
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

    if url := extract_bilibili_url_from_message(message, check_hyper=check_hyper):
        logger.debug(f"从消息中提取到B站URL: {url}", "B站解析")
        return True

    if plain_text_for_check := message.extract_plain_text().strip():
        logger.debug(f"检查文本内容: '{plain_text_for_check[:100]}...'", "B站解析")
        parser_found = UrlParserRegistry.get_parser(plain_text_for_check)
        if (
            parser_found
            and parser_found.__name__ == "PureVideoIdParser"
            and parser_found.PATTERN.fullmatch(plain_text_for_check)  # type: ignore
        ):
            logger.debug("文本内容匹配到纯视频ID，符合规则", "B站解析")
            return True

    logger.debug("消息不符合被动解析规则", "B站解析")
    return False


async def _build_video_message(
    video_info: VideoInfo, render_enabled: bool
) -> UniMessage | None:
    if render_enabled:
        logger.debug(
            f"渲染视频消息 (style_blue): {video_info.title} (BV: {video_info.bvid})",
            "B站解析",
        )
        try:
            image_bytes = await render_video_info_to_image(video_info)
            if image_bytes:
                return MessageUtils.build_message(
                    [image_bytes, f"链接: {video_info.parsed_url}"]
                )
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
) -> UniMsg | None:
    logger.debug(
        f"构建文章/动态消息: {article_info.type} {article_info.id},"
        f" 渲染模式: {render_enabled}",
        "B站解析",
    )
    article_message = await MessageBuilder.build_article_message(
        article_info, render_enabled=render_enabled
    )

    if not article_message or not article_info.url:
        return article_message
    image_segment = next(
        (seg for seg in article_message if isinstance(seg, Image)), None
    )
    return (
        MessageUtils.build_message([image_segment, f"\n链接: {article_info.url}"])
        if image_segment
        else article_message
    )


async def _build_season_message(
    season_info: SeasonInfo, render_enabled: bool
) -> UniMsg | None:
    if render_enabled:
        logger.debug(f"渲染番剧消息 (style_blue): {season_info.title}", "B站解析")
        try:
            image_bytes = await render_season_info_to_image(season_info)
            if image_bytes:
                return MessageUtils.build_message(
                    [image_bytes, f"\n链接: {season_info.parsed_url}"]
                )
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
) -> UniMessage | None:
    if render_enabled:
        logger.warning("UserInfo 渲染暂未实现，将发送原始消息", "B站解析")
    else:
        logger.debug(
            f"构建用户消息: {user_info.name} (Mid: {user_info.mid})", "B站解析"
        )

    return await MessageBuilder.build_user_message(user_info)


_matcher = on_message(priority=50, block=False, rule=_rule)


@_matcher.handle()
async def _(
    bot: Bot,
    event: Event,
    session: EventSession,
    message: UniMsg,
):
    logger.debug(f"Handler received message: {message}", "B站解析")

    parsed_content: (
        VideoInfo | LiveInfo | ArticleInfo | SeasonInfo | UserInfo | None
    ) = None

    check_hyper = base_config.get("ENABLE_MINIAPP_PARSE", True)
    if not check_hyper:
        logger.debug("小程序/卡片解析已禁用，跳过 Hyper 检查", "B站解析")

    target_url = extract_bilibili_url_from_message(message, check_hyper=check_hyper)

    if not target_url:
        logger.debug("未在消息中找到有效的 B 站 URL/ID，退出处理", "B站解析")
        return

    should_parse = await CacheService.should_parse_url(target_url, session)
    logger.debug(
        f"缓存检查: '{target_url}' 在上下文 '{CacheService._get_context_key(session)}'"
        f" 中: should_parse = {should_parse}",
        "B站解析",
    )
    if not should_parse:
        logger.debug(f"URL在缓存中且TTL未过期，跳过解析: {target_url}", "B站解析")
        return

    try:
        logger.info(f"开始解析URL: {target_url}", "B站解析", session=session)

        parsed_content: (
            VideoInfo | LiveInfo | ArticleInfo | SeasonInfo | UserInfo | None
        ) = await ParserService.parse(target_url)
        logger.debug(f"解析结果类型: {type(parsed_content).__name__}", "B站解析")
    except ResourceNotFoundError as e:
        logger.info(
            f"资源不存在: {target_url}, 错误: {e}",
            "B站解析",
            session=session,
        )
        return

    except (UrlParseError, UnsupportedUrlError) as e:
        logger.warning(
            f"URL解析失败: {target_url}. 原因: {e}",
            "B站解析",
            session=session,
        )
        return

    except (BilibiliRequestError, BilibiliResponseError) as e:
        logger.error(
            f"API请求或响应错误: {target_url}. 类型: {type(e).__name__}, 原因: {e}",
            "B站解析",
            session=session,
        )
        return

    except ScreenshotError as e:
        logger.error(
            f"截图失败: {target_url}. 原因: {e}",
            "B站解析",
            session=session,
        )
        return

    except Exception as e:
        logger.error(
            f"处理URL时发生意外错误: {target_url}",
            "B站解析",
            session=session,
            e=e,
        )
        logger.error(traceback.format_exc())
        return

    if parsed_content:
        logger.debug(
            f"Building message for parsed content type:{type(parsed_content).__name__}",
            "B站解析",
        )
        try:
            final_message: UniMsg | None = None
            render_enabled = base_config.get("RENDER_AS_IMAGE", False)

            if isinstance(parsed_content, VideoInfo) and base_config.get(
                "ENABLE_VIDEO_PARSE", True
            ):
                final_message = await _build_video_message(
                    parsed_content, render_enabled
                )

            elif isinstance(parsed_content, LiveInfo) and base_config.get(
                "ENABLE_LIVE_PARSE", True
            ):
                final_message = await _build_live_message(
                    parsed_content, render_enabled
                )

            elif isinstance(parsed_content, ArticleInfo) and base_config.get(
                "ENABLE_ARTICLE_PARSE", True
            ):
                final_message = await _build_article_message(
                    parsed_content, render_enabled
                )

            elif isinstance(parsed_content, SeasonInfo):
                final_message = await _build_season_message(
                    parsed_content, render_enabled
                )

            elif isinstance(parsed_content, UserInfo) and base_config.get(
                "ENABLE_USER_PARSE", True
            ):
                final_message = await _build_user_message(
                    parsed_content, render_enabled
                )

            else:
                logger.warning(
                    f"内容类型不支持或已禁用: {type(parsed_content).__name__}",
                    "B站解析",
                )
                if isinstance(parsed_content, VideoInfo) and not base_config.get(
                    "ENABLE_VIDEO_PARSE", True
                ):
                    logger.warning("视频解析已在配置中禁用", "B站解析")
                elif isinstance(parsed_content, LiveInfo) and not base_config.get(
                    "ENABLE_LIVE_PARSE", True
                ):
                    logger.warning("直播间解析已在配置中禁用", "B站解析")
                elif isinstance(parsed_content, ArticleInfo) and not base_config.get(
                    "ENABLE_ARTICLE_PARSE", True
                ):
                    logger.warning("文章/动态解析已在配置中禁用", "B站解析")

                elif isinstance(parsed_content, UserInfo) and not base_config.get(
                    "ENABLE_USER_PARSE", True
                ):
                    logger.warning("用户空间解析已在配置中禁用", "B站解析")

            if final_message:
                logger.debug(f"准备发送最终消息: {final_message}", "B站解析")
                await final_message.send()
                await CacheService.add_url_to_cache(target_url, session)
                logger.info(
                    f"成功被动解析并发送: {target_url}", "B站解析", session=session
                )

                if isinstance(parsed_content, VideoInfo):
                    if await AutoDownloadManager.is_enabled(session):
                        logger.debug(
                            f"群组 {session.id2} 开启了自动下载，检查时长限制..."
                        )

                        max_duration_minutes = base_config.get(
                            "AUTO_DOWNLOAD_MAX_DURATION", 10
                        )
                        max_duration_seconds = max_duration_minutes * 60

                        video_duration_minutes = round(parsed_content.duration / 60, 1)

                        if (
                            max_duration_minutes > 0
                            and parsed_content.duration > max_duration_seconds
                        ):
                            logger.info(
                                f"视频时长 {video_duration_minutes}分钟 超过限制"
                                f" {max_duration_minutes}分钟，取消自动下载",
                                "B站解析",
                            )
                        else:
                            logger.info(
                                f"视频时长 {video_duration_minutes}分钟 "
                                "符合要求或限制已禁用，开始执行自动下载..."
                            )
                            try:
                                await _perform_video_download(
                                    bot, event, parsed_content
                                )
                            except Exception as download_e:
                                logger.error(
                                    "自动下载过程中发生错误", "B站解析", e=download_e
                                )
                    else:
                        logger.debug(f"群组 {session.id2} 未开启自动下载", "B站解析")

            else:
                logger.info(
                    f"最终消息为空或未构建 (被动解析): {target_url}",
                    "B站解析",
                    session=session,
                )
                await CacheService.add_url_to_cache(target_url, session)

        except Exception as e:
            logger.error(
                f"Error building or sending message for {target_url}: {e}",
                "B站解析",
                session=session,
            )
            logger.error(traceback.format_exc())
