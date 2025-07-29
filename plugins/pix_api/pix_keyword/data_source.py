from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from .._config import PixResult, base_config
from .._enum import KwType


class KeywordManage:
    @classmethod
    async def add_content(cls, content: tuple[str, ...], kw_type: KwType) -> str:
        """添加pix

        参数:
            content: 关键词
            kw_type: 类型

        返回:
            str: 返回信息
        """
        api = base_config.get("pix_api") + "/pix/pix_add"
        json_data = {"content": list(set(content)), "add_type": kw_type}
        logger.debug(f"尝试调用pix api: {api}, 参数: {json_data}")
        headers = None
        if token := base_config.get("token"):
            headers = {"Authorization": token}
        res = await AsyncHttpx.post(
            api, json=json_data, headers=headers, timeout=base_config.get("timeout")
        )
        res.raise_for_status()
        return PixResult(**res.json()).info
