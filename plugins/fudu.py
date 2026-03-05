import asyncio
import base64
from collections import OrderedDict, deque
from io import BytesIO
from pathlib import Path
import random
import time
from typing import Any

import imagehash
from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Message as V11Message
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot.utils import run_sync
from nonebot_plugin_alconna import Image as alcImg
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo
from PIL import Image

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import DATA_PATH
from zhenxun.configs.utils import PluginExtraData, RegisterConfig, Task
from zhenxun.services.log import logger
from zhenxun.utils.common_utils import CommonUtils
from zhenxun.utils.enum import PluginType
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

FUDU_IMAGE_PATH = DATA_PATH / "fudu"
FUDU_IMAGE_PATH.mkdir(parents=True, exist_ok=True)

_BLOCK_CACHE_TTL_SECONDS = 2.0
_IMAGE_HASH_CACHE_TTL_SECONDS = 60.0
_IMAGE_HASH_CACHE_MAX_ITEMS = 1024
_IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 8.0
_task_block_cache: dict[str, tuple[float, bool]] = {}
_image_hash_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
_image_hash_inflight: dict[str, asyncio.Task[str]] = {}
_image_hash_lock = asyncio.Lock()

# 支持的图片扩展名
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

__plugin_meta__ = PluginMetadata(
    name="复读",
    description="群友的本质是什么？是复读机哒！",
    usage="""
    usage：
        重复3次相同的消息时会复读
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier & webjoin111",
        version="0.5",
        menu_type="其他",
        plugin_type=PluginType.DEPENDANT,
        tasks=[Task(module="fudu", name="复读")],
        ignore_prompt=True,
        configs=[
            RegisterConfig(
                key="FUDU_PROBABILITY",
                value=0.7,
                help="复读概率",
                default_value=0.7,
                type=float,
            ),
            RegisterConfig(
                key="FUDU_TRIGGER_COUNT",
                value=3,
                help="触发复读所需的消息重复次数",
                default_value=3,
                type=int,
            ),
            RegisterConfig(
                key="FUDU_BREAK_PROBABILITY",
                value=0.2,
                help="打断复读的概率（基于复读概率）",
                default_value=0.2,
                type=float,
            ),
            RegisterConfig(
                key="FUDU_BREAK_TEXTS",
                value=["打断施法！"],
                help="用于打断复读时随机发送的文本列表",
                type=list[str],
            ),
            RegisterConfig(
                key="FUDU_BREAK_USE_IMAGE",
                value=True,
                help="是否启用图片作为打断复读的内容 (图片存放于 data/fudu/ 目录下)",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="FUDU_BREAK_USE_TEXT",
                value=True,
                help="是否启用文本作为打断复读的内容",
                default_value=True,
                type=bool,
            ),
        ],
    ).to_dict(),
)


class Fudu:
    MAX_GROUPS = 500  # 最大缓存群组数量

    def __init__(self):
        self._data: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def _get_or_create(self, key: str) -> dict[str, Any]:
        """获取或创建群组数据，同时维护 LRU 顺序"""
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]

        # 超出限制时删除最旧的条目
        while len(self._data) >= self.MAX_GROUPS:
            self._data.popitem(last=False)

        trigger_count = Config.get_config("fudu", "FUDU_TRIGGER_COUNT", 3)
        self._data[key] = {
            "is_repeater": False,
            "data": deque(maxlen=trigger_count),
            "message_obj": None,
            "reply_info": None,
        }
        return self._data[key]

    def append(self, key: str, content: str, msg_obj: Any, reply_info: Any) -> None:
        """添加消息内容及原始消息对象"""
        group_data = self._get_or_create(key)
        group_data["data"].append(content)
        group_data["message_obj"] = msg_obj
        group_data["reply_info"] = reply_info

    def clear(self, key: str) -> None:
        """清空群组的复读数据"""
        group_data = self._get_or_create(key)
        group_data["data"].clear()
        group_data["is_repeater"] = False
        group_data["message_obj"] = None
        group_data["reply_info"] = None

    def size(self, key: str) -> int:
        """获取当前消息数量"""
        return len(self._get_or_create(key)["data"])

    def check(self, key: str, content: str) -> bool:
        """检查内容是否与第一条消息相同"""
        data_list = self._get_or_create(key)["data"]
        return bool(data_list) and data_list[0] == content

    def get_repeat_target(self, key: str) -> tuple[Any, Any]:
        """获取要复读的消息对象和回复信息"""
        group_data = self._get_or_create(key)
        return group_data["message_obj"], group_data["reply_info"]

    def is_repeater(self, key: str) -> bool:
        """检查是否已经复读过"""
        return self._get_or_create(key)["is_repeater"]

    def set_repeater(self, key: str) -> None:
        """标记已复读"""
        self._get_or_create(key)["is_repeater"] = True


_manager = Fudu()
base_config = Config.get("fudu")


def _get_cached_task_block_state(cache_key: str) -> bool | None:
    cached = _task_block_cache.get(cache_key)
    if not cached:
        return None
    expire_at, value = cached
    if expire_at <= time.monotonic():
        _task_block_cache.pop(cache_key, None)
        return None
    return value


def _set_cached_task_block_state(cache_key: str, value: bool) -> None:
    _task_block_cache[cache_key] = (time.monotonic() + _BLOCK_CACHE_TTL_SECONDS, value)


def _cleanup_image_hash_cache() -> None:
    now = time.monotonic()
    while _image_hash_cache:
        expire_at, _ = next(iter(_image_hash_cache.values()))
        if expire_at > now:
            break
        _image_hash_cache.popitem(last=False)
    while len(_image_hash_cache) > _IMAGE_HASH_CACHE_MAX_ITEMS:
        _image_hash_cache.popitem(last=False)


def _get_cached_image_hash(url: str) -> str | None:
    cached = _image_hash_cache.get(url)
    if not cached:
        return None
    expire_at, value = cached
    if expire_at <= time.monotonic():
        _image_hash_cache.pop(url, None)
        return None
    _image_hash_cache.move_to_end(url)
    return value


def _set_cached_image_hash(url: str, img_hash: str) -> None:
    _image_hash_cache[url] = (
        time.monotonic() + _IMAGE_HASH_CACHE_TTL_SECONDS,
        img_hash,
    )
    _image_hash_cache.move_to_end(url)
    _cleanup_image_hash_cache()


def _calc_image_hash(content: bytes) -> str:
    with Image.open(BytesIO(content)) as image:
        return str(imagehash.average_hash(image))


async def _get_image_hash_by_url(url: str) -> str:
    async with _image_hash_lock:
        if cached := _get_cached_image_hash(url):
            return cached
        task = _image_hash_inflight.get(url)
        if task is None:

            async def _worker() -> str:
                content = await AsyncHttpx.get_content(
                    url,
                    timeout=_IMAGE_DOWNLOAD_TIMEOUT_SECONDS,
                )
                return await run_sync(_calc_image_hash)(content)

            task = asyncio.create_task(_worker())
            _image_hash_inflight[url] = task

            def _cleanup_inflight(_: asyncio.Task[str], key: str = url) -> None:
                _image_hash_inflight.pop(key, None)

            task.add_done_callback(_cleanup_inflight)

    img_hash = await task
    if img_hash:
        async with _image_hash_lock:
            _set_cached_image_hash(url, img_hash)
    return img_hash


def get_break_images() -> list[Path]:
    """获取打断复读用的图片列表"""
    if not FUDU_IMAGE_PATH.exists():
        return []
    return [
        f
        for f in FUDU_IMAGE_PATH.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    ]


async def send_break_response() -> None:
    """发送打断复读的响应"""
    response_pool: list[str | Path] = []

    if base_config.get("FUDU_BREAK_USE_TEXT"):
        if break_texts := base_config.get("FUDU_BREAK_TEXTS"):
            response_pool.extend(break_texts)

    if base_config.get("FUDU_BREAK_USE_IMAGE"):
        response_pool.extend(get_break_images())

    if not response_pool:
        response_pool.append("打断施法！")

    response = random.choice(response_pool)

    if isinstance(response, Path):
        file_data = f"base64://{base64.b64encode(response.read_bytes()).decode()}"
        await _matcher.finish(
            MessageSegment("image", {"file": file_data, "sub_type": "1"})
        )
    else:
        await MessageUtils.build_message(response).finish()


async def rule(message: UniMsg, session: Uninfo, event: Event) -> bool:
    """消息匹配规则：仅匹配群聊中的有效消息"""
    if not session.group:
        return False
    if event.is_tome():
        return False
    plain_text = message.extract_plain_text()
    image_list = [m.url for m in message if isinstance(m, alcImg) and m.url]
    if not plain_text and not image_list:
        return False
    group_id = session.group.id
    cache_key = f"{session.self_id}:{group_id}:fudu"
    cached_block = _get_cached_task_block_state(cache_key)
    if cached_block is not None:
        return not cached_block
    blocked = await CommonUtils.task_is_block(session, "fudu")
    _set_cached_task_block_state(cache_key, blocked)
    return not blocked


_matcher = on_message(rule=rule, priority=999)


@_matcher.handle()
async def _(bot: Bot, message: UniMsg, event: Event, session: Uninfo):
    # rule 已确保 session.group 存在
    group_id = session.group.id  # type: ignore

    raw_message = event.get_message()
    reply_info = getattr(event, "reply", None)
    plain_text = message.extract_plain_text()
    image_list = [m.url for m in message if isinstance(m, alcImg) and m.url]

    # 检测虚空艾特
    if plain_text and plain_text.startswith(f"@可爱的{BotConfig.self_nickname}"):
        await MessageUtils.build_message("复制粘贴的虚空艾特？").send(reply_to=True)

    # 计算图片哈希
    img_hash = ""
    if image_list:
        try:
            img_hash = await _get_image_hash_by_url(image_list[0])
        except Exception as e:
            logger.warning("下载复读图片以获取Hash时出错", "复读", e=e)

    add_msg = f"{plain_text}|-|{img_hash}"

    if _manager.size(group_id) != 0 and not _manager.check(group_id, add_msg):
        _manager.clear(group_id)
    _manager.append(group_id, add_msg, raw_message, reply_info)
    # 检查是否触发复读
    trigger_count = base_config.get("FUDU_TRIGGER_COUNT")
    if _manager.size(group_id) < trigger_count:
        return
    if _manager.is_repeater(group_id):
        return
    if random.random() >= base_config.get("FUDU_PROBABILITY"):
        return

    # 判断是否打断复读
    if random.random() < base_config.get("FUDU_BREAK_PROBABILITY"):
        _manager.clear(group_id)
        await send_break_response()

    # 执行复读
    message_to_send, reply = _manager.get_repeat_target(group_id)
    if not message_to_send:
        return

    _manager.set_repeater(group_id)

    # 处理回复消息
    if reply and isinstance(message_to_send, V11Message):
        message_to_send.insert(0, MessageSegment.reply(reply.message_id))

    await _matcher.finish(message_to_send)
