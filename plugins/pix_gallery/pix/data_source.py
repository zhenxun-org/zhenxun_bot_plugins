from pathlib import Path
import random

from tortoise.expressions import Q

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.utils.common_utils import SqlUtils
from zhenxun.utils.http_utils import AsyncHttpx

from ..config import base_config
from ..models.pix_gallery import PixGallery

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.6;"
    " rv:2.0.1) Gecko/20100101 Firefox/4.0.1",
    "Referer": "https://www.pixiv.net/",
}


class PixManage:
    @classmethod
    async def get_pix(
        cls, tags: tuple[str, ...], num: int, is_r18: bool, ai: bool | None
    ) -> list[PixGallery]:
        """获取图片

        参数:
            tags: tags，包含uid和pid
            num: 数量

        返回:
            list[PixGallery]: 图片数据列表
        """
        query = PixGallery
        if is_r18:
            query = query.filter(is_r18=True)
        if ai is not None:
            query = query.filter(ai=ai)
        for tag in tags:
            query = query.filter(
                Q(tags__contains=tag) | Q(author__contains=tag) | Q(pid__contains=tag)
            )
        return await PixGallery.raw(SqlUtils.random(query.annotate(), num))  # type: ignore

    @classmethod
    async def get_image(cls, pix: PixGallery, is_original: bool = False) -> Path | None:
        """获取图片

        参数:
            pix: PixGallery
            is_original: 是否下载原图

        返回:
            Path | None: 图片路径
        """
        image_size = base_config.get("PIX_IMAGE_SIZE")
        if image_size in pix.image_urls:
            url = pix.image_urls[image_size]
        else:
            key = next(iter(pix.image_urls.keys()))
            url = pix.image_urls[key]
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
    async def get_pix_result(cls, pix: PixGallery) -> tuple[list, PixGallery]:
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
