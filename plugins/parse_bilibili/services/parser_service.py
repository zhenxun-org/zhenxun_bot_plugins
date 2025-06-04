from typing import Optional, Union

from zhenxun.services.log import logger

from ..model import VideoInfo, LiveInfo, ArticleInfo, UserInfo, SeasonInfo
from ..services.api_service import BilibiliApiService
from ..services.network_service import NetworkService
from ..services.screenshot_service import ScreenshotService
from ..utils.exceptions import UrlParseError, UnsupportedUrlError, ShortUrlError
from ..utils.url_parser import ResourceType, UrlParserRegistry


class ParserService:
    """URL解析服务，负责解析B站各类URL并返回对应的信息模型"""

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
