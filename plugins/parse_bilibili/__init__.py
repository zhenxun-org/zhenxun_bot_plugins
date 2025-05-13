import traceback
import ujson as json
from typing import Union, Optional
from nonebot import on_message, get_driver
from nonebot.plugin import PluginMetadata
from nonebot.params import RawCommand
from nonebot.adapters import Bot, Event

from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_session import EventSession
from nonebot_plugin_alconna import UniMsg, Text, Hyper, Image

from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType

from zhenxun.utils.common_utils import CommonUtils
from zhenxun.configs.utils import Task, RegisterConfig, PluginExtraData

from .config import base_config, MODULE_NAME, load_credential_from_file
from .services.parser_service import ParserService
from .services.cache import CacheService
from .services.file_cleaner import FileCleaner
from .services.network_service import NetworkService
from .services import auto_download_manager
from .utils.message import (
    MessageBuilder,
    render_video_info_to_image,
    render_season_info_to_image,
)
from .utils.exceptions import (
    UrlParseError,
    UnsupportedUrlError,
    BilibiliRequestError,
    BilibiliResponseError,
    ScreenshotError,
    ResourceNotFoundError,
)
from .model import VideoInfo, LiveInfo, ArticleInfo, SeasonInfo, UserInfo
from .utils.url_parsers import UrlParserRegistry

from .commands import _perform_video_download


async def _initialize_services():
    await CacheService.initialize()
    await FileCleaner.initialize()
    await NetworkService.get_session()
    await auto_download_manager.load_auto_download_config()
    await load_credential_from_file()


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
       - 支持视频(av/BV)、直播、专栏(cv)、动态(t.bili/opus)、番剧/影视(ss/ep)、用户空间(space)。
       - 支持短链(b23.tv)、小程序/卡片（需开启）。
       - 默认配置下，5分钟内同一链接在同一会话不重复解析。
       - 开启方式：
         方式一：使用命令「开启群被动b站解析」或「关闭群被动b站解析」
         方式二：在bot的Webui页面的「群组」中修改群被动状态「b站解析」

    2. 手动视频下载命令：
       bili/b站下载 [链接/ID]  # 专门用于下载 B 站视频

       - 支持视频链接、av/BV号、引用包含链接的消息或卡片。
       - 命令执行过程中会发送提示信息，并在下载完成后发送视频文件。

    3. 自动下载控制命令 (需要管理员权限):
       bili/b站自动下载 on    # 为当前群聊开启视频自动下载
       bili/b站自动下载 off   # 为当前群聊关闭视频自动下载
       - 开启后，当被动解析到视频链接时，会自动执行下载并发送视频文件。

    4. B站账号登录命令 (仅超级用户):
       bili/b站登录  # 生成二维码进行B站账号登录

       - 登录后可以获取更多需要登录才能查看的内容和更高清晰度的视频。
    """.strip(),
    extra=PluginExtraData(
        author="leekooyo (Refactored by Assistant)",
        version="1.2.0",
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
                key="FILE_CLEAN_INTERVAL",
                value=60,
                default_value=60,
                help="临时文件清理间隔（分钟）",
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
                key="VIDEO_FILE_EXPIRY_DAYS",
                value=1,
                default_value=1,
                help="视频文件过期时间(天), 超过此时间自动清理",
                type=int,
            ),
        ],
        tasks=[Task(module="parse_bilibili", name="b站解析")],
    ).dict(),
)


async def _rule(
    uninfo: Uninfo, message: UniMsg, cmd: tuple | None = RawCommand()
) -> bool:
    if await CommonUtils.task_is_block(uninfo, "parse_bilibili"):
        return False
    if cmd is not None and cmd and (cmd[0] == "bili下载" or cmd[0] == "b站下载"):
        logger.debug("消息被识别为 bili下载 命令，被动解析跳过", "B站解析")
        return False
    if (
        cmd is not None
        and cmd
        and (cmd[0] == "bili自动下载" or cmd[0] == "b站自动下载")
    ):
        logger.debug("消息被识别为 bili自动下载 命令，被动解析跳过", "B站解析")
        return False

    plain_text = message.extract_plain_text().strip()
    if (
        plain_text.startswith("bili下载")
        or plain_text.startswith("b站下载")
        or plain_text.startswith("bili自动下载")
        or plain_text.startswith("b站自动下载")
    ):
        logger.debug(f"消息文本以命令开头，被动解析跳过: {plain_text}", "B站解析")
        return False

    has_bilibili_content_in_hyper = False
    if base_config.get("ENABLE_MINIAPP_PARSE", True):
        for seg in message:
            if isinstance(seg, Hyper) and seg.raw:
                logger.debug(f"检查 Hyper 段: {seg.raw[:100]}...", "B站解析")
                try:
                    data = json.loads(seg.raw)
                    excluded_apps = [
                        "com.tencent.qun.invite",
                        "com.tencent.qqav.groupvideo",
                        "com.tencent.mobileqq.reading",
                        "com.tencent.weather",
                    ]
                    app_name = data.get("app") or data.get("meta", {}).get(
                        "detail_1", {}
                    ).get("appid")
                    if app_name in excluded_apps:
                        logger.debug(
                            f"Hyper 消息 app '{app_name}' 在排除列表，跳过", "B站解析"
                        )
                        continue

                    jump_url = (
                        data.get("meta", {}).get("news", {}).get("jumpUrl")
                        or data.get("meta", {}).get("detail_1", {}).get("qqdocurl")
                        or data.get("meta", {}).get("detail_1", {}).get("preview")
                    )
                    if (
                        jump_url
                        and isinstance(jump_url, str)
                        and ("bilibili.com" in jump_url or "b23.tv" in jump_url)
                    ):
                        has_bilibili_content_in_hyper = True
                        break
                except Exception:
                    logger.debug("解析 Hyper 失败，继续检查其他段", "B站解析")
                    pass
        if has_bilibili_content_in_hyper:
            logger.debug("Hyper 消息包含B站跳转链接，符合规则", "B站解析")
            return True
    else:
        logger.debug("小程序/卡片解析已禁用，跳过 Hyper 检查", "B站解析")

    plain_text_for_check = message.extract_plain_text().strip()
    if plain_text_for_check:
        logger.debug(f"检查文本内容: '{plain_text_for_check[:100]}...'", "B站解析")
        parser_found = UrlParserRegistry.get_parser(plain_text_for_check)
        if parser_found:
            if parser_found.PATTERN and parser_found.PATTERN.search(
                plain_text_for_check
            ):
                logger.debug(
                    f"文本内容匹配到 B 站模式 '{parser_found.__name__}'，符合规则",
                    "B站解析",
                )
                return True
            elif parser_found.__name__ == "PureVideoIdParser":
                if parser_found.PATTERN.fullmatch(plain_text_for_check):
                    logger.debug("文本内容匹配到纯视频ID，符合规则", "B站解析")
                    return True

    logger.debug("消息不符合被动解析规则", "B站解析")
    return False


async def _build_video_message(
    video_info: VideoInfo, render_enabled: bool
) -> Optional[UniMsg]:
    """构建视频信息消息"""
    if render_enabled:
        logger.debug(
            f"渲染视频消息 (style_blue): {video_info.title} (BV: {video_info.bvid})",
            "B站解析",
        )
        try:
            image_bytes = await render_video_info_to_image(video_info)
            if image_bytes:
                return UniMsg(
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
    """构建直播间信息消息"""
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
    """构建文章/动态信息消息"""
    logger.debug(
        f"构建文章/动态消息: {article_info.type} {article_info.id}, 渲染模式: {render_enabled}",
        "B站解析",
    )
    article_message = await MessageBuilder.build_article_message(
        article_info, render_enabled=render_enabled
    )

    if article_message and article_info.url:
        image_segment = None
        for seg in article_message:
            if isinstance(seg, Image):
                image_segment = seg
                break

        if image_segment:
            return UniMsg([image_segment, Text(f"\n链接: {article_info.url}")])
        else:
            return article_message
    else:
        return article_message


async def _build_season_message(
    season_info: SeasonInfo, render_enabled: bool
) -> Optional[UniMsg]:
    """构建番剧/影视信息消息"""
    if render_enabled:
        logger.debug(f"渲染番剧消息 (style_blue): {season_info.title}", "B站解析")
        try:
            image_bytes = await render_season_info_to_image(season_info)
            if image_bytes:
                return UniMsg(
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
    """构建用户信息消息"""
    if render_enabled:
        logger.warning("UserInfo 渲染暂未实现，将发送原始消息", "B站解析")
        return await MessageBuilder.build_user_message(user_info)
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
    """处理消息，解析 B 站链接"""
    logger.debug(f"Handler received message: {message}", "B站解析")

    parsed_content: Union[
        VideoInfo, LiveInfo, ArticleInfo, SeasonInfo, UserInfo, None
    ] = None
    target_url: Optional[str] = None

    if base_config.get("ENABLE_MINIAPP_PARSE", True):
        for seg in message:
            if isinstance(seg, Hyper) and seg.raw:
                try:
                    data = json.loads(seg.raw)
                    if data.get("app") == "com.tencent.qun.invite":
                        continue
                    meta_data = data.get("meta", {})
                    jump_url = (
                        meta_data.get("news", {}).get("jumpUrl")
                        or meta_data.get("detail_1", {}).get("qqdocurl")
                        or meta_data.get("detail_1", {}).get("preview")
                    )
                    if (
                        jump_url
                        and isinstance(jump_url, str)
                        and ("bilibili.com" in jump_url or "b23.tv" in jump_url)
                    ):
                        target_url = jump_url.split("?")[0]
                        if target_url.endswith("/"):
                            target_url = target_url[:-1]
                        logger.debug(f"从 Hyper 段提取到 URL: {target_url}", "B站解析")
                        break
                except Exception as e:
                    logger.debug(f"解析 Hyper 失败: {e}", "B站解析")
    else:
        logger.debug("小程序/卡片解析已禁用，跳过 Hyper 检查", "B站解析")

    if not target_url:
        logger.debug("未从 Hyper 提取到 URL，尝试从 Text 段提取", "B站解析")
        plain_text_content = message.extract_plain_text().strip()
        if plain_text_content:
            parser_found = UrlParserRegistry.get_parser(plain_text_content)
            if parser_found:
                match = (
                    parser_found.PATTERN.search(plain_text_content)
                    if parser_found.PATTERN
                    else None
                )
                if match:
                    target_url = match.group(0)
                    logger.debug(
                        f"从文本内容提取到 URL/ID ({parser_found.__name__}): {target_url}",
                        "B站解析",
                    )
                elif parser_found.__name__ == "PureVideoIdParser":
                    if parser_found.PATTERN.fullmatch(plain_text_content):
                        target_url = plain_text_content
                        logger.debug(
                            f"从文本内容提取到纯视频 ID: {target_url}", "B站解析"
                        )
                    else:
                        logger.debug("文本包含视频ID，但不是纯ID，忽略", "B站解析")
                else:
                    logger.debug(
                        f"找到解析器 {parser_found.__name__} 但未在文本中匹配到模式",
                        "B站解析",
                    )
            else:
                logger.debug("未找到能解析该文本内容的解析器", "B站解析")

    if not target_url:
        logger.debug("未在消息中找到有效的 B 站 URL/ID，退出处理", "B站解析")
        return

    should_parse = await CacheService.should_parse(target_url, session)
    logger.debug(
        f"Cache check for '{target_url}' in context '{CacheService._get_context_key(session)}': should_parse = {should_parse}",
        "B站解析",
    )
    if not should_parse:
        logger.debug(
            f"URL cached and TTL not expired, skipping: {target_url}", "B站解析"
        )
        return

    try:
        logger.info(f"开始解析URL: {target_url}", "B站解析", session=session)

        parsed_content: Union[
            VideoInfo, LiveInfo, ArticleInfo, SeasonInfo, UserInfo, None
        ] = await ParserService.parse(target_url)
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
            f"Building message for parsed content type: {type(parsed_content).__name__}",
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
                await CacheService.add_to_cache(target_url, session)
                logger.info(
                    f"成功被动解析并发送: {target_url}", "B站解析", session=session
                )

                if isinstance(parsed_content, VideoInfo):
                    if await auto_download_manager.is_auto_download_enabled(session):
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
                                f"视频时长 {video_duration_minutes}分钟 超过限制 {max_duration_minutes}分钟，取消自动下载",
                                "B站解析",
                            )
                        else:
                            logger.info(
                                f"视频时长 {video_duration_minutes}分钟 符合要求或限制已禁用，开始执行自动下载..."
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
                await CacheService.add_to_cache(target_url, session)

        except Exception as e:
            logger.error(
                f"Error building or sending message for {target_url}: {e}",
                "B站解析",
                session=session,
            )
            logger.error(traceback.format_exc())
