from pathlib import Path

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import FONT_PATH, IMAGE_PATH, DATA_PATH

base_config = Config.get("word_clouds")


class WordCloudConfig:
    """词云配置类"""

    _plugin_data_dir = DATA_PATH / "word_cloud"
    schedule_file_path = _plugin_data_dir / "schedule.json"

    IMAGE_DPI = 220
    IMAGE_QUALITY = 100
    RESOLUTION_FACTOR = 1.5

    DEFAULT_CACHE_TTL = 1
    YEARLY_CACHE_TTL = 336
    QUARTERLY_CACHE_TTL = 168
    MONTHLY_CACHE_TTL = 72
    WEEKLY_CACHE_TTL = 12

    @classmethod
    def get_font_path(cls) -> Path:
        """获取字体路径"""
        return FONT_PATH / "STKAITI.TTF"

    @classmethod
    def get_userdict_path(cls) -> Path:
        """获取用户词典路径"""
        return cls._plugin_data_dir / "wordcloud_userdict.txt"

    @classmethod
    def get_stopwords_path(cls) -> Path:
        """获取停用词文件路径"""
        return cls._plugin_data_dir / "wordcloud_stopwords.txt"

    @classmethod
    def get_template_dir(cls) -> Path:
        """获取模板目录"""
        return IMAGE_PATH / "wordcloud"
