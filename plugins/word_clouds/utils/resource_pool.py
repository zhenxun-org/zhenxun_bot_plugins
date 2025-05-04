import time
from typing import Dict, Any, Callable, TypeVar, Generic, List
import threading
from collections import deque
import asyncio

from zhenxun.services.log import logger

T = TypeVar("T")


class PooledResource(Generic[T]):
    """池化资源包装类，用于跟踪资源的使用情况"""

    def __init__(self, resource: T, resource_id: str, created_time: float):
        self.resource = resource
        self.resource_id = resource_id
        self.created_time = created_time
        self.last_used_time = created_time
        self.use_count = 0
        self.in_use = False

    def mark_as_used(self):
        """标记资源为正在使用状态"""
        self.in_use = True
        self.last_used_time = time.time()
        self.use_count += 1

    def mark_as_free(self):
        """标记资源为空闲状态"""
        self.in_use = False
        self.last_used_time = time.time()


class ResourcePool(Generic[T]):
    """资源池基类，管理可重用资源"""

    def __init__(
        self,
        factory: Callable[..., T],
        max_size: int = 10,
        min_size: int = 2,
        max_idle_time: int = 300,
        cleanup_interval: int = 60,
        name: str = "ResourcePool",
    ):
        """初始化资源池，配置资源管理参数"""
        self.factory = factory
        self.max_size = max_size
        self.min_size = min_size
        self.max_idle_time = max_idle_time
        self.cleanup_interval = cleanup_interval
        self.name = name

        self._resources: Dict[str, PooledResource[T]] = {}
        self._free_resources: deque = deque()
        self._lock = threading.RLock()
        self._resource_counter = 0
        self._cleanup_timer = None
        self._started = False

        self._initialize_pool()

    def _initialize_pool(self):
        """初始化资源池，创建初始资源"""
        with self._lock:
            for _ in range(self.min_size):
                self._create_resource()

    def _create_resource(self) -> PooledResource[T]:
        """创建新资源并添加到资源池"""
        try:
            resource_id = f"{self.name}_{self._resource_counter}"
            self._resource_counter += 1

            resource = self.factory()

            pooled_resource = PooledResource(
                resource=resource, resource_id=resource_id, created_time=time.time()
            )

            self._resources[resource_id] = pooled_resource
            self._free_resources.append(resource_id)

            logger.debug(
                f"{self.name}: 创建新资源 {resource_id}, 当前资源池大小: {len(self._resources)}"
            )
            return pooled_resource

        except Exception as e:
            logger.error(f"{self.name}: 创建资源失败", e=e)
            raise

    def _destroy_resource(self, resource_id: str):
        """销毁资源并从资源池中移除"""
        with self._lock:
            if resource_id in self._resources:
                resource = self._resources.pop(resource_id)
                logger.debug(
                    f"{self.name}: 销毁资源 {resource_id}, 当前资源池大小: {len(self._resources)}"
                )

                if hasattr(resource.resource, "close") and callable(
                    resource.resource.close
                ):
                    try:
                        resource.resource.close()
                    except Exception as e:
                        logger.error(f"{self.name}: 关闭资源 {resource_id} 失败", e=e)

                if len(self._resources) < self.min_size:
                    self._create_resource()

    def acquire(self) -> T:
        """获取资源，如果没有空闲资源会创建新资源"""
        with self._lock:
            while self._free_resources:
                resource_id = self._free_resources.popleft()
                if resource_id in self._resources:
                    resource = self._resources[resource_id]
                    resource.mark_as_used()
                    logger.debug(
                        f"{self.name}: 获取现有资源 {resource_id}, 剩余空闲资源: {len(self._free_resources)}"
                    )
                    return resource.resource

            if len(self._resources) < self.max_size:
                resource = self._create_resource()
                resource.mark_as_used()
                logger.debug(
                    f"{self.name}: 创建并获取新资源 {resource.resource_id}, 当前资源池大小: {len(self._resources)}"
                )
                return resource.resource

            logger.warning(f"{self.name}: 资源池已满，等待资源释放")

            oldest_resource_id = None
            oldest_use_time = float("inf")

            for rid, res in self._resources.items():
                if res.in_use and res.last_used_time < oldest_use_time:
                    oldest_use_time = res.last_used_time
                    oldest_resource_id = rid

            if oldest_resource_id:
                resource = self._resources[oldest_resource_id]
                logger.warning(
                    f"{self.name}: 强制释放长时间占用的资源 {oldest_resource_id}"
                )
                resource.mark_as_free()
                resource.mark_as_used()
                return resource.resource

            logger.error(
                f"{self.name}: 所有资源都在使用中，创建临时资源（不在池中管理）"
            )
            return self.factory()

    def release(self, resource: T):
        """释放资源，将其标记为空闲状态"""
        with self._lock:
            resource_id = None
            for rid, res in self._resources.items():
                if res.resource is resource:
                    resource_id = rid
                    break

            if resource_id:
                self._resources[resource_id].mark_as_free()
                self._free_resources.append(resource_id)
                logger.debug(
                    f"{self.name}: 释放资源 {resource_id}, 当前空闲资源: {len(self._free_resources)}"
                )
            else:
                logger.warning(f"{self.name}: 尝试释放未知资源，可能是临时创建的")

    def start_cleanup(self):
        """启动定期清理"""
        if self._started:
            return

        self._started = True
        self._schedule_cleanup()
        logger.info(
            f"{self.name}: 启动资源池清理定时器，间隔 {self.cleanup_interval} 秒"
        )

    def stop_cleanup(self):
        """停止定期清理"""
        self._started = False
        if self._cleanup_timer:
            self._cleanup_timer.cancel()
            self._cleanup_timer = None
        logger.info(f"{self.name}: 停止资源池清理定时器")

    def _schedule_cleanup(self):
        """调度下一次清理"""
        if not self._started:
            return

        self._cleanup_timer = threading.Timer(self.cleanup_interval, self._cleanup)
        self._cleanup_timer.daemon = True
        self._cleanup_timer.start()

    def _cleanup(self):
        """清理空闲时间过长的资源"""
        try:
            with self._lock:
                now = time.time()
                to_remove = []

                for resource_id, resource in self._resources.items():
                    if (
                        not resource.in_use
                        and now - resource.last_used_time > self.max_idle_time
                        and len(self._resources) > self.min_size
                    ):
                        to_remove.append(resource_id)

                for resource_id in to_remove:
                    try:
                        self._free_resources.remove(resource_id)
                    except ValueError:
                        pass
                    self._destroy_resource(resource_id)

                if to_remove:
                    logger.debug(
                        f"{self.name}: 清理了 {len(to_remove)} 个空闲资源，当前资源池大小: {len(self._resources)}"
                    )

        except Exception as e:
            logger.error(f"{self.name}: 清理资源时出错", e=e)

        finally:
            self._schedule_cleanup()

    def get_stats(self) -> Dict[str, Any]:
        """获取资源池统计信息，包括总数、空闲数等"""
        with self._lock:
            total = len(self._resources)
            free = len(self._free_resources)
            in_use = total - free

            avg_use_count = 0
            if total > 0:
                avg_use_count = (
                    sum(r.use_count for r in self._resources.values()) / total
                )

            return {
                "name": self.name,
                "total": total,
                "free": free,
                "in_use": in_use,
                "max_size": self.max_size,
                "min_size": self.min_size,
                "avg_use_count": avg_use_count,
            }

    def __del__(self):
        """析构函数，确保清理定时器被取消"""
        self.stop_cleanup()


class AsyncResourcePool(Generic[T]):
    """异步资源池，用于异步环境中的资源管理"""

    def __init__(
        self,
        factory: Callable[..., T],
        max_size: int = 10,
        min_size: int = 2,
        max_idle_time: int = 300,
        cleanup_interval: int = 60,
        name: str = "AsyncResourcePool",
    ):
        """初始化异步资源池，配置资源管理参数"""
        self.factory = factory
        self.max_size = max_size
        self.min_size = min_size
        self.max_idle_time = max_idle_time
        self.cleanup_interval = cleanup_interval
        self.name = name

        self._resources: Dict[str, PooledResource[T]] = {}
        self._free_resources: List[str] = []
        self._lock = asyncio.Lock()
        self._resource_counter = 0
        self._cleanup_task = None
        self._started = False

    async def _initialize_pool(self):
        """初始化资源池"""
        async with self._lock:
            for _ in range(self.min_size):
                await self._create_resource()

    async def _create_resource(self) -> PooledResource[T]:
        """创建新资源"""
        try:
            resource_id = f"{self.name}_{self._resource_counter}"
            self._resource_counter += 1

            if asyncio.iscoroutinefunction(self.factory):
                resource = await self.factory()
            else:
                resource = self.factory()

            pooled_resource = PooledResource(
                resource=resource, resource_id=resource_id, created_time=time.time()
            )

            self._resources[resource_id] = pooled_resource
            self._free_resources.append(resource_id)

            logger.debug(
                f"{self.name}: 创建新资源 {resource_id}, 当前资源池大小: {len(self._resources)}"
            )
            return pooled_resource

        except Exception as e:
            logger.error(f"{self.name}: 创建资源失败", e=e)
            raise

    async def _destroy_resource(self, resource_id: str):
        """销毁资源"""
        if resource_id in self._resources:
            resource = self._resources.pop(resource_id)
            logger.debug(
                f"{self.name}: 销毁资源 {resource_id}, 当前资源池大小: {len(self._resources)}"
            )

            if hasattr(resource.resource, "close"):
                if asyncio.iscoroutinefunction(resource.resource.close):
                    try:
                        await resource.resource.close()
                    except Exception as e:
                        logger.error(f"{self.name}: 关闭资源 {resource_id} 失败", e=e)
                else:
                    try:
                        resource.resource.close()
                    except Exception as e:
                        logger.error(f"{self.name}: 关闭资源 {resource_id} 失败", e=e)

            if len(self._resources) < self.min_size:
                await self._create_resource()

    async def acquire(self) -> T:
        """获取资源，如果没有空闲资源会创建新资源"""
        async with self._lock:
            while self._free_resources:
                resource_id = self._free_resources.pop(0)
                if resource_id in self._resources:
                    resource = self._resources[resource_id]
                    resource.mark_as_used()
                    logger.debug(
                        f"{self.name}: 获取现有资源 {resource_id}, 剩余空闲资源: {len(self._free_resources)}"
                    )
                    return resource.resource

            if len(self._resources) < self.max_size:
                resource = await self._create_resource()
                resource.mark_as_used()
                logger.debug(
                    f"{self.name}: 创建并获取新资源 {resource.resource_id}, 当前资源池大小: {len(self._resources)}"
                )
                return resource.resource

            logger.warning(f"{self.name}: 资源池已满，等待资源释放")

            oldest_resource_id = None
            oldest_use_time = float("inf")

            for rid, res in self._resources.items():
                if res.in_use and res.last_used_time < oldest_use_time:
                    oldest_use_time = res.last_used_time
                    oldest_resource_id = rid

            if oldest_resource_id:
                resource = self._resources[oldest_resource_id]
                logger.warning(
                    f"{self.name}: 强制释放长时间占用的资源 {oldest_resource_id}"
                )
                resource.mark_as_free()
                resource.mark_as_used()
                return resource.resource

            logger.error(
                f"{self.name}: 所有资源都在使用中，创建临时资源（不在池中管理）"
            )
            if asyncio.iscoroutinefunction(self.factory):
                return await self.factory()
            else:
                return self.factory()

    async def release(self, resource: T):
        """释放资源，将其标记为空闲状态"""
        async with self._lock:
            resource_id = None
            for rid, res in self._resources.items():
                if res.resource is resource:
                    resource_id = rid
                    break

            if resource_id:
                self._resources[resource_id].mark_as_free()
                self._free_resources.append(resource_id)
                logger.debug(
                    f"{self.name}: 释放资源 {resource_id}, 当前空闲资源: {len(self._free_resources)}"
                )
            else:
                logger.warning(f"{self.name}: 尝试释放未知资源，可能是临时创建的")

    async def start_cleanup(self):
        """启动定期清理"""
        if self._started:
            return

        self._started = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"{self.name}: 启动资源池清理任务，间隔 {self.cleanup_interval} 秒")

    async def stop_cleanup(self):
        """停止定期清理"""
        self._started = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.info(f"{self.name}: 停止资源池清理任务")

    async def _cleanup_loop(self):
        """清理循环"""
        while self._started:
            try:
                await self._cleanup()
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"{self.name}: 清理循环出错", e=e)
                await asyncio.sleep(self.cleanup_interval)

    async def _cleanup(self):
        """清理空闲时间过长的资源"""
        async with self._lock:
            now = time.time()
            to_remove = []

            for resource_id, resource in self._resources.items():
                if (
                    not resource.in_use
                    and now - resource.last_used_time > self.max_idle_time
                    and len(self._resources) > self.min_size
                ):
                    to_remove.append(resource_id)

            for resource_id in to_remove:
                try:
                    self._free_resources.remove(resource_id)
                except ValueError:
                    pass
                await self._destroy_resource(resource_id)

            if to_remove:
                logger.debug(
                    f"{self.name}: 清理了 {len(to_remove)} 个空闲资源，当前资源池大小: {len(self._resources)}"
                )

    async def get_stats(self) -> Dict[str, Any]:
        """获取资源池统计信息"""
        async with self._lock:
            total = len(self._resources)
            free = len(self._free_resources)
            in_use = total - free

            avg_use_count = 0
            if total > 0:
                avg_use_count = (
                    sum(r.use_count for r in self._resources.values()) / total
                )

            return {
                "name": self.name,
                "total": total,
                "free": free,
                "in_use": in_use,
                "max_size": self.max_size,
                "min_size": self.min_size,
                "avg_use_count": avg_use_count,
            }

    async def __aenter__(self) -> T:
        """异步上下文管理器入口"""
        self._current_resource = await self.acquire()
        return self._current_resource

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if hasattr(self, "_current_resource") and self._current_resource:
            await self.release(self._current_resource)
            self._current_resource = None
        _ = exc_type, exc_val, exc_tb
