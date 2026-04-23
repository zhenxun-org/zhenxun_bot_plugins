from pathlib import Path

import nonebot
from nonebot.plugin import PluginMetadata

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.utils.enum import PluginType

Config.set_name("pix", "PIX图库")

__plugin_meta__ = PluginMetadata(
    name="Pix",
    description="PIX 图库功能聚合插件（检索、收藏、统计、管理）",
    usage="请使用子模块命令：pix、pix图库、pix收藏、pix排行、pixtag 等",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.3",
        plugin_type=PluginType.PARENT,
        configs=[
            RegisterConfig(
                module="pix",
                key="pix_api",
                value="http://pix.zhenxun.org",
                help="pix-api 服务地址",
                default_value=None,
            ),
            RegisterConfig(
                module="pixiv",
                key="PIXIV_SMALL_NGINX_URL",
                value="i.suimoe.com",
                help="Pixiv 缩略图反代域名",
            ),
            RegisterConfig(
                module="pixiv",
                key="PIXIV_NGINX_URL",
                value="pixiv.re",
                help="Pixiv 原图反代域名",
            ),
            RegisterConfig(
                module="pix",
                key="PIX_IMAGE_SIZE",
                value="large",
                help="图片尺寸，可选：large/medium/original/square_medium",
                default_value="large",
            ),
            RegisterConfig(
                module="pix",
                key="TIMEOUT",
                value=10,
                help="下载图片超时（秒）",
                default_value=10,
                type=int,
            ),
            RegisterConfig(
                module="pix",
                key="SHOW_INFO",
                value=True,
                help="发图时是否显示图片基本信息（如 PID）",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="pix",
                key="MAX_ONCE_NUM2FORWARD",
                value=None,
                help="单次发送图片数量达到该值时转为合并转发",
                default_value=None,
                type=int,
            ),
            RegisterConfig(
                module="pix",
                key="ALLOW_GROUP_R18",
                value=False,
                help="是否允许群内非超管使用 r 参数",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="pix",
                key="TOKEN",
                value="",
                help="pix-api 调用 token",
                default_value="",
            ),
            RegisterConfig(
                module="pix",
                key="FORCE_NSFW",
                value=None,
                help="强制 NSFW 等级（0/1/2），例如 [0, 1]",
                default_value=None,
                type=list[int],
            ),
        ],
    ).to_dict(),
)

nonebot.load_plugins(str(Path(__file__).parent.resolve()))
