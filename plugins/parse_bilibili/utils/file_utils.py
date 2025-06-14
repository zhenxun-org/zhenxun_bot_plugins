import asyncio
import aiofiles
import httpx
from pathlib import Path
from typing import Optional, Dict

from zhenxun.services.log import logger

from ..config import PLUGIN_TEMP_DIR
from ..services.network_service import async_handle_errors


async def _download_file_core(
    url: str,
    file_path: Path,
    headers: Optional[Dict[str, str]] = None,
    proxies: Optional[Dict[str, str]] = None,
    chunk_size: int = 8192,
    timeout: int = 60,
) -> bool:
    """核心下载逻辑，不包含重试机制"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    download_timeout = httpx.Timeout(timeout)

    current_size = 0
    if file_path.exists():
        current_size = file_path.stat().st_size
        if current_size > 0:
            logger.info(
                f"文件已存在，尝试断点续传: {file_path.name}, 已下载: {current_size / 1024 / 1024:.2f}MB"
            )
            if headers is None:
                headers = {}
            headers["Range"] = f"bytes={current_size}-"

    async with httpx.AsyncClient(
        headers=headers,
        proxies=proxies,
        timeout=download_timeout,
        follow_redirects=True,
    ) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()

            if current_size > 0 and resp.status_code == 206:
                logger.debug(f"服务器支持断点续传，从 {current_size} 字节继续下载")
            elif current_size > 0 and resp.status_code == 200:
                logger.warning("服务器不支持断点续传，将重新下载完整文件")
                current_size = 0

            total_len = int(resp.headers.get("content-length", 0))
            if resp.status_code == 206:
                total_len += current_size

            mode = "ab" if current_size > 0 and resp.status_code == 206 else "wb"
            downloaded_size = current_size

            async with aiofiles.open(file_path, mode) as f:
                async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
                    await f.write(chunk)
                    downloaded_size += len(chunk)

            if total_len == 0 or downloaded_size == total_len:
                logger.debug(
                    f"文件流下载完成: {file_path.name}, 大小: {downloaded_size / 1024 / 1024:.2f}MB"
                )
                return True
            else:
                logger.warning(
                    f"文件下载不完整: {file_path.name}, {downloaded_size}/{total_len} ({downloaded_size / total_len * 100:.1f}%)"
                )
                raise Exception(f"文件下载不完整: {downloaded_size}/{total_len}")


async def download_file(
    url: str,
    file_path: Path,
    headers: Optional[Dict[str, str]] = None,
    proxies: Optional[Dict[str, str]] = None,
    chunk_size: int = 8192,
    timeout: int = 60,
    max_retries: int = 3,
) -> bool:
    """下载文件（使用统一重试机制）"""
    from .common import retry_async, RetryConfig

    async def _download_wrapper():
        return await _download_file_core(
            url, file_path, headers, proxies, chunk_size, timeout
        )

    config = RetryConfig.download_default()
    config.max_attempts = max_retries
    config.exceptions = (
        httpx.HTTPError,
        httpx.RequestError,
        asyncio.TimeoutError,
        Exception,
    )

    try:
        return await retry_async(_download_wrapper, config=config)
    except Exception as e:
        logger.error(f"下载失败: {file_path.name}, 错误: {e}")
        return False


@async_handle_errors(
    error_msg="音视频合并失败",
    log_level="error",
    reraise=False,
    default_return=False,
)
async def merge_media_files(
    video_path: Path,
    audio_path: Optional[Path],
    output_path: Path,
    use_copy_codec: bool = False,
    log_output: bool = False,
) -> bool:
    """合并音视频文件"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        logger.error(f"视频文件不存在: {video_path}")
        return False

    if audio_path and not audio_path.exists():
        logger.error(f"音频文件不存在: {audio_path}")
        return False

    actual_use_copy_codec = use_copy_codec

    if audio_path:
        if actual_use_copy_codec:
            logger.info(f"开始快速合并音视频 (copy codec) 到: {output_path.name}")
            command = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path.resolve()),
                "-i",
                str(audio_path.resolve()),
                "-c",
                "copy",
                "-loglevel",
                "error" if not log_output else "info",
                str(output_path.resolve()),
            ]
        else:
            logger.info(
                f"开始合并音视频并编码为 H.264 (可能耗时较长) 到: {output_path.name}"
            )
            command = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path.resolve()),
                "-i",
                str(audio_path.resolve()),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-loglevel",
                "error" if not log_output else "info",
                str(output_path.resolve()),
            ]
    else:
        if actual_use_copy_codec:
            logger.info(f"开始转换视频文件 (copy codec) 到: {output_path.name}")
            command = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path.resolve()),
                "-c",
                "copy",
                "-loglevel",
                "error" if not log_output else "info",
                str(output_path.resolve()),
            ]
        else:
            logger.info(f"开始转换视频文件并编码为 H.264 到: {output_path.name}")
            command = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path.resolve()),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-loglevel",
                "error" if not log_output else "info",
                str(output_path.resolve()),
            ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE if log_output else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode("utf-8", errors="ignore") if stderr else "未知错误"
        logger.error(f"FFmpeg合并失败: {error_msg}")
        return False

    if not output_path.exists() or output_path.stat().st_size == 0:
        logger.error(f"FFmpeg合并后文件不存在或为空: {output_path}")
        return False

    if audio_path:
        logger.info(f"音视频合并成功: {output_path.name}")
    else:
        logger.info(f"视频转换成功: {output_path.name}")
    return True


def get_temp_file_path(
    prefix: str,
    suffix: str,
    identifier: str,
    title: Optional[str] = None,
) -> Path:
    """生成临时文件路径"""
    filename = f"{prefix}{identifier}{suffix}"
    return PLUGIN_TEMP_DIR / filename


@async_handle_errors(
    error_msg="检查FFmpeg可用性失败",
    log_level="debug",
    reraise=False,
    default_return=False,
)
async def check_ffmpeg_available() -> bool:
    """检查FFmpeg是否可用"""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate()
        is_available = process.returncode == 0

        if is_available:
            logger.debug("FFmpeg可用", "B站解析")
        else:
            logger.warning("FFmpeg不可用，返回码非零", "B站解析")

        return is_available
    except FileNotFoundError:
        logger.warning(
            "FFmpeg未找到，请确保已安装FFmpeg并添加到PATH环境变量", "B站解析"
        )
        return False
