import re
from typing import Dict, List
from collections import Counter
from emoji import replace_emoji
from nonebot.utils import run_sync

from zhenxun.services.log import logger
from ..utils.segmenter_pool import segmenter_pool


class TextProcessor:
    """文本处理服务，使用资源池管理分词器实例"""

    def __init__(self):
        """初始化文本处理器"""

    async def preprocess(self, messages: List[str], command_start: tuple) -> List[str]:
        """预处理消息文本，移除命令、链接和表情等"""
        return await self._preprocess_sync(messages, command_start)

    @run_sync
    def _preprocess_sync(self, messages: List[str], command_start: tuple) -> List[str]:
        """同步预处理消息文本（实际处理逻辑）"""
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
                processed_messages.append(processed)

        return processed_messages

    async def extract_keywords(self, messages: List[str], top_k: int = None) -> Dict[str, float]:
        """分词并统计词频，每条消息中的重复词只统计一次"""
        if not messages:
            return {}

        segmenter = None
        try:
            segmenter = await segmenter_pool.get_segmenter()
            stopwords = await segmenter_pool.get_stopwords()

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
                    filtered_words.append(word)

                total_remaining_words += len(filtered_words)
                unique_words = set(filtered_words)

                if unique_words:
                    message_word_sets.append(unique_words)

            if message_word_sets:
                logger.debug(
                    f"[过滤统计] 总词数: {total_words_count}个, 停用词过滤: {total_stopword_filtered}个, "
                    f"单字词过滤: {total_length_filtered}个, 剩余: {total_remaining_words}个, "
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

            word_frequencies = {
                word: float(count) for word, count in word_counts.items()
            }

            return word_frequencies

        except Exception as e:
            logger.error("使用 pkuseg 提取关键词时出错", e=e)
            return {}

        finally:
            if segmenter:
                await segmenter_pool.release_segmenter(segmenter)
