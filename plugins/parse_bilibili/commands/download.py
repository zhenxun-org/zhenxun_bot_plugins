import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import requests
from typing import Optional, Dict, Any, Literal, List, Tuple

from arclet.alconna import (
    Alconna,
    Args,
    Arparma,
    CommandMeta,
)
from nonebot.adapters import Bot, Event
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import (
    GROUP_ADMIN,
    GROUP_OWNER,
    MessageSegment as V11MessageSegment,
)
from nonebot_plugin_alconna import AlconnaMatcher, on_alconna, AlconnaMatches
from nonebot_plugin_session import EventSession, SessionLevel

from bilibili_api import video
from zhenxun.services.log import logger

from ..config import (
    base_config,
    get_credential,
    PLUGIN_TEMP_DIR,
    DOWNLOAD_TIMEOUT,
    DOWNLOAD_MAX_RETRIES,
    SEND_VIDEO_MAX_RETRIES,
    SEND_VIDEO_RETRY_DELAY,
)
from ..model import VideoInfo
from ..services.parser_service import ParserService
from ..utils.exceptions import MediaProcessError, DownloadError, BilibiliBaseException
from ..utils.url_parser import ResourceType, UrlParserRegistry
from ..services.network_service import async_handle_errors, handle_errors

from ..services import auto_download_manager

BILIBILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}


@async_handle_errors(
    error_msg="下载B站文件失败",
    exc_types=[Exception],
    reraise=True,
)
async def download_b_file(url: str, file_path: Path):
    """下载B站文件"""
    from ..utils.file_utils import download_file
    from ..utils.exceptions import DownloadError

    proxy_setting = base_config.get("PROXY")
    proxies = (
        {"http://": proxy_setting, "https://": proxy_setting} if proxy_setting else None
    )

    logger.info(f"开始下载文件: {file_path.name}, 最大重试次数: {DOWNLOAD_MAX_RETRIES}")
    result = await download_file(
        url=url,
        file_path=file_path,
        headers=BILIBILI_HEADERS,
        proxies=proxies,
        timeout=DOWNLOAD_TIMEOUT,
        max_retries=DOWNLOAD_MAX_RETRIES,
    )

    if not result:
        error_msg = f"下载文件 {file_path.name} 失败，已达到最大重试次数 ({DOWNLOAD_MAX_RETRIES})"
        logger.error(error_msg)
        raise DownloadError(
            error_msg, context={"url": url, "file_path": str(file_path)}
        )

    return result


@async_handle_errors(
    error_msg="合并音视频文件失败",
    exc_types=[Exception],
    reraise=True,
)
async def merge_file_to_mp4(
    v_path: Path,
    a_path: Path,
    output_path: Path,
    use_copy_codec: bool = False,
    log_output: bool = False,
):
    """合并音视频文件"""
    from ..utils.file_utils import merge_media_files
    from ..utils.exceptions import MediaProcessError

    try:
        success = await merge_media_files(
            video_path=v_path,
            audio_path=a_path,
            output_path=output_path,
            use_copy_codec=use_copy_codec,
            log_output=log_output,
        )

        if not success and use_copy_codec:
            logger.warning("使用copy编解码器合并失败，尝试重新编码音频...")
            success = await merge_media_files(
                video_path=v_path,
                audio_path=a_path,
                output_path=output_path,
                use_copy_codec=False,
                log_output=log_output,
            )

        if not success:
            raise MediaProcessError(
                "音视频合并失败",
                context={
                    "video_path": str(v_path),
                    "audio_path": str(a_path),
                    "output_path": str(output_path),
                    "use_copy_codec": use_copy_codec,
                },
            )

        return success
    finally:
        try:
            if v_path.exists():
                v_path.unlink()
            if a_path.exists():
                a_path.unlink()
            logger.debug(f"已清理临时文件: {v_path.name}, {a_path.name}")
        except OSError as e:
            logger.warning("清理临时文件失败", e=e)


@async_handle_errors(
    error_msg="发送视频文件失败",
    exc_types=[Exception],
    reraise=False,
    default_return=False,
)
async def send_video_final(bot: Bot, event: Event, video_path: Path):
    """发送最终视频，失败时自动重试"""
    from ..utils.exceptions import DownloadError

    if not video_path.exists():
        error_msg = f"尝试发送时合并后的文件已不存在: {video_path}"
        logger.error(error_msg)
        raise DownloadError(error_msg, context={"video_path": str(video_path)})

    file_size = video_path.stat().st_size
    if file_size == 0:
        error_msg = f"视频文件大小为0: {video_path}"
        logger.error(error_msg)
        raise DownloadError(error_msg, context={"video_path": str(video_path)})

    if file_size > 100 * 1024 * 1024:
        logger.warning(
            f"视频文件较大 ({file_size / 1024 / 1024:.1f}MB)，可能发送失败: {video_path}"
        )

    path_str = str(video_path.resolve())
    path_str = path_str.replace("\\", "/")
    file_uri = "file:///" + path_str
    video_segment = V11MessageSegment.video(file_uri)

    max_retries = SEND_VIDEO_MAX_RETRIES
    base_delay = SEND_VIDEO_RETRY_DELAY
    send_timeout = base_config.get("SEND_VIDEO_TIMEOUT", 120)

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(
                f"尝试发送视频 (尝试 {attempt}/{max_retries}), 超时设置: {send_timeout}秒"
            )

            send_task = asyncio.create_task(
                bot.send(event=event, message=video_segment)
            )

            await asyncio.wait_for(send_task, timeout=send_timeout)

            logger.info(f"视频文件发送成功: {video_path}")
            return True
        except asyncio.TimeoutError:
            is_last_attempt = attempt >= max_retries

            from ..utils.common import calculate_retry_wait_time

            delay = calculate_retry_wait_time(attempt=attempt, base_delay=base_delay)

            logger.warning(
                f"发送视频超时 (尝试 {attempt}/{max_retries}): {video_path}, 超时设置: {send_timeout}秒"
            )

            if not is_last_attempt:
                logger.info(f"将在 {delay:.1f}秒后重试发送视频")
                await asyncio.sleep(delay)
            else:
                error_msg = f"视频发送超时，已达到最大重试次数 ({max_retries})"
                logger.error(error_msg)
                raise DownloadError(
                    error_msg,
                    context={
                        "video_path": str(video_path),
                        "attempts": max_retries,
                        "timeout": send_timeout,
                    },
                )
        except Exception as e:
            is_last_attempt = attempt >= max_retries

            from ..utils.common import calculate_retry_wait_time

            delay = calculate_retry_wait_time(attempt=attempt, base_delay=base_delay)

            error_type = type(e).__name__
            error_msg = str(e)

            if (
                "rich media transfer failed" in error_msg.lower()
                or "timeout" in error_msg.lower()
                or "network" in error_msg.lower()
            ):
                logger.warning(
                    f"发送视频失败 (网络/传输错误) (尝试 {attempt}/{max_retries}): {video_path}, 错误: {error_type}: {error_msg}"
                )
                if not is_last_attempt:
                    logger.info(f"将在 {delay:.1f}秒后重试发送视频")
                    await asyncio.sleep(delay)
                else:
                    error_msg = f"视频发送失败，已达到最大重试次数 ({max_retries}): {error_type}: {error_msg}"
                    logger.error(error_msg)
                    raise DownloadError(
                        error_msg,
                        context={
                            "video_path": str(video_path),
                            "attempts": max_retries,
                            "error_type": error_type,
                        },
                    )
            else:
                logger.error(
                    f"视频发送失败 (尝试 {attempt}/{max_retries}): {error_type}: {error_msg}"
                )
                if not is_last_attempt:
                    logger.info(f"将在 {delay:.1f}秒后重试发送视频")
                    await asyncio.sleep(delay)
                else:
                    error_msg = f"视频发送失败，已达到最大重试次数 ({max_retries})"
                    logger.error(error_msg)
                    raise DownloadError(
                        error_msg,
                        context={
                            "video_path": str(video_path),
                            "attempts": max_retries,
                            "error_type": error_type,
                        },
                    )

    return False


def sanitize_filename(filename: str) -> str:
    """清理文件名中的非法字符"""
    from ..utils.common import sanitize_filename as common_sanitize_filename

    return common_sanitize_filename(filename, max_length=100)


def estimate_video_size(
    video_stream: Dict[str, Any], audio_stream: Dict[str, Any], duration_seconds: float
) -> float:
    """估算视频大小（MB）"""
    video_size_bytes = 0
    audio_size_bytes = 0

    if "size" in video_stream:
        video_size_bytes = video_stream["size"]
    elif "bandwidth" in video_stream:
        video_size_bytes = (video_stream["bandwidth"] / 8) * duration_seconds

    if "size" in audio_stream:
        audio_size_bytes = audio_stream["size"]
    elif "bandwidth" in audio_stream:
        audio_size_bytes = (audio_stream["bandwidth"] / 8) * duration_seconds

    total_size_mb = (video_size_bytes + audio_size_bytes) / (1024 * 1024)

    return total_size_mb


def select_appropriate_quality(
    video_streams: List[Dict[str, Any]],
    audio_streams: List[Dict[str, Any]],
    duration_seconds: float,
    max_size_mb: float = 100.0,
    initial_quality_id: int = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
    """根据大小限制选择合适的视频和音频流"""
    quality_preference = [120, 116, 112, 80, 74, 64, 32, 16]

    audio_streams.sort(key=lambda s: s.get("bandwidth", 0), reverse=True)
    selected_audio_stream = audio_streams[0]

    video_streams.sort(key=lambda s: s.get("id", 0), reverse=True)

    if initial_quality_id is not None:
        filtered_streams = [
            s for s in video_streams if s.get("id", 0) <= initial_quality_id
        ]
        if filtered_streams:
            video_streams = filtered_streams

    selected_video_stream = video_streams[0]
    original_quality_id = selected_video_stream.get("id", 0)
    quality_reduced = False

    estimated_size = estimate_video_size(
        selected_video_stream, selected_audio_stream, duration_seconds
    )

    logger.debug(
        f"初始视频流质量: {original_quality_id}, 估算大小: {estimated_size:.2f}MB"
    )

    if estimated_size > max_size_mb:
        current_quality_id = original_quality_id

        try:
            current_index = quality_preference.index(current_quality_id)
        except ValueError:
            lower_qualities = [q for q in quality_preference if q < current_quality_id]
            if lower_qualities:
                current_index = quality_preference.index(max(lower_qualities)) - 1
            else:
                current_index = len(quality_preference) - 1

        for i in range(current_index + 1, len(quality_preference)):
            next_quality_id = quality_preference[i]

            for stream in video_streams:
                if stream.get("id", 0) == next_quality_id:
                    new_size = estimate_video_size(
                        stream, selected_audio_stream, duration_seconds
                    )

                    logger.debug(
                        f"尝试降低清晰度: {next_quality_id}, 估算大小: {new_size:.2f}MB"
                    )

                    if new_size <= max_size_mb:
                        selected_video_stream = stream
                        quality_reduced = True
                        logger.info(
                            f"视频大小超过限制({estimated_size:.2f}MB > {max_size_mb}MB)，"
                            f"已降低清晰度: {original_quality_id} -> {next_quality_id}"
                        )
                        return (
                            selected_video_stream,
                            selected_audio_stream,
                            quality_reduced,
                        )

                    if i == len(quality_preference) - 1:
                        selected_video_stream = stream
                        quality_reduced = True
                        logger.warning(
                            f"即使最低清晰度({next_quality_id})也超过大小限制"
                            f"({new_size:.2f}MB > {max_size_mb}MB)，但仍将使用此清晰度"
                        )
                        return (
                            selected_video_stream,
                            selected_audio_stream,
                            quality_reduced,
                        )

    return selected_video_stream, selected_audio_stream, quality_reduced


@async_handle_errors(
    error_msg="解析小程序消息失败",
    log_level="error",
    reraise=False,
    default_return=None,
)
async def extract_bilibili_url_from_miniprogram(raw_str: str) -> Optional[str]:
    """从小程序消息提取B站URL"""
    from ..utils.url_parser import extract_bilibili_url_from_miniprogram as extract_url

    return extract_url(raw_str)


async def check_video_duration(
    duration_seconds: float, event: Event, matcher: Optional[AlconnaMatcher] = None
) -> bool:
    """检查视频时长是否超过限制"""
    from nonebot import get_driver

    max_duration_minutes = base_config.get("MANUAL_DOWNLOAD_MAX_DURATION", 0)
    if max_duration_minutes <= 0:
        logger.debug("视频时长限制未启用，允许下载")
        return True

    user_id = event.get_user_id()
    superusers = get_driver().config.superusers
    if user_id in superusers:
        logger.debug(f"用户 {user_id} 是超级用户，不受时长限制")
        return True

    duration_minutes = round(duration_seconds / 60, 1)
    max_duration_seconds = max_duration_minutes * 60

    if duration_seconds > max_duration_seconds:
        logger.debug(
            f"视频时长 {duration_minutes}分钟 超过限制 {max_duration_minutes}分钟，取消下载"
        )
        if matcher:
            await matcher.send(
                f"视频时长 {duration_minutes}分钟 超过限制 {max_duration_minutes}分钟，无法下载"
            )
        return False
    else:
        logger.debug(f"视频时长 {duration_minutes}分钟 符合要求，继续执行下载")
        if matcher:
            await matcher.send("正在解析B站链接并准备下载，请稍候...")
        return True


@handle_errors(
    error_msg="获取番剧信息失败",
    exc_types=[requests.RequestException, json.JSONDecodeError],
    log_level="error",
    reraise=False,
    default_return=None,
)
def get_bangumi_info_sync(url_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """获取番剧信息(同步)"""
    api_url = None
    if "ep_id" in url_info:
        api_url = (
            f"https://api.bilibili.com/pgc/view/web/season?ep_id={url_info['ep_id']}"
        )
    elif "season_id" in url_info:
        api_url = f"https://api.bilibili.com/pgc/view/web/season?season_id={url_info['season_id']}"
    else:
        logger.error("无效的番剧信息输入")
        return None

    logger.debug(f"请求番剧信息 (同步): {api_url}")

    cred = get_credential()
    response = requests.get(
        api_url,
        headers=BILIBILI_HEADERS,
        cookies=cred.get_cookies() if cred else None,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("code") == 0 and "result" in data:
        logger.debug(f"获取到番剧信息: {data['result'].get('title', '未知')}")
        return data["result"]
    else:
        logger.error(
            f"获取番剧信息 API 错误: Code={data.get('code')} Msg={data.get('message')}"
        )
        return None


@handle_errors(
    error_msg="获取番剧播放链接失败",
    exc_types=[requests.RequestException, json.JSONDecodeError],
    log_level="error",
    reraise=False,
    default_return=None,
)
def get_play_url_sync(
    ep_id: int, cid: int, quality: int = 120, fnval: int = 16
) -> Optional[Dict[str, Any]]:
    """获取番剧播放链接(同步)"""
    api_url = "https://api.bilibili.com/pgc/player/web/playurl"
    params = {
        "ep_id": ep_id,
        "cid": cid,
        "qn": quality,
        "fnval": fnval,
        "fnver": 0,
        "fourk": 1,
    }
    logger.debug(f"请求播放链接 (同步): {api_url} Params: {params}")

    cred = get_credential()
    response = requests.get(
        api_url,
        params=params,
        headers=BILIBILI_HEADERS,
        cookies=cred.get_cookies() if cred else None,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("code") == 0 and "result" in data:
        logger.debug("获取播放链接成功")
        return data["result"]
    else:
        logger.warning(
            f"获取播放链接失败: Code={data.get('code')} Msg={data.get('message')}"
        )
        return None


async def get_bangumi_play_url_with_fallback(
    ep_id: int, cid: int
) -> Optional[Dict[str, Any]]:
    """获取番剧播放链接"""
    loop = asyncio.get_running_loop()

    play_info = await loop.run_in_executor(None, get_play_url_sync, ep_id, cid)

    if not play_info:
        logger.warning("获取播放链接失败")
        return None

    if "durl" not in play_info and "dash" not in play_info:
        logger.warning("获取的播放信息中缺少 durl 或 dash")
        return None

    logger.debug("获取播放链接成功")
    return play_info


@async_handle_errors(
    error_msg="下载并发送番剧视频失败",
    exc_types=[Exception],
    reraise=True,
)
async def _perform_bangumi_download(
    bot: Bot,
    event: Event,
    url_info_dict: Dict[str, Any],
    matcher: Optional[AlconnaMatcher] = None,
):
    """下载并发送番剧视频"""
    from ..utils.exceptions import ResourceNotFoundError

    loop = asyncio.get_running_loop()
    logger.info(f"开始下载番剧: {url_info_dict}")

    bangumi_info = await loop.run_in_executor(
        None, get_bangumi_info_sync, url_info_dict
    )
    if not bangumi_info:
        error_msg = "无法获取番剧信息"
        logger.error(error_msg)
        raise ResourceNotFoundError(error_msg, context={"url_info": url_info_dict})

    episodes = bangumi_info.get("episodes", [])
    if not episodes:
        error_msg = "番剧没有剧集信息"
        logger.error(error_msg)
        raise ResourceNotFoundError(
            error_msg,
            context={
                "url_info": url_info_dict,
                "bangumi_title": bangumi_info.get("title"),
            },
        )

    target_episode = None
    target_ep_id = url_info_dict.get("ep_id")
    if target_ep_id:
        for ep in episodes:
            if ep.get("id") == target_ep_id:
                target_episode = ep
                break
    else:
        target_episode = episodes[0]

    if not target_episode:
        error_msg = "未找到目标剧集"
        logger.error(error_msg)
        raise ResourceNotFoundError(
            error_msg,
            context={
                "url_info": url_info_dict,
                "bangumi_title": bangumi_info.get("title"),
                "ep_id": target_ep_id,
            },
        )
    ep_id = target_episode.get("id")
    cid = target_episode.get("cid")
    title = sanitize_filename(target_episode.get("long_title", f"EP{ep_id}"))

    play_info = await get_bangumi_play_url_with_fallback(ep_id, cid)
    if not play_info:
        error_msg = f"获取播放链接失败 for ep {ep_id}"
        logger.error(error_msg)
        raise DownloadError(
            error_msg, context={"ep_id": ep_id, "cid": cid, "title": title}
        )

    downloaded_file_path: Optional[Path] = None
    v_stream_path: Optional[Path] = None
    a_stream_path: Optional[Path] = None
    output_path = PLUGIN_TEMP_DIR / f"bili_video_ep{ep_id}.mp4"

    try:
        if "dash" in play_info:
            logger.debug("处理 DASH 流")
            dash_info = play_info["dash"]
            video_streams = dash_info.get("video", [])
            audio_streams = dash_info.get("audio", [])
            if not video_streams or not audio_streams:
                raise DownloadError("DASH 流缺少视频或音频")

            max_quality = base_config.get("VIDEO_DOWNLOAD_QUALITY", 64)
            logger.debug(f"配置的番剧视频质量上限: qn={max_quality}")

            filtered_streams = [
                s for s in video_streams if s.get("id", 0) <= max_quality
            ]

            if not filtered_streams:
                logger.warning(
                    f"未找到质量 <= {max_quality} 的番剧视频流，尝试选择最接近的质量"
                )
                all_streams = sorted(video_streams, key=lambda s: s.get("id", 0))

                for stream in all_streams:
                    if stream.get("id", 0) > max_quality:
                        filtered_streams = [stream]
                        break

            if not filtered_streams and video_streams:
                filtered_streams = video_streams

            if not filtered_streams:
                raise DownloadError("未找到可用的番剧视频流")

            if not audio_streams:
                raise DownloadError("未找到可用的番剧音频流")

            episode_duration_seconds = target_episode.get("duration", 0) / 1000

            video_stream, audio_stream, _ = select_appropriate_quality(
                video_streams=filtered_streams,
                audio_streams=audio_streams,
                duration_seconds=episode_duration_seconds,
                max_size_mb=100.0,
                initial_quality_id=max_quality,
            )

            logger.info(f"最终选择的番剧视频流: qn={video_stream.get('id')}")

            video_url = video_stream.get("baseUrl") or video_stream.get("base_url")
            audio_url = audio_stream.get("baseUrl") or audio_stream.get("base_url")
            if not video_url or not audio_url:
                raise DownloadError("无法获取 DASH 流 URL")

            v_stream_path = PLUGIN_TEMP_DIR / f"bili_video_ep{ep_id}_video.m4s"
            a_stream_path = PLUGIN_TEMP_DIR / f"bili_video_ep{ep_id}_audio.m4s"

            logger.info("开始下载番剧视频流...")
            dl_video_ok = await download_b_file(video_url, v_stream_path)
            logger.info("开始下载番剧音频流...")
            dl_audio_ok = await download_b_file(audio_url, a_stream_path)

            if not dl_video_ok or not dl_audio_ok:
                raise DownloadError("番剧音视频流下载失败")

            merge_ok = await merge_file_to_mp4(
                v_stream_path, a_stream_path, output_path, use_copy_codec=True
            )
            if not merge_ok:
                raise MediaProcessError("番剧合并失败")
            downloaded_file_path = output_path

        elif "durl" in play_info:
            logger.debug("处理 DURL 流 (FLV/MP4)")
            durl_info = play_info["durl"]
            if not durl_info:
                raise DownloadError("无法获取 DURL 信息")
            url = durl_info[0].get("url")
            if not url:
                raise DownloadError("无法获取 DURL URL")
            ext = ".flv" if ".flv" in url else ".mp4"
            output_path = PLUGIN_TEMP_DIR / f"bili_video_ep{ep_id}{ext}"
            logger.info(f"开始下载 DURL 流: {title}{ext}")
            dl_ok = await download_b_file(url, output_path)
            if not dl_ok:
                raise DownloadError("DURL 流下载失败")
            downloaded_file_path = output_path
        else:
            raise DownloadError("不支持的播放信息格式")

        if downloaded_file_path and downloaded_file_path.exists():
            logger.info(f"番剧下载/处理完成: {downloaded_file_path}")
            await send_video_final(bot, event, downloaded_file_path)
        else:
            logger.error("最终文件不存在")

    except Exception as e:
        logger.error(f"执行番剧下载失败 for ep {ep_id}: {e}")
        if v_stream_path and v_stream_path.exists():
            v_stream_path.unlink(missing_ok=True)
        if a_stream_path and a_stream_path.exists():
            a_stream_path.unlink(missing_ok=True)
        if matcher:
            await matcher.finish(f"番剧下载处理失败: {str(e)[:100]}")


@async_handle_errors(
    error_msg="下载并发送普通视频失败",
    exc_types=[Exception],
    reraise=True,
)
async def _perform_video_download(
    bot: Bot,
    event: Event,
    video_info: VideoInfo,
    matcher: Optional[AlconnaMatcher] = None,
):
    """下载并发送普通视频"""
    from ..services.cache_service import CacheService
    from ..utils.exceptions import DownloadError, MediaProcessError

    video_id = video_info.bvid or f"av{video_info.aid}"
    final_url = video_info.parsed_url
    page_num = 0

    parsed_final_url = urlparse(final_url)
    if parsed_final_url.query:
        query_params = parse_qs(parsed_final_url.query)
        p_value = query_params.get("p")
        if p_value and p_value[0].isdigit():
            page_num = int(p_value[0]) - 1
            if page_num < 0:
                page_num = 0

    logger.info(
        f"开始处理视频 (供 {event.get_event_name()}): {video_info.title} (ID: {video_id}, P{page_num + 1})"
    )

    cached_file = await CacheService.get_video_cache(video_id, page_num)
    if cached_file:
        logger.info(f"找到视频缓存: {cached_file}")
        try:
            path_str = str(cached_file.resolve())
            path_str = path_str.replace("\\", "/")
            file_uri = "file:///" + path_str
            video_segment = V11MessageSegment.video(file_uri)
            logger.debug(
                f"从缓存发送视频: {type(video_segment)}, 内容: {video_segment}"
            )
            await bot.send(event=event, message=video_segment)
            logger.info(f"缓存视频发送成功: {cached_file}")
            return
        except Exception as send_e:
            logger.error("发送缓存视频文件失败 (Bot API)", e=send_e)

    if matcher:
        await matcher.send("正在下载视频，请稍候...")

    downloaded_file_path: Path | None = None
    v_stream_path: Path | None = None
    a_stream_path: Path | None = None

    try:
        logger.debug("创建 bilibili_api.Video 对象")
        cred = get_credential()
        if video_id.startswith("BV"):
            v = video.Video(bvid=video_id, credential=cred)
        elif video_id.startswith("av"):
            v = video.Video(aid=int(video_id[2:]), credential=cred)
        else:
            error_msg = f"无效 video_id: {video_id}"
            logger.error(error_msg)
            raise DownloadError(error_msg, context={"video_id": video_id})

        logger.debug(f"获取下载链接 (P{page_num + 1})")
        download_url_data: Dict[str, Any] = await v.get_download_url(
            page_index=page_num
        )

        selected_video_stream: Optional[Dict[str, Any]] = None
        selected_audio_stream: Optional[Dict[str, Any]] = None
        video_url = None
        audio_url = None
        use_copy_codec = False

        if "dash" in download_url_data:
            max_quality = base_config.get("VIDEO_DOWNLOAD_QUALITY", 64)
            logger.debug(f"配置的视频质量上限: qn={max_quality}")

            dash_video_streams = download_url_data["dash"].get("video", [])
            dash_audio_streams = download_url_data["dash"].get("audio", [])

            h264_streams = [
                s
                for s in dash_video_streams
                if isinstance(s.get("codecs"), str)
                and s["codecs"].startswith("avc")
                and s.get("id", 0) <= max_quality
            ]

            non_h264_streams = [
                s
                for s in dash_video_streams
                if s.get("id", 0) <= max_quality
                and (
                    not isinstance(s.get("codecs"), str)
                    or not s["codecs"].startswith("avc")
                )
            ]

            video_streams_to_use = h264_streams if h264_streams else non_h264_streams

            if not video_streams_to_use:
                logger.warning(
                    f"未找到质量 <= {max_quality} 的视频流，尝试选择最接近的质量"
                )
                all_streams = sorted(dash_video_streams, key=lambda s: s.get("id", 0))

                for stream in all_streams:
                    if stream.get("id", 0) > max_quality:
                        video_streams_to_use = [stream]
                        break

            if not video_streams_to_use and dash_video_streams:
                video_streams_to_use = dash_video_streams

            if not video_streams_to_use:
                error_msg = "未找到可用视频流"
                logger.error(error_msg)
                raise DownloadError(
                    error_msg, context={"video_id": video_id, "page_num": page_num}
                )

            if not dash_audio_streams:
                error_msg = "未找到可用音频流"
                logger.error(error_msg)
                raise DownloadError(
                    error_msg, context={"video_id": video_id, "page_num": page_num}
                )

            selected_video_stream, selected_audio_stream, _ = (
                select_appropriate_quality(
                    video_streams=video_streams_to_use,
                    audio_streams=dash_audio_streams,
                    duration_seconds=video_info.duration,
                    max_size_mb=100.0,
                    initial_quality_id=max_quality,
                )
            )

            use_copy_codec = isinstance(
                selected_video_stream.get("codecs"), str
            ) and selected_video_stream["codecs"].startswith("avc")

            video_url = selected_video_stream.get(
                "baseUrl"
            ) or selected_video_stream.get("base_url")
            audio_url = selected_audio_stream.get(
                "baseUrl"
            ) or selected_audio_stream.get("base_url")

            logger.info(
                f"最终选择的视频流: qn={selected_video_stream.get('id')}, 编码: {selected_video_stream.get('codecs')}"
            )
        if not video_url or not audio_url:
            error_msg = "未能选择有效的音视频流 URL"
            logger.error(error_msg)
            raise DownloadError(
                error_msg,
                context={
                    "video_id": video_id,
                    "page_num": page_num,
                    "video_url_exists": video_url is not None,
                    "audio_url_exists": audio_url is not None,
                },
            )

        from ..services.cache_service import VIDEO_CACHE_DIR

        base_filename = f"bili_video_{video_id}_P{page_num + 1}"
        v_stream_path = PLUGIN_TEMP_DIR / f"{base_filename}-video.m4s"
        a_stream_path = PLUGIN_TEMP_DIR / f"{base_filename}-audio.m4s"

        cache_filename = f"{video_id}_P{page_num + 1}.mp4"
        output_mp4_path = VIDEO_CACHE_DIR / cache_filename
        logger.info("开始下载音视频流...")
        results = await asyncio.gather(
            download_b_file(video_url, v_stream_path),
            download_b_file(audio_url, a_stream_path),
            return_exceptions=True,
        )
        if isinstance(results[0], Exception) or not results[0]:
            error_msg = f"下载视频流失败: {results[0] if isinstance(results[0], Exception) else '未知错误'}"
            logger.error(error_msg)
            raise DownloadError(
                error_msg,
                context={
                    "video_id": video_id,
                    "page_num": page_num,
                    "video_url": video_url,
                    "video_path": str(v_stream_path),
                },
            )
        if isinstance(results[1], Exception) or not results[1]:
            error_msg = f"下载音频流失败: {results[1] if isinstance(results[1], Exception) else '未知错误'}"
            logger.error(error_msg)
            raise DownloadError(
                error_msg,
                context={
                    "video_id": video_id,
                    "page_num": page_num,
                    "audio_url": audio_url,
                    "audio_path": str(a_stream_path),
                },
            )
        logger.info("音视频流下载完成.")

        merge_success = await merge_file_to_mp4(
            v_stream_path, a_stream_path, output_mp4_path, use_copy_codec=use_copy_codec
        )
        if merge_success:
            downloaded_file_path = output_mp4_path
            logger.info(f"视频处理成功: {downloaded_file_path}")

            cache_key = f"{video_id}_{page_num}"
            logger.info(
                f"视频已直接保存到缓存目录: {cache_key} -> {downloaded_file_path}"
            )

            await CacheService.save_video_to_cache(
                video_id, page_num, downloaded_file_path
            )

            logger.debug(f"准备发送最终视频文件: {downloaded_file_path}")
            if downloaded_file_path.exists():
                try:
                    path_str = str(downloaded_file_path.resolve())
                    path_str = path_str.replace("\\", "/")
                    file_uri = "file:///" + path_str
                    video_segment = V11MessageSegment.video(file_uri)
                    logger.debug(
                        f"自动下载：准备发送的消息段类型: {type(video_segment)}, 内容: {video_segment}"
                    )
                    await bot.send(event=event, message=video_segment)
                except Exception as send_e:
                    logger.error("发送视频文件失败 (Bot API)", e=send_e)
            else:
                logger.error(f"尝试发送时文件已不存在: {downloaded_file_path}")

        else:
            raise MediaProcessError("FFmpeg 合并或编码失败")

    except Exception as e:
        logger.error(f"执行视频下载/处理失败 for {video_id}", e=e)
        if v_stream_path and v_stream_path.exists():
            v_stream_path.unlink(missing_ok=True)
        if a_stream_path and a_stream_path.exists():
            a_stream_path.unlink(missing_ok=True)
        if matcher:
            await matcher.finish(f"视频下载处理失败: {str(e)[:100]}")


bili_download_cmd = Alconna("bili下载", Args["link?", str])

bili_download_matcher = on_alconna(
    bili_download_cmd,
    block=True,
    priority=5,
    aliases={"b站下载"},
    skip_for_unmatch=False,
)


@bili_download_matcher.handle()
async def handle_bili_download(
    matcher: AlconnaMatcher, bot: Bot, event: Event, result: Arparma = AlconnaMatches()
):
    logger.info("处理 bili下载 命令")
    target_url_or_id = None
    url_info_dict: Optional[Dict[str, Any]] = None

    if result.matched and "link" in result.main_args:
        target_url_or_id = result.main_args["link"]
        logger.info(f"从命令参数中获取到链接: {target_url_or_id}")
    else:
        logger.debug("尝试从事件中提取B站链接")
        from ..utils.url_parser import extract_bilibili_url_from_event

        target_url_or_id = await extract_bilibili_url_from_event(bot, event)

    if not target_url_or_id:
        logger.debug("未找到有效链接/ID")
        await matcher.finish(
            "未找到有效的B站链接或视频ID，请检查输入或回复包含B站链接的消息。"
        )

    resource_type: Optional[ResourceType] = None
    resource_id: Optional[str] = None
    try:
        parser = UrlParserRegistry.get_parser(target_url_or_id)
        if parser:
            resource_type, resource_id = parser.parse(target_url_or_id)
            logger.debug(f"通过 Registry 解析: Type={resource_type}, ID={resource_id}")
            if resource_type == ResourceType.BANGUMI:
                if resource_id.startswith("ss"):
                    url_info_dict = {"season_id": int(resource_id[2:])}
                elif resource_id.startswith("ep"):
                    url_info_dict = {"ep_id": int(resource_id[2:])}
            elif resource_type == ResourceType.VIDEO:
                if resource_id.startswith("av"):
                    url_info_dict = {"av_id": int(resource_id[2:])}
                elif resource_id.startswith("BV"):
                    url_info_dict = {"bv_id": resource_id}
    except Exception as e:
        logger.warning(f"使用 UrlParserRegistry 解析失败: {e}, 将尝试原始解析")

    if not url_info_dict and not resource_type:
        logger.error(f"无法识别的 URL 或 ID: {target_url_or_id}")
        await matcher.finish(f"无法识别的B站链接或ID: {target_url_or_id}")

    if resource_type == ResourceType.SHORT_URL:
        logger.info(f"检测到短链接: {target_url_or_id}，尝试解析为实际链接")
        try:
            from ..services.network_service import NetworkService

            resolved_url = await NetworkService.resolve_short_url(target_url_or_id)
            logger.info(f"短链接解析结果: {resolved_url}")

            parser = UrlParserRegistry.get_parser(resolved_url)
            if parser:
                resource_type, resource_id = parser.parse(resolved_url)
                logger.debug(f"解析后的资源类型: {resource_type}, ID: {resource_id}")

                target_url_or_id = resolved_url

                if resource_type == ResourceType.BANGUMI:
                    if resource_id.startswith("ss"):
                        url_info_dict = {"season_id": int(resource_id[2:])}
                    elif resource_id.startswith("ep"):
                        url_info_dict = {"ep_id": int(resource_id[2:])}
                elif resource_type == ResourceType.VIDEO:
                    if resource_id.startswith("av"):
                        url_info_dict = {"av_id": int(resource_id[2:])}
                    elif resource_id.startswith("BV"):
                        url_info_dict = {"bv_id": resource_id}
            else:
                logger.error(f"无法解析短链接解析后的URL: {resolved_url}")
                await matcher.finish(f"无法解析短链接: {target_url_or_id}")
        except Exception as e:
            logger.error(f"解析短链接失败: {e}")
            await matcher.finish(f"解析短链接失败: {str(e)[:100]}")

    if resource_type == ResourceType.BANGUMI and url_info_dict:
        loop = asyncio.get_running_loop()
        bangumi_info = await loop.run_in_executor(
            None, get_bangumi_info_sync, url_info_dict
        )

        if not bangumi_info:
            logger.error("无法获取番剧信息")
            await matcher.finish("无法获取番剧信息，请稍后重试。")

        episodes = bangumi_info.get("episodes", [])
        if not episodes:
            logger.error("番剧没有剧集信息")
            await matcher.finish("番剧没有剧集信息，请检查链接是否正确。")

        target_episode = None
        target_ep_id = url_info_dict.get("ep_id")
        if target_ep_id:
            for ep in episodes:
                if ep.get("id") == target_ep_id:
                    target_episode = ep
                    break
        else:
            target_episode = episodes[0]

        if not target_episode:
            logger.error("未找到目标剧集")
            await matcher.finish("未找到目标剧集，请检查链接是否正确。")

        episode_duration = target_episode.get("duration", 0) / 1000

        duration_check_result = await check_video_duration(
            episode_duration, event, matcher
        )
        if not duration_check_result:
            return

        await matcher.send("正在下载番剧，视频较大请耐心等待...")

        try:
            await _perform_bangumi_download(bot, event, url_info_dict, matcher)
        except BilibiliBaseException as e:
            logger.error(f"番剧下载失败 (已处理异常): {e}")
            await matcher.finish(f"番剧下载失败: {str(e)[:100]}")
        except Exception as e:
            logger.error(f"番剧下载失败 (未处理异常): {e}")
            await matcher.finish(f"番剧下载失败: {str(e)[:100]}")
    elif resource_type == ResourceType.VIDEO and resource_id:
        video_info: Optional[VideoInfo] = None
        try:
            logger.debug(f"准备获取普通视频信息: {resource_id}")
            parsed_content = await ParserService.parse(target_url_or_id)
            if isinstance(parsed_content, VideoInfo):
                video_info = parsed_content

                duration_check_result = await check_video_duration(
                    parsed_content.duration, event, matcher
                )
                if not duration_check_result:
                    return

                await _perform_video_download(bot, event, video_info, matcher)
            else:
                logger.error(
                    f"解析普通视频链接未返回 VideoInfo: {type(parsed_content)}"
                )
                await matcher.finish("解析视频信息失败，请稍后重试。")
        except BilibiliBaseException as e:
            logger.error(f"执行普通视频下载失败 for {resource_id} (已处理异常): {e}")
            await matcher.finish(f"下载视频失败: {str(e)[:100]}")
        except Exception as e:
            logger.error(f"执行普通视频下载失败 for {resource_id} (未处理异常): {e}")
            await matcher.finish(f"下载视频失败: {str(e)[:100]}")
    elif resource_type == ResourceType.SHORT_URL:
        logger.info(f"检测到短链接类型，尝试使用ParserService解析: {target_url_or_id}")
        try:
            parsed_content = await ParserService.parse(target_url_or_id)

            if isinstance(parsed_content, VideoInfo):
                logger.debug(f"短链接解析为视频: {parsed_content.title}")
                video_info = parsed_content

                duration_check_result = await check_video_duration(
                    parsed_content.duration, event, matcher
                )
                if not duration_check_result:
                    return

                await _perform_video_download(bot, event, video_info, matcher)
                return
            else:
                logger.error(f"短链接解析结果不是视频: {type(parsed_content)}")
        except BilibiliBaseException as e:
            logger.error(f"使用ParserService解析短链接失败 (已处理异常): {e}")
            await matcher.finish(f"解析短链接失败: {str(e)[:100]}")
        except Exception as e:
            logger.error(f"使用ParserService解析短链接失败 (未处理异常): {e}")
            await matcher.finish(f"解析短链接失败: {str(e)[:100]}")
    else:
        logger.warning(
            f"识别的资源类型 ({resource_type}) 不是支持的下载类型 (Video/Bangumi/SHORT_URL)"
        )
        await matcher.finish(f"不支持下载此类型的内容: {resource_type}")

    logger.debug("handle_bili_download 函数执行完毕")


auto_download_cmd = Alconna(
    "bili自动下载",
    Args["action", Literal["on", "off"]],
    meta=CommandMeta(description="开启或关闭当前群聊的B站视频自动下载功能"),
)

auto_download_matcher = on_alconna(
    auto_download_cmd,
    aliases={"b站自动下载"},
    permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER,
    priority=10,
    block=True,
)


@auto_download_matcher.handle()
async def handle_auto_download_switch(
    matcher: AlconnaMatcher,
    session: EventSession,
    action: Literal["on", "off"],
):
    if session.level != SessionLevel.GROUP:
        await matcher.finish("此命令仅限群聊使用。")

    group_id = str(session.id2)
    if action == "on":
        success = await auto_download_manager.enable_auto_download(session)
        if success:
            await matcher.send(f"已为当前群聊({group_id})开启B站视频自动下载功能。")
        else:
            await matcher.send(f"当前群聊({group_id})已开启自动下载，无需重复操作。")
    elif action == "off":
        success = await auto_download_manager.disable_auto_download(session)
        if success:
            await matcher.send(f"已为当前群聊({group_id})关闭B站视频自动下载功能。")
        else:
            await matcher.send(f"当前群聊({group_id})未开启自动下载，无需重复操作。")
