from pathlib import Path

import nonebot
from nonebot.plugin import PluginMetadata

from zhenxun.configs.config import Config
from zhenxun.utils.enum import PluginType
from zhenxun.configs.utils import RegisterConfig, PluginExtraData

Config.set_name("pix", "PIX图库")

__plugin_meta__ = PluginMetadata(
    name="Pix",
    description="",
    usage="",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.PARENT,
        configs=[
            RegisterConfig(
                module="pix",
                key="pix_api",
                value="http://pix.zhenxun.org",
                help="符合pix-api的Api",
                default_value=None,
            ),
            RegisterConfig(
                module="pixiv",
                key="PIXIV_NGINX_URL",
                value="i.pximg.cf",
                help="PIXPixiv反向代理",
            ),
            RegisterConfig(
                module="pix",
                key="PIX_IMAGE_SIZE",
                value="large",
                help="PIX图库下载的画质,可能的值:large,medium,original,square_medium",
                default_value="large",
            ),
            RegisterConfig(
                module="pix",
                key="TIMEOUT",
                value=10,
                help="下载图片超时限制（秒）",
                default_value=10,
                type=int,
            ),
            RegisterConfig(
                module="pix",
                key="SHOW_INFO",
                value=True,
                help="是否显示图片的基本信息，如PID等",
                default_value=True,
                type=bool,
            ),
        ],
    ).dict(),
)


nonebot.load_plugins(str(Path(__file__).parent.resolve()))
