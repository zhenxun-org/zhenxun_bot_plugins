from pathlib import Path

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import FONT_PATH, IMAGE_PATH, DATA_PATH

base_config = Config.get("word_clouds")


class WordCloudConfig:
    """词云配置类 - 只包含路径相关的常量和方法"""

    _plugin_data_dir = DATA_PATH / "word_cloud"
    schedule_file_path = _plugin_data_dir / "schedule.json"

    @classmethod
    def get_font_path(cls) -> Path:
        """获取字体路径 (使用默认字体)

        返回:
            Path: 字体路径
        """
        return FONT_PATH / "STKAITI.TTF"

    @classmethod
    def get_userdict_path(cls) -> Path:
        """获取用户词典路径 (固定路径)

        返回:
            Path: 用户词典路径 (data/word_cloud/wordcloud_userdict.txt)
        """
        return cls._plugin_data_dir / "wordcloud_userdict.txt"

    @classmethod
    def get_stopwords_path(cls) -> Path:
        """获取停用词文件路径 (固定路径)

        返回:
            Path: 停用词文件路径 (data/word_cloud/wordcloud_stopwords.txt)
        """
        return cls._plugin_data_dir / "wordcloud_stopwords.txt"

    @classmethod
    def get_template_dir(cls) -> Path:
        """获取模板目录

        返回:
            Path: 模板目录
        """
        return IMAGE_PATH / "wordcloud"
