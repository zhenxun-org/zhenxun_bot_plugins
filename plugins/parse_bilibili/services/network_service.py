import urllib.parse
from typing import Union, Optional
from pathlib import Path

import httpx
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.exception import AllURIsFailedError
from zhenxun.services.log import logger

from ..model import VideoInfo, LiveInfo, ArticleInfo, UserInfo, SeasonInfo
from ..utils.exceptions import (
    UrlParseError,
    UnsupportedUrlError,
    ShortUrlError,
    DownloadError,
)
from ..utils.url_parser import ResourceType, UrlParserRegistry


async def download_bilibili_file(url: str, file_path: Path) -> bool:
    """
    下载B站文件，利用 AsyncHttpx 的健壮下载能力。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
        "Referer": "https://www.bilibili.com",
    }
    logger.info(f"开始下载文件: {file_path.name} (使用 AsyncHttpx)")
    try:
        success = await AsyncHttpx.download_file(
            url=url, path=file_path, headers=headers, stream=True
        )
        if not success:
            raise DownloadError(f"下载文件 {file_path.name} 失败，但未抛出异常。")
        return success
    except AllURIsFailedError as e:
        logger.error(f"下载文件 {file_path.name} 失败，已达到最大重试次数", e=e)
        raise DownloadError(
            f"下载文件 {file_path.name} 失败，已达到最大重试次数",
            context={"url": url, "file_path": str(file_path)},
            cause=e,
        ) from e


class ParserService:
    """URL解析服务"""

    @staticmethod
    async def resolve_short_url(url: str) -> str:
        """解析短链接，返回原始URL"""
        original_url = url.strip()

        if "b23.tv" in original_url:
            logger.debug(f"检测到b23.tv短链接: {original_url}", "B站解析")
            try:
                if not original_url.startswith(("http://", "https://")):
                    original_url = f"https://{original_url}"

                response = await AsyncHttpx.get(original_url, timeout=10)
                resolved_url = str(response.url)

                parsed_url_obj = urllib.parse.urlparse(resolved_url)
                query_params = urllib.parse.parse_qs(parsed_url_obj.query)
                filtered_params = {k: v for k, v in query_params.items() if k in ["p"]}
                new_query = (
                    urllib.parse.urlencode(filtered_params, doseq=True)
                    if filtered_params
                    else ""
                )

                clean_url = urllib.parse.urlunparse(
                    (
                        parsed_url_obj.scheme,
                        parsed_url_obj.netloc,
                        parsed_url_obj.path,
                        parsed_url_obj.params,
                        new_query,
                        "",
                    )
                )

                logger.debug(f"短链接解析结果: {clean_url}", "B站解析")
                return clean_url
            except (ShortUrlError, httpx.HTTPError) as e:
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
