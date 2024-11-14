from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from .._config import PixModel, PixResult, base_config


class PixManage:
    @classmethod
    async def block_pix(
        cls, pix: PixModel, level: int, is_uid: bool, is_all: bool
    ) -> str:
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
            _id = f"{pix.pid}-{'all' if is_all else pix.img_p}"
            kw_type = "PID"
        api = base_config.get("pix_api") + "/pix/set_pix"
        json_data = {"id": _id, "type": kw_type, "block_level": level}
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
        json_data = {"id": f"{pix.pid}-{pix.img_p}", "type": "PID", "nsfw_tag": nsfw}
        logger.debug(f"尝试调用pix api: {api}, 参数: {json_data}")
        headers = None
        if token := base_config.get("token"):
            headers = {"Authorization": token}
        res = await AsyncHttpx.post(api, json=json_data, headers=headers)
        res.raise_for_status()
        return PixResult(**res.json()).info
