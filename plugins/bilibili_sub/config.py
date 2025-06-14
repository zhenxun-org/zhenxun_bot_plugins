from zhenxun.configs.path_config import DATA_PATH, IMAGE_PATH
from zhenxun.utils.utils import ResourceDirManager

LOG_COMMAND = "bilibili_sub"
BASE_PATH = DATA_PATH / "bilibili_sub"

BASE_PATH.mkdir(parents=True, exist_ok=True)

SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/all/v2"

DYNAMIC_PATH = IMAGE_PATH / "bilibili_sub" / "dynamic"
DYNAMIC_PATH.mkdir(exist_ok=True, parents=True)

ResourceDirManager.add_temp_dir(DYNAMIC_PATH)
