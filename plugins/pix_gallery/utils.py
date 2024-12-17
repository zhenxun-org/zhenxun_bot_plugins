from zhenxun.configs.config import Config

from .config import KwType


def get_api(t: KwType) -> str:
    """返回接口api地址

    参数:
        t: KwType

    返回:
        str: api地址
    """
    hibiapi = Config.get_config("hibiapi", "HIBIAPI")
    # hibiapi = "http://43.143.112.57:13667"
    if t == KwType.PID:
        return f"{hibiapi}/api/pixiv/illust"
    elif t == KwType.UID:
        return f"{hibiapi}/api/pixiv/member_illust"
    return f"{hibiapi}/api/pixiv/search"
