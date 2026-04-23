import json
from typing import Any

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from .model import MusicMetaData, MusicHelper

DOMAIN = "https://music.163.com"
REAL_IP = "58.100.87.193"


async def request(uri: str, data: dict[str, Any]) -> dict[str, Any]:
    url = DOMAIN + uri
    response = await AsyncHttpx.post(
        url=url,
        data=data,
        headers={
            "X-Real-IP": REAL_IP,
            "X-Forwarded-For": REAL_IP,
        },
    )
    if response.status_code != 200:
        raise RuntimeError(f"请求网易云接口失败: {response.status_code}")
    try:
        return response.json()
    except Exception:
        return json.loads(response.text or "{}")


async def search(keywords: str, limit: int = 1, type: int = 1, offset: int = 0) -> dict:
    # 搜索接口
    return await request(
        uri="/api/search/get/",
        data={"s": keywords, "limit": limit, "type": type, "offset": offset},
    )


async def song_detail(id: str) -> dict:
    # 歌曲详情
    c = json.dumps([{"id": id}])
    data = {"c": c}
    return await request("/api/v3/song/detail", data)


async def comment_info(id: str, resourceType: int = 4) -> dict:
    # 简略评论信息
    data = {
        "fixliked": True,
        "needupgradedinfo": True,
        "resourceIds": json.dumps([id]),
        "resourceType": resourceType,
    }
    return await request(uri="/api/resource/commentInfo/list", data=data)


def get_artist_names(artists: list[dict[str, Any]]) -> str:
    # 获取歌手名称
    names = []
    for artist in artists:
        if "name" in artist:
            names.append(artist["name"])

    return " / ".join(names) if names else ""


class MusicHelper163(MusicHelper):
    @staticmethod
    async def meta_data(keywords: str) -> MusicMetaData | None:
        try:
            ret0 = await search(keywords)
            songs = list(ret0.get("result", {}).get("songs", []))
            if not songs:
                return None
            song_id = str(songs[0].get("id", "")).strip()
            if not song_id:
                return None

            ret1 = await song_detail(song_id)
            ret2 = await comment_info(song_id)

            song_list = ret1.get("songs", [])
            if not song_list:
                return None
            song: dict[str, Any] = song_list[0]

            comment_list = ret2.get("data", [])
            comment = comment_list[0] if comment_list else {}

            alias_list = list(song.get("tns", [])) + list(song.get("alia", []))
            alias = " / ".join(dict.fromkeys([item for item in alias_list if item]))

            return MusicMetaData(
                type_="163",
                id=song_id,
                name=song.get("name", ""),
                alias=alias,
                duration=int(song.get("dt", 0)),
                album_name=song.get("al", {}).get("name", ""),
                artist_names=get_artist_names(song.get("ar", [])),
                comment_count=int(comment.get("commentCount", 0)),
                share_count=int(comment.get("shareCount", 0)),
                url=f"https://music.163.com/#/song?id={song_id}",
                picUrl=song.get("al", {}).get("picUrl", ""),
            )
        except Exception as e:
            logger.warning(f"网易云点歌数据获取失败: {e}", "music")
            return None
