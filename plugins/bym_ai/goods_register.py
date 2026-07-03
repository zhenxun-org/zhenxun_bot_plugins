import nonebot
from nonebot.drivers import Driver

from zhenxun.configs.config import BotConfig
from zhenxun.services.ai.context.memory import memory_manager
from zhenxun.utils.decorator.shop import shop_register

from .data_source import get_memory_config

driver: Driver = nonebot.get_driver()


@shop_register(
    name="失忆卡",
    price=200,
    des=f"当你养成失败或{BotConfig.self_nickname}变得奇怪时，你需要这个道具。",
    icon="reload_ai_card.png",
)
async def _(user_id: str):
    from nonebot.matcher import current_bot, current_event

    from zhenxun.utils.platform import PlatformUtils

    try:
        bot = current_bot.get()
        event = current_event.get()
        platform = PlatformUtils.get_platform(bot)
        self_id = str(bot.self_id)
        group_id = getattr(event, "group_id", None)
    except Exception:
        platform = "qq"
        self_id = "default"
        group_id = None

    c = (
        memory_manager.cleaner()
        .config(get_memory_config())
        .platform(platform)
        .bot(self_id)
        .user(user_id)
    )
    if group_id:
        c.group(str(group_id))

    await c.clear_short_term()

    try:
        from .data_source import group_buffer_manager

        if group_id:
            k = f"{platform}_{self_id}_{group_id}"
            group_buffer_manager.clear_group(k)
        else:
            k = f"{platform}_{self_id}_private_{user_id}"
            group_buffer_manager.clear_group(k)
    except Exception:
        pass
    return f"{BotConfig.self_nickname}忘记了你之前说过的话，仿佛一切可以重新开始..."
