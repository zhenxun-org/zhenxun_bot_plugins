import contextlib

import nonebot

from zhenxun.configs.config import Config
from zhenxun.configs.utils import NoSuchConfig
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from ._config import base_config

driver = nonebot.get_driver()


@driver.on_startup
async def _():
    token = None
    with contextlib.suppress(NoSuchConfig):
        token = Config.get_config("pix", "token")
    if not token and (base_api := base_config.get("pix_api")):
        base_api += "/pix/token"
        res = await AsyncHttpx.post(base_api)
        if res.status_code != 200:
            logger.warning(f"鑾峰彇PIX token澶辫触, code: {res.status_code}")
            return
        res_data = res.json()
        access_token = res_data["access_token"]
        Config.set_config(
            "pix",
            "token",
            f"{res_data['token_type']} {res_data['access_token']}",
            True,
        )
        mask_token = f"{access_token[:6]}***" if len(access_token) > 6 else "***"
        logger.info(f"成功生成PIX token: {mask_token}")
