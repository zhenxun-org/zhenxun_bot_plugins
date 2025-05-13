import re
import time
import asyncio
from pathlib import Path
from typing import Optional, Dict, TypeVar, Callable, Awaitable

from zhenxun.services.log import logger

T = TypeVar("T")


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """清理文件名"""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", filename)
    if len(safe_name) > max_length:
        safe_name = safe_name[:max_length]
    return safe_name


def format_number(num: int) -> str:
    """格式化数字，大数字使用万/亿单位"""
    if num >= 100000000:
        return f"{num / 100000000:.1f}亿"
    if num >= 10000:
        return f"{num / 10000:.1f}万"
    return str(num)


def format_duration(seconds: int) -> str:
    """格式化时间长度为 HH:MM:SS 或 MM:SS 格式"""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if hours > 0
        else f"{minutes:02d}:{seconds:02d}"
    )


def format_timestamp(timestamp: int, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化Unix时间戳为指定格式的时间字符串"""
    try:
        time_obj = time.localtime(timestamp)
        return time.strftime(format_str, time_obj)
    except Exception as e:
        logger.warning(f"格式化时间戳失败 {timestamp}: {e}", "B站解析")
        return str(timestamp)


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    **kwargs,
) -> T:
    """异步函数重试装饰器，支持指数退避重试"""
    last_exception = None
    delay = retry_delay

    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.debug(
                    f"函数 {func.__name__} 执行失败 (尝试 {attempt + 1}/{max_retries}): {e}，"
                    f"{delay:.1f}秒后重试",
                    "B站解析",
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                logger.warning(
                    f"函数 {func.__name__} 在 {max_retries} 次尝试后仍然失败: {e}",
                    "B站解析",
                )

    if last_exception:
        raise last_exception

    raise RuntimeError("Unexpected error in retry_async")


def get_path_with_mkdir(base_dir: Path, *parts: str) -> Path:
    """获取路径并确保目录存在"""
    path = base_dir.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


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
    except Exception as e:
        logger.warning(f"解析cookies字符串失败: {e}", "B站解析")
    return cookies


def dict_to_cookies_str(cookies_dict: Dict[str, str]) -> str:
    """将字典转换为cookies字符串"""
    if not cookies_dict:
        return ""
    try:
        return "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
    except Exception as e:
        logger.warning(f"转换cookies字典失败: {e}", "B站解析")
        return ""


def extract_url_from_text(text: str) -> Optional[str]:
    """从文本中提取第一个URL"""
    url_pattern = re.compile(
        r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*(?:\?[/\w\.-=%&+]*)?"
    )
    match = url_pattern.search(text)
    if match:
        return match.group(0)
    return None


def calculate_retry_wait_time(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential: bool = True,
    jitter: bool = True,
) -> float:
    """计算重试等待时间"""
    import random

    if exponential:
        wait_time = base_delay * (2 ** (attempt - 1))
    else:
        wait_time = base_delay * attempt

    wait_time = min(wait_time, max_delay)

    if jitter:
        jitter_amount = wait_time * 0.25
        wait_time += random.uniform(-jitter_amount, jitter_amount)
        wait_time = max(base_delay * 0.5, wait_time)

    return wait_time
