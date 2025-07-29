import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import AlconnaMatcher

from zhenxun.services.log import logger

from ..config import MAX_CONCURRENT_DOWNLOADS


@dataclass
class DownloadTask:
    """封装一个下载任务所需的所有信息 (移除 matcher)"""

    bot: Bot
    event: Event
    info_model: Any
    is_manual: bool


class DownloadManager:
    """下载管理器，负责队列和并发控制"""

    def __init__(self):
        self._initialized = False
        self.queue: asyncio.Queue[DownloadTask] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.semaphore: Optional[asyncio.Semaphore] = None

    def initialize(self):
        """初始化下载管理器，启动工作者协程"""
        if self._initialized:
            return

        max_concurrent = MAX_CONCURRENT_DOWNLOADS
        num_workers = max_concurrent

        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.workers = [asyncio.create_task(self._worker()) for _ in range(num_workers)]
        self._initialized = True
        logger.info(
            f"下载管理器已启动，工作者数量: {num_workers}, 最大并发数: {max_concurrent}"
        )

    async def add_task(
        self, task: DownloadTask, matcher: Optional[AlconnaMatcher] = None
    ):
        """将新任务添加到下载队列，并使用传入的 matcher (如果存在) 通知用户"""
        queue_size_before_add = self.queue.qsize()
        await self.queue.put(task)

        if matcher:
            if queue_size_before_add > 0:
                await matcher.send(
                    f"“{task.info_model.title}”已加入下载队列，当前有 {queue_size_before_add} 个任务在您之前。"
                )

    async def _worker(self):
        """
        工作者协程，从队列中获取任务，通过信号量控制并发，并执行下载。
        现在使用 bot.send() 来发送所有状态更新。
        """
        from .download_service import DownloadService

        while True:
            task = await self.queue.get()

            try:
                logger.info(f"工作者获取到任务: {task.info_model.title}, 等待信号量...")
                async with self.semaphore:
                    logger.info(f"信号量已获取，开始处理任务: {task.info_model.title}")

                    if task.is_manual:
                        try:
                            await task.bot.send(
                                task.event, f"▶️ 开始下载: {task.info_model.title}"
                            )
                        except Exception as send_err:
                            logger.warning(f"发送'开始下载'消息失败: {send_err}")

                    await DownloadService.execute_download(
                        task.bot,
                        task.event,
                        task.info_model,
                        task.is_manual,
                    )

            except Exception as e:
                logger.error(f"下载任务 '{task.info_model.title}' 执行失败", e=e)
                if task.is_manual:
                    try:
                        error_message = getattr(e, "message", str(e))
                        await task.bot.send(
                            task.event,
                            f"❌ 下载“{task.info_model.title}”失败: {error_message}",
                        )
                    except Exception as send_err:
                        logger.error(f"发送下载失败消息也失败了: {send_err}")
            finally:
                self.queue.task_done()


download_manager = DownloadManager()
