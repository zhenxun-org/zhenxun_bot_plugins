import time
import json
import asyncio
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from collections import OrderedDict
from nonebot_plugin_session import EventSession

from zhenxun.services.log import logger

from ..config import base_config, PLUGIN_TEMP_DIR, PLUGIN_CACHE_DIR, IMAGE_CACHE_DIR

VIDEO_CACHE_DIR = PLUGIN_TEMP_DIR / "video_cache"
VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_INDEX_FILE = PLUGIN_CACHE_DIR / "cache_index.json"
URL_CACHE_FILE = PLUGIN_CACHE_DIR / "url_cache.json"

_video_cache_lock = asyncio.Lock()
_url_cache_lock = asyncio.Lock()
_clean_lock = asyncio.Lock()

_video_cache_index: Dict[str, Dict[str, Any]] = {}
_url_context_caches: Dict[str, OrderedDict[str, float]] = {}
_URL_CONTEXT_CACHE_CAPACITY = 100

_video_cache_initialized = False
_url_cache_initialized = False


class CacheService:
    """统一缓存管理服务"""

    FILE_EXPIRY = {
        "bili_video_cover_": 1,
        "bili_avatar_": 7,
        "bili_live_cover_": 1,
        "bili_live_keyframe_": 0.04,
        "bili_article_": 1,
        "bili_opus_": 1,
        "bili_video_": 1,
    }

    _CLEAN_INTERVAL = 24 * 3600

    @classmethod
    async def initialize(cls):
        """初始化缓存服务"""
        logger.info("正在初始化统一缓存服务...", "B站解析")

        await cls._init_video_cache()
        await cls._init_url_cache()

        clean_interval_hours = base_config.get("CACHE_CLEAN_INTERVAL_HOURS", 24)
        cls._CLEAN_INTERVAL = clean_interval_hours * 3600

        video_file_expiry_days = base_config.get("VIDEO_FILE_EXPIRY_DAYS", 1)
        cls.FILE_EXPIRY["bili_video_"] = video_file_expiry_days

        if not PLUGIN_TEMP_DIR.exists():
            PLUGIN_TEMP_DIR.mkdir(parents=True, exist_ok=True)

        cache_expiry_days = base_config.get("CACHE_EXPIRY_DAYS", 7)
        auto_clean_enabled = cache_expiry_days > 0

        if auto_clean_enabled:
            task = asyncio.create_task(cls._auto_clean_task())
            task.set_name("bilibili_cache_cleaner")
            logger.info("缓存自动清理任务已启动", "B站解析")

        logger.info("统一缓存服务初始化完成", "B站解析")

    @classmethod
    async def _init_video_cache(cls):
        """初始化视频文件缓存"""
        global _video_cache_initialized, _video_cache_index

        if _video_cache_initialized:
            return

        async with _video_cache_lock:
            if not VIDEO_CACHE_DIR.exists():
                VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                logger.info(f"已创建视频缓存目录: {VIDEO_CACHE_DIR}", "B站解析")

            if CACHE_INDEX_FILE.exists():
                try:
                    _video_cache_index = json.loads(CACHE_INDEX_FILE.read_text(encoding="utf-8"))
                    logger.info(
                        f"已加载视频缓存索引，包含 {len(_video_cache_index)} 个条目",
                        "B站解析",
                    )
                except Exception as e:
                    logger.error(f"加载视频缓存索引失败: {e}", "B站解析")
                    _video_cache_index = {}

            invalid_keys = []
            for cache_key, cache_info in _video_cache_index.items():
                file_path = cache_info.get("file_path", "")
                if not file_path or not Path(file_path).exists():
                    invalid_keys.append(cache_key)

            for key in invalid_keys:
                del _video_cache_index[key]

            if invalid_keys:
                logger.info(f"已移除 {len(invalid_keys)} 个无效的缓存条目", "B站解析")
                await cls._save_video_cache_index()

            _video_cache_initialized = True

    @classmethod
    async def _init_url_cache(cls):
        """初始化URL缓存"""
        global _url_cache_initialized, _url_context_caches

        if _url_cache_initialized:
            return

        await cls._load_url_cache_from_disk()
        _url_cache_initialized = True

    @classmethod
    async def get_video_cache(cls, video_id: str, page_num: int = 0) -> Optional[Path]:
        """获取视频缓存文件路径"""
        if not _video_cache_initialized:
            await cls._init_video_cache()

        cache_key = cls._get_video_cache_key(video_id, page_num)

        async with _video_cache_lock:
            cache_info = _video_cache_index.get(cache_key)
            if not cache_info:
                logger.debug(f"视频缓存未命中: {cache_key}", "B站解析")
                return None

            file_path_str = cache_info.get("file_path")
            if not file_path_str:
                logger.warning(f"缓存索引中的文件路径为空: {cache_key}", "B站解析")
                return None

            file_path = Path(file_path_str)
            if not file_path.exists():
                logger.warning(f"缓存文件不存在: {file_path}", "B站解析")
                del _video_cache_index[cache_key]
                await cls._save_video_cache_index()
                return None

            _video_cache_index[cache_key]["last_access_time"] = time.time()
            await cls._save_video_cache_index()

            logger.info(f"视频缓存命中: {cache_key} -> {file_path}", "B站解析")
            return file_path

    @classmethod
    async def save_video_to_cache(cls, video_id: str, page_num: int, file_path: Path) -> bool:
        """保存视频到缓存"""
        if not _video_cache_initialized:
            await cls._init_video_cache()

        if not file_path.exists():
            logger.warning(f"要缓存的文件不存在: {file_path}", "B站解析")
            return False

        cache_key = cls._get_video_cache_key(video_id, page_num)
        cache_file_name = f"{video_id}_P{page_num + 1}.mp4"
        cache_file_path = VIDEO_CACHE_DIR / cache_file_name

        try:
            if str(file_path) == str(cache_file_path):
                logger.debug(f"文件已在缓存目录中，无需复制: {file_path}", "B站解析")
            else:
                if cache_file_path.exists():
                    cache_file_path.unlink()

                shutil.copy2(file_path, cache_file_path)
                logger.debug(f"已复制文件到缓存: {file_path} -> {cache_file_path}", "B站解析")

            async with _video_cache_lock:
                _video_cache_index[cache_key] = {
                    "video_id": video_id,
                    "page_num": page_num,
                    "file_path": str(cache_file_path),
                    "file_size": cache_file_path.stat().st_size,
                    "create_time": time.time(),
                    "last_access_time": time.time(),
                }
                await cls._save_video_cache_index()

            logger.info(f"视频已保存到缓存: {cache_key} -> {cache_file_path}", "B站解析")
            return True
        except Exception as e:
            logger.error(f"保存视频到缓存失败: {e}", "B站解析")
            return False

    @classmethod
    async def should_parse_url(cls, url: str, session: EventSession) -> bool:
        """检查URL是否应该被解析（基于缓存TTL）"""
        if not _url_cache_initialized:
            await cls._init_url_cache()

        cache_ttl_minutes = base_config.get("CACHE_TTL", 5)
        if cache_ttl_minutes <= 0:
            return True

        cache_ttl_seconds = cache_ttl_minutes * 60
        context_key = cls._get_context_key(session)
        current_time = time.time()

        if context_key not in _url_context_caches:
            _url_context_caches[context_key] = OrderedDict()
            logger.debug(f"为上下文 '{context_key}' 创建了新的缓存", "B站解析")

        context_cache = _url_context_caches[context_key]
        timestamp = context_cache.get(url)

        if timestamp is None:
            logger.debug(f"URL '{url}' 在上下文 '{context_key}' 的缓存中未找到", "B站解析")
            if len(context_cache) >= _URL_CONTEXT_CACHE_CAPACITY:
                try:
                    removed_url, _ = context_cache.popitem(last=False)
                    logger.debug(
                        f"上下文 '{context_key}' 缓存已满，移除最旧条目: {removed_url}",
                        "B站解析",
                    )
                except KeyError:
                    pass
            context_cache[url] = current_time
            asyncio.create_task(cls._save_url_cache_to_disk())
            return True
        else:
            if current_time - timestamp > cache_ttl_seconds:
                logger.debug(
                    f"URL '{url}' 在上下文 '{context_key}' 的缓存已过期 (TTL={cache_ttl_minutes}分钟)",
                    "B站解析",
                )
                context_cache[url] = current_time
                context_cache.move_to_end(url)
                asyncio.create_task(cls._save_url_cache_to_disk())
                return True
            else:
                logger.debug(f"URL '{url}' 在上下文 '{context_key}' 的缓存未过期", "B站解析")
                context_cache.move_to_end(url)
                return False

    @classmethod
    async def add_url_to_cache(cls, url: str, session: EventSession):
        """手动将URL添加到指定会话的缓存"""
        if not _url_cache_initialized:
            await cls._init_url_cache()

        cache_ttl_minutes = base_config.get("CACHE_TTL", 5)
        if cache_ttl_minutes <= 0:
            return

        context_key = cls._get_context_key(session)
        current_time = time.time()

        if context_key not in _url_context_caches:
            _url_context_caches[context_key] = OrderedDict()

        context_cache = _url_context_caches[context_key]

        if url in context_cache:
            context_cache.move_to_end(url)
        elif len(context_cache) >= _URL_CONTEXT_CACHE_CAPACITY:
            try:
                context_cache.popitem(last=False)
            except KeyError:
                pass
        context_cache[url] = current_time
        logger.debug(f"手动添加/更新 URL '{url}' 到上下文 '{context_key}' 的缓存", "B站解析")

        asyncio.create_task(cls._save_url_cache_to_disk())

    @classmethod
    async def clear_url_cache(cls, context_key: Optional[str] = None):
        """清空URL缓存"""
        if not _url_cache_initialized:
            await cls._init_url_cache()

        if context_key:
            if context_key in _url_context_caches:
                _url_context_caches[context_key].clear()
                logger.info(f"已清空上下文 '{context_key}' 的缓存", "B站解析")
            else:
                logger.info(f"尝试清空缓存，但未找到上下文 '{context_key}'", "B站解析")
        else:
            _url_context_caches.clear()
            logger.info("已清空所有上下文的缓存", "B站解析")

        asyncio.create_task(cls._save_url_cache_to_disk())

    @classmethod
    async def clean_expired_cache(cls, force: bool = False) -> int:
        """清理过期缓存文件和视频缓存"""
        if not _video_cache_initialized:
            await cls._init_video_cache()

        async with _clean_lock:
            cleaned_videos = await cls._clean_video_cache(force)

            cleaned_files = await cls._clean_temp_files()

            total_cleaned = cleaned_videos + cleaned_files
            if total_cleaned > 0:
                logger.info(f"缓存清理完成，共清理 {total_cleaned} 个文件", "B站解析")

            return total_cleaned

    @classmethod
    async def _clean_video_cache(cls, force: bool = False) -> int:
        """清理过期视频缓存"""
        expiry_days = base_config.get("CACHE_EXPIRY_DAYS", 7)
        max_cache_size_mb = base_config.get("MAX_VIDEO_CACHE_SIZE_MB", 1024)

        if expiry_days <= 0 and not force:
            logger.debug("视频缓存过期时间设置为0或负数，跳过清理", "B站解析")
            return 0

        current_time = time.time()
        expiry_seconds = expiry_days * 86400

        async with _video_cache_lock:
            sorted_cache = sorted(
                _video_cache_index.items(),
                key=lambda x: x[1].get("last_access_time", 0),
            )

            total_size = sum(info.get("file_size", 0) for _, info in sorted_cache)
            total_size_mb = total_size / (1024 * 1024)

            logger.debug(
                f"当前视频缓存大小: {total_size_mb:.2f}MB, 限制: {max_cache_size_mb}MB",
                "B站解析",
            )

            to_clean = []

            for cache_key, cache_info in sorted_cache:
                last_access_time = cache_info.get("last_access_time", 0)
                if current_time - last_access_time > expiry_seconds:
                    to_clean.append((cache_key, cache_info))

            if total_size_mb > max_cache_size_mb:
                size_to_free = total_size - (max_cache_size_mb * 1024 * 1024)
                freed_size = 0

                for cache_key, cache_info in sorted_cache:
                    if cache_key not in [x[0] for x in to_clean]:
                        to_clean.append((cache_key, cache_info))
                        freed_size += cache_info.get("file_size", 0)
                        if freed_size >= size_to_free:
                            break

            cleaned_count = 0
            for cache_key, cache_info in to_clean:
                file_path_str = cache_info.get("file_path", "")
                if file_path_str:
                    file_path = Path(file_path_str)
                    if file_path.exists():
                        try:
                            file_path.unlink()
                            logger.debug(f"已删除缓存文件: {file_path}", "B站解析")
                            cleaned_count += 1
                        except Exception as e:
                            logger.warning(f"删除缓存文件失败: {file_path}, 错误: {e}", "B站解析")

                if cache_key in _video_cache_index:
                    del _video_cache_index[cache_key]

            if to_clean:
                await cls._save_video_cache_index()

            if cleaned_count > 0:
                logger.info(f"视频缓存清理完成，共清理 {cleaned_count} 个文件", "B站解析")

            return cleaned_count

    @classmethod
    async def _clean_temp_files(cls) -> int:
        """清理临时文件"""
        current_time = time.time()
        temp_files = []

        if IMAGE_CACHE_DIR.exists():
            for file in IMAGE_CACHE_DIR.glob("*"):
                if file.is_file():
                    temp_files.append(file)
            logger.debug(
                f"扫描图片缓存目录: {IMAGE_CACHE_DIR}，找到 {len(temp_files)} 个文件",
                "B站解析",
            )

        for file in PLUGIN_TEMP_DIR.glob("*"):
            if file.is_file() and file.parent == PLUGIN_TEMP_DIR:
                temp_files.append(file)

        files_by_prefix = {}
        for file in temp_files:
            for prefix in cls.FILE_EXPIRY.keys():
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

        return cleaned_count

    @classmethod
    async def _auto_clean_task(cls):
        """定时清理任务"""
        clean_interval_hours = base_config.get("CACHE_CLEAN_INTERVAL_HOURS", 24)
        clean_interval_seconds = clean_interval_hours * 3600

        logger.info(f"缓存自动清理任务启动，间隔: {clean_interval_hours} 小时", "B站解析")

        while True:
            try:
                cleaned = await cls.clean_expired_cache(force=True)
                logger.info(
                    f"缓存自动清理完成，清理了 {cleaned} 个文件，下次清理将在 {clean_interval_hours} 小时后进行",
                    "B站解析",
                )

                await asyncio.sleep(clean_interval_seconds)
            except Exception as e:
                logger.error(f"缓存自动清理任务出错: {e}", "B站解析")
                await asyncio.sleep(3600)

    @staticmethod
    def _get_video_cache_key(video_id: str, page_num: int) -> str:
        """生成视频缓存键"""
        return f"{video_id}_{page_num}"

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
            logger.warning("无法从 Session 中获取有效的上下文 ID，将使用全局缓存 Key", "B站解析")
            return "global_fallback_cache"

    @classmethod
    async def _save_video_cache_index(cls):
        """保存视频缓存索引"""
        try:
            CACHE_INDEX_FILE.write_text(json.dumps(_video_cache_index, ensure_ascii=False), encoding="utf-8")
            logger.debug(f"视频缓存索引已保存: {len(_video_cache_index)} 个条目", "B站解析")
        except Exception as e:
            logger.error(f"保存视频缓存索引失败: {e}", "B站解析")

    @classmethod
    async def _load_url_cache_from_disk(cls):
        """从磁盘加载URL缓存数据"""
        global _url_context_caches

        if not URL_CACHE_FILE.exists():
            logger.info("URL缓存文件不存在，将使用空缓存", "B站解析")
            return

        try:
            async with _url_cache_lock:
                cache_data = json.loads(URL_CACHE_FILE.read_text(encoding="utf-8"))

                for context_key, urls_data in cache_data.items():
                    if context_key not in _url_context_caches:
                        _url_context_caches[context_key] = OrderedDict()

                    sorted_items = sorted(urls_data.items(), key=lambda x: x[1])

                    if len(sorted_items) > _URL_CONTEXT_CACHE_CAPACITY:
                        sorted_items = sorted_items[-_URL_CONTEXT_CACHE_CAPACITY:]

                    for url, timestamp in sorted_items:
                        _url_context_caches[context_key][url] = timestamp

                logger.info(
                    f"从磁盘加载了 {len(_url_context_caches)} 个上下文的URL缓存数据",
                    "B站解析",
                )
        except Exception as e:
            logger.error(f"从磁盘加载URL缓存失败: {e}", "B站解析")
            _url_context_caches = {}

    @classmethod
    async def _save_url_cache_to_disk(cls):
        """将URL缓存数据保存到磁盘"""
        try:
            async with _url_cache_lock:
                cache_data = {}
                for context_key, ordered_dict in _url_context_caches.items():
                    cache_data[context_key] = dict(ordered_dict)

                URL_CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")
                logger.debug(f"URL缓存数据已保存到磁盘: {URL_CACHE_FILE}", "B站解析")
        except Exception as e:
            logger.error(f"保存URL缓存到磁盘失败: {e}", "B站解析")
