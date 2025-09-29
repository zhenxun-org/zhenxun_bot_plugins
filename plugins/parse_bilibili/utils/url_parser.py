import re
import json
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import List, Optional, Pattern, Tuple, Type, ClassVar, Dict, Any
from nonebot.adapters import Event, Bot
from nonebot_plugin_alconna.uniseg import Hyper, UniMsg, Text, UniMessage
from nonebot_plugin_alconna.uniseg.tools import reply_fetch

from zhenxun.services.log import logger

from ..utils.exceptions import UrlParseError, UnsupportedUrlError


class ResourceType(Enum):
    """资源类型"""

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
    RESOURCE_TYPE: ClassVar[ResourceType] = None  # type: ignore
    PATTERN: ClassVar[Optional[Pattern]] = None

    @classmethod
    @abstractmethod
    def can_parse(cls, url: str) -> bool:
        """检查是否可以解析指定URL"""
        pass

    @classmethod
    @abstractmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """解析URL，提取资源类型和ID"""
        pass


class RegexUrlParser(UrlParser):
    """基于正则表达式的URL解析器基类"""

    PATTERN: ClassVar[Pattern] = None  # type: ignore
    GROUP_INDEX: ClassVar[int] = 1

    @classmethod
    def can_parse(cls, url: str) -> bool:
        """检查是否可以解析指定URL"""
        if not cls.PATTERN:
            return False
        return bool(cls.PATTERN.search(url))

    @classmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """解析URL，提取资源类型和ID"""
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
    # 修改正则表达式，使其能匹配 /video/ 路径或 bvid=... 的URL参数
    PATTERN = re.compile(
        r"bilibili\.com/.*?(?:video/(av\d+|BV[A-Za-z0-9]+)|[?&]bvid=(BV[A-Za-z0-9]+))"
    )

    @classmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """
        重写 parse 方法以处理更复杂的正则表达式。
        它可以从路径或URL参数中提取视频ID。
        """
        if not cls.RESOURCE_TYPE:
            raise ValueError(f"解析器 {cls.__name__} 未定义资源类型")

        match = cls.PATTERN.search(url)
        if not match:
            raise UrlParseError(f"URL不匹配视频模式: {url}")

        # group(1) 匹配 /video/后的ID, group(2) 匹配 bvid=后的ID
        resource_id = match.group(1) or match.group(2)
        if not resource_id:
            raise UrlParseError(f"无法从URL提取视频资源ID: {url}")

        return cls.RESOURCE_TYPE, resource_id


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

    @classmethod
    def can_parse(cls, url: str) -> bool:
        """检查是否可以解析指定URL，增强番剧链接识别能力"""
        if super().can_parse(url):
            return True
        if "/bangumi/play/ep" in url or "/bangumi/play/ss" in url:
            logger.debug(f"通过关键字匹配识别到番剧链接: {url}")
            return True
        return False

    @classmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """解析URL，提取资源类型和ID，增强番剧链接解析能力"""
        try:
            return super().parse(url)
        except UrlParseError:
            ep_match = re.search(r"/ep(\d+)", url)
            if ep_match:
                return cls.RESOURCE_TYPE, f"ep{ep_match.group(1)}"

            ss_match = re.search(r"/ss(\d+)", url)
            if ss_match:
                return cls.RESOURCE_TYPE, f"ss{ss_match.group(1)}"

            raise UrlParseError(f"无法从URL提取番剧ID: {url}")


class PureVideoIdParser(RegexUrlParser):
    """纯视频ID解析器"""

    PRIORITY = 80
    RESOURCE_TYPE = ResourceType.VIDEO
    PATTERN = re.compile(r"(?:av|AV)(\d+)|(?:bv|BV)([A-Za-z0-9]+)")

    @classmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """解析纯视频ID"""
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
        """注册解析器"""
        if parser_class not in cls._parsers:
            cls._parsers.append(parser_class)
            cls._parsers.sort(key=lambda p: p.PRIORITY)
            logger.debug(f"注册URL解析器: {parser_class.__name__}", "B站解析")

    @classmethod
    def get_parser(cls, url: str) -> Optional[Type[UrlParser]]:
        """获取能够解析指定URL的解析器"""
        for parser in cls._parsers:
            if parser.can_parse(url):
                return parser
        return None

    @classmethod
    def parse(cls, url: str) -> Tuple[ResourceType, str]:
        """解析URL"""
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


def _extract_url_from_hyper_or_json(raw_str: str) -> Optional[str]:
    """从Hyper(小程序/JSON卡片)的原始数据中提取B站URL"""
    qqdocurl_match = re.search(r'"qqdocurl"\s*:\s*"([^"]+)"', raw_str)
    if qqdocurl_match:
        qqdocurl = qqdocurl_match.group(1).replace("\\", "")
        if "b23.tv" in qqdocurl or "bilibili.com" in qqdocurl:
            logger.debug(f"通过qqdocurl提取到链接: {qqdocurl}")
            return qqdocurl

    url_match = re.search(
        r'https?://[^\s"\']+(?:bilibili\.com|b23\.tv)[^\s"\']*', raw_str
    )
    if url_match:
        extracted_url = url_match.group(0)
        logger.debug(f"通过通用URL正则提取到链接: {extracted_url}")
        return extracted_url

    try:
        data = json.loads(raw_str)

        meta_data = data.get("meta", {})
        detail_1 = meta_data.get("detail_1", {})
        news = meta_data.get("news", {})

        jump_url = (
            news.get("jumpUrl")
            or detail_1.get("qqdocurl")
            or detail_1.get("preview")
            or detail_1.get("url")
            or data.get("jumpUrl")
            or data.get("url")
            or data.get("qqdocurl")
        )

        if jump_url and isinstance(jump_url, str):
            if "bilibili.com" in jump_url or "b23.tv" in jump_url:
                logger.debug(f"从JSON数据提取到B站链接: {jump_url}")
                return jump_url

    except Exception as e:
        logger.debug(f"解析JSON失败: {e}")

    return None


def extract_bilibili_url_from_miniprogram(raw_str: str) -> Optional[str]:
    """从小程序消息提取B站URL（现在是_extract_url_from_hyper_or_json的包装）"""
    logger.debug(f"开始解析小程序/卡片消息，原始数据长度: {len(raw_str)}")
    url = _extract_url_from_hyper_or_json(raw_str)
    if url:
        logger.info(f"从小程序/卡片提取到B站链接: {url}")
    return url


def extract_bilibili_url_from_message(
    message, check_hyper: bool = True
) -> Optional[str]:
    """从消息提取B站URL"""
    target_url = None

    if check_hyper:
        for seg in message:
            if isinstance(seg, Hyper) and seg.raw:
                try:
                    excluded_apps = [
                        "com.tencent.qun.invite",
                        "com.tencent.qqav.groupvideo",
                        "com.tencent.mobileqq.reading",
                        "com.tencent.weather",
                    ]
                    if any(app_name in seg.raw for app_name in excluded_apps):
                        logger.debug("消息中的小程序/卡片在排除列表，跳过", "B站解析")
                        continue

                    extracted_url = _extract_url_from_hyper_or_json(seg.raw)
                    if extracted_url:
                        target_url = extracted_url
                        logger.debug(f"从Hyper段提取到B站链接: {target_url}")
                        break
                except Exception as e:
                    logger.debug(f"解析Hyper段失败: {e}")

    if not target_url:
        plain_text = message.extract_plain_text().strip()
        if plain_text:
            match = re.search(
                r"b23\.tv/([A-Za-z0-9]+)|bilibili\.com/video/(av\d+|BV[A-Za-z0-9]+)",
                plain_text,
            )
            if match:
                target_url = match.group(0)
                logger.debug(f"从文本内容提取到URL: {target_url}")
            elif re.fullmatch(r"((av|AV)\d+|(bv|BV)[A-Za-z0-9]+)", plain_text):
                target_url = plain_text
                logger.debug(f"从文本内容提取到纯视频ID: {target_url}")
            elif "bilibili.com" in plain_text or "b23.tv" in plain_text:
                from .common import extract_url_from_text

                url = extract_url_from_text(plain_text)
                if url and ("bilibili.com" in url or "b23.tv" in url):
                    target_url = url
                    logger.debug(f"从文本内容提取到通用URL: {target_url}")

    return target_url


def parse_bilibili_url(
    url: str,
) -> Tuple[Optional[ResourceType], Optional[str], Optional[Dict[str, Any]]]:
    """解析B站URL，返回资源类型、资源ID和额外信息"""
    resource_type = None
    resource_id = None
    url_info_dict = {}

    try:
        parser = UrlParserRegistry.get_parser(url)
        if parser:
            resource_type, resource_id = parser.parse(url)

            if resource_type == ResourceType.BANGUMI:
                if resource_id.startswith("ep"):
                    url_info_dict["ep_id"] = resource_id[2:]
                elif resource_id.startswith("ss"):
                    url_info_dict["season_id"] = resource_id[2:]
            elif resource_type == ResourceType.VIDEO:
                if resource_id.startswith("av"):
                    url_info_dict["aid"] = resource_id[2:]
                elif resource_id.startswith("BV"):
                    url_info_dict["bvid"] = resource_id

            logger.debug(
                f"解析URL成功: {url} -> 类型={resource_type}, ID={resource_id}"
            )
    except Exception as e:
        logger.warning(f"解析URL失败: {url}, 错误: {e}")

    return resource_type, resource_id, url_info_dict


async def extract_bilibili_url_from_reply(reply: Optional[UniMsg]) -> Optional[str]:
    """从回复消息中提取B站URL"""
    if not reply:
        logger.debug("回复消息为空")
        return None

    target_url = None

    for seg in reply:
        if isinstance(seg, Hyper) and seg.raw:
            logger.debug(f"处理回复消息的 Hyper 段，raw 长度: {len(seg.raw)}")
            extracted_url = _extract_url_from_hyper_or_json(seg.raw)
            if extracted_url:
                target_url = extracted_url
                logger.info(f"从回复消息提取到B站链接: {target_url}")
                break

    if not target_url:
        patterns = {
            "b23_tv": ShortUrlParser.PATTERN,
            "video": VideoUrlParser.PATTERN,
            "live": LiveUrlParser.PATTERN,
            "article": ArticleUrlParser.PATTERN,
            "opus": OpusUrlParser.PATTERN,
            "bangumi": BangumiUrlParser.PATTERN,
            "pure_video_id": PureVideoIdParser.PATTERN,
        }
        url_match_order = ["b23_tv", "video", "bangumi", "live", "article", "opus"]

        for seg in reply:
            if isinstance(seg, Text):
                text_content = seg.text.strip()
                if not text_content:
                    continue
                logger.debug(f"检查回复消息的 Text 段: '{text_content}'")

                for key in url_match_order:
                    match = patterns[key].search(text_content)
                    if match:
                        potential_url = match.group(0)
                        if (
                            potential_url.startswith("http")
                            or "b23.tv" in potential_url
                            or key == "b23_tv"
                        ):
                            target_url = potential_url
                            logger.info(f"从回复消息提取到B站链接: {target_url}")
                            break

                if target_url:
                    break

                if not target_url:
                    match = patterns["pure_video_id"].search(text_content)
                    if match:
                        target_url = match.group(0)
                        logger.info(f"从回复消息提取到B站视频ID: {target_url}")
                        break

        if not target_url:
            try:
                plain_text = reply.extract_plain_text().strip()
                if plain_text:
                    logger.debug(f"尝试从回复消息的纯文本提取: '{plain_text}'")

                    bangumi_pattern = re.compile(
                        r"(?:https?://)?(?:www\.|m\.)?bilibili\.com/bangumi/play/(ss\d+|ep\d+)"
                    )
                    bangumi_match = bangumi_pattern.search(plain_text)
                    if bangumi_match:
                        target_url = bangumi_match.group(0)
                        logger.info(f"从回复消息提取到B站番剧链接: {target_url}")
                    else:
                        for key in url_match_order:
                            match = patterns[key].search(plain_text)
                            if match:
                                potential_url = match.group(0)
                                if (
                                    potential_url.startswith("http")
                                    or "b23.tv" in potential_url
                                    or "bilibili.com" in potential_url
                                    or key == "b23_tv"
                                ):
                                    target_url = potential_url
                                    logger.info(
                                        f"从回复消息提取到B站链接: {target_url}"
                                    )
                                    break

                        if not target_url:
                            match = patterns["pure_video_id"].fullmatch(plain_text)
                            if match:
                                target_url = match.group(0)
                                logger.info(f"从回复消息提取到B站视频ID: {target_url}")
            except Exception as e:
                logger.warning(f"提取回复纯文本失败: {e}")

    return target_url


async def extract_bilibili_url_from_json_data(json_data: str) -> Optional[str]:
    """从JSON数据中提取B站URL"""
    if not json_data:
        return None

    url = _extract_url_from_hyper_or_json(json_data)
    if url:
        logger.info(f"从JSON数据中提取到B站链接: {url}")
    return url


async def extract_bilibili_url_from_event(bot: Bot, event: Event) -> Optional[str]:
    """从事件中提取B站URL（包括回复和当前消息）"""
    target_url = None

    try:
        reply: UniMessage = await reply_fetch(event, bot)  # type: ignore
        if reply:
            logger.debug("找到回复消息")
            target_url = await extract_bilibili_url_from_reply(reply)
            if target_url:
                return target_url

        if hasattr(event, "model_dump"):
            raw_event = event.model_dump()
        elif hasattr(event, "dict"):
            raw_event = event.dict()
        else:
            raw_event = {}
            logger.debug("事件对象没有model_dump或dict方法")

        if reply_attr := getattr(event, "reply", None):
            logger.debug("事件中包含回复信息")

            reply_message = reply_attr.message
            logger.debug("获取到回复消息")

            for seg in reply_message:
                if (
                    hasattr(seg, "type")
                    and seg.type == "json"
                    and hasattr(seg, "data")
                    and "data" in seg.data
                ):
                    json_data = seg.data["data"]
                    logger.debug("找到回复消息中的JSON数据")

                    extracted_url = await extract_bilibili_url_from_json_data(json_data)
                    if extracted_url:
                        target_url = extracted_url
                        return target_url

        elif "reply" in raw_event:
            logger.debug("原始事件中包含回复字段")

            reply_data = raw_event.get("reply", {})
            if "message" in reply_data:
                reply_message = reply_data["message"]
                logger.debug("获取到原始回复消息")

                json_match = re.search(r"\[CQ:json,data=(.+?)\]", str(reply_message))
                if json_match:
                    json_data = json_match.group(1)
                    logger.debug("找到原始回复消息中的JSON数据")

                    extracted_url = await extract_bilibili_url_from_json_data(json_data)
                    if extracted_url:
                        target_url = extracted_url
                        return target_url

        message = event.get_message()
        reply_id = None

        for i, seg in enumerate(message):
            logger.debug(f"检查消息段 {i}")
            if hasattr(seg, "type") and seg.type == "reply":
                logger.debug("找到回复段")
                if hasattr(seg, "data") and "id" in seg.data:
                    reply_id = seg.data["id"]
                    logger.debug(f"从消息段中提取到回复ID: {reply_id}")
                    break

        if reply_id and hasattr(bot, "get_msg"):
            logger.debug("尝试使用bot.get_msg获取消息")
            try:
                msg_info = await bot.get_msg(message_id=int(reply_id))
                logger.debug("获取到消息")

                if "message" in msg_info:
                    raw_message = msg_info["message"]
                    logger.debug("获取到原始消息内容")

                    if isinstance(raw_message, str) and "json" in raw_message:
                        logger.debug("消息包含JSON内容，可能是小程序")
                        json_match = re.search(r"\[json:data=(.+?)\]", raw_message)
                        if json_match:
                            json_data = json_match.group(1)
                            logger.debug("提取到JSON数据")

                            extracted_url = await extract_bilibili_url_from_json_data(
                                json_data
                            )
                            if extracted_url:
                                target_url = extracted_url
                                return target_url
            except Exception as e:
                logger.error(f"使用bot.get_msg获取消息失败: {e}")

    except Exception as e:
        logger.error(f"检查事件回复信息时出错: {e}")

    try:
        current_message = event.get_message()

        for seg in current_message:
            if isinstance(seg, Hyper) and seg.raw:
                extracted_url = _extract_url_from_hyper_or_json(seg.raw)
                if extracted_url:
                    target_url = extracted_url
                    logger.info(f"从当前消息提取到B站链接: {target_url}")
                    return target_url

        target_url = extract_bilibili_url_from_message(current_message)
        if target_url:
            return target_url

    except Exception as e:
        logger.error(f"从当前消息提取URL失败: {e}")

    return target_url
