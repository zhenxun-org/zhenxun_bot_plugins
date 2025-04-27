import asyncio
import json
from typing import Set

import aiofiles
from nonebot_plugin_session import EventSession

from zhenxun.configs.path_config import DATA_PATH
from zhenxun.services.log import logger

MODULE_NAME = "parse_bilibili"
AUTO_DOWNLOAD_FILE = DATA_PATH / MODULE_NAME / "auto_download_groups.json"
_auto_download_groups: Set[str] = set()
_lock = asyncio.Lock()
_initialized = False


async def load_auto_download_config():
    """Load the set of groups with auto-download enabled from JSON file."""
    global _auto_download_groups, _initialized
    async with _lock:
        if _initialized:
            return
        try:
            AUTO_DOWNLOAD_FILE.parent.mkdir(parents=True, exist_ok=True)
            if AUTO_DOWNLOAD_FILE.exists():
                async with aiofiles.open(
                    AUTO_DOWNLOAD_FILE, mode="r", encoding="utf-8"
                ) as f:
                    content = await f.read()
                    if content.strip():
                        data = json.loads(content)
                        if isinstance(data, list):
                            _auto_download_groups = set(str(gid) for gid in data)
                        else:
                            logger.warning(
                                f"自动下载配置文件格式错误，应为列表: {AUTO_DOWNLOAD_FILE}"
                            )
                            _auto_download_groups = set()
                    else:
                        _auto_download_groups = set()

            else:
                _auto_download_groups = set()
                async with aiofiles.open(
                    AUTO_DOWNLOAD_FILE, mode="w", encoding="utf-8"
                ) as f:
                    await f.write(json.dumps([]))
            _initialized = True
            logger.info(
                f"自动下载配置加载完成，当前启用群组数: {len(_auto_download_groups)}"
            )
        except Exception as e:
            logger.error(f"加载自动下载配置失败: {e}", e=e)
            _auto_download_groups = set()
            _initialized = True


async def save_auto_download_config():
    """Save the current set of auto-download enabled groups to JSON file."""
    global _auto_download_groups
    async with _lock:
        try:
            AUTO_DOWNLOAD_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_file = AUTO_DOWNLOAD_FILE.with_suffix(".json.tmp")
            async with aiofiles.open(temp_file, mode="w", encoding="utf-8") as f:
                await f.write(
                    json.dumps(
                        list(_auto_download_groups), ensure_ascii=False, indent=2
                    )
                )
            temp_file.replace(AUTO_DOWNLOAD_FILE)
            logger.debug(f"自动下载配置已保存: {AUTO_DOWNLOAD_FILE}")
        except Exception as e:
            logger.error(f"保存自动下载配置失败: {e}", e=e)


async def is_auto_download_enabled(session: EventSession) -> bool:
    """Check if auto-download is enabled for the given session's group."""
    if not _initialized:
        await load_auto_download_config()

    if session.id2:
        group_id = str(session.id2)
        enabled = group_id in _auto_download_groups
        logger.debug(f"检查群组 {group_id} 自动下载状态: {enabled}")
        return enabled
    elif session.id3:
        logger.debug(f"频道消息 ({session.id3}/{session.id2}) 暂不支持自动下载")
        return False
    else:
        logger.debug("私聊消息，不进行自动下载")
        return False


async def enable_auto_download(session: EventSession):
    """Enable auto-download for the given session's group."""
    if not _initialized:
        await load_auto_download_config()

    if session.id2:
        group_id = str(session.id2)
        if group_id not in _auto_download_groups:
            _auto_download_groups.add(group_id)
            await save_auto_download_config()
            logger.info(f"群组 {group_id} 已开启自动下载")
            return True
        return False
    return False


async def disable_auto_download(session: EventSession):
    """Disable auto-download for the given session's group."""
    if not _initialized:
        await load_auto_download_config()

    if session.id2:
        group_id = str(session.id2)
        if group_id in _auto_download_groups:
            _auto_download_groups.discard(group_id)
            await save_auto_download_config()
            logger.info(f"群组 {group_id} 已关闭自动下载")
            return True
        return False
    return False
