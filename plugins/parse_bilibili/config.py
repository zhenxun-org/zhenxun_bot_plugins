from typing import Optional, Dict
import asyncio
import json
import aiofiles

from bilibili_api import Credential
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
base_config = Config.get(MODULE_NAME)

HTTP_TIMEOUT = 30
HTTP_CONNECT_TIMEOUT = 10

CREDENTIAL_FILE = DATA_PATH / MODULE_NAME / "credential.json"

bili_credential: Optional[Credential] = None
_credential_lock = asyncio.Lock()
_credential_loaded = False


async def load_credential_from_file():
    """从文件加载 Credential"""
    global bili_credential, _credential_loaded
    async with _credential_lock:
        if _credential_loaded:
            return
        if CREDENTIAL_FILE.exists():
            try:
                async with aiofiles.open(CREDENTIAL_FILE, "r", encoding="utf-8") as f:
                    content = await f.read()
                    if content.strip():
                        data = json.loads(content)
                        bili_credential = Credential(
                            sessdata=data.get("sessdata"),
                            bili_jct=data.get("bili_jct"),
                            buvid3=data.get("buvid3"),
                            buvid4=data.get("buvid4"),
                            dedeuserid=data.get("dedeuserid"),
                            ac_time_value=data.get("ac_time_value"),
                        )
                        logger.info(f"成功从文件加载 B站 Credential: {CREDENTIAL_FILE}")
                    else:
                        logger.info(f"Credential 文件为空: {CREDENTIAL_FILE}")
            except Exception as e:
                logger.error(f"加载 Credential 文件失败: {CREDENTIAL_FILE}", e=e)
                bili_credential = None
        else:
            logger.info(f"未找到 Credential 文件: {CREDENTIAL_FILE}")
        _credential_loaded = True


async def save_credential_to_file(credential: Credential):
    """将 Credential 保存到文件"""
    global bili_credential
    async with _credential_lock:
        try:
            credential_dict = {
                "sessdata": credential.sessdata,
                "bili_jct": credential.bili_jct,
                "buvid3": credential.buvid3,
                "buvid4": credential.buvid4,
                "dedeuserid": credential.dedeuserid,
                "ac_time_value": credential.ac_time_value,
            }
            CREDENTIAL_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_file = CREDENTIAL_FILE.with_suffix(".json.tmp")
            async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(credential_dict, ensure_ascii=False, indent=2))
            temp_file.replace(CREDENTIAL_FILE)
            bili_credential = credential
            logger.info(
                f"全局 bili_credential 已更新。保存 Credential 到文件: {CREDENTIAL_FILE}"
            )
        except Exception as e:
            logger.error(f"保存 Credential 文件失败: {CREDENTIAL_FILE}", e=e)


def get_credential() -> Optional[Credential]:
    """获取当前的全局 Credential 对象"""
    return bili_credential


PLUGIN_CACHE_DIR = DATA_PATH / MODULE_NAME / "cache"
PLUGIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

PLUGIN_TEMP_DIR = TEMP_PATH / MODULE_NAME
PLUGIN_TEMP_DIR.mkdir(parents=True, exist_ok=True)

SCREENSHOT_ELEMENT_OPUS = "#app > div.opus-detail > div.bili-opus-view"
SCREENSHOT_ELEMENT_ARTICLE = ".article-holder"
SCREENSHOT_TIMEOUT = 60

