"""
URL解析器模块

提供了一组基于策略模式的URL解析器，用于解析不同类型的B站URL
"""

import re
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import List, Optional, Pattern, Tuple, Type, ClassVar

from zhenxun.services.log import logger

from ..utils.exceptions import UrlParseError, UnsupportedUrlError


class ResourceType(Enum):
    """资源类型枚举"""

    VIDEO = auto()
    LIVE = auto()
    ARTICLE = auto()
    OPUS = auto()
    USER = auto()
    BANGUMI = auto()
    SHORT_URL = auto()


class UrlParser(ABC):
    """URL解析器基类"""

    PRIORITY: ClassVar[int] = 100

    RESOURCE_TYPE: ClassVar[ResourceType] = None

    @classmethod
    @abstractmethod
    def can_parse(cls, url: str) -> bool:
        """
        检查是否可以解析指定URL

        Args:
            url: 要检查的URL

        Returns:
            是否可以解析
        """
        pass

    @classmethod
    @abstractmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """
        解析URL，提取资源类型和ID

        Args:
            url: 要解析的URL

        Returns:
            元组 (资源类型, 资源ID)

        Raises:
            UrlParseError: 当无法解析URL时
        """
        pass


class RegexUrlParser(UrlParser):
    """基于正则表达式的URL解析器基类"""

    PATTERN: ClassVar[Pattern] = None

    GROUP_INDEX: ClassVar[int] = 1

    @classmethod
    def can_parse(cls, url: str) -> bool:
        """
        检查是否可以解析指定URL

        Args:
            url: 要检查的URL

        Returns:
            是否可以解析
        """
        if not cls.PATTERN:
            return False
        return bool(cls.PATTERN.search(url))

    @classmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """
        解析URL，提取资源类型和ID

        Args:
            url: 要解析的URL

        Returns:
            元组 (资源类型, 资源ID)

        Raises:
            UrlParseError: 当无法解析URL时
        """
        if not cls.RESOURCE_TYPE:
            raise ValueError(f"解析器 {cls.__name__} 未定义资源类型")

        match = cls.PATTERN.search(url)
        if not match:
            raise UrlParseError(f"URL不匹配模式: {url}")

        resource_id = match.group(cls.GROUP_INDEX)
        if not resource_id:
            raise UrlParseError(f"无法从URL提取资源ID: {url}")

        return cls.RESOURCE_TYPE, resource_id


class ShortUrlParser(RegexUrlParser):
    """B站短链接解析器"""

    PRIORITY = 10
    RESOURCE_TYPE = ResourceType.SHORT_URL
    PATTERN = re.compile(r"(?:https?://)?b23\.tv/([A-Za-z0-9]+)")


class VideoUrlParser(RegexUrlParser):
    """视频链接解析器"""

    PRIORITY = 20
    RESOURCE_TYPE = ResourceType.VIDEO
    PATTERN = re.compile(
        r"(?:https?://)?(?:www\.|m\.)?bilibili\.com/video/(av\d+|BV[A-Za-z0-9]+)"
    )


class LiveUrlParser(RegexUrlParser):
    """直播链接解析器"""

    PRIORITY = 30
    RESOURCE_TYPE = ResourceType.LIVE
    PATTERN = re.compile(r"(?:https?://)?live\.bilibili\.com/(\d+)")


class ArticleUrlParser(RegexUrlParser):
    """专栏文章链接解析器"""

    PRIORITY = 40
    RESOURCE_TYPE = ResourceType.ARTICLE
    PATTERN = re.compile(r"(?:https?://)?www\.bilibili\.com/read/(cv\d+)")


class OpusUrlParser(RegexUrlParser):
    """动态链接解析器"""

    PRIORITY = 50
    RESOURCE_TYPE = ResourceType.OPUS
    PATTERN = re.compile(
        r"(?:https?://)?(?:www\.bilibili\.com/opus/|t\.bilibili\.com/)(\d+)"
    )


class UserUrlParser(RegexUrlParser):
    """用户空间链接解析器"""

    PRIORITY = 60
    RESOURCE_TYPE = ResourceType.USER
    PATTERN = re.compile(r"(?:https?://)?space\.bilibili\.com/(\d+)")


class BangumiUrlParser(RegexUrlParser):
    """番剧/影视链接解析器"""

    PRIORITY = 70
    RESOURCE_TYPE = ResourceType.BANGUMI
    PATTERN = re.compile(
        r"(?:https?://)?(?:www\.|m\.)?bilibili\.com/bangumi/play/(ss\d+|ep\d+)"
    )


class PureVideoIdParser(RegexUrlParser):
    """纯视频ID解析器"""

    PRIORITY = 80
    RESOURCE_TYPE = ResourceType.VIDEO
    PATTERN = re.compile(r"(?:av|AV)(\d+)|(?:bv|BV)([A-Za-z0-9]+)")

    @classmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """
        解析纯视频ID

        Args:
            url: 要解析的URL或ID

        Returns:
            元组 (资源类型, 资源ID)

        Raises:
            UrlParseError: 当无法解析URL时
        """
        match = cls.PATTERN.search(url)
        if not match:
            raise UrlParseError(f"无法解析视频ID: {url}")

        av_id = match.group(1)
        bv_id = match.group(2)

        if av_id:
            return cls.RESOURCE_TYPE, f"av{av_id}"
        elif bv_id:
            return cls.RESOURCE_TYPE, f"BV{bv_id}"
        else:
            raise UrlParseError(f"无法从匹配中提取视频ID: {url}")


class UrlParserRegistry:
    """URL解析器注册表"""

    _parsers: List[Type[UrlParser]] = []

    @classmethod
    def register(cls, parser_class: Type[UrlParser]):
        """
        注册解析器

        Args:
            parser_class: 要注册的解析器类
        """
        if parser_class not in cls._parsers:
            cls._parsers.append(parser_class)
            cls._parsers.sort(key=lambda p: p.PRIORITY)
            logger.debug(f"注册URL解析器: {parser_class.__name__}", "B站解析")

    @classmethod
    def get_parser(cls, url: str) -> Optional[Type[UrlParser]]:
        """
        获取能够解析指定URL的解析器

        Args:
            url: 要解析的URL

        Returns:
            能够解析URL的解析器，如果没有找到则返回None
        """
        for parser in cls._parsers:
            if parser.can_parse(url):
                return parser
        return None

    @classmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """
        解析URL

        Args:
            url: 要解析的URL

        Returns:
            元组 (资源类型, 资源ID)

        Raises:
            UnsupportedUrlError: 当没有找到能够解析URL的解析器时
            UrlParseError: 当解析过程中出错时
        """
        parser = cls.get_parser(url)
        if not parser:
            raise UnsupportedUrlError(f"不支持的URL格式: {url}")

        try:
            return parser.parse(url)
        except UrlParseError:
            raise
        except Exception as e:
            raise UrlParseError(f"解析URL时出错: {e}") from e


UrlParserRegistry.register(ShortUrlParser)
UrlParserRegistry.register(VideoUrlParser)
UrlParserRegistry.register(LiveUrlParser)
UrlParserRegistry.register(ArticleUrlParser)
UrlParserRegistry.register(OpusUrlParser)
UrlParserRegistry.register(UserUrlParser)
UrlParserRegistry.register(BangumiUrlParser)
UrlParserRegistry.register(PureVideoIdParser)
