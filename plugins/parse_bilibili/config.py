from typing import Optional, Dict
import asyncio
import time

try:
    from bilibili_api import Credential
except ImportError:
    raise ImportError(
        "错误：无法导入 bilibili_api 模块。\n"
        "请确保已安装 bilibili-api-python 包，而不是 bilibili-api。\n"
        "请使用以下命令安装：pip install bilibili-api-python"
    )
from zhenxun.configs.config import Config
from zhenxun.configs.path_config import DATA_PATH, TEMP_PATH
from zhenxun.services.log import logger


def cookies_str_to_dict(cookies_str: str) -> Dict[str, str]:
    """将cookies字符串转换为字典"""
    cookies = {}
    if not cookies_str:
        return cookies
    try:
        items = cookies_str.split(";")
        for item in items:
            if "=" not in item:
                continue
            item = item.strip()
            key, value = item.split("=", 1)
            cookies[key.strip()] = value.strip()
    except Exception:
        pass
    return cookies


MODULE_NAME = "parse_bilibili"
MODULE_NAME_BILI = "BiliBili"
base_config = Config.get(MODULE_NAME)

HTTP_TIMEOUT = 30
HTTP_CONNECT_TIMEOUT = 10

bili_credential: Optional[Credential] = None
_credential_lock = asyncio.Lock()
_credential_loaded = False
_last_refresh_check_time = 0
_REFRESH_CHECK_INTERVAL = 24 * 60 * 60


async def load_credential_from_file():
    """从配置加载 Credential"""
    global bili_credential, _credential_loaded
    async with _credential_lock:
        if _credential_loaded:
            return

        try:
            cookies_str = Config.get(MODULE_NAME_BILI).get("COOKIES", "")
            if cookies_str:
                cookies_dict = cookies_str_to_dict(cookies_str)

                bili_credential = Credential(
                    sessdata=cookies_dict.get("SESSDATA"),
                    bili_jct=cookies_dict.get("bili_jct"),
                    buvid3=cookies_dict.get("buvid3"),
                    buvid4=cookies_dict.get("buvid4"),
                    dedeuserid=cookies_dict.get("DedeUserID"),
                    ac_time_value=cookies_dict.get("ac_time_value"),
                )
                logger.info("成功从模块变量加载 B站 Credential")
            else:
                logger.info("模块变量中的 Cookies 为空")
                bili_credential = None
        except Exception as e:
            logger.error("加载 Credential 失败", e=e)
            bili_credential = None

        _credential_loaded = True


async def save_credential_to_file(credential: Credential):
    """将 Credential 保存到模块变量"""
    global bili_credential
    async with _credential_lock:
        try:
            cookies_parts = []
            if credential.sessdata:
                cookies_parts.append(f"SESSDATA={credential.sessdata}")
            if credential.bili_jct:
                cookies_parts.append(f"bili_jct={credential.bili_jct}")
            if credential.buvid3:
                cookies_parts.append(f"buvid3={credential.buvid3}")
            if credential.buvid4:
                cookies_parts.append(f"buvid4={credential.buvid4}")
            if credential.dedeuserid:
                cookies_parts.append(f"DedeUserID={credential.dedeuserid}")
            if credential.ac_time_value:
                cookies_parts.append(f"ac_time_value={credential.ac_time_value}")

            cookies_str = "; ".join(cookies_parts)

            Config.set_config(MODULE_NAME_BILI, "COOKIES", cookies_str, auto_save=True)

            bili_credential = credential
            logger.info("全局 bili_credential 已更新并保存到模块变量")
        except Exception as e:
            logger.error("保存 Credential 失败", e=e)


def get_credential() -> Optional[Credential]:
    """获取当前的全局 Credential 对象"""
    return bili_credential


async def check_and_refresh_credential():
    """检查并刷新凭证（如果需要）"""
    global _last_refresh_check_time, bili_credential

    current_time = time.time()
    if current_time - _last_refresh_check_time < _REFRESH_CHECK_INTERVAL:
        return

    _last_refresh_check_time = current_time

    if not bili_credential or not bili_credential.has_ac_time_value():
        logger.debug("凭证不存在或没有 ac_time_value，无法刷新")
        return

    try:
        need_refresh = await bili_credential.check_refresh()
        if need_refresh:
            logger.info("B站凭证需要刷新，正在刷新...")
            await bili_credential.refresh()
            await save_credential_to_file(bili_credential)
            logger.info("B站凭证刷新成功")
        else:
            logger.debug("B站凭证不需要刷新")
    except Exception as e:
        logger.error("检查或刷新凭证时出错", e=e)


PLUGIN_CACHE_DIR = DATA_PATH / MODULE_NAME / "cache"
PLUGIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

PLUGIN_TEMP_DIR = TEMP_PATH / MODULE_NAME
PLUGIN_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# 图片缓存目录
IMAGE_CACHE_DIR = PLUGIN_TEMP_DIR / "image"
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

SCREENSHOT_ELEMENT_OPUS = "#app > div.opus-detail > div.bili-opus-view"
SCREENSHOT_ELEMENT_ARTICLE = ".article-holder"
SCREENSHOT_TIMEOUT = 60


# 视频下载和发送相关配置
DOWNLOAD_TIMEOUT = 120  # 下载超时时间(秒)
DOWNLOAD_MAX_RETRIES = 3  # 下载文件最大重试次数
SEND_VIDEO_MAX_RETRIES = 3  # 发送视频最大重试次数
SEND_VIDEO_RETRY_DELAY = 5.0  # 发送视频重试基础延迟(秒)
SEND_VIDEO_TIMEOUT = 120  # 发送视频超时时间(秒)
