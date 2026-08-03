from typing import Any


class BilibiliBaseException(Exception):
    """B站相关异常基类"""

    def __init__(
        self,
        message: str,
        cause: Exception | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """初始化异常"""
        self.message = message
        self.cause = cause
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        result = self.message

        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            result += f" [上下文: {context_str}]"

        if self.cause:
            result += f" (原因: {self.cause})"

        return result

    def with_context(self, **kwargs) -> "BilibiliBaseException":
        """添加上下文信息并返回自身"""
        self.context.update(kwargs)
        return self


class NetworkError(BilibiliBaseException):
    """网络错误基类"""


class BilibiliRequestError(NetworkError):
    """Bilibili API请求错误，如网络连接失败、超时等"""


class BilibiliResponseError(NetworkError):
    """Bilibili API响应数据错误，如响应格式错误、状态码异常等"""


class RateLimitError(NetworkError):
    """请求频率限制错误"""

    def __init__(self, message: str, retry_after: int | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class UrlError(BilibiliBaseException):
    """URL错误基类"""


class UrlParseError(UrlError):
    """无法解析URL或识别类型，如URL格式错误、缺少必要参数等"""


class UnsupportedUrlError(UrlParseError):
    """不支持的URL类型，如非B站URL或未实现支持的B站页面类型"""


class ShortUrlError(UrlError):
    """短链接解析错误"""


class ResourceError(BilibiliBaseException):
    """资源错误基类"""


class ResourceNotFoundError(ResourceError):
    """请求的资源（视频/直播间/专栏）不存在或已被删除"""


class ResourceAccessDeniedError(ResourceError):
    """资源访问被拒绝，如需要登录、地区限制等"""


class ResourceForbiddenError(ResourceError):
    """资源被禁止访问，如违规内容"""


class FeatureError(BilibiliBaseException):
    """功能错误基类"""


class ScreenshotError(FeatureError):
    """截图失败，如浏览器渲染错误、页面加载失败等"""


class DownloadError(FeatureError):
    """下载失败，如无法获取下载链接、写入文件失败等"""


class MediaProcessError(FeatureError):
    """媒体处理错误，如视频合并失败、格式转换失败等"""


class ConfigError(BilibiliBaseException):
    """配置错误，如配置项缺失、格式错误等"""
