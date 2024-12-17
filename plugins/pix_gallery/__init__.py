from pathlib import Path

import nonebot
from nonebot.plugin import PluginMetadata

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.utils.enum import PluginType

Config.set_name("pix", "PIX图库")

__plugin_meta__ = PluginMetadata(
    name="Pix",
    description="",
    usage="",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        plugin_type=PluginType.PARENT,
        configs=[
            RegisterConfig(
                module="hibiapi",
                key="HIBIAPI",
                value="https://api.obfs.dev",
                help="如果没有自建或其他hibiapi请不要修改",
                default_value="https://api.obfs.dev",
            ),
            RegisterConfig(
                module="pixiv",
                key="PIXIV_NGINX_URL",
                value="pximg.re",
                help="PIXPixiv反向代理",
            ),
            RegisterConfig(
                module="pix",
                key="PIX_IMAGE_SIZE",
                value="master",
                help="PIX图库下载的画质 可能的值：original：原图，"
                "master：缩略图（加快发送速度）",
                default_value="master",
            ),
            RegisterConfig(
                module="pix",
                key="SEARCH_HIBIAPI_BOOKMARKS",
                value=5000,
                help="最低收藏，PIX使用HIBIAPI搜索图片时达到最低收藏才会添加至图库",
                default_value=5000,
                type=int,
            ),
            RegisterConfig(
                module="pix",
                key="WITHDRAW_PIX_MESSAGE",
                value=(0, 1),
                help="自动撤回，参1：延迟撤回色图时间(秒)"
                "，0 为关闭 | 参2：监控聊天类型，0(私聊) 1(群聊) 2(群聊+私聊)",
                default_value=(0, 1),
                type=tuple[int, int],
            ),
            RegisterConfig(
                module="pix",
                key="PIX_OMEGA_PIXIV_RATIO",
                value=(10, 0),
                help="PIX图库 与 额外图库OmegaPixivIllusts 混合搜索的比例 "
                "参1：PIX图库 参2：OmegaPixivIllusts扩展图库（没有此图库请设置为0）",
                default_value=(10, 0),
                type=tuple[int, int],
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
                key="ALLOW_GROUP_SETU",
                value=False,
                help="允许非超级用户使用-s参数",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="pix",
                key="ALLOW_GROUP_R18",
                value=False,
                help="允许非超级用户使用-r参数",
                default_value=False,
                type=bool,
            ),
        ],
    ).dict(),
)


nonebot.load_plugins(str(Path(__file__).parent.resolve()))
