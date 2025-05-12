import os
import time
import hashlib
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import pickle

from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger

from ..config import WordCloudConfig


class CacheEntry:
    """缓存条目"""

    def __init__(self, data: Any, expire_time: float):
        self.data = data
        self.expire_time = expire_time
        self.create_time = time.time()

    def is_expired(self) -> bool:
        """检查缓存是否过期"""
        return time.time() > self.expire_time


class WordCloudCache:
    """词云缓存服务"""

    _instance = None

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = WordCloudCache()
        return cls._instance

    def __init__(self):
        self.cache: Dict[str, CacheEntry] = {}
        self.default_ttl = WordCloudConfig.DEFAULT_CACHE_TTL * 3600
        self.yearly_ttl = WordCloudConfig.YEARLY_CACHE_TTL * 3600
        self.quarterly_ttl = WordCloudConfig.QUARTERLY_CACHE_TTL * 3600
        self.monthly_ttl = WordCloudConfig.MONTHLY_CACHE_TTL * 3600
        self.weekly_ttl = WordCloudConfig.WEEKLY_CACHE_TTL * 3600
        self.max_cache_size = 100
        self.cleanup_threshold = 80
        self.cache_dir = self._get_cache_dir()
        self._ensure_cache_dir()
        self._load_persistent_cache()

    def _get_cache_dir(self) -> Path:
        """获取缓存目录的绝对路径"""
        cache_dir = TEMP_PATH / "word_clouds"
        return cache_dir

    def _ensure_cache_dir(self) -> None:
        """确保缓存目录存在"""
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.debug(f"确保缓存目录存在: {self.cache_dir}")

    def _get_cache_file_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{key}.pkl"

    def _create_hash_key(self, key_str: str) -> str:
        """创建哈希键"""
        hash_key = hashlib.md5(key_str.encode()).hexdigest()
        logger.debug(f"生成缓存键: 原始字符串='{key_str}', 哈希值={hash_key}")
        return hash_key

    def _save_to_disk(self, key: str, entry: CacheEntry) -> bool:
        """将缓存保存到磁盘"""
        try:
            cache_file = self._get_cache_file_path(key)
            with open(cache_file, "wb") as f:
                pickle.dump(entry, f)
            logger.debug(f"已将缓存保存到磁盘: {cache_file}")
            return True
        except Exception as e:
            logger.error(f"保存缓存到磁盘失败: {e}")
            return False

    def _load_from_disk(self, key: str) -> Optional[CacheEntry]:
        """从磁盘加载缓存"""
        try:
            cache_file = self._get_cache_file_path(key)
            if not os.path.exists(cache_file):
                return None

            with open(cache_file, "rb") as f:
                entry = pickle.load(f)

            if entry.is_expired():
                os.remove(cache_file)
                logger.debug(f"删除过期的缓存文件: {cache_file}")
                return None

            logger.debug(f"从磁盘加载缓存: {cache_file}")
            return entry
        except Exception as e:
            logger.error(f"从磁盘加载缓存失败: {e}")
            return None

    def _load_persistent_cache(self) -> None:
        """加载所有持久化缓存"""
        try:
            if not os.path.exists(self.cache_dir):
                return

            count = 0
            for file in os.listdir(self.cache_dir):
                if file.endswith(".pkl"):
                    key = file[:-4]
                    entry = self._load_from_disk(key)
                    if entry and not entry.is_expired():
                        self.cache[key] = entry
                        count += 1

            if count > 0:
                logger.info(f"已从磁盘加载 {count} 个缓存条目")
        except Exception as e:
            logger.error(f"加载持久化缓存失败: {e}")

    def _get_date_type_from_time_span(
        self, start_time: datetime, end_time: datetime
    ) -> str:
        """根据时间跨度推断日期类型"""
        if self.is_yearly_request(start_time, end_time):
            return "年度"

        time_span = end_time - start_time

        if 80 <= time_span.days < 100:
            return "本季"

        if (
            start_time.year == end_time.year and start_time.month == end_time.month
        ) or (20 <= time_span.days < 40):
            return "本月"

        if 5 <= time_span.days < 10:
            return "本周"

        if start_time.date() == end_time.date():
            if start_time.date() == datetime.now().date():
                return "今日"
            if start_time.date() == (datetime.now().date() - timedelta(days=1)):
                return "昨日"
            return "今日"

        return "自定义"

    def _build_cache_key_from_date_type(
        self,
        user_id: Optional[int],
        group_id: int,
        date_type: str,
        start_time: datetime,
        end_time: datetime,
    ) -> str:
        """根据日期类型构建缓存键"""
        user_part = f"{user_id or 'all'}"

        if date_type in ["今日", "昨日"]:
            date_str = start_time.strftime("%Y-%m-%d")
            key_str = f"{user_part}:{group_id}:daily:{date_str}"
            logger.debug(f"生成日度词云缓存键: {key_str}")

        elif date_type in ["本周", "上周"]:
            year = start_time.year
            week = start_time.isocalendar()[1]
            current_day = datetime.now().strftime("%Y-%m-%d")
            key_str = f"{user_part}:{group_id}:weekly:{year}:W{week}:{current_day}"
            logger.debug(f"生成周度词云缓存键: {key_str}")

        elif date_type in ["本月", "上月"]:
            month_str = start_time.strftime("%Y-%m")
            key_str = f"{user_part}:{group_id}:monthly:{month_str}"
            logger.debug(f"生成月度词云缓存键: {key_str}")

        elif date_type == "本季":
            year = start_time.year
            quarter = (start_time.month - 1) // 3 + 1
            current_month = datetime.now().month
            key_str = (
                f"{user_part}:{group_id}:quarterly:{year}:Q{quarter}:{current_month}"
            )
            logger.debug(f"生成季度词云缓存键: {key_str}")

        elif date_type == "年度":
            year = start_time.year
            current_month = datetime.now().month
            key_str = f"{user_part}:{group_id}:yearly:{year}:{current_month}"
            logger.debug(f"生成年度词云缓存键: {key_str}")

        else:
            start_str = start_time.strftime("%Y-%m-%d-%H-%M")
            end_str = end_time.strftime("%Y-%m-%d-%H-%M")
            key_str = f"{user_part}:{group_id}:custom:{start_str}:{end_str}"
            logger.debug(f"生成自定义时间范围词云缓存键: {key_str}")

        return self._create_hash_key(key_str)

    def generate_key(
        self,
        user_id: Optional[int],
        group_id: int,
        start_time: datetime,
        end_time: datetime,
        is_yearly: bool = None,
        date_type: str = None,
    ) -> str:
        """生成缓存键"""
        if not date_type:
            if is_yearly is not None and is_yearly:
                date_type = "年度"
            else:
                date_type = self._get_date_type_from_time_span(start_time, end_time)

        logger.debug(f"使用日期类型生成缓存键: {date_type}")
        return self._build_cache_key_from_date_type(
            user_id, group_id, date_type, start_time, end_time
        )

    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        if key in self.cache:
            entry = self.cache[key]
            if entry.is_expired():
                logger.debug(f"内存缓存已过期: {key}")
                del self.cache[key]
                try:
                    cache_file = self._get_cache_file_path(key)
                    if os.path.exists(cache_file):
                        os.remove(cache_file)
                except Exception:
                    pass
                return None

            logger.debug(
                f"命中内存缓存: {key}, 已缓存 {int(time.time() - entry.create_time)} 秒"
            )
            return entry.data

        entry = self._load_from_disk(key)
        if entry:
            self.cache[key] = entry
            logger.debug(
                f"命中磁盘缓存: {key}, 已缓存 {int(time.time() - entry.create_time)} 秒"
            )
            return entry.data

        return None

    def set(
        self, key: str, data: Any, ttl: Optional[int] = None, persist: bool = False
    ) -> None:
        """设置缓存数据"""
        if len(self.cache) >= self.cleanup_threshold:
            self._cleanup()

        if len(self.cache) >= self.max_cache_size:
            self._remove_oldest()

        expire_time = time.time() + (ttl if ttl is not None else self.default_ttl)
        entry = CacheEntry(data, expire_time)
        self.cache[key] = entry

        logger.debug(
            f"已缓存数据: {key}, TTL: {ttl if ttl is not None else self.default_ttl} 秒"
        )

        if persist:
            self._save_to_disk(key, entry)

    def invalidate(self, key: str) -> bool:
        """使缓存失效"""
        result = False

        if key in self.cache:
            del self.cache[key]
            result = True

        try:
            cache_file = self._get_cache_file_path(key)
            if os.path.exists(cache_file):
                os.remove(cache_file)
                result = True
        except Exception as e:
            logger.error(f"删除磁盘缓存失败: {e}")

        if result:
            logger.debug(f"已使缓存失效: {key}")

        return result

    def clear(self) -> None:
        """清空所有缓存"""
        self.cache.clear()

        try:
            if os.path.exists(self.cache_dir):
                for file in os.listdir(self.cache_dir):
                    if file.endswith(".pkl"):
                        os.remove(os.path.join(self.cache_dir, file))
        except Exception as e:
            logger.error(f"清空磁盘缓存失败: {e}")

        logger.debug("已清空所有缓存")

    def _cleanup(self) -> None:
        """清理过期缓存"""
        expired_keys = [key for key, entry in self.cache.items() if entry.is_expired()]
        for key in expired_keys:
            del self.cache[key]
            try:
                cache_file = self._get_cache_file_path(key)
                if os.path.exists(cache_file):
                    os.remove(cache_file)
            except Exception:
                pass

        if expired_keys:
            logger.debug(f"已清理 {len(expired_keys)} 个过期缓存")

    def _remove_oldest(self) -> None:
        """移除最旧的缓存条目"""
        if not self.cache:
            return
        oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].create_time)
        del self.cache[oldest_key]
        try:
            cache_file = self._get_cache_file_path(oldest_key)
            if os.path.exists(cache_file):
                os.remove(cache_file)
        except Exception:
            pass

        logger.debug(f"已移除最旧的缓存条目: {oldest_key}")

    def is_yearly_request(self, start_time: datetime, end_time: datetime) -> bool:
        """检查是否为年度请求"""
        if start_time.month == 1 and start_time.day == 1:
            logger.debug(
                f"检测到年度请求(1月1日开始): 开始={start_time}, 结束={end_time}"
            )
            return True

        time_span = end_time - start_time
        is_yearly = time_span.days >= 300

        if is_yearly:
            logger.debug(
                f"检测到年度请求(时间跨度): 时间跨度={time_span.days}天, 开始={start_time}, 结束={end_time}"
            )

        return is_yearly

    def get_ttl(self, start_time: datetime, end_time: datetime) -> int:
        """根据请求类型获取TTL"""
        if self.is_yearly_request(start_time, end_time):
            return self.yearly_ttl

        time_span = end_time - start_time
        if 80 <= time_span.days < 100:
            logger.debug(f"检测到季度请求: 时间跨度={time_span.days}天")
            return self.quarterly_ttl

        if (
            start_time.year == end_time.year and start_time.month == end_time.month
        ) or (20 <= time_span.days < 40):
            logger.debug(f"检测到月度请求: 时间跨度={time_span.days}天")
            return self.monthly_ttl

        if 5 <= time_span.days < 10:
            logger.debug(f"检测到周度请求: 时间跨度={time_span.days}天")
            return self.weekly_ttl

        return self.default_ttl


word_cloud_cache = WordCloudCache.get_instance()
