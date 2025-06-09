import asyncio
import time
import urllib.parse
import functools
import traceback
from typing import Dict, Any, Optional, Callable, TypeVar, Awaitable, Union, List, Type

import aiohttp
from collections import defaultdict

from zhenxun.services.log import logger

from ..config import HTTP_TIMEOUT, HTTP_CONNECT_TIMEOUT
from ..model import VideoInfo, LiveInfo, ArticleInfo, UserInfo, SeasonInfo
from ..utils.exceptions import (
    BilibiliRequestError,
    BilibiliResponseError,
    RateLimitError,
    NetworkError,
    BilibiliBaseException,
    UrlParseError,
    UnsupportedUrlError,
    ShortUrlError,
)
from ..utils.headers import get_bilibili_headers
from ..utils.url_parser import ResourceType, UrlParserRegistry

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
AF = TypeVar("AF", bound=Callable[..., Awaitable[Any]])

RetryConditionType = Callable[[Exception, int], bool]


def _log_exception(
    e: Exception, error_msg: str, log_level: str, error_context: Dict[str, Any]
):
    """记录异常日志"""
    log_func = getattr(logger, log_level)
    if isinstance(e, BilibiliBaseException):
        e.with_context(**error_context)
        log_func(f"{error_msg}: {e}", "B站解析")
    else:
        log_func(f"{error_msg}: {e}", "B站解析")


def format_exception(e: Exception) -> str:
    """格式化异常信息"""
    tb = traceback.format_exception(type(e), e, e.__traceback__)
    tb_simplified = tb[-3:]
    return f"{type(e).__name__}: {str(e)}\n{''.join(tb_simplified)}"


def network_retry_condition(exception: Exception, attempt: int) -> bool:
    """网络错误重试条件"""
    network_error_types = {
        "ConnectionError",
        "Timeout",
        "TimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "HTTPError",
        "SSLError",
        "ProxyError",
        "RequestError",
        "ClientError",
    }

    exception_type = type(exception).__name__
    return any(error_type in exception_type for error_type in network_error_types)


def transient_retry_condition(exception: Exception, attempt: int) -> bool:
    """临时错误重试条件"""
    if network_retry_condition(exception, attempt):
        return True

    transient_keywords = [
        "timeout",
        "timed out",
        "temporary",
        "temporarily",
        "retry",
        "rate limit",
        "ratelimit",
        "throttle",
        "throttling",
        "overload",
        "busy",
        "unavailable",
        "maintenance",
        "503",
        "502",
        "500",
        "429",
    ]

    error_message = str(exception).lower()
    return any(keyword in error_message for keyword in transient_keywords)


def calculate_next_wait_time(
    attempt: int,
    base_wait: float = 1.0,
    max_wait: float = 60.0,
    exponential: bool = True,
    jitter: bool = True,
) -> float:
    """计算重试等待时间"""
    from ..utils.common import calculate_retry_wait_time

    return calculate_retry_wait_time(
        attempt=attempt,
        base_delay=base_wait,
        max_delay=max_wait,
        exponential=exponential,
        jitter=jitter,
    )


def handle_errors(
    error_msg: str = "操作执行失败",
    exc_types: Union[Type[Exception], List[Type[Exception]]] = Exception,
    log_level: str = "error",
    reraise: bool = True,
    default_return: Any = None,
    context: Optional[Dict[str, Any]] = None,
) -> Callable[[F], F]:
    """同步函数错误处理装饰器"""
    if isinstance(exc_types, type) and issubclass(exc_types, Exception):
        exc_types = [exc_types]

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except tuple(exc_types) as e:
                error_context = context or {}
                error_context.update(
                    {
                        "function": func.__name__,
                        "args": str(args),
                        "kwargs": str(kwargs),
                    }
                )

                _log_exception(e, error_msg, log_level, error_context)

                if reraise:
                    raise

                return default_return

        return wrapper

    return decorator


def async_handle_errors(
    error_msg: str = "操作执行失败",
    exc_types: Union[Type[Exception], List[Type[Exception]]] = Exception,
    log_level: str = "error",
    reraise: bool = True,
    default_return: Any = None,
    context: Optional[Dict[str, Any]] = None,
) -> Callable[[AF], AF]:
    """异步函数错误处理装饰器"""
    if isinstance(exc_types, type) and issubclass(exc_types, Exception):
        exc_types = [exc_types]

    def decorator(func: AF) -> AF:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except tuple(exc_types) as e:
                error_context = context or {}
                error_context.update(
                    {
                        "function": func.__name__,
                        "args": str(args),
                        "kwargs": str(kwargs),
                    }
                )

                _log_exception(e, error_msg, log_level, error_context)

                if reraise:
                    raise

                return default_return

        return wrapper

    return decorator


class RateLimiter:
    """请求限流器，控制对特定域名的请求频率"""

    _domain_limits: Dict[str, tuple[float, float]] = {}

    _domain_counters = defaultdict(int)

    _domain_rate_limits = {
        "api.bilibili.com": 0.5,
        "www.bilibili.com": 0.5,
        "live.bilibili.com": 0.5,
        "b23.tv": 1.0,
    }

    _DEFAULT_INTERVAL = 0.2

    @classmethod
    async def acquire(cls, url: str) -> float:
        """获取请求许可"""
        domain = url.split("//")[-1].split("/")[0]

        interval = cls._domain_rate_limits.get(domain, cls._DEFAULT_INTERVAL)

        last_time, _ = cls._domain_limits.get(domain, (0, interval))
        current_time = time.time()
        wait_time = max(0, last_time + interval - current_time)

        if wait_time > 0:
            logger.debug(f"限流: 等待 {wait_time:.2f}s 后请求 {domain}", "B站解析")
            await asyncio.sleep(wait_time)

        cls._domain_limits[domain] = (time.time(), interval)

        cls._domain_counters[domain] += 1
        if cls._domain_counters[domain] % 10 == 0:
            logger.debug(
                f"已对 {domain} 发送 {cls._domain_counters[domain]} 个请求", "B站解析"
            )

        return wait_time

    @classmethod
    def get_domain_stats(cls) -> Dict[str, Dict[str, Any]]:
        """获取域名请求统计"""
        stats = {}
        for domain, counter in cls._domain_counters.items():
            last_time, interval = cls._domain_limits.get(
                domain, (0, cls._DEFAULT_INTERVAL)
            )
            stats[domain] = {
                "requests": counter,
                "last_request": last_time,
                "interval": interval,
                "rate_limit": cls._domain_rate_limits.get(
                    domain, cls._DEFAULT_INTERVAL
                ),
            }
        return stats

    @classmethod
    def update_rate_limit(cls, domain: str, interval: float):
        """更新域名请求间隔"""
        cls._domain_rate_limits[domain] = interval
        logger.debug(f"更新 {domain} 的请求间隔为 {interval}s", "B站解析")


class NetworkService:
    """网络请求服务，提供优化的请求方法"""

    _session: Optional[aiohttp.ClientSession] = None

    _session_lock = asyncio.Lock()

    _DEFAULT_RETRY_CONFIG = {
        "max_attempts": 3,
        "min_wait": 1.0,
        "max_wait": 10.0,
        "multiplier": 2.0,
    }

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        async with cls._session_lock:
            if cls._session is None or cls._session.closed:
                timeout = aiohttp.ClientTimeout(
                    total=HTTP_TIMEOUT,
                    connect=HTTP_CONNECT_TIMEOUT,
                )
                cls._session = aiohttp.ClientSession(
                    timeout=timeout,
                    headers=get_bilibili_headers(),
                )
                logger.debug("创建了新的HTTP会话", "B站解析")
            return cls._session

    @classmethod
    async def close_session(cls):
        """关闭HTTP会话"""
        async with cls._session_lock:
            if cls._session and not cls._session.closed:
                await cls._session.close()
                cls._session = None
                logger.debug("关闭了HTTP会话", "B站解析")

    @classmethod
    async def get(
        cls,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        use_rate_limit: bool = True,
        max_attempts: int = 3,
    ) -> aiohttp.ClientResponse:
        """发送GET请求"""
        if use_rate_limit:
            await RateLimiter.acquire(url)

        context = {
            "url": url,
            "params": str(params) if params else None,
            "attempt": 0,
            "max_attempts": max_attempts,
        }

        for attempt in range(1, max_attempts + 1):
            context["attempt"] = attempt

            try:
                session = await cls.get_session()

                if timeout:
                    timeout_obj = aiohttp.ClientTimeout(total=timeout)
                else:
                    timeout_obj = session.timeout

                response = await session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout_obj,
                    allow_redirects=True,
                )

                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", "5"))
                    logger.warning(
                        f"请求频率限制 ({attempt}/{max_attempts}): {url}, 需等待 {retry_after}s",
                        "B站解析",
                    )

                    if attempt < max_attempts:
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        raise RateLimitError(
                            f"请求频率限制: {url}",
                            retry_after=retry_after,
                            context=context,
                        )

                return response

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < max_attempts:
                    wait_time = 1.0 * (2 ** (attempt - 1))
                    logger.warning(
                        f"请求失败 ({attempt}/{max_attempts}): {url}, 等待 {wait_time:.1f}s 后重试: {e}",
                        "B站解析",
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"请求失败 ({attempt}/{max_attempts}): {url}: {e}", "B站解析"
                    )
                    raise BilibiliRequestError(f"请求失败: {e}", context=context) from e

            except Exception as e:
                logger.error(
                    f"请求异常 ({attempt}/{max_attempts}): {url}: {e}", "B站解析"
                )
                raise BilibiliRequestError(f"请求异常: {e}", context=context) from e

    @classmethod
    @async_handle_errors(
        error_msg="获取JSON数据失败",
        exc_types=[
            aiohttp.ClientError,
            asyncio.TimeoutError,
            BilibiliRequestError,
            BilibiliResponseError,
        ],
        reraise=True,
    )
    async def get_json(
        cls,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        use_bilibili_headers: bool = True,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        """发送GET请求并解析JSON响应"""
        if headers is None and use_bilibili_headers:
            headers = get_bilibili_headers()

        request_context = {"url": url, "params": str(params) if params else None}

        async with await cls.get(
            url, params, headers, timeout, max_attempts=max_attempts
        ) as response:
            if response.status != 200:
                raise BilibiliRequestError(
                    f"HTTP状态码错误: {response.status}",
                    context={"url": url, "status": response.status},
                )

            try:
                return await response.json()
            except aiohttp.ContentTypeError as e:
                raise BilibiliResponseError(
                    f"JSON解析失败: {e}",
                    context=request_context,
                ) from e

    @classmethod
    @async_handle_errors(
        error_msg="获取文本数据失败",
        exc_types=[aiohttp.ClientError, asyncio.TimeoutError, BilibiliRequestError],
        reraise=True,
    )
    async def get_text(
        cls,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        max_attempts: int = 3,
    ) -> str:
        """发送GET请求并获取文本响应"""
        async with await cls.get(
            url, params, headers, timeout, max_attempts=max_attempts
        ) as response:
            if response.status != 200:
                raise BilibiliRequestError(
                    f"HTTP状态码错误: {response.status}",
                    context={"url": url, "status": response.status},
                )

            return await response.text()

    @staticmethod
    @handle_errors(
        error_msg="清理URL失败",
        log_level="warning",
        reraise=False,
        default_return=lambda url: url,
    )
    def clean_bilibili_url(url: str) -> str:
        """清理B站URL，移除不必要的参数"""
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        keep_params = ["p"]

        filtered_params = {k: v for k, v in query_params.items() if k in keep_params}

        if "p" in filtered_params and filtered_params["p"][0] == "1":
            filtered_params.pop("p")

        new_query = (
            urllib.parse.urlencode(filtered_params, doseq=True)
            if filtered_params
            else ""
        )

        netloc = parsed_url.netloc
        if netloc.startswith("m."):
            netloc = netloc.replace("m.", "www.", 1)

        clean_url = urllib.parse.urlunparse(
            (
                parsed_url.scheme,
                netloc,
                parsed_url.path,
                parsed_url.params,
                new_query,
                "",
            )
        )

        return clean_url

    @classmethod
    @async_handle_errors(
        error_msg="解析短链接失败",
        exc_types=[aiohttp.ClientError, asyncio.TimeoutError, BilibiliRequestError],
        reraise=True,
    )
    async def resolve_short_url(cls, url: str, max_attempts: int = 3) -> str:
        """解析短链接"""
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        async with await cls.get(
            url, use_rate_limit=True, timeout=10, max_attempts=max_attempts
        ) as response:
            resolved_url = str(response.url)
            clean_url = cls.clean_bilibili_url(resolved_url)

            logger.debug(f"短链接 {url} 解析为 {resolved_url}", "B站解析")
            if clean_url != resolved_url:
                logger.debug(f"清理后的URL: {clean_url}", "B站解析")

            return clean_url

    @classmethod
    async def with_retry(
        cls,
        func: Callable[[], Awaitable[T]],
        retry_exceptions: tuple = (Exception,),
        max_attempts: int = 3,
        base_wait: float = 1.0,
        exponential: bool = True,
        jitter: bool = True,
        retry_condition=None,
    ) -> T:
        """使用重试机制执行异步函数"""
        if retry_condition is None:
            retry_condition = transient_retry_condition

        last_exception = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await func()
            except retry_exceptions as e:
                last_exception = e

                is_last_attempt = attempt >= max_attempts

                should_retry = not is_last_attempt and retry_condition(e, attempt)

                if not should_retry:
                    logger.error(
                        f"操作失败 (尝试 {attempt}/{max_attempts}), 不再重试: {e}",
                        "B站解析",
                    )
                    break

                from ..utils.common import calculate_retry_wait_time

                wait_time = calculate_retry_wait_time(
                    attempt=attempt,
                    base_delay=base_wait,
                    max_delay=30.0,
                    exponential=exponential,
                    jitter=jitter,
                )

                logger.debug(
                    f"操作失败 (尝试 {attempt}/{max_attempts}), 等待 {wait_time:.1f}s 后重试: {e}",
                    "B站解析",
                )

                await asyncio.sleep(wait_time)

        if last_exception:
            if isinstance(last_exception, NetworkError):
                last_exception.with_context(attempts=max_attempts)
            raise last_exception

        raise RuntimeError("Unexpected error in with_retry")


class ParserService:
    """URL解析服务"""

    @staticmethod
    async def resolve_short_url(url: str) -> str:
        """解析短链接，返回原始URL"""
        original_url = url.strip()

        if "b23.tv" in original_url:
            logger.debug(f"检测到b23.tv短链接: {original_url}", "B站解析")
            try:
                resolved_url = await NetworkService.resolve_short_url(original_url)
                logger.debug(f"短链接解析结果: {resolved_url}", "B站解析")
                return resolved_url
            except ShortUrlError as e:
                logger.warning(
                    f"短链接解析失败 {original_url}: {e}，将使用原始链接继续尝试解析",
                    "B站解析",
                )

        return original_url

    @staticmethod
    async def fetch_resource_info(
        resource_type: ResourceType, resource_id: str, parsed_url: str
    ) -> Union[VideoInfo, LiveInfo, ArticleInfo, UserInfo, SeasonInfo]:
        """根据资源类型和ID获取详细信息"""
        from .api_service import BilibiliApiService
        from .utility_service import ScreenshotService

        logger.debug(
            f"获取资源信息: 类型={resource_type.name}, ID={resource_id}",
            "B站解析",
        )

        if resource_type == ResourceType.VIDEO:
            return await BilibiliApiService.get_video_info(
                vid=resource_id, parsed_url=parsed_url
            )
        elif resource_type == ResourceType.LIVE:
            return await BilibiliApiService.get_live_info(
                room_id=int(resource_id), parsed_url=parsed_url
            )
        elif resource_type == ResourceType.ARTICLE:
            return await BilibiliApiService.get_article_info(
                cv_id=resource_id, parsed_url=parsed_url
            )
        elif resource_type == ResourceType.OPUS:
            screenshot_bytes = await ScreenshotService.get_opus_screenshot(
                opus_id=resource_id, url=parsed_url
            )
            return ArticleInfo(
                id=resource_id,
                type="opus",
                url=parsed_url,
                screenshot_bytes=screenshot_bytes,
            )
        elif resource_type == ResourceType.USER:
            return await BilibiliApiService.get_user_info(
                uid=int(resource_id), parsed_url=parsed_url
            )
        elif resource_type == ResourceType.BANGUMI:
            ss_id: Optional[int] = None
            ep_id: Optional[int] = None
            if resource_id.startswith("ss"):
                ss_id = int(resource_id[2:])
            elif resource_id.startswith("ep"):
                ep_id = int(resource_id[2:])
            else:
                raise UrlParseError(
                    f"BangumiUrlParser 返回了无效的 ID 格式: {resource_id}"
                )

            return await BilibiliApiService.get_bangumi_info(
                parsed_url=parsed_url, season_id=ss_id, ep_id=ep_id
            )
        else:
            raise UnsupportedUrlError(f"不支持的资源类型: {resource_type}")

    @classmethod
    async def parse(
        cls, url: str
    ) -> Union[VideoInfo, LiveInfo, ArticleInfo, UserInfo, SeasonInfo]:
        """解析Bilibili URL，返回相应的信息模型"""
        original_url = url.strip()
        logger.debug(f"开始解析URL: {original_url}", "B站解析")

        final_url = await cls.resolve_short_url(original_url)

        try:
            resource_type, resource_id = UrlParserRegistry.parse(final_url)
            logger.debug(
                f"从URL提取资源信息: 类型={resource_type.name}, ID={resource_id}",
                "B站解析",
            )
        except (UrlParseError, UnsupportedUrlError):
            if final_url != original_url:
                logger.debug(
                    f"最终URL解析失败，尝试解析原始URL: {original_url}", "B站解析"
                )
                try:
                    resource_type, resource_id = UrlParserRegistry.parse(original_url)
                    logger.debug(
                        f"从原始URL提取资源信息: 类型={resource_type.name}, ID={resource_id}",
                        "B站解析",
                    )
                except (UrlParseError, UnsupportedUrlError) as e:
                    logger.warning(
                        f"无法从URL确定资源类型或ID: {original_url} (解析为: {final_url})",
                        "B站解析",
                    )
                    raise UrlParseError(
                        f"无法从URL确定资源类型或ID: {original_url} (解析为: {final_url})",
                        cause=e,
                        context={"original_url": original_url, "final_url": final_url},
                    )
            else:
                logger.warning(f"无法解析URL: {original_url}", "B站解析")
                raise

        if resource_type == ResourceType.SHORT_URL:
            resolved_url = await cls.resolve_short_url(original_url)
            if resolved_url == original_url:
                raise ShortUrlError(
                    f"无法解析短链接: {original_url}", context={"url": original_url}
                )

            logger.debug(f"递归解析短链接解析结果: {resolved_url}", "B站解析")
            return await cls.parse(resolved_url)

        parsed_url = final_url if final_url != original_url else original_url

        if resource_type == ResourceType.VIDEO and (
            parsed_url.startswith("av")
            or parsed_url.startswith("AV")
            or parsed_url.startswith("BV")
            or parsed_url.startswith("bv")
        ):
            if parsed_url.upper().startswith("BV"):
                full_url = f"https://www.bilibili.com/video/{parsed_url}"
                logger.debug(f"为纯BV号生成完整URL: {full_url}", "B站解析")
                parsed_url = full_url
            elif parsed_url.lower().startswith("av"):
                full_url = f"https://www.bilibili.com/video/{parsed_url}"
                logger.debug(f"为纯AV号生成完整URL: {full_url}", "B站解析")
                parsed_url = full_url

        return await cls.fetch_resource_info(
            resource_type=resource_type, resource_id=resource_id, parsed_url=parsed_url
        )
