from nonebot_plugin_alconna import Image
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx


async def get_anime(anime: str) -> str | list:
    anime = anime.replace("&", "%26")
    url = f"https://api.trace.moe/search?anilistInfo&url={anime}"
    logger.debug(f"Now starting get the {url}")
    try:
        anime_json: dict = (await AsyncHttpx.get(url)).json()
        if anime_json == "Error reading imagenull":
            return "图像源错误，注意必须是静态图片哦"
        if anime_json["error"]:
            return f"访问错误 error：{anime_json['error']}"
        return [
            [
                f"名称: {anime['filename'].rsplit('.')[0]}\n"
                f"集数: {anime['episode']}\n"
                f"相似度: {float(anime['similarity'] * 100):.2f}%\n"
                f"图片:",
                Image(url=anime["image"]),
                "----------\n",
            ]
            for anime in anime_json["result"][:5]
        ]
    except Exception as e:
        logger.error("识番发生错误", e=e)
        return "发生了奇怪的错误，那就没办法了，再试一次？"
