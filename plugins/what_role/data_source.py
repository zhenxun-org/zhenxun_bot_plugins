import random
from pathlib import Path

from strenum import StrEnum
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils._build_image import BuildImage
from zhenxun.utils.http_utils import AsyncHttpx

from .build_image import ConstructImage
from .config import Response


class SearchType(StrEnum):
    """搜索类型"""

    ANIME_MODEL_LOVELIVE = "anime_model_lovelive"
    """高级动画识别模型①"""
    PRE_STABLE = "pre_stable"
    """高级动画识别模型②"""
    ANIME = "anime"
    """普通动画识别模型"""
    FULL_GAME_MODEL_KIRA = "full_game_model_kira "
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
    url: str = "https://api.animetrace.com/v1/search"

    @classmethod
    def int2type(cls, n: int) -> str:
        return list(SearchType)[n].value

    @classmethod
    async def search(
        cls, image_data: bytes, search_type: int
    ) -> tuple[str | list[str], BuildImage, Path | None]:
        rand = random.randint(1, 100000)
        file = TEMP_PATH / f"what_anime_{rand}_test.png"
        image = BuildImage.open(image_data)
        await image.save(file)
        search_type_enum = cls.int2type(search_type - 1)
        json_data = {
            "model": search_type_enum,
            "ai_detect": 1,
            "is_multi": 1,
            "base64": image.pic2bs4()[9:],
        }
        response = await AsyncHttpx.post(cls.url, json=json_data)
        json_data = response.json()
        logger.debug(f"角色识别获取数据: {json_data}", "角色识别")
        if er := code2error.get(json_data.get("code")):
            return er, image, file
        data = Response(**json_data)
        if not data.data:
            return "未找到角色信息...", image, file
        message_list = []
        width, height = image.size
        info_list = []
        for item in data.data:
            box: tuple[int, int, int, int] = (
                int(item.box[0] * width),
                int(item.box[1] * height),
                int(item.box[2] * width),
                int(item.box[3] * height),
            )
            copy_image = image.copy()
            crop: BuildImage = await copy_image.crop(box)
            # circle_crop = await crop.circle()
            chars = item.character[:10] if len(item.character) > 10 else item.character
            chars_list = [
                f"角色名称: {char.work}\n出处: {char.character}"
                "\n---------------------\n"
                for char in chars
            ]
            info: list[str] = [
                f"角色名称: {char.work}\n出处: {char.character}\n" for char in chars
            ]
            chars_list.insert(0, crop)  # type: ignore
            info.insert(0, crop)  # type: ignore
            message_list.append(chars_list)
            info_list.append(info)
        c = ConstructImage(search_type_enum, image, info_list)
        return message_list, await c.to_image(), file
