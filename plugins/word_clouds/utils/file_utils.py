import os

from zhenxun.configs.path_config import FONT_PATH, IMAGE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx


async def ensure_resources() -> bool:
    """确保资源文件存在"""
    wordcloud_dir = IMAGE_PATH / "wordcloud"
    wordcloud_dir.mkdir(exist_ok=True, parents=True)

    zx_logo_path = wordcloud_dir / "default.png"
    wordcloud_ttf = FONT_PATH / "STKAITI.TTF"

    if not os.listdir(wordcloud_dir):
        url = "https://ghproxy.com/https://raw.githubusercontent.com/HibiKier/zhenxun_bot/main/resources/image/wordcloud/default.png"
        try:
            await AsyncHttpx.download_file(url, zx_logo_path)
        except Exception as e:
            logger.error("词云图片资源下载发生错误", e=e)
            return False

    if not wordcloud_ttf.exists():
        ttf_url = "https://ghproxy.com/https://raw.githubusercontent.com/HibiKier/zhenxun_bot/main/resources/font/STKAITI.TTF"
        try:
            await AsyncHttpx.download_file(ttf_url, wordcloud_ttf)
        except Exception as e:
            logger.error("词云字体资源下载发生错误", e=e)
            return False

    return True
