from typing import Dict

from zhenxun.utils.user_agent import get_user_agent_str


def get_bilibili_headers() -> Dict[str, str]:
    """
    获取B站请求头

    Returns:
        B站请求头字典
    """
    user_agent = get_user_agent_str()

    headers = {
        "User-Agent": user_agent,
        "Referer": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://www.bilibili.com",
    }

    return headers


def get_bilibili_video_headers() -> Dict[str, str]:
    """
    获取B站视频请求头

    Returns:
        B站视频请求头字典
    """
    headers = get_bilibili_headers()
    headers.update(
        {
            "Referer": "https://www.bilibili.com/video/",
        }
    )

    return headers


def get_bilibili_live_headers() -> Dict[str, str]:
    """
    获取B站直播请求头

    Returns:
        B站直播请求头字典
    """
    headers = get_bilibili_headers()
    headers.update(
        {
            "Referer": "https://live.bilibili.com/",
        }
    )

    return headers


def get_bilibili_article_headers() -> Dict[str, str]:
    """
    获取B站专栏请求头

    Returns:
        B站专栏请求头字典
    """
    headers = get_bilibili_headers()
    headers.update(
        {
            "Referer": "https://www.bilibili.com/read/",
        }
    )

    return headers
