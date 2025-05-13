# 导入所有命令模块
from .login import login_matcher
from .download import (
    _perform_video_download,
    _perform_bangumi_download,
    bili_download_matcher,
    auto_download_matcher,
)

__all__ = [
    "login_matcher",
    "_perform_video_download",
    "_perform_bangumi_download",
    "bili_download_matcher",
    "auto_download_matcher",
]
