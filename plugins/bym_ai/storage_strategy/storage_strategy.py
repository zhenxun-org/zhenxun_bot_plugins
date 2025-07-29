from abc import ABC, abstractmethod
from pathlib import Path


class StorageStrategy(ABC):
    @abstractmethod
    async def upload(self, file_path: Path) -> str | None:
        pass
