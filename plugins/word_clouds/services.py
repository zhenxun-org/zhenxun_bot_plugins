from collections import Counter
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import pickle
import re
import time
from typing import Any

from emoji import replace_emoji
from nonebot.utils import run_sync
import pytz

from zhenxun.configs.path_config import DATA_PATH
from zhenxun.models.chat_history import ChatHistory
from zhenxun.services.log import logger

from .config import WordCloudConfig
from .models import MessageData, WordCloudTaskParams
from .utils.segmenter_pool import segmenter_pool


class TimeService:
    """时间服务"""

    @staticmethod
    def get_datetime_now_with_timezone() -> datetime:
        """获取当前时间(带时区)"""
        return datetime.now().astimezone()

    @staticmethod
    def get_datetime_fromisoformat_with_timezone(date_string: str) -> datetime:
        """从ISO格式字符串获取时间(带时区)"""
        return datetime.fromisoformat(date_string).astimezone()

    @staticmethod
    def get_time_range(time_type: str) -> tuple[datetime, datetime]:
        """获取时间范围"""
        dt = TimeService.get_datetime_now_with_timezone()

        if time_type == "今日":
            start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            stop = dt
        elif time_type == "昨日":
            stop = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            start = stop - timedelta(days=1)
        elif time_type == "本周":
            start = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                days=dt.weekday()
            )
            stop = dt
        elif time_type == "上周":
            this_week_start = dt.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=dt.weekday())
            start = this_week_start - timedelta(days=7)
            stop = this_week_start
        elif time_type == "本月":
            start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            stop = dt
        elif time_type == "上月":
            this_month_start = dt.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            last_month_end = this_month_start - timedelta(days=1)
            start = last_month_end.replace(day=1)
            stop = this_month_start
        elif time_type == "本季":
            quarter_month = ((dt.month - 1) // 3) * 3 + 1
            start = dt.replace(
                month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            stop = dt
        elif time_type == "年度":
            start = dt.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            stop = dt
        else:
            start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            stop = dt

        return start, stop

    @staticmethod
    def parse_time_range(time_str: str) -> tuple[datetime, datetime] | None:
        """解析 YYYY-MM-DD 或 MM-DD 格式的日期范围字符串"""

        def _parse_date_str(d_str: str) -> datetime:
            d_str = d_str.strip()
            if re.fullmatch(r"^\d{1,2}-\d{1,2}$", d_str):
                d_str = f"{datetime.now().year}-{d_str}"
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            return dt.astimezone()

        match = re.match(r"^(.+?)(?:~(.+))?$", time_str)
        if not match:
            return None

        start_str, stop_str = match.groups()

        try:
            start_dt = _parse_date_str(start_str)
            start = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            stop = (
                (
                    _parse_date_str(stop_str).replace(
                        hour=23, minute=59, second=59, microsecond=999999
                    )
                )
                if stop_str
                else (start + timedelta(days=1))
            )
            return start, stop
        except ValueError:
            return None

    @staticmethod
    def convert_to_timezone(
        dt: datetime, timezone_str: str = "Asia/Shanghai"
    ) -> datetime:
        """将时间转换到指定时区"""
        return dt.astimezone(pytz.timezone(timezone_str))


class DataService:
    """数据服务"""

    @staticmethod
    async def get_messages(
        user_id: int | None, group_id: int, time_range: tuple[datetime, datetime]
    ) -> MessageData | None:
        """获取消息数据"""
        start, stop = time_range

        messages_list = await ChatHistory().get_message(
            uid=str(user_id) if user_id else None,  # type: ignore
            gid=str(group_id),
            type_="group",
            days=(start, stop),
        )

        if not messages_list:
            return None

        return MessageData(
            messages=[i.plain_text for i in messages_list],
            user_id=user_id,
            group_id=group_id,
            start_time=start,
            end_time=stop,
        )

    @staticmethod
    async def get_messages_stream(
        user_id: int | None,
        group_id: int,
        time_range: tuple[datetime, datetime],
        chunk_size: int = 50000,
    ) -> AsyncGenerator[list[str], None]:
        """
        以流式（异步生成器）方式分块获取消息数据。
        这用于处理可能导致内存溢出的大量数据查询。
        """
        start, stop = time_range
        offset = 0

        while True:
            query = ChatHistory.filter(
                group_id=str(group_id),
                create_time__range=(start, stop),
            )
            if user_id:
                query = query.filter(user_id=str(user_id))

            messages_list = await query.offset(offset).limit(chunk_size).all()

            if not messages_list:
                break

            yield [i.plain_text for i in messages_list if i.plain_text]

            if len(messages_list) < chunk_size:
                break

            offset += chunk_size


class TextProcessor:
    """文本处理服务"""

    def __init__(self):
        pass

    async def preprocess(self, messages: list[str], command_start: tuple) -> list[str]:
        """预处理消息文本，移除命令、链接和表情等"""
        return await self._preprocess_sync(messages, command_start)

    @run_sync
    def _preprocess_sync(self, messages: list[str], command_start: tuple) -> list[str]:
        """同步预处理消息文本"""
        processed_messages = []
        for message in messages:
            if message.startswith(command_start):
                continue

            processed = message
            processed = re.sub(r"https?://[\w/:%#\$&\?\(\)~\.=\+\-]+", "", processed)
            processed = re.sub(r"[\u200b]", "", processed)
            processed = re.sub(r"\[CQ:.*?]", "", processed)
            processed = re.sub("[	(1|3);]", "", processed)
            processed = replace_emoji(processed)

            if processed.strip():
                symbols_pattern = r"^[^\u4e00-\u9fa5a-zA-Z0-9]+$"
                if not re.match(symbols_pattern, processed.strip()):
                    processed_messages.append(processed)

        return processed_messages

    async def extract_keywords(
        self, messages: list[str], top_k: int | None = None
    ) -> dict[str, float]:
        """分词并统计词频"""
        if not messages:
            return {}

        segmenter = None
        try:
            segmenter = await segmenter_pool.get_segmenter()
            stopwords = await segmenter_pool.get_stopwords()

            return await self._extract_keywords_sync(
                messages, segmenter, stopwords, top_k
            )

        except Exception as e:
            logger.error("使用 pkuseg 提取关键词时出错", e=e)
            return {}

        finally:
            if segmenter:
                await segmenter_pool.release_segmenter(segmenter)

    @run_sync
    def _extract_keywords_sync(
        self, messages: list[str], segmenter, stopwords, top_k: int | None = None
    ) -> dict[str, float]:
        """同步执行分词和关键词提取（在线程池中执行）"""
        message_word_sets = []
        total_words_count = 0
        total_stopword_filtered = 0
        total_length_filtered = 0
        total_remaining_words = 0

        for message in messages:
            if not message.strip():
                continue

            words = segmenter.cut(message)
            words_count = len(words)
            total_words_count += words_count

            filtered_words = []

            for word in words:
                if word in stopwords:
                    total_stopword_filtered += 1
                    continue
                if len(word.strip()) <= 1:
                    total_length_filtered += 1
                    continue
                if re.match(r"^[^\u4e00-\u9fa5a-zA-Z0-9]+$", word.strip()):
                    total_stopword_filtered += 1
                    continue
                filtered_words.append(word)

            total_remaining_words += len(filtered_words)
            unique_words = set(filtered_words)

            if unique_words:
                message_word_sets.append(unique_words)

        if message_word_sets:
            logger.debug(
                f"[过滤统计] 总词数: {total_words_count}个, "
                f"停用词过滤: {total_stopword_filtered}个, "
                f"单字词过滤: {total_length_filtered}个, "
                f"剩余: {total_remaining_words}个, "
                f"停用词表大小: {len(stopwords)}个"
            )
        else:
            logger.warning("[过滤] pkuseg 分词结果为空")
            return {}

        word_counts = Counter()
        for word_set in message_word_sets:
            word_counts.update(word_set)

        if not word_counts:
            logger.warning("[过滤] 没有找到有效的词汇进行统计")
            return {}

        word_frequencies = {word: float(count) for word, count in word_counts.items()}

        return word_frequencies


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
        self.cache: dict[str, CacheEntry] = {}
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
        cache_dir = DATA_PATH / "cache" / "word_clouds"
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

    def _load_from_disk(self, key: str) -> CacheEntry | None:
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

    def _is_today_request(self, start_time: datetime, end_time: datetime) -> bool:
        """检查是否为今日词云请求"""
        today = datetime.now(start_time.tzinfo).date()
        return start_time.date() == end_time.date() == today

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
            if self._is_today_request(start_time, end_time):
                return "今日"
            yesterday = datetime.now(start_time.tzinfo).date() - timedelta(days=1)
            if start_time.date() == yesterday:
                return "昨日"

        return "自定义"

    def _build_cache_key_from_date_type(
        self,
        user_id: int | None,
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

    def generate_key(self, params: WordCloudTaskParams) -> str:
        """生成缓存键"""
        date_type = params.date_type or self._get_date_type_from_time_span(
            params.start_time, params.end_time
        )

        if params.is_yearly:
            date_type = "年度"

        logger.debug(f"使用日期类型生成缓存键: {date_type}")
        return self._build_cache_key_from_date_type(
            params.user_id,
            params.group_id,
            date_type,
            params.start_time,
            params.end_time,
        )

    def _calculate_ttl(
        self, date_type: str | None, start_time: datetime, end_time: datetime
    ) -> int:
        """根据日期类型和时间范围计算缓存TTL"""
        if date_type in ["本月", "上月"]:
            ttl = self.monthly_ttl
            logger.debug(f"使用月度缓存TTL: {ttl // 3600}小时")
        elif date_type in ["本周", "上周"]:
            ttl = self.weekly_ttl
            logger.debug(f"使用周度缓存TTL: {ttl // 3600}小时")
        elif date_type == "年度":
            ttl = self.yearly_ttl
            logger.debug(f"使用年度缓存TTL: {ttl // 3600}小时")
        elif date_type == "本季":
            ttl = self.quarterly_ttl
            logger.debug(f"使用季度缓存TTL: {ttl // 3600}小时")
        else:
            ttl = self.get_ttl(start_time, end_time)
            logger.debug(f"根据时间范围判断使用缓存TTL: {ttl // 3600}小时")

        return ttl

    def get(self, key: str) -> Any | None:
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

    def set(self, key: str, data: Any, *, params: WordCloudTaskParams) -> None:
        """设置缓存数据"""
        if len(self.cache) >= self.cleanup_threshold:
            self._cleanup()

        if len(self.cache) >= self.max_cache_size:
            self._remove_oldest()

        ttl = self._calculate_ttl(params.date_type, params.start_time, params.end_time)
        persist = not self._is_today_request(params.start_time, params.end_time)

        expire_time = time.time() + ttl
        entry = CacheEntry(data, expire_time)
        self.cache[key] = entry

        logger.debug(f"已缓存数据: {key}, TTL: {ttl} 秒, 持久化: {persist}")

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

__all__ = [
    "DataService",
    "TextProcessor",
    "TimeService",
    "word_cloud_cache",
]
