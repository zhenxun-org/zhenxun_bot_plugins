import asyncio
import time
from typing import Dict, Optional, Callable, Awaitable, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
import heapq

from nonebot import get_driver
from zhenxun.services.log import logger

MAX_CONCURRENT_TASKS = 5  # 增加并发任务数
TASK_QUEUE_SIZE = 200  # 增加队列大小
DEFAULT_TIMEOUT = 1200  # 增加超时时间到20分钟
EXECUTOR_MAX_WORKERS = 20  # 增加线程池大小


class TaskPriority:
    """任务优先级定义"""

    HIGH = 0
    NORMAL = 1
    LOW = 2


class TaskStatus:
    """任务状态定义"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class Task:
    """任务类，表示一个需要执行的任务"""

    def __init__(
        self,
        task_id: str,
        func: Callable[..., Awaitable[Any]],
        args: Tuple = None,
        kwargs: Dict = None,
        priority: int = TaskPriority.NORMAL,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.task_id = task_id
        self.func = func
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.priority = priority
        self.timeout = timeout
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.create_time = time.time()
        self.start_time = None
        self.end_time = None

    def __lt__(self, other):
        """用于优先级队列比较"""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.create_time < other.create_time


class TaskManager:
    """任务管理器"""

    _instance = None

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    def __init__(self):
        self.task_queue = []
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.completed_tasks: Dict[str, Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=EXECUTOR_MAX_WORKERS)
        self.lock = asyncio.Lock()
        self.running = False
        self.worker_task = None

    async def start(self):
        """启动管理器"""
        if self.running:
            return

        self.running = True
        self.worker_task = asyncio.create_task(self._worker())
        logger.info("任务管理器已启动")

    async def stop(self):
        """停止管理器"""
        if not self.running:
            return

        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None

        for task_id, task in list(self.running_tasks.items()):
            task.cancel()

        self.executor.shutdown(wait=False)
        logger.info("任务管理器已停止")

    async def add_task(
        self,
        task_id: str,
        func: Callable[..., Awaitable[Any]],
        args: Tuple = None,
        kwargs: Dict = None,
        priority: int = TaskPriority.NORMAL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> bool:
        """添加任务到队列"""
        if len(self.task_queue) >= TASK_QUEUE_SIZE:
            logger.warning(f"任务队列已满，无法添加任务: {task_id}")
            return False

        task = Task(task_id, func, args, kwargs, priority, timeout)

        async with self.lock:
            heapq.heappush(self.task_queue, task)

        logger.debug(f"已添加任务到队列: {task_id}, 优先级: {priority}")
        return True

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        async with self.lock:
            for i, task in enumerate(self.task_queue):
                if task.task_id == task_id:
                    self.task_queue.pop(i)
                    heapq.heapify(self.task_queue)
                    logger.debug(f"已从队列中取消任务: {task_id}")
                    return True

        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            logger.debug(f"已取消正在运行的任务: {task_id}")
            return True

        return False

    async def get_task_status(self, task_id: str) -> Optional[str]:
        """获取任务状态"""
        async with self.lock:
            for task in self.task_queue:
                if task.task_id == task_id:
                    return task.status

        if task_id in self.running_tasks:
            return TaskStatus.RUNNING

        if task_id in self.completed_tasks:
            return self.completed_tasks[task_id].status

        return None

    async def get_queue_info(self) -> Dict:
        """获取队列信息"""
        async with self.lock:
            pending_count = len(self.task_queue)

        running_count = len(self.running_tasks)
        completed_count = len(self.completed_tasks)

        return {
            "pending": pending_count,
            "running": running_count,
            "completed": completed_count,
            "total": pending_count + running_count + completed_count,
        }

    async def _worker(self):
        """工作线程"""
        while self.running:
            try:
                if len(self.running_tasks) >= MAX_CONCURRENT_TASKS:
                    await asyncio.sleep(0.1)
                    continue

                task = None
                try:
                    async with self.lock:
                        if self.task_queue:
                            task = heapq.heappop(self.task_queue)
                except Exception as e:
                    logger.error("从任务队列获取任务失败", e=e)
                    await asyncio.sleep(1)
                    continue

                if not task:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    asyncio_task = asyncio.create_task(self._execute_task(task))
                    self.running_tasks[task.task_id] = asyncio_task

                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"创建任务执行失败: {task.task_id}", e=e)

            except asyncio.CancelledError:
                logger.info("任务管理器工作线程被取消")
                break
            except Exception as e:
                logger.error("任务管理器工作线程发生未处理异常", e=e)
                await asyncio.sleep(1)

        logger.debug("任务管理器工作线程已退出")

    async def _execute_task(self, task: Task):
        """执行任务"""
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()

        try:
            shielded_task = asyncio.shield(task.func(*task.args, **task.kwargs))

            try:
                result = await asyncio.wait_for(shielded_task, timeout=task.timeout)

                task.result = result
                task.status = TaskStatus.COMPLETED
                logger.debug(f"任务执行成功: {task.task_id}")

            except asyncio.TimeoutError:
                task.status = TaskStatus.TIMEOUT
                task.error = "Task execution timed out"
                logger.warning(f"任务执行超时: {task.task_id}")

            except asyncio.CancelledError:
                task.status = TaskStatus.FAILED
                task.error = "Task was cancelled"
                logger.warning(f"任务被取消: {task.task_id}")

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                logger.error(f"任务执行失败: {task.task_id}", e=e)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = f"Unexpected error: {str(e)}"
            logger.error(f"任务执行过程中发生意外错误: {task.task_id}", e=e)

        finally:
            task.end_time = time.time()

            try:
                if task.task_id in self.running_tasks:
                    del self.running_tasks[task.task_id]
            except Exception as e:
                logger.error(f"清理运行中任务记录失败: {task.task_id}", e=e)

            try:
                self.completed_tasks[task.task_id] = task

                if len(self.completed_tasks) > TASK_QUEUE_SIZE:
                    oldest_task_id = min(
                        self.completed_tasks.keys(),
                        key=lambda k: self.completed_tasks[k].end_time,
                    )
                    del self.completed_tasks[oldest_task_id]
            except Exception as e:
                logger.error(f"更新已完成任务记录失败: {task.task_id}", e=e)


task_manager = TaskManager.get_instance()

driver = get_driver()


@driver.on_startup
async def _():
    await task_manager.start()


@driver.on_shutdown
async def _():
    await task_manager.stop()
