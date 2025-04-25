import time
import json
import asyncio
from typing import Optional, Dict
from collections import OrderedDict
from nonebot_plugin_session import EventSession

from ..config import base_config, PLUGIN_CACHE_DIR
from zhenxun.services.log import logger

_context_caches: Dict[str, OrderedDict[str, float]] = {}
_CONTEXT_CACHE_CAPACITY = 100

_CACHE_FILE = PLUGIN_CACHE_DIR / "url_cache.json"

_cache_lock = asyncio.Lock()


class CacheService:
    _initialized = False

    @classmethod
    async def initialize(cls):
        """初始化缓存服务，加载持久化数据"""
        if cls._initialized:
            return

        await cls._load_cache_from_disk()
        cls._initialized = True
        logger.info("缓存服务初始化完成", "B站解析")

    @staticmethod
    def _get_context_key(session: EventSession) -> str:
        """根据 EventSession 生成唯一的上下文 Key"""
        if session.id3:
            return f"guild_{session.id3}_channel_{session.id2}"
        elif session.id2:
            return f"group_{session.id2}"
        elif session.id1:
            return f"private_{session.id1}"
        else:
            logger.warning(
                "无法从 Session 中获取有效的上下文 ID，将使用全局缓存 Key", "B站解析"
            )
            return "global_fallback_cache"

    @classmethod
    async def should_parse(cls, url: str, session: EventSession) -> bool:
        """检查 URL 是否应该在指定会话上下文中被解析（基于缓存和 TTL）"""
        if not cls._initialized:
            await cls.initialize()

        if not base_config.get("CACHE_ENABLED", True):
            return True

        context_key = cls._get_context_key(session)
        current_time = time.time()

        if context_key not in _context_caches:
            _context_caches[context_key] = OrderedDict()
            logger.debug(f"为上下文 '{context_key}' 创建了新的缓存", "B站解析")

        context_cache = _context_caches[context_key]
        timestamp = context_cache.get(url)

        if timestamp is None:
            logger.debug(
                f"URL '{url}' 在上下文 '{context_key}' 的缓存中未找到", "B站解析"
            )
            if len(context_cache) >= _CONTEXT_CACHE_CAPACITY:
                try:
                    removed_url, _ = context_cache.popitem(last=False)
                    logger.debug(
                        f"上下文 '{context_key}' 缓存已满，移除最旧条目: {removed_url}",
                        "B站解析",
                    )
                except KeyError:
                    pass
            context_cache[url] = current_time
            asyncio.create_task(cls._save_cache_to_disk())
            return True
        else:
            cache_ttl = base_config.get("CACHE_TTL", 300)
            if current_time - timestamp > cache_ttl:
                logger.debug(
                    f"URL '{url}' 在上下文 '{context_key}' 的缓存已过期 (TTL={cache_ttl}s)",
                    "B站解析",
                )
                context_cache[url] = current_time
                context_cache.move_to_end(url)
                asyncio.create_task(cls._save_cache_to_disk())
                return True
            else:
                logger.debug(
                    f"URL '{url}' 在上下文 '{context_key}' 的缓存未过期", "B站解析"
                )
                context_cache.move_to_end(url)
                return False

    @classmethod
    async def add_to_cache(cls, url: str, session: EventSession):
        """
        手动将 URL 添加到指定会话的缓存（并更新时间戳）。
        (通常在 should_parse 返回 False 但仍然解析了之后调用，虽然当前逻辑下不太需要)
        """
        if not cls._initialized:
            await cls.initialize()

        if not base_config.get("CACHE_ENABLED", True):
            return

        context_key = cls._get_context_key(session)
        current_time = time.time()

        if context_key not in _context_caches:
            _context_caches[context_key] = OrderedDict()

        context_cache = _context_caches[context_key]

        if url in context_cache:
            context_cache.move_to_end(url)
        elif len(context_cache) >= _CONTEXT_CACHE_CAPACITY:
            try:
                context_cache.popitem(last=False)
            except KeyError:
                pass
        context_cache[url] = current_time
        logger.debug(
            f"手动添加/更新 URL '{url}' 到上下文 '{context_key}' 的缓存", "B站解析"
        )

        asyncio.create_task(cls._save_cache_to_disk())

    @classmethod
    async def clear_cache(cls, context_key: Optional[str] = None):
        """
        清空缓存。
        如果提供了 context_key，则只清空该上下文的缓存。
        否则清空所有缓存。
        """
        if not cls._initialized:
            await cls.initialize()

        if context_key:
            if context_key in _context_caches:
                _context_caches[context_key].clear()
                logger.info(f"已清空上下文 '{context_key}' 的缓存", "B站解析")
            else:
                logger.info(f"尝试清空缓存，但未找到上下文 '{context_key}'", "B站解析")
        else:
            _context_caches.clear()
            logger.info("已清空所有上下文的缓存", "B站解析")

        asyncio.create_task(cls._save_cache_to_disk())

    @classmethod
    async def _load_cache_from_disk(cls):
        """从磁盘加载缓存数据"""
        global _context_caches

        if not _CACHE_FILE.exists():
            logger.info("缓存文件不存在，将使用空缓存", "B站解析")
            return

        try:
            async with _cache_lock:
                cache_data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))

                for context_key, urls_data in cache_data.items():
                    if context_key not in _context_caches:
                        _context_caches[context_key] = OrderedDict()

                    sorted_items = sorted(urls_data.items(), key=lambda x: x[1])

                    if len(sorted_items) > _CONTEXT_CACHE_CAPACITY:
                        sorted_items = sorted_items[-_CONTEXT_CACHE_CAPACITY:]

                    for url, timestamp in sorted_items:
                        _context_caches[context_key][url] = timestamp

                logger.info(
                    f"从磁盘加载了 {len(_context_caches)} 个上下文的缓存数据", "B站解析"
                )
        except Exception as e:
            logger.error(f"从磁盘加载缓存失败: {e}", "B站解析")
            _context_caches = {}

    @classmethod
    async def _save_cache_to_disk(cls):
        """将缓存数据保存到磁盘"""
        try:
            async with _cache_lock:
                cache_data = {}
                for context_key, ordered_dict in _context_caches.items():
                    cache_data[context_key] = dict(ordered_dict)

                _CACHE_FILE.write_text(
                    json.dumps(cache_data, ensure_ascii=False), encoding="utf-8"
                )
                logger.debug(f"缓存数据已保存到磁盘: {_CACHE_FILE}", "B站解析")
        except Exception as e:
            logger.error(f"保存缓存到磁盘失败: {e}", "B站解析")
