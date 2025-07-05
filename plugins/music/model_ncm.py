import json

from zhenxun.utils.http_utils import AsyncHttpx

from .model import *


@staticmethod
async def request(uri: str, data) -> dict:
    domain = "https://music.163.com"
    url = domain + uri
    realIp = "58.100.87.193"
    response = await AsyncHttpx.post(
        url=url,
        data=data,
        headers={
            "X-Real-IP": realIp,
            "X-Forwarded-For": realIp,
        },
    )
    data = json.loads(response.text)
    return data


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


def get_artist_names(artists):
    # 获取歌手名称
    names = []
    for artist in artists:
        if "name" in artist:
            names.append(artist["name"])

    return " / ".join(names) if names else ""


class MusicHelper163(MusicHelper):
    @staticmethod
    async def meta_data(keywords: str) -> MusicMetaData | None:
        ret0 = await search(keywords)
        songs = list(ret0["result"].get("songs", []))
        if len(songs) < 1:
            return None
        id: str = str(songs[0]["id"])

        ret1 = await song_detail(id)
        ret2 = await comment_info(id)

        song: dict = {**ret1["songs"][0], **ret2["data"][0]}

        data = MusicMetaData(
            type_="163",
            id=id,
            name=song["name"],
            alias=" / ".join(list(song.get("tns", [])) + list(song.get("alia", []))),
            duration=song["dt"],
            album_name=song.get("al", {}).get("name", ""),
            artist_names=get_artist_names(song["ar"]),
            comment_count=song["commentCount"],
            share_count=song["shareCount"],
            url=f"https://music.163.com/#/song?id={id}",
            picUrl=song.get("al", {}).get("picUrl", ""),
        )

        return data
