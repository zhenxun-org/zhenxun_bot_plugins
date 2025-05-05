from abc import ABC, abstractmethod
from typing import Dict, Optional


class BaseGenerator(ABC):
    """词云生成器基类"""

    @abstractmethod
    async def generate(
        self, word_frequencies: Dict[str, float], **kwargs
    ) -> Optional[bytes]:
        """生成词云"""
        pass
