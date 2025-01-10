from pathlib import Path

import nonebot
from nonebot.plugin import PluginMetadata

from zhenxun.configs.config import Config
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.utils.enum import PluginType

Config.set_name("pix", "PIX图库")

__plugin_meta__ = PluginMetadata(
    name="Pix",
    description="",
    usage="",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.3",
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
                key="PIXIV_SMALL_NGINX_URL",
                value="i.suimoe.com",
                help="PIXPixiv反向代理，缩略图",
            ),
            RegisterConfig(
                module="pixiv",
                key="PIXIV_NGINX_URL",
                value="pixiv.re",
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
            RegisterConfig(
                module="pix",
                key="MAX_ONCE_NUM2FORWARD",
                value=None,
                help="单次发送的图片数量达到指定值时转发为合并消息",
                default_value=None,
                type=int,
            ),
            RegisterConfig(
                module="pix",
                key="ALLOW_GROUP_R18",
                value=False,
                help="允许非超级用户使用-r参数",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="pix",
                key="TOKEN",
                value="",
                help="获取调用token",
                default_value="",
            ),
        ],
    ).to_dict(),
)


nonebot.load_plugins(str(Path(__file__).parent.resolve()))
