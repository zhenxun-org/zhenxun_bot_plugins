import asyncio
from pathlib import Path
from typing import Optional, Tuple

from zhenxun.services.log import logger

from ..config import PLUGIN_TEMP_DIR


async def merge_media_files(
    video_path: Path,
    audio_path: Optional[Path],
    output_path: Path,
    log_output: bool = False,
) -> bool:
    """
    合并音视频文件，并确保 FFmpeg 进程在任何情况下都能被正确终止。
    - 优先尝试直接复制所有流。
    - 如果失败，则回退到仅重新编码音频流的模式，以解决兼容性问题并保持性能。
    - 完成后自动清理临时文件。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        logger.error(f"视频文件不存在: {video_path}")
        return False

    if audio_path and not audio_path.exists():
        logger.error(f"音频文件不存在: {audio_path}")
        return False

    async def _run_ffmpeg(vcodec: str, acodec: str) -> Tuple[bool, str]:
        """运行FFmpeg命令并确保其进程被管理"""
        command = ["ffmpeg", "-y", "-i", str(video_path.resolve())]
        if audio_path:
            command.extend(["-i", str(audio_path.resolve())])

        command.extend(["-c:v", vcodec])
        if audio_path:
            command.extend(["-c:a", acodec])

        command.extend(["-nostdin", "-loglevel", "error", str(output_path.resolve())])

        logger.info(f"执行FFmpeg命令: {' '.join(command)}")

        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE
                if log_output
                else asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            error_msg = stderr.decode("utf-8", errors="ignore") if stderr else ""

            if process.returncode != 0:
                logger.error(
                    f"FFmpeg执行失败 (vcodec={vcodec}, acodec={acodec}): {error_msg}"
                )
                return False, error_msg

            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error(f"FFmpeg执行后文件不存在或为空: {output_path}")
                return False, "输出文件为空"

            return True, ""

        finally:
            if process and process.returncode is None:
                logger.warning(f"FFmpeg 进程 ({process.pid}) 未正常结束，将强制终止。")
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"终止 FFmpeg 进程 ({process.pid}) 超时，将强制杀死。"
                    )
                    process.kill()
                except Exception as e:
                    logger.error(f"终止/杀死 FFmpeg 进程时出错: {e}")

    try:
        logger.info("尝试快速合并 (stream copy)...")
        success, error_log = await _run_ffmpeg("copy", "copy" if audio_path else "")

        if not success:
            logger.warning(
                f"快速合并失败，回退到音频重编码模式。失败原因: {error_log[:200]}..."
            )
            success, error_log = await _run_ffmpeg("copy", "aac" if audio_path else "")

        if success:
            logger.info(f"媒体文件处理成功: {output_path.name}")
        else:
            logger.error(f"所有合并策略均失败。最终错误: {error_log[:200]}")

        return success

    finally:
        for path_to_delete in (video_path, audio_path):
            if not (path_to_delete and path_to_delete.exists()):
                continue

            for attempt in range(3):
                try:
                    path_to_delete.unlink()
                    logger.debug(f"成功清理临时文件: {path_to_delete.name}")
                    break
                except PermissionError:
                    if attempt < 2:
                        await asyncio.sleep(0.1 * (attempt + 1))
                    else:
                        logger.warning(
                            f"清理临时文件失败 (文件被占用): {path_to_delete.name}"
                        )
                except Exception as e:
                    logger.warning(f"清理临时文件时发生未知错误: {e}")
                    break


def get_temp_file_path(
    prefix: str,
    suffix: str,
    identifier: str,
    title: Optional[str] = None,
) -> Path:
    """生成临时文件路径"""
    filename = f"{prefix}{identifier}{suffix}"
    return PLUGIN_TEMP_DIR / filename


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
    except Exception as e:
        logger.debug(f"检查FFmpeg可用性失败: {e}", e=e)
        return False
