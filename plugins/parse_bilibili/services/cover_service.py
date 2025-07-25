from typing import Optional, Union

from nonebot_plugin_alconna import UniMsg
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from ..model import SeasonInfo, VideoInfo
from ..utils.exceptions import BilibiliBaseException
from .network_service import ParserService


class CoverService:
    """获取封面的服务"""

    @staticmethod
    async def _extract_cover_url(
        content_info: Union[VideoInfo, SeasonInfo],
    ) -> Optional[str]:
        """从内容信息中提取封面URL"""
        cover_url = getattr(content_info, "pic", None) or getattr(
            content_info, "cover", None
        )
        if cover_url and "@" in cover_url:
            return cover_url.split("@")[0]
        return cover_url

    @staticmethod
    async def get_cover_message(url: str) -> UniMsg:
        """
        根据URL获取封面，并构建一个包含图片和信息的UniMsg。
        如果失败，则抛出 BilibiliBaseException。
        """
        logger.info(f"开始获取封面: {url}")
        try:
            parsed_content = await ParserService.parse(url)

            if not isinstance(parsed_content, (VideoInfo, SeasonInfo)):
                raise BilibiliBaseException(
                    f"该链接内容类型 ({type(parsed_content).__name__}) 不支持获取封面。"
                )

            cover_url = await CoverService._extract_cover_url(parsed_content)
            if not cover_url:
                raise BilibiliBaseException("该内容没有可用的封面图片。")

            logger.info(f"获取到封面URL: {cover_url}")

            headers = {"Referer": "https://www.bilibili.com/"}
            image_data = await AsyncHttpx.get_content(cover_url, headers=headers)

            if not image_data:
                raise BilibiliBaseException("下载封面图片失败。")

            title = f"《{parsed_content.title}》的封面"
            return (
                UniMsg.image(
                    raw=image_data,
                    name=f"{parsed_content.bvid or parsed_content.season_id}.jpg",
                )
                + f"\n{title}\n原始链接: {cover_url}"
            )

        except BilibiliBaseException:
            raise
        except Exception as e:
            logger.error(f"获取封面时发生未知错误: {e}", e=e)
            raise BilibiliBaseException("获取封面时发生未知错误，请检查日志。") from e
