import asyncio
import time
from pathlib import Path
from typing import List

from zhenxun.services.log import logger

from ..config import base_config, PLUGIN_TEMP_DIR


class FileCleaner:
    """临时文件清理服务"""

    FILE_EXPIRY = {
        "bili_video_cover_": 1,
        "bili_avatar_": 7,
        "bili_live_cover_": 1,
        "bili_live_keyframe_": 0.04,
        "bili_article_": 1,
        "bili_opus_": 1,
        "bili_video_": 1,
    }

    _clean_lock = asyncio.Lock()

    _last_clean_time = 0

    _CLEAN_INTERVAL = 3600

    @classmethod
    async def initialize(cls):
        """初始化文件清理服务"""
        logger.info("正在初始化文件清理服务...", "B站解析")

        video_expiry_days = base_config.get("VIDEO_FILE_EXPIRY_DAYS", 1)
        auto_clean_enabled = video_expiry_days > 0
        enabled_text = "启用"
        disabled_text = "禁用"
        logger.info(
            f"自动清理功能状态: {enabled_text if auto_clean_enabled else disabled_text}",
            "B站解析",
        )

        minutes = base_config.get("FILE_CLEAN_INTERVAL", 60)
        cls._CLEAN_INTERVAL = minutes * 60
        logger.info(
            f"设置文件清理间隔为 {minutes} 分钟 ({cls._CLEAN_INTERVAL} 秒)", "B站解析"
        )

        video_expiry_days = base_config.get("VIDEO_FILE_EXPIRY_DAYS", 1)
        cls.FILE_EXPIRY["bili_video_"] = video_expiry_days
        logger.info(f"设置视频文件过期时间为 {video_expiry_days} 天", "B站解析")

        if not PLUGIN_TEMP_DIR.exists():
            logger.warning(f"临时文件目录不存在: {PLUGIN_TEMP_DIR}", "B站解析")
            PLUGIN_TEMP_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"已创建临时文件目录: {PLUGIN_TEMP_DIR}", "B站解析")
        else:
            logger.info(
                f"临时文件目录: {PLUGIN_TEMP_DIR} (绝对路径: {PLUGIN_TEMP_DIR.absolute()})",
                "B站解析",
            )

        if auto_clean_enabled:
            task = asyncio.create_task(cls._auto_clean_task())
            task.set_name("bilibili_file_cleaner")
            logger.info("临时文件自动清理服务已启动", "B站解析")
        else:
            logger.warning("自动清理功能已禁用，不会启动清理任务", "B站解析")

    @classmethod
    async def _auto_clean_task(cls):
        """自动清理任务"""
        logger.info(
            f"自动清理任务启动，间隔: {cls._CLEAN_INTERVAL // 60} 分钟", "B站解析"
        )

        while True:
            try:
                cleaned = await cls.clean_expired_files(force=True)
                logger.info(
                    f"自动清理完成，清理了 {cleaned} 个文件，下次清理将在 {cls._CLEAN_INTERVAL // 60} 分钟后进行",
                    "B站解析",
                )

                await asyncio.sleep(cls._CLEAN_INTERVAL)
            except Exception as e:
                logger.error(f"自动清理任务出错: {e}", "B站解析")
                await asyncio.sleep(60)

    @classmethod
    async def clean_expired_files(cls, force: bool = False) -> int:
        """
        清理过期的临时文件

        Args:
            force: 是否强制清理，忽略时间间隔限制

        Returns:
            清理的文件数量
        """
        current_time = time.time()
        if not force and current_time - cls._last_clean_time < cls._CLEAN_INTERVAL:
            minutes = cls._CLEAN_INTERVAL // 60
            logger.debug(f"距离上次清理不足 {minutes} 分钟，跳过清理", "B站解析")
            return 0

        async with cls._clean_lock:
            cls._last_clean_time = current_time

            if not PLUGIN_TEMP_DIR.exists():
                logger.warning(f"临时文件目录不存在: {PLUGIN_TEMP_DIR}", "B站解析")
                PLUGIN_TEMP_DIR.mkdir(parents=True, exist_ok=True)
                logger.info(f"已创建临时文件目录: {PLUGIN_TEMP_DIR}", "B站解析")

            logger.debug(
                f"清理目录: {PLUGIN_TEMP_DIR} (绝对路径: {PLUGIN_TEMP_DIR.absolute()})",
                "B站解析",
            )

            temp_files = list(PLUGIN_TEMP_DIR.glob("bili_*.*"))
            logger.debug(f"找到 {len(temp_files)} 个匹配的文件", "B站解析")

            if not temp_files:
                logger.debug("没有找到需要清理的临时文件", "B站解析")
                return 0

            files_by_prefix: dict[str, List[Path]] = {}
            for file in temp_files:
                for prefix in cls.FILE_EXPIRY:
                    if file.name.startswith(prefix):
                        if prefix not in files_by_prefix:
                            files_by_prefix[prefix] = []
                        files_by_prefix[prefix].append(file)
                        break

            cleaned_count = 0
            for prefix, files in files_by_prefix.items():
                expiry_days = cls.FILE_EXPIRY.get(prefix, 1)
                expiry_seconds = expiry_days * 86400

                logger.debug(
                    f"文件类型 {prefix} 的过期时间为 {expiry_days} 天 ({expiry_seconds} 秒)",
                    "B站解析",
                )

                for file in files:
                    try:
                        mtime = file.stat().st_mtime
                        file_age_seconds = current_time - mtime
                        file_age_days = file_age_seconds / 86400

                        if file_age_seconds > expiry_seconds:
                            logger.debug(
                                f"文件 {file.name} 已存在 {file_age_days:.2f} 天，超过过期时间 {expiry_days} 天",
                                "B站解析",
                            )
                            file.unlink()
                            cleaned_count += 1
                            logger.debug(f"已清理过期文件: {file.name}", "B站解析")
                    except Exception as e:
                        logger.warning(f"清理文件 {file.name} 时出错: {e}", "B站解析")

            if cleaned_count > 0:
                logger.info(
                    f"临时文件清理完成，共清理 {cleaned_count} 个文件", "B站解析"
                )
            else:
                logger.debug("没有找到过期的临时文件", "B站解析")

            return cleaned_count

    @classmethod
    async def clean_all_temp_files(cls) -> int:
        """
        清理所有B站相关临时文件

        Returns:
            清理的文件数量
        """
        async with cls._clean_lock:
            temp_files = list(PLUGIN_TEMP_DIR.glob("bili_*.*"))
            if not temp_files:
                logger.debug("没有找到需要清理的临时文件", "B站解析")
                return 0

            cleaned_count = 0
            for file in temp_files:
                try:
                    file.unlink()
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"清理文件 {file.name} 时出错: {e}", "B站解析")

            logger.info(
                f"所有临时文件清理完成，共清理 {cleaned_count} 个文件", "B站解析"
            )
            return cleaned_count
