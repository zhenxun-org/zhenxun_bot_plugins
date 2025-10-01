from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse
import asyncio
from dataclasses import dataclass

from bilibili_api import bangumi, video
from nonebot import get_driver
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import AlconnaMatcher

from zhenxun.services.log import logger

from ..config import (
    MAX_CONCURRENT_DOWNLOADS,
    PLUGIN_TEMP_DIR,
    base_config,
    get_credential,
)
from ..model import SeasonInfo, VideoInfo
from ..utils.exceptions import BilibiliBaseException, DownloadError, MediaProcessError
from ..utils.file_utils import merge_media_files
from ..utils.message import send_video_with_retry
from .cache_service import CacheService, VIDEO_CACHE_DIR
from .network_service import download_bilibili_file


@dataclass
class DownloadTask:
    """封装一个下载任务所需的所有信息"""

    bot: Bot
    event: Event
    info_model: Any
    is_manual: bool


class DownloadManager:
    """下载管理器，负责队列、并发控制和任务执行"""

    def __init__(self):
        self._initialized = False
        self.active_tasks: set[asyncio.Task] = set()
        self.semaphore: Optional[asyncio.Semaphore] = None

    def initialize(self):
        """初始化下载管理器，启动工作者协程"""
        if self._initialized:
            return
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self._initialized = True
        logger.info(f"下载管理器已初始化，最大并发数: {MAX_CONCURRENT_DOWNLOADS}")

    async def add_task(
        self, task: DownloadTask, matcher: Optional[AlconnaMatcher] = None
    ):
        """为下载任务创建后台任务，并进行并发控制"""
        if matcher and self.semaphore and self.semaphore.locked():
            await matcher.send(
                f'"{task.info_model.title}" 已加入下载任务，正在等待空闲下载位...'
            )

        new_task = asyncio.create_task(self._task_wrapper(task))
        self.active_tasks.add(new_task)
        new_task.add_done_callback(self.active_tasks.discard)

    async def _task_wrapper(self, task: DownloadTask):
        """
        包装单个下载任务的完整生命周期，包括并发控制、消息通知和异常处理。
        """
        try:
            logger.info(f"任务: {task.info_model.title}, 等待信号量...")
            assert self.semaphore is not None
            async with self.semaphore:
                logger.info(f"信号量已获取，开始处理任务: {task.info_model.title}")
                if task.is_manual:
                    try:
                        await task.bot.send(
                            task.event, f"▶️ 开始下载: {task.info_model.title}"
                        )
                    except Exception as send_err:
                        logger.warning(f"发送'开始下载'消息失败: {send_err}")
                await self._execute_download(
                    task.bot, task.event, task.info_model, task.is_manual
                )
        except Exception as e:
            logger.error(f"下载任务 '{task.info_model.title}' 执行失败", e=e)
            if task.is_manual:
                try:
                    error_message = getattr(e, "message", str(e))
                    await task.bot.send(
                        task.event,
                        f'❌ 下载"{task.info_model.title}"失败: {error_message}',
                    )
                except Exception as send_err:
                    logger.error(f"发送下载失败消息也失败了: {send_err}")

    @staticmethod
    def _estimate_video_size(
        video_stream: Dict[str, Any],
        audio_stream: Optional[Dict[str, Any]],
        duration_seconds: float,
    ) -> float:
        """估算视频大小（MB）"""
        video_size_bytes = video_stream.get("size", 0) or (
            video_stream.get("bandwidth", 0) / 8 * duration_seconds
        )
        audio_size_bytes = 0
        if audio_stream:
            audio_size_bytes = audio_stream.get("size", 0) or (
                audio_stream.get("bandwidth", 0) / 8 * duration_seconds
            )

        return (video_size_bytes + audio_size_bytes) / (1024 * 1024)

    @staticmethod
    def _select_appropriate_quality(
        video_streams: List[Dict[str, Any]],
        audio_streams: List[Dict[str, Any]],
        duration_seconds: float,
        max_size_mb: float = 100.0,
        initial_quality_id: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], bool]:
        """根据大小限制选择合适的视频和音频流"""
        quality_preference = [120, 116, 112, 80, 74, 64, 32, 16]
        quality_reduced = False

        if not video_streams:
            raise DownloadError("没有可用的视频流列表。")

        best_audio = (
            max(audio_streams, key=lambda s: s.get("bandwidth", 0))
            if audio_streams
            else None
        )

        available_streams = sorted(
            [s for s in video_streams if s.get("id") in quality_preference],
            key=lambda s: quality_preference.index(s.get("id")),  # type: ignore
        )
        if initial_quality_id:
            available_streams = [
                s for s in available_streams if s.get("id", 0) <= initial_quality_id
            ]

        if not available_streams:
            available_streams = sorted(
                video_streams, key=lambda s: s.get("id", 0), reverse=True
            )

        selected_video = available_streams[0]
        original_quality_id = selected_video.get("id", 0)

        estimated_size = DownloadManager._estimate_video_size(
            selected_video, best_audio, duration_seconds
        )
        logger.debug(
            f"初始视频流质量: {original_quality_id}, 估算大小: {estimated_size:.2f}MB"
        )

        if estimated_size > max_size_mb:
            quality_reduced = True
            for stream in available_streams[1:]:
                new_size = DownloadManager._estimate_video_size(
                    stream, best_audio, duration_seconds
                )
                logger.debug(
                    f"尝试降低清晰度: {stream.get('id')}, 估算大小: {new_size:.2f}MB"
                )
                if new_size <= max_size_mb:
                    selected_video = stream
                    logger.info(
                        f"视频大小超过限制({estimated_size:.2f}MB > {max_size_mb}MB)，已自动降低清晰度: {original_quality_id} -> {selected_video.get('id')}"
                    )
                    return selected_video, best_audio, quality_reduced

            selected_video = available_streams[-1]
            logger.warning(
                f"即使使用最低可用清晰度({selected_video.get('id')})，估算大小仍超过限制。将继续下载。"
            )

        return selected_video, best_audio, quality_reduced

    @staticmethod
    def _check_duration(
        duration_seconds: float, max_duration_minutes: int, user_id: str
    ) -> None:
        """检查视频时长是否超过限制"""
        if max_duration_minutes <= 0:
            return

        superusers = get_driver().config.superusers
        if user_id in superusers:
            logger.debug(f"用户 {user_id} 是超级用户，不受时长限制")
            return

        duration_minutes = round(duration_seconds / 60, 1)
        if duration_seconds > max_duration_minutes * 60:
            error_msg = (
                f"视频时长 {duration_minutes}分钟 超过限制 {max_duration_minutes}分钟"
            )
            logger.warning(error_msg)
            raise DownloadError(error_msg)

    async def _execute_download(
        self,
        bot: Bot,
        event: Event,
        info_model: Any,
        is_manual: bool,
    ) -> None:
        """根据模型类型分发到具体的下载方法"""
        if isinstance(info_model, VideoInfo):
            await self._download_video(bot, event, info_model, is_manual)
        elif isinstance(info_model, SeasonInfo):
            await self._download_bangumi(bot, event, info_model)
        else:
            raise BilibiliBaseException(
                f"不支持下载此类型的内容: {type(info_model).__name__}"
            )

    async def _download_video(
        self,
        bot: Bot,
        event: Event,
        video_info: VideoInfo,
        is_manual: bool,
    ) -> None:
        """执行普通视频的下载、合并和发送"""
        video_id = video_info.bvid or f"av{video_info.aid}"
        page_num = 0
        parsed_url = urlparse(video_info.parsed_url)
        if parsed_url.query:
            query_params = parse_qs(parsed_url.query)
            if p_value := query_params.get("p"):
                if p_value[0].isdigit():
                    page_num = int(p_value[0]) - 1

        logger.info(
            f"开始处理视频: {video_info.title} (ID: {video_id}, P{page_num + 1})"
        )

        if cached_file := await CacheService.get_video_cache(video_id, page_num):
            logger.info(f"使用缓存视频: {cached_file.name}")
            await send_video_with_retry(bot, event, cached_file)
            return

        max_duration_key = (
            "MANUAL_DOWNLOAD_MAX_DURATION"
            if is_manual
            else "AUTO_DOWNLOAD_MAX_DURATION"
        )
        max_duration = base_config.get(max_duration_key, 0)
        self._check_duration(video_info.duration, max_duration, event.get_user_id())

        v = video.Video(
            bvid=video_info.bvid, aid=video_info.aid, credential=get_credential()
        )
        download_url_data = await v.get_download_url(page_index=page_num)

        if not (dash_info := download_url_data.get("dash")):
            raise DownloadError("无法获取DASH信息", context={"video_id": video_id})

        if not (video_streams := dash_info.get("video", [])):
            raise DownloadError("没有可用的视频流", context={"video_id": video_id})

        audio_streams = dash_info.get("audio", [])

        target_quality = base_config.get("VIDEO_DOWNLOAD_QUALITY", 80)
        max_size_mb = base_config.get("MAX_DOWNLOAD_SIZE_MB", 100)

        selected_video_stream, selected_audio_stream, _ = (
            self._select_appropriate_quality(
                video_streams,
                audio_streams,
                video_info.duration,
                max_size_mb,
                target_quality,
            )
        )

        video_url = selected_video_stream.get("baseUrl")
        audio_url = (
            selected_audio_stream.get("baseUrl") if selected_audio_stream else None
        )

        if not video_url:
            raise DownloadError(
                "未能选择有效的视频流URL", context={"video_id": video_id}
            )

        base_filename = f"bili_video_{video_id}_P{page_num + 1}"
        v_stream_path = PLUGIN_TEMP_DIR / f"{base_filename}-video.m4s"
        a_stream_path = (
            PLUGIN_TEMP_DIR / f"{base_filename}-audio.m4s" if audio_url else None
        )

        cache_filename = f"{video_id}_P{page_num + 1}.mp4"
        output_mp4_path = VIDEO_CACHE_DIR / cache_filename

        try:
            dl_tasks = [download_bilibili_file(video_url, v_stream_path)]
            if audio_url and a_stream_path:
                dl_tasks.append(download_bilibili_file(audio_url, a_stream_path))

            logger.info(f"开始并行下载 {len(dl_tasks)} 个视频媒体流...")
            if not all(await asyncio.gather(*dl_tasks)):
                raise DownloadError(f"下载视频媒体流失败: {video_id}")

            merge_success = await merge_media_files(
                v_stream_path, a_stream_path, output_mp4_path
            )
            if not merge_success:
                raise MediaProcessError("FFmpeg合并或编码失败")

            logger.info(f"视频处理成功: {output_mp4_path.name}")
            await CacheService.save_video_to_cache(video_id, page_num, output_mp4_path)
            await send_video_with_retry(bot, event, output_mp4_path)
        finally:
            if v_stream_path.exists():
                v_stream_path.unlink(missing_ok=True)
            if a_stream_path and a_stream_path.exists():
                a_stream_path.unlink(missing_ok=True)

    async def _download_bangumi(
        self,
        bot: Bot,
        event: Event,
        season_info: SeasonInfo,
    ) -> None:
        """执行番剧的下载、合并和发送"""

        ep_id = season_info.target_ep_id
        duration_seconds = 0
        video_obj = None
        if ep_id is None:
            raise DownloadError("番剧分集ID (ep_id) 未找到")
        try:
            ep = bangumi.Episode(epid=ep_id, credential=get_credential())
            video_obj = await ep.turn_to_video()
            video_detail_info = await video_obj.get_info()
            duration_seconds = video_detail_info.get("duration", 0)

            if duration_seconds > 0:
                logger.info(f"成功获取番剧分集 ep{ep_id} 的时长: {duration_seconds}秒")
            else:
                logger.warning(
                    f"获取番剧分集 ep{ep_id} 时长为0，将无法进行大小估算和时长检查。"
                )
        except Exception as e:
            logger.warning(
                f"获取番剧分集时长时发生错误，将无法进行大小估算和时长检查: {e}", e=e
            )

        if duration_seconds > 0:
            self._check_duration(
                duration_seconds,
                base_config.get("MANUAL_DOWNLOAD_MAX_DURATION", 0),
                event.get_user_id(),
            )

        title = f"{season_info.title}"
        if season_info.target_ep_long_title:
            title += f" - {season_info.target_ep_long_title}"

        if video_obj is None:
            ep = bangumi.Episode(epid=ep_id, credential=get_credential())
            video_obj = await ep.turn_to_video()
        play_info = await video_obj.get_download_url(page_index=0)

        downloaded_file_path: Optional[Path] = None

        if "dash" in play_info and (dash_info := play_info.get("dash")):
            logger.debug("处理 DASH 流")
            if not (video_streams := dash_info.get("video", [])):
                raise DownloadError("没有可用的视频流")
            audio_streams = dash_info.get("audio", [])

            target_quality = base_config.get("VIDEO_DOWNLOAD_QUALITY", 80)
            max_size_mb = base_config.get("MAX_DOWNLOAD_SIZE_MB", 100)

            selected_video_stream, selected_audio_stream, _ = (
                self._select_appropriate_quality(
                    video_streams,
                    audio_streams,
                    duration_seconds,
                    max_size_mb,
                    target_quality,
                )
            )

            video_url = selected_video_stream.get(
                "baseUrl"
            ) or selected_video_stream.get("base_url")
            audio_url = (
                (
                    selected_audio_stream.get("baseUrl")
                    or selected_audio_stream.get("base_url")
                )
                if selected_audio_stream
                else None
            )

            if not video_url:
                raise DownloadError("无法获取视频流 URL")

            v_stream_path = PLUGIN_TEMP_DIR / f"bili_bangumi_ep{ep_id}-video.m4s"
            a_stream_path = (
                PLUGIN_TEMP_DIR / f"bili_bangumi_ep{ep_id}-audio.m4s"
                if audio_url
                else None
            )
            output_path = PLUGIN_TEMP_DIR / f"bili_bangumi_ep{ep_id}.mp4"

            logger.info(f"开始并行下载 {1 + (1 if audio_url else 0)} 个番剧媒体流...")
            dl_tasks = [download_bilibili_file(video_url, v_stream_path)]
            if audio_url and a_stream_path:
                dl_tasks.append(download_bilibili_file(audio_url, a_stream_path))

            if not all(await asyncio.gather(*dl_tasks)):
                raise DownloadError(f"下载番剧媒体流失败: ep{ep_id}")

            logger.info("番剧音视频流下载完成，开始合并...")
            if not await merge_media_files(
                video_path=v_stream_path,
                audio_path=a_stream_path,
                output_path=output_path,
            ):
                raise MediaProcessError("番剧合并失败")
            downloaded_file_path = output_path

        elif "durl" in play_info and (durl_info := play_info.get("durl")):
            logger.debug("处理 DURL 流 (FLV/MP4)")
            url = durl_info[0].get("url")
            if not url:
                raise DownloadError("无法获取 DURL URL")
            ext = ".flv" if ".flv" in url else ".mp4"
            output_path = PLUGIN_TEMP_DIR / f"bili_bangumi_ep{ep_id}{ext}"
            logger.info(f"开始下载 DURL 流: {title}{ext}")
            dl_ok = await download_bilibili_file(url, output_path)
            if not dl_ok:
                raise DownloadError("DURL 流下载失败")
            downloaded_file_path = output_path
        else:
            raise DownloadError("不支持的播放信息格式")

        if downloaded_file_path and downloaded_file_path.exists():
            logger.info(f"番剧下载成功: {downloaded_file_path}")
            await send_video_with_retry(bot, event, output_path)
            if downloaded_file_path.exists():
                downloaded_file_path.unlink()
        else:
            raise DownloadError("番剧文件下载失败或文件不存在")


download_manager = DownloadManager()
