from pathlib import Path
import random

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from .._config import PixModel, PixResult, base_config

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.6;"
    " rv:2.0.1) Gecko/20100101 Firefox/4.0.1",
    "Referer": "https://www.pixiv.net/",
}


class PixManage:
    @classmethod
    async def get_pix(
        cls,
        tags: tuple[str, ...],
        num: int,
        is_r18: bool,
        ai: bool | None,
        nsfw: tuple[int, ...],
        ratio_tuple: list[float] | None,
    ) -> PixResult[list[PixModel]]:
        """获取图片

        参数:
            tags: tags，包含uid和pid
            num: 数量
            is_r18: 是否r18
            ai: 是否ai
            nsfw: nsfw标签
            ratio_tuple: 图片比例范围

        返回:
            list[PixGallery]: 图片数据列表
        """
        force_nsfw = base_config.get("FORCE_NSFW")
        size = base_config.get("PIX_IMAGE_SIZE")
        api = base_config.get("pix_api") + "/pix/get_pix"
        json_data = {
            "tags": tags,
            "num": num,
            "r18": is_r18,
            "ai": ai,
            "size": size,
            "nsfw_tag": force_nsfw or nsfw or None,
            "ratio": ratio_tuple,
        }
        logger.debug(f"尝试调用pix api: {api}, 参数: {json_data}")
        headers = None
        if token := base_config.get("token"):
            headers = {"Authorization": token}
        res = await AsyncHttpx.post(api, json=json_data, headers=headers)
        res.raise_for_status()
        res_data = res.json()
        res_data["data"] = [PixModel(**item) for item in res_data["data"]]
        return PixResult[list[PixModel]](**res_data)

    @classmethod
    async def get_image(cls, pix: PixModel, is_original: bool = False) -> Path | None:
        """获取图片

        参数:
            pix: PixGallery
            is_original: 是否下载原图

        返回:
            Path | None: 图片路径
        """
        url = pix.url
        nginx_url = Config.get_config("pixiv", "PIXIV_NGINX_URL")
        if "limit_sanity_level" in url or (is_original and nginx_url):
            image_type = url.split(".")[-1]
            if pix.is_multiple:
                url = f"https://{nginx_url}/{pix.pid}-{int(pix.img_p) + 1}.{image_type}"
            else:
                url = f"https://{nginx_url}/{pix.pid}.{image_type}"
        elif small_url := Config.get_config("pixiv", "PIXIV_SMALL_NGINX_URL"):
            if "img-master" in url:
                url = "img-master" + url.split("img-master")[-1]
            elif "img-original" in url:
                url = "img-original" + url.split("img-original")[-1]
            url = f"https://{small_url}/{url}"
        timeout = base_config.get("timeout")
        file = TEMP_PATH / f"pix_{pix.pid}_{random.randint(1, 1000)}.png"
        return (
            file
            if await AsyncHttpx.download_file(
                url, file, headers=headers, timeout=timeout
            )
            else None
        )

    @classmethod
    async def get_pix_result(cls, pix: PixModel) -> tuple[list, PixModel]:
        """构建返回消息

        参数:
            pix: PixGallery

        返回:
            list: 返回消息
        """
        if not (image := await cls.get_image(pix)):
            return [f"获取图片 pid: {pix.pid} 失败..."], pix
        message_list = []
        if base_config.get("SHOW_INFO"):
            message_list.append(
                f"title: {pix.title}\n"
                f"author: {pix.author}\n"
                f"pid: {pix.pid}\n"
                f"uid: {pix.uid}\n",
            )
        message_list.append(image)
        return message_list, pix

    @classmethod
    async def block_pix(cls, pix: PixModel, is_uid: bool) -> str:
        """block pix

        参数:
            pix: pixModel
            is_uid: 是否为uid

        返回:
            str: 返回信息
        """
        if is_uid:
            _id = pix.uid
            kw_type = "UID"
        else:
            _id = pix.pid
            kw_type = "PID"
        api = base_config.get("pix_api") + "/pix/set_pix"
        json_data = {"id": _id, "type": kw_type, "is_block": True}
        logger.debug(f"尝试调用pix api: {api}, 参数: {json_data}")
        headers = None
        if token := base_config.get("token"):
            headers = {"Authorization": token}
        res = await AsyncHttpx.post(api, json=json_data, headers=headers)
        res.raise_for_status()
        return PixResult(**res.json()).info

    @classmethod
    async def set_nsfw(cls, pix: PixModel, nsfw: int) -> str:
        """set_nsfw

        参数:
            pix: pixModel
            nsfw: nsfw

        返回:
            str: 返回信息
        """
        api = base_config.get("pix_api") + "/pix/set_pix"
        json_data = {"id": pix.pid, "type": "PID", "nsfw_tag": nsfw}
        logger.debug(f"尝试调用pix api: {api}, 参数: {json_data}")
        headers = None
        if token := base_config.get("token"):
            headers = {"Authorization": token}
        res = await AsyncHttpx.post(api, json=json_data, headers=headers)
        res.raise_for_status()
        return PixResult(**res.json()).info
