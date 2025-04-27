"""
网络服务模块

提供了优化的网络请求服务，包括请求限流、自动重试、错误处理等功能
"""

import asyncio
import time
import urllib.parse
from typing import Dict, Any, Optional, Callable, TypeVar, Awaitable
import aiohttp
from collections import defaultdict


from zhenxun.services.log import logger

from ..config import HTTP_TIMEOUT, HTTP_CONNECT_TIMEOUT
from ..utils.exceptions import (
    BilibiliRequestError,
    BilibiliResponseError,
    RateLimitError,
    ShortUrlError,
    NetworkError,
)
from ..utils.headers import get_bilibili_headers

T = TypeVar("T")


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
        """
        获取请求许可

        Args:
            url: 请求URL

        Returns:
            等待的时间（秒）
        """
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
        """
        获取所有域名的请求统计信息

        Returns:
            域名统计信息字典
        """
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
        """
        更新域名的请求间隔

        Args:
            domain: 域名
            interval: 新的请求间隔（秒）
        """
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
        """
        获取或创建HTTP会话

        Returns:
            HTTP会话对象
        """
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
        """
        发送GET请求

        Args:
            url: 请求URL
            params: 请求参数
            headers: 请求头
            timeout: 超时时间（秒）
            use_rate_limit: 是否使用限流
            max_attempts: 最大尝试次数

        Returns:
            响应对象

        Raises:
            BilibiliRequestError: 请求失败
        """
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
    async def get_json(
        cls,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        use_bilibili_headers: bool = True,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        """
        发送GET请求并解析JSON响应

        Args:
            url: 请求URL
            params: 请求参数
            headers: 请求头
            timeout: 超时时间（秒）
            use_bilibili_headers: 是否使用B站请求头
            max_attempts: 最大尝试次数

        Returns:
            JSON响应数据

        Raises:
            BilibiliRequestError: 请求失败
            BilibiliResponseError: 响应解析失败
        """
        if headers is None and use_bilibili_headers:
            headers = get_bilibili_headers()

        context = {"url": url, "params": str(params) if params else None}

        try:
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
                        context=context,
                    ) from e

        except BilibiliRequestError:
            raise
        except Exception as e:
            raise BilibiliRequestError(f"获取JSON失败: {e}", context=context) from e

    @classmethod
    async def get_text(
        cls,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        max_attempts: int = 3,
    ) -> str:
        """
        发送GET请求并获取文本响应

        Args:
            url: 请求URL
            params: 请求参数
            headers: 请求头
            timeout: 超时时间（秒）
            max_attempts: 最大尝试次数

        Returns:
            文本响应数据

        Raises:
            BilibiliRequestError: 请求失败
            BilibiliResponseError: 响应解析失败
        """
        context = {"url": url, "params": str(params) if params else None}

        try:
            async with await cls.get(
                url, params, headers, timeout, max_attempts=max_attempts
            ) as response:
                if response.status != 200:
                    raise BilibiliRequestError(
                        f"HTTP状态码错误: {response.status}",
                        context={"url": url, "status": response.status},
                    )

                return await response.text()

        except BilibiliRequestError:
            raise
        except Exception as e:
            raise BilibiliRequestError(f"获取文本失败: {e}", context=context) from e

    @staticmethod
    def clean_bilibili_url(url: str) -> str:
        """
        清理B站URL，移除不必要的参数

        Args:
            url: 原始URL

        Returns:
            清理后的URL
        """
        try:
            parsed_url = urllib.parse.urlparse(url)

            query_params = urllib.parse.parse_qs(parsed_url.query)

            keep_params = ["p"]

            filtered_params = {
                k: v for k, v in query_params.items() if k in keep_params
            }

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
        except Exception as e:
            logger.warning(f"清理URL失败: {url}, 错误: {e}", "B站解析")
            return url

    @classmethod
    async def resolve_short_url(cls, url: str, max_attempts: int = 3) -> str:
        """
        解析短链接

        Args:
            url: 短链接URL
            max_attempts: 最大尝试次数

        Returns:
            解析后的URL

        Raises:
            ShortUrlError: 解析失败
        """
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        context = {"url": url}

        try:
            async with await cls.get(
                url, use_rate_limit=True, timeout=10, max_attempts=max_attempts
            ) as response:
                resolved_url = str(response.url)

                clean_url = cls.clean_bilibili_url(resolved_url)

                logger.debug(f"短链接 {url} 解析为 {resolved_url}", "B站解析")
                if clean_url != resolved_url:
                    logger.debug(f"清理后的URL: {clean_url}", "B站解析")

                return clean_url

        except BilibiliRequestError as e:
            raise ShortUrlError(f"解析短链接请求失败: {e}", cause=e, context=context)
        except Exception as e:
            raise ShortUrlError(f"解析短链接失败: {e}", context=context) from e

    @classmethod
    async def with_retry(
        cls,
        func: Callable[[], Awaitable[T]],
        retry_exceptions: tuple = (Exception,),
        max_attempts: int = 3,
        base_wait: float = 1.0,
        max_wait: float = 30.0,
        exponential: bool = True,
    ) -> T:
        """
        使用重试机制执行异步函数

        Args:
            func: 要执行的异步函数
            retry_exceptions: 需要重试的异常类型
            max_attempts: 最大尝试次数
            base_wait: 基础等待时间（秒）
            max_wait: 最大等待时间（秒）
            exponential: 是否使用指数退避

        Returns:
            函数执行结果

        Raises:
            Exception: 所有尝试都失败时抛出最后一个异常
        """
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await func()
            except retry_exceptions as e:
                last_error = e

                if attempt < max_attempts:
                    if exponential:
                        wait_time = min(base_wait * (2 ** (attempt - 1)), max_wait)
                    else:
                        wait_time = base_wait

                    logger.warning(
                        f"操作失败 (尝试 {attempt}/{max_attempts}), 等待 {wait_time:.1f}s 后重试: {e}",
                        "B站解析",
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"操作失败 (尝试 {attempt}/{max_attempts}), 不再重试: {e}",
                        "B站解析",
                    )

        if isinstance(last_error, NetworkError):
            last_error.with_context(attempts=max_attempts)

        raise last_error
