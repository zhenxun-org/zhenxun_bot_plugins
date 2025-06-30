import mimetypes
import tempfile
from pathlib import Path
from PIL import Image
from urllib.parse import urlparse, urlunparse

from zhenxun.services.llm import api

from .storage_strategy import StorageStrategy

from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger

from ..config import (
    base_config,
)

image_cache_path = TEMP_PATH / 'bym_ai' / 'image_cache'

class GeminiStorageStrategy(StorageStrategy):
    def __init__(self, api_key: str):
        self.proxy_host = base_config.get("IMAGE_UNDERSTANDING_DATA_STORAGE_STRATEGY_GEMINI_PROXY")
        self.api_key = api_key
        self.base_url = f"https://{self.proxy_host}/upload/v1beta/files"

    def _compress_image_if_needed(self, file_path: Path, max_size: int) -> Path:
        """
        检查图片大小，如果超过限制则进行压缩。

        :param file_path: 原始文件的 Path 对象。
        :param max_size: 允许的最大文件大小（单位：字节）。
        """
        # 初始检查保持不变
        if not file_path.is_file():
            return file_path

        file_size = file_path.stat().st_size
        mime_type, _ = mimetypes.guess_type(file_path)

        if not (mime_type and mime_type.startswith("image/") and file_size > max_size):
            return file_path
    
        
        temp_path: Path | None = None
        image_cache_path.mkdir(parents=True, exist_ok=True)
        
        img = Image.open(file_path)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        with tempfile.NamedTemporaryFile(
            suffix=".jpg", 
            delete=False,
            dir=image_cache_path,
            prefix=f"{file_path.stem}_"
        ) as temp_file:
            temp_path = Path(temp_file.name)

        # 压缩循环保持不变
        current_quality = 85
        scale_factor = 0.9
        
        img.save(temp_path, "jpeg", quality=current_quality, optimize=True)
        
        while temp_path.stat().st_size > max_size:
            new_width = int(img.width * scale_factor)
            new_height = int(img.height * scale_factor)
            
            if new_width < 1 or new_height < 1:
                temp_path.unlink()
                return file_path

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            img.save(temp_path, "jpeg", quality=current_quality, optimize=True)
        
        return temp_path
        
    async def upload(self, file_path: Path) -> str | None:
        """
        使用两步可续传协议上传单个文件，并适配代理。
        如果文件是图片且大于指定大小，会先进行压缩。

        :param file_path: 要上传的文件的 Path 对象。
        :return: 图片上传成功后的地址，或在失败时返回 None。
        """
        if not file_path.is_file():
            return None
        
        # 检查并压缩文件
        path_for_upload = self._compress_image_if_needed(file_path, 4 * 1024 * 1024)

        # 准备上传元数据
        file_size = path_for_upload.stat().st_size
        mime_type, _ = mimetypes.guess_type(path_for_upload)
        if not mime_type:
            mime_type = "application/octet-stream"
        
        display_name = file_path.name
    
        # 初始化上传
        start_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        }
        metadata = {"file": {"display_name": display_name}}
        
        
        response_start = await AsyncHttpx.post(
            f"{self.base_url}?key={self.api_key}",
            headers=start_headers,
            json=metadata,
            timeout=30
        )
        response_start.raise_for_status()
        
        original_upload_url = response_start.headers.get("x-goog-upload-url")
        if not original_upload_url:
            return None
        
        # 替换为代理 URL
        parsed_url = urlparse(original_upload_url)
        proxied_url_parts = parsed_url._replace(netloc=self.proxy_host)
        proxied_upload_url = urlunparse(proxied_url_parts)

        # 上传文件
        upload_headers = {
            "Content-Type": mime_type,
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
        }

        try:
            response_upload = await AsyncHttpx.post(
                str(proxied_upload_url),
                headers=upload_headers,
                data=path_for_upload.read_bytes(),
                timeout=120
            )
            response_upload.raise_for_status()

            file_info = response_upload.json()
                
            return file_info['file']['uri']

        except Exception as e:
            logger.error("gemini 图片存储策略上传失败", "BYM_AI", e=e)
            return None