import nonebot
from nonebot.plugin import PluginMetadata

from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.manager.priority_manager import PriorityLifecycle

from ._model import WordBank
from .word_index import WordBankIndex

__plugin_meta__ = PluginMetadata(
    name="词库问答",
    description="",
    usage="",
    extra=PluginExtraData(
        author="HibiKier & yajiwa",
        version="0.7",
        plugin_type=PluginType.PARENT,
        configs=[
            RegisterConfig(
                key="WORD_BANK_LEVEL",
                value=5,
                default_value=5,
                type=int,
                help="设置增删词库的权限等级",
            )
        ],
    ).to_dict(),
)

for plugin_name in ("read_word_bank", "message_handle", "word_handle"):
    nonebot.load_plugin(f"{__name__}.{plugin_name}")


@PriorityLifecycle.on_startup(priority=2)
async def _ensure_word_bank_indexes() -> None:
    try:
        await WordBank.ensure_query_indexes()
        await WordBankIndex.preload_global(WordBank)
    except Exception as e:
        logger.warning("词库索引初始化失败", "词库问答", e=e)
