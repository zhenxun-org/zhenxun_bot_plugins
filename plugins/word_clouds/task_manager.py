import asyncio
import time
from typing import Dict, Optional, Callable, Awaitable, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
import heapq

from nonebot import get_driver
from zhenxun.services.log import logger

MAX_CONCURRENT_TASKS = 5
TASK_QUEUE_SIZE = 100
DEFAULT_TIMEOUT = 300
EXECUTOR_MAX_WORKERS = 20


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
    
    def __init__(self, 
                 task_id: str, 
                 func: Callable[..., Awaitable[Any]], 
                 args: Tuple = None, 
                 kwargs: Dict = None,
                 priority: int = TaskPriority.NORMAL,
                 timeout: int = DEFAULT_TIMEOUT):
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
    """任务管理器，负责管理和执行任务"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance
    
    def __init__(self):
        """初始化任务管理器"""
        self.task_queue = []
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.completed_tasks: Dict[str, Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=EXECUTOR_MAX_WORKERS)
        self.lock = asyncio.Lock()
        self.running = False
        self.worker_task = None
        
    async def start(self):
        """启动任务管理器"""
        if self.running:
            return
        
        self.running = True
        self.worker_task = asyncio.create_task(self._worker())
        logger.info("任务管理器已启动")
        
    async def stop(self):
        """停止任务管理器"""
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
        
    async def add_task(self, 
                      task_id: str, 
                      func: Callable[..., Awaitable[Any]], 
                      args: Tuple = None, 
                      kwargs: Dict = None,
                      priority: int = TaskPriority.NORMAL,
                      timeout: int = DEFAULT_TIMEOUT) -> bool:
        """添加任务到队列
        
        Args:
            task_id: 任务ID
            func: 异步函数
            args: 位置参数
            kwargs: 关键字参数
            priority: 优先级
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否成功添加
        """
        if len(self.task_queue) >= TASK_QUEUE_SIZE:
            logger.warning(f"任务队列已满，无法添加任务: {task_id}")
            return False
        
        task = Task(task_id, func, args, kwargs, priority, timeout)
        
        async with self.lock:
            heapq.heappush(self.task_queue, task)
            
        logger.debug(f"已添加任务到队列: {task_id}, 优先级: {priority}")
        return True
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功取消
        """
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
        """获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[str]: 任务状态，如果任务不存在则返回None
        """
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
        """获取队列信息
        
        Returns:
            Dict: 队列信息
        """
        async with self.lock:
            pending_count = len(self.task_queue)
            
        running_count = len(self.running_tasks)
        completed_count = len(self.completed_tasks)
        
        return {
            "pending": pending_count,
            "running": running_count,
            "completed": completed_count,
            "total": pending_count + running_count + completed_count
        }
    
    async def _worker(self):
        """工作线程，负责从队列中取出任务并执行"""
        while self.running:
            if len(self.running_tasks) >= MAX_CONCURRENT_TASKS:
                await asyncio.sleep(0.1)
                continue
                
            task = None
            async with self.lock:
                if self.task_queue:
                    task = heapq.heappop(self.task_queue)
            
            if not task:
                await asyncio.sleep(0.1)
                continue
                
            asyncio_task = asyncio.create_task(self._execute_task(task))
            self.running_tasks[task.task_id] = asyncio_task
            
        logger.debug("任务管理器工作线程已退出")
    
    async def _execute_task(self, task: Task):
        """执行任务
        
        Args:
            task: 任务对象
        """
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        
        try:
            result = await asyncio.wait_for(
                task.func(*task.args, **task.kwargs),
                timeout=task.timeout
            )
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            logger.debug(f"任务执行成功: {task.task_id}")
            
        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            task.error = "Task execution timed out"
            logger.warning(f"任务执行超时: {task.task_id}")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error(f"任务执行失败: {task.task_id}", e=e)
            
        finally:
            task.end_time = time.time()
            
            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]
                
            self.completed_tasks[task.task_id] = task
            
            if len(self.completed_tasks) > TASK_QUEUE_SIZE:
                oldest_task_id = min(
                    self.completed_tasks.keys(),
                    key=lambda k: self.completed_tasks[k].end_time
                )
                del self.completed_tasks[oldest_task_id]


task_manager = TaskManager.get_instance()

driver = get_driver()

@driver.on_startup
async def _():
    await task_manager.start()

@driver.on_shutdown
async def _():
    await task_manager.stop()
