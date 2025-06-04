import spacy_pkuseg as pkuseg
from typing import Dict, Any
from pathlib import Path

from zhenxun.services.log import logger
from nonebot import get_driver

from .resource_pool import AsyncResourcePool
from ..config import WordCloudConfig


class SegmenterPool:
    """分词器资源池管理器，单例模式"""

    _instance = None

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = SegmenterPool()
        return cls._instance

    def __init__(self):
        """初始化分词器池"""
        self.pool = None
        self.stopwords = set()
        self.userdict_path = None
        self.stopwords_path = None
        self._initialized = False

    async def initialize(self):
        """初始化分词器池"""
        if self._initialized:
            return

        self.userdict_path = WordCloudConfig.get_userdict_path()
        self.stopwords_path = WordCloudConfig.get_stopwords_path()
        self.userdict_path.parent.mkdir(parents=True, exist_ok=True)
        self.stopwords_path.parent.mkdir(parents=True, exist_ok=True)

        await self._load_stopwords()

        self.pool = AsyncResourcePool(
            factory=self._create_segmenter,
            max_size=5,
            min_size=2,
            max_idle_time=600,
            cleanup_interval=300,
            name="SegmenterPool",
        )

        await self.pool._initialize_pool()
        await self.pool.start_cleanup()

        self._initialized = True
        logger.info("分词器资源池初始化完成")

    async def _load_stopwords(self):
        """加载停用词"""
        self.stopwords = set()
        default_stopwords_count = 0
        assets_stopwords_count = 0

        if self.stopwords_path.exists() and self.stopwords_path.stat().st_size > 0:
            try:
                with open(self.stopwords_path, "r", encoding="utf-8") as f:
                    default_stopwords = {line.strip() for line in f if line.strip()}
                    default_stopwords_count = len(default_stopwords)
                    self.stopwords.update(default_stopwords)
            except Exception as e:
                logger.error(f"加载默认停用词表失败: {self.stopwords_path}", e=e)

        assets_stopwords_path = (
            Path(__file__).parent.parent / "assets" / "stopwords.txt"
        )
        if assets_stopwords_path.exists() and assets_stopwords_path.stat().st_size > 0:
            try:
                with open(assets_stopwords_path, "r", encoding="utf-8") as f:
                    assets_stopwords = {line.strip() for line in f if line.strip()}
                    assets_stopwords_count = len(assets_stopwords)
                    self.stopwords.update(assets_stopwords)
            except Exception as e:
                logger.error(f"加载额外停用词表失败: {assets_stopwords_path}", e=e)

        total_stopwords = len(self.stopwords)
        logger.debug(
            f"[停用词加载] 默认停用词: {default_stopwords_count}个 + 额外停用词: {assets_stopwords_count}个 = 总计: {total_stopwords}个"
        )

    def _create_segmenter(self):
        """创建分词器实例"""
        pkuseg_userdict_param = "default"
        if self.userdict_path.exists() and self.userdict_path.stat().st_size > 0:
            pkuseg_userdict_param = str(self.userdict_path)
            logger.debug(f"将使用词云用户词典: {self.userdict_path}")

        try:
            segmenter = pkuseg.pkuseg(model_name="web", user_dict=pkuseg_userdict_param)
            logger.debug("pkuseg 分词器初始化成功")
            return segmenter
        except Exception as e:
            logger.error("初始化 pkuseg 分词器失败", e=e)
            raise

    async def get_segmenter(self):
        """获取分词器实例"""
        if not self._initialized:
            await self.initialize()

        return await self.pool.acquire()

    async def release_segmenter(self, segmenter):
        """释放分词器实例"""
        if not self._initialized:
            return

        await self.pool.release(segmenter)

    async def get_stopwords(self):
        """获取停用词集合"""
        if not self._initialized:
            await self.initialize()

        return self.stopwords

    async def get_stats(self) -> Dict[str, Any]:
        """获取资源池统计信息"""
        if not self._initialized:
            return {"initialized": False}

        stats = await self.pool.get_stats()
        stats["stopwords_count"] = len(self.stopwords)
        return stats

    async def shutdown(self):
        """关闭资源池"""
        if self.pool:
            await self.pool.stop_cleanup()
            logger.info("分词器资源池已关闭")


segmenter_pool = SegmenterPool.get_instance()

driver = get_driver()


@driver.on_startup
async def _():
    await segmenter_pool.initialize()


@driver.on_shutdown
async def _():
    await segmenter_pool.shutdown()
