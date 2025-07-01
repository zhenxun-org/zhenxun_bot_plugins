from ..config import (
    base_config,
)
from .gemini_storage_strategy import GeminiStorageStrategy
from .storage_strategy import StorageStrategy


class StorageStrategyFactory:
    @staticmethod
    def create_strategy(**kwargs) -> StorageStrategy | None:
        data_storage_strategy = base_config.get(
            "IMAGE_UNDERSTANDING_DATA_STORAGE_STRATEGY"
        )
        if data_storage_strategy == "gemini":
            if api_key := kwargs.get("api_key"):
                return GeminiStorageStrategy(api_key=api_key)
