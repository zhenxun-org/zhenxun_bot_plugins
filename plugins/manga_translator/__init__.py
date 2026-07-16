"""漫画翻译 — 基于 Cotrans API (VoileLabs)，适配真寻(ZhenXun)框架

新 Cotrans API 与旧版 manga-image-translator 的关键差异:
- 返回的是 translation_mask (透明蒙版)，需要和原图合成
- 不支持人工翻译
- 参数格式完全改变
"""

import asyncio
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from nonebot import get_bot, on_command, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import ArgStr, CommandArg, State
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from PIL import Image

from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.configs.utils import BaseBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.enum import LimitWatchType, PluginType

# ==================== 常量 ====================
API_BASE = "https://api.cotrans.touhou.ai"
CACHE_DIR: Path = TEMP_PATH / "manga_translator"
HTTP_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# 默认翻译参数
DEFAULT_TARGET_LANG = "CHS"  # 简体中文
DEFAULT_DETECTOR = "default"
DEFAULT_DIRECTION = "auto"
DEFAULT_TRANSLATOR = "google"
DEFAULT_SIZE = "L"

# WebSocket 地址 (用于实时状态推送)
WS_BASE = "wss://api.cotrans.touhou.ai"

# 任务超时
_TASK_TIMEOUT = 300  # 5 分钟


# ==================== 插件元数据 ====================
__plugin_meta__ = PluginMetadata(
    name="漫画翻译",
    description="基于 Cotrans API 的图片/漫画翻译插件，支持多语种翻译",
    usage="""
    使用方法：
    1. 自动翻译：发送 "图片翻译" / "漫画翻译" / "翻译图片" / "翻译漫画"
       然后发送要翻译的图片
    2. 指定参数 (在命令后附加):
       -t <语言>  目标语言 (CHS/ENG/JPN/KOR/CHT 等，默认 CHS)
       -s <尺寸>  处理尺寸 (S/M/L/X，默认 L)
       --translator <引擎>  翻译引擎 (google/gpt3.5/deepl 等，默认 google)
    3. 查询进度：发送命令 + task_id 查询处理状态

    支持的目标语言: CHS CHT ENG JPN KOR FRA DEU RUS ESP PTB ITA NLD PLK HUN ROM TRK UKR VIN CSY
    支持的翻译引擎: google gpt3.5 youdao baidu deepl papago offline none original
    """.strip(),
    extra=PluginExtraData(
        author="秦心",
        version="2.0",
        plugin_type=PluginType.NORMAL,
        limits=[
            BaseBlock(result="当前有任务正在处理，请稍等...", watch_type=LimitWatchType.GROUP),
        ],
    ).to_dict(),
)

# ==================== 任务队列 ====================
_task_queue: dict[str, tuple[str, float, bytes]] = {}
# task_id -> (group_id, start_time, original_image_bytes)

CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ==================== HTTP 工具 ====================
async def _api_get(url: str) -> dict:
    """GET 请求 API"""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def _api_post_form(url: str, data: dict, file_bytes: bytes | None = None, filename: str = "image.png") -> dict:
    """POST multipart/form-data 请求"""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        if file_bytes:
            files = {"file": (filename, file_bytes, "image/png")}
            resp = await client.post(url, data=data, files=files)
        else:
            resp = await client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()


async def _download_bytes(url: str) -> Optional[bytes]:
    """下载二进制内容"""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
    except Exception as e:
        logger.warning(f"下载失败: {url} -> {e}")
    return None


# ==================== 图片合成 ====================
def _composite_mask(original_bytes: bytes, mask_bytes: bytes) -> bytes:
    """
    将翻译蒙版叠加到原图上，生成最终翻译图片。

    新 Cotrans API 返回的是透明 PNG 蒙版 (translation_mask)，
    需要客户端自行与原图合成。
    """
    original = Image.open(BytesIO(original_bytes)).convert("RGBA")
    mask = Image.open(BytesIO(mask_bytes)).convert("RGBA")

    # 确保尺寸一致
    if mask.size != original.size:
        mask = mask.resize(original.size, Image.LANCZOS)

    # 合成: 蒙版在上，原图在下
    composited = Image.alpha_composite(original, mask)

    # 转为 RGB PNG 字节 (QQ 发送用)
    output = BytesIO()
    composited.convert("RGB").save(output, format="PNG")
    return output.getvalue()


# ==================== API 调用 ====================
async def _submit_task(
    file_bytes: bytes,
    filename: str = "image.png",
    target_lang: str = DEFAULT_TARGET_LANG,
    detector: str = DEFAULT_DETECTOR,
    direction: str = DEFAULT_DIRECTION,
    translator: str = DEFAULT_TRANSLATOR,
    size: str = DEFAULT_SIZE,
) -> dict:
    """提交翻译任务到 Cotrans API"""
    form_data = {
        "target_language": target_lang,
        "detector": detector,
        "direction": direction,
        "translator": translator,
        "size": size,
    }
    url = f"{API_BASE}/task/upload/v1"
    logger.info(f"提交翻译: url={url}, size={size}, lang={target_lang}, translator={translator}")
    return await _api_post_form(url, form_data, file_bytes, filename)


async def _query_task(task_id: str) -> dict:
    """查询任务状态 (REST 方式)"""
    url = f"{API_BASE}/task/{task_id}/status/v1"
    return await _api_get(url)


# ==================== 定时轮询 ====================
scheduler = require("nonebot_plugin_apscheduler").scheduler


@scheduler.scheduled_job("cron", second="*/15")
async def _poll_tasks():
    """每 15 秒检查翻译任务队列"""
    bot: Bot = get_bot()
    now = time.time()
    for task_id, (group_id, start_time, original_bytes) in list(_task_queue.items()):
        # 清理过期任务
        if now - start_time > _TASK_TIMEOUT:
            logger.warning(f"漫画翻译任务过期: {task_id}")
            _task_queue.pop(task_id, None)
            try:
                await bot.send_group_msg(
                    group_id=group_id,
                    message=f"task_id: {task_id}\n翻译超时，请重试",
                )
            except Exception:
                pass
            continue

        try:
            result = await _query_task(task_id)
            msg_type = result.get("type")

            if msg_type == "result":
                mask_url = result.get("result", {}).get("translation_mask", "")
                logger.info(f"后台翻译完成: {task_id}")
                msg = await _build_result_message(task_id, mask_url, original_bytes)
                await bot.send_group_msg(group_id=group_id, message=msg)
                _task_queue.pop(task_id, None)

            elif msg_type == "error":
                error_msg = result.get("error", "unknown")
                logger.warning(f"翻译出错: {task_id}, error={error_msg}")
                await bot.send_group_msg(
                    group_id=group_id,
                    message=f"task_id: {task_id}\n翻译出错: {error_msg}",
                )
                _task_queue.pop(task_id, None)

            elif msg_type == "not_found":
                logger.warning(f"任务未找到: {task_id}")
                _task_queue.pop(task_id, None)

            elif msg_type == "pending":
                pos = result.get("pos", "?")
                logger.debug(f"翻译排队中: {task_id}, pos={pos}")

            elif msg_type == "status":
                status = result.get("status", "?")
                logger.debug(f"翻译处理中: {task_id}, status={status}")

        except Exception as e:
            logger.error(f"轮询翻译任务出错: {task_id} -> {e}")


# ==================== 命令注册 ====================
manga_trans = on_command(
    "图片翻译",
    aliases={"漫画翻译", "翻译图片", "翻译漫画"},
    priority=5,
    block=True,
)


# ==================== 第一层: 参数解析 / task_id 查询 / 同消息图片处理 ====================
@manga_trans.handle()
async def _handle_first_receive(
    event: GroupMessageEvent,
    matcher: Matcher,
    args: Message = CommandArg(),
    state: T_State = State(),
):
    """解析命令参数，如果同一条消息包含图片则直接处理，否则等待用户发送图片"""
    plain_text = args.extract_plain_text().strip()

    # 解析参数 (-t, -s, --translator)
    if plain_text:
        _parse_params(plain_text, state)

    # task_id 查询 (纯字母数字下划线连字符)
    if plain_text and re.match(r"^[a-zA-Z0-9_-]+$", plain_text):
        task_id = plain_text
        if task_id in _task_queue:
            await manga_trans.finish("该图片仍在处理队列中，请耐心等待")
        try:
            result = await _query_task(task_id)
            msg_type = result.get("type")
            status_map = {
                "result": "已完成",
                "error": "出错",
                "pending": "排队中",
                "status": "处理中",
                "not_found": "未找到",
            }
            detail = result.get("status") or result.get("error") or result.get("pos") or ""
            await manga_trans.finish(f"task_id: {task_id}\n状态: {status_map.get(msg_type, msg_type)} {detail}".strip())
        except Exception as e:
            await manga_trans.finish(f"查询出错: {e}")

    # 检查当前消息是否包含图片 → 直接处理
    pic_url = _extract_image_from_event(event)
    if pic_url:
        await _process_translation(event, matcher, pic_url, state)
        return

    # 无图片，等待用户发送
    # (got handler 在下一消息触发)


# ==================== 图片接收 + 翻译 ====================
@manga_trans.got("image", prompt="请发送要翻译的图片")
async def _handle_manga_trans(
    event: GroupMessageEvent,
    image: str = ArgStr("image"),
    state: T_State = State(),
):
    """接收图片（命令行后单独发送的图片），提交到 Cotrans API"""
    pic_url = _extract_image_url(image)
    if not pic_url:
        pic_url = _extract_image_from_event(event)
    if not pic_url:
        await manga_trans.finish("没有收到图片，请发送一张包含文字的图片")
    await _process_translation(event, manga_trans, pic_url, state)


# ==================== 核心翻译流程 ====================
async def _process_translation(
    event: GroupMessageEvent,
    matcher: Matcher,
    pic_url: str,
    state: T_State,
):
    """下载原图 → 提交 API → 轮询等待 → 合成蒙版 → 返回结果"""
    # 下载用户发送的原图 (用于后续和蒙版合成)
    logger.info(f"下载原图: {pic_url[:80]}...")
    original_bytes = await _download_bytes(pic_url)
    if not original_bytes:
        await matcher.finish("下载图片失败，请重试")

    # 读取参数
    target_lang = state.get("target_lang", DEFAULT_TARGET_LANG)
    size = state.get("size", DEFAULT_SIZE)
    translator = state.get("translator", DEFAULT_TRANSLATOR)

    # 提交任务
    try:
        result = await _submit_task(
            file_bytes=original_bytes,
            target_lang=target_lang,
            size=size,
            translator=translator,
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"提交翻译任务 HTTP 错误: {e.response.status_code}")
        await matcher.finish(f"提交失败: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"提交翻译任务失败: {e}")
        await matcher.finish(f"提交失败: {e}")

    # 检查提交结果
    task_id = result.get("id")
    if not task_id:
        error = result.get("error", "unknown")
        error_map = {
            "queue-full": "服务器队列已满，请稍后再试",
            "fetch-failed": "服务器获取图片失败",
            "file-too-large": "图片过大 (限制 20MB)",
            "resize-crash": "图片尺寸或格式不支持",
        }
        await matcher.finish(f"提交失败: {error_map.get(error, error)}")

    # 如果已完成 (命中缓存)，直接合成返回
    if result.get("result"):
        mask_url = result["result"].get("translation_mask", "")
        logger.info(f"命中缓存: {task_id}")
        final_msg = await _build_result_message(task_id, mask_url, original_bytes)
        await matcher.finish(final_msg)

    # 等待结果 (轮询 120 秒)
    await matcher.send(
        f"已提交翻译 task_id: {task_id}\n"
        f"目标语言: {target_lang} | 引擎: {translator} | 尺寸: {size}\n"
        f"处理中..."
    )
    await matcher.finish(
        await _wait_for_result(task_id, str(event.group_id), original_bytes)
    )


# ==================== 辅助函数 ====================
def _parse_params(text: str, state: T_State):
    """从命令文本中解析翻译参数"""
    # -t 目标语言
    m = re.search(r"-t\s+(\S+)", text)
    if m:
        lang = m.group(1).upper()
        valid_langs = {"CHS", "CHT", "ENG", "JPN", "KOR", "FRA", "DEU", "RUS",
                       "ESP", "PTB", "ITA", "NLD", "PLK", "HUN", "ROM", "TRK", "UKR", "VIN", "CSY"}
        if lang in valid_langs:
            state["target_lang"] = lang

    # -s 尺寸
    m = re.search(r"-s\s+(\S)", text)
    if m and m.group(1).upper() in ("S", "M", "L", "X"):
        state["size"] = m.group(1).upper()

    # --translator 引擎
    m = re.search(r"--translator\s+(\S+)", text)
    if m:
        state["translator"] = m.group(1)


def _extract_image_url(text: str) -> str:
    """从 OneBot CQ 码文本中提取图片 URL"""
    match = re.search(r"(http|https)://.+?\]", text)
    if match:
        return match.group()[:-1]
    return ""


def _extract_image_from_event(event: GroupMessageEvent) -> str:
    """从事件中直接提取第一张图片的 URL"""
    for seg in event.message:
        if seg.type == "image":
            url = seg.data.get("url") or seg.data.get("file")
            if url:
                return url
    return ""


async def _build_result_message(task_id: str, mask_url: str, original_bytes: bytes) -> Message:
    """下载蒙版 + 合成原图 + 构建结果消息"""
    if not mask_url:
        return f"task_id: {task_id}\n翻译完成但结果为空 (图片可能无文字)"
    mask_bytes = await _download_bytes(mask_url)
    if not mask_bytes:
        return f"task_id: {task_id}\n翻译完成但下载蒙版失败"
    final_bytes = _composite_mask(original_bytes, mask_bytes)
    save_path = CACHE_DIR / f"translated-{task_id}.png"
    save_path.write_bytes(final_bytes)
    return (
        MessageSegment.image(str(save_path))
        + f"task_id: {task_id}\n"
        "由 Cotrans (VoileLabs) 提供翻译\n"
        "https://cotrans.touhou.ai/"
    )


async def _wait_for_result(task_id: str, group_id: str, original_bytes: bytes) -> Message:
    """轮询等待翻译结果 (最多 120 秒)，超时则加入后台队列"""
    for _ in range(40):
        await asyncio.sleep(3)
        try:
            result = await _query_task(task_id)
            msg_type = result.get("type")

            if msg_type == "result":
                mask_url = result.get("result", {}).get("translation_mask", "")
                logger.info(f"翻译完成: {task_id}")
                return await _build_result_message(task_id, mask_url, original_bytes)

            elif msg_type == "error":
                return f"task_id: {task_id}\n翻译出错: {result.get('error', 'unknown')}"

            elif msg_type == "not_found":
                return f"task_id: {task_id}\n任务未找到"

        except Exception as e:
            logger.warning(f"轮询 {task_id} 出错: {e}")

    # 超时，加入后台轮询队列
    _task_queue[task_id] = (group_id, time.time(), original_bytes)
    return f"task_id: {task_id}\n处理时间较长，已加入后台队列，完成后自动发送\n当前队列长度: {len(_task_queue)}"
