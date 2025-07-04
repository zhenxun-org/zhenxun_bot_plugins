from zhenxun.services.log import logger
from zhenxun.utils._build_image import BuildImage
from zhenxun.utils._image_template import ImageTemplate
from zhenxun.utils.http_utils import AsyncHttpx

from .._config import base_config
from .config import ImageCount


class InfoManage:
    @classmethod
    async def get_pix_gallery(cls, tags: tuple[str, ...]) -> BuildImage:
        """查看pix图库

        参数:
            tags: tags列表

        返回:
            BuildImage: 图片
        """
        api = base_config.get("pix_api") + "/pix/pix_gallery_count"
        json_data = {"tags": tags}
        logger.debug(f"尝试调用pix api: {api}, 参数: {json_data}")
        headers = None
        if token := base_config.get("token"):
            headers = {"Authorization": token}
        res = await AsyncHttpx.post(
            api, json=json_data, headers=headers, timeout=base_config.get("timeout")
        )
        res.raise_for_status()
        data = ImageCount(**res.json()["data"])
        tip = ",".join(tags) if tags else ""
        return await ImageTemplate.table_page(
            "PIX图库",
            tip,
            ["类型", "数量"],
            [
                ["总数", data.count],
                ["普通", data.normal],
                ["色图", data.setu],
                ["R18", data.r18],
                ["AI", data.ai],
            ],
        )
