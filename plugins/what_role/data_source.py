import random
from pathlib import Path

from strenum import StrEnum

from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.configs.path_config import TEMP_PATH

from .config import Response


class SearchType(StrEnum):
    """搜索类型"""

    ANIME_MODEL_LOVELIVE = "anime_model_lovelive"
    """高级动画识别模型①"""
    PRE_STABLE = "pre_stable"
    """高级动画识别模型②"""
    ANIME = "anime"
    """普通动画识别模型"""
    GAME = "game"
    """普通Gal识别模型"""
    GAME_MODEL_KIRAKIRA = "game_model_kirakira"
    """高级Gal识别模型"""


code2error = {
    17701: "图片大小过大",
    17702: "服务器繁忙，请重试",
    17703: "请求参数不正确",
    17704: "API维护中",
    17705: "图片格式不支持",
    17706: "识别无法完成（内部错误，请重试）",
    17707: "内部错误",
    17708: "图片中的人物数量超过限制",
    17709: "无法加载统计数量",
    17710: "图片验证码错误",
    17711: "无法完成识别前准备工作（请重试）",
    17712: "需要图片名称",
    17799: "不明错误发生",
}


class AnimeManage:
    url: str = "https://aiapiv2.animedb.cn/ai/api/detect"

    @classmethod
    def int2type(cls, n: int) -> str:
        return list(SearchType)[n].value

    @classmethod
    async def search(
        cls, img_url: str, search_type: int
    ) -> tuple[str | list[str], Path | None]:
        file = await cls.download_image(img_url)
        if not file:
            return "下载图片失败...", None
        # img = BuildImage.open(file)
        json_data = {
            "model": cls.int2type(search_type),
            "ai_detect": 1,
            "is_multi": 1,
        }
        file_data = {"image": file.open("rb")}
        response = await AsyncHttpx.post(cls.url, params=json_data, files=file_data)
        data = Response(**response.json())
        if er := code2error.get(data.new_code or data.code):
            return er, file
        if not data.data:
            return "未找到角色信息...", file
        message_list = []
        for item in data.data:
            item.box = [int(i) for i in item.box]
            chars = item.char[:5] if len(item.char) > 5 else item.char
            chars_list = [
                f"角色名称: {char.name}\n出处: {char.cartoonname}\n相似度: {char.acc}"
                "\n---------------------\n"
                for char in chars
            ]
            message_list.append(chars_list)
        return message_list, file

    @classmethod
    async def download_image(cls, img_url: str) -> Path | None:
        rand = random.randint(1, 100000)
        file = TEMP_PATH / f"what_anime_{rand}_test.png"
        return file if await AsyncHttpx.download_file(img_url, file) else None
