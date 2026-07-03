from arclet.alconna import MultiVar
from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Option,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg import At
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_waiter import prompt

from zhenxun.builtin_plugins.superuser.plugin_config_manager import pconf_cmd
from zhenxun.services.ai.context.memory import memory_manager
from zhenxun.services.group_settings_service import group_settings_service
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .config import PERSONAS_CACHE, load_prompts, save_prompts
from .data_source import base_config
from . import build_persona_list

bym_cmd = on_alconna(
    Alconna(
        "bym",
        Subcommand(
            "clear",
            Args["targets?", MultiVar(At)],
            Option("--group", alias=["-g"], help_text="清除当前群所有记忆"),
            Option("--all", alias=["-a"], help_text="清除整个插件所有记忆"),
        ),
        Subcommand(
            "prompt",
            Subcommand("list", alias=["查看人设"]),
            Subcommand("reload", alias=["重载人设"]),
            Subcommand("add", Args["persona_name", str], alias=["添加人设"]),
            Subcommand("del", Args["persona_name", str], alias=["删除人设"]),
            Subcommand("edit", Args["persona_name", str], alias=["修改人设"]),
        ),
        Subcommand(
            "show",
            Option("-g|--group", Args["group_id", str], help_text="指定群组"),
            alias=["查看配置"],
        ),
    ),
    permission=SUPERUSER,
    block=True,
    priority=1,
)


@bym_cmd.assign("clear")
async def _(bot: Bot, arp: Arparma, session: Uninfo):
    is_all = arp.exist("clear.all")
    is_group = arp.exist("clear.group")
    targets = arp.query("clear.targets", ())

    platform = PlatformUtils.get_platform(bot)
    group_id = session.group.id if session.group else None

    from .data_source import get_memory_config, group_buffer_manager
    base_cleaner = memory_manager.cleaner().config(get_memory_config())
    scoped_cleaner = memory_manager.cleaner().config(get_memory_config()).platform(platform).bot(str(bot.self_id))
    if group_id:
        scoped_cleaner.group(str(group_id))

    if is_all:
        confirm_msg = (
            "⚠️ 即将永久删除 [bym_ai] 插件下的**所有**会话记忆！\n"
            "确认删除请在 30 秒内回复「Y」或「是」，取消请回复其他内容。"
        )
        resp = await prompt(confirm_msg, timeout=30)
        if resp is None:
            await bym_cmd.finish("⏳ 等待超时，已自动取消清理操作。")

        user_input = resp.extract_plain_text().strip().lower()
        if user_input not in {"y", "yes", "是", "1", "确认", "ok"}:
            await bym_cmd.finish("🛑 已取消清理操作。")

        await base_cleaner.clear_short_term()
        group_buffer_manager.clear_all()
        await MessageUtils.build_message(
            "✅ 已成功清理 [bym_ai] 插件的所有记忆！"
        ).finish(reply_to=True)

    if is_group:
        if not group_id:
            await bym_cmd.finish("❌ 请在群聊中使用 --group 选项！")

        await scoped_cleaner.clear_short_term()
        group_buffer_manager.clear_group(f"{platform}_{group_id}")
        await MessageUtils.build_message("✅ 已成功清理当前群组的所有记忆！").finish(
            reply_to=True
        )

    if targets:
        for target in targets:
            target_id = str(target.target)
            scoped_cleaner.user(target_id)
            if not group_id:
                group_buffer_manager.clear_group(f"{platform}_private_{target_id}")
            await scoped_cleaner.clear_all()
        if group_id:
            group_buffer_manager.clear_group(f"{platform}_{group_id}")
        await MessageUtils.build_message(
            f"✅ 已成功清理 {len(targets)} 名指定用户的记忆！"
        ).finish(reply_to=True)

    else:
        scoped_cleaner.user(session.user.id)
        if group_id:
            group_buffer_manager.clear_group(f"{platform}_{group_id}")
        else:
            group_buffer_manager.clear_group(f"{platform}_private_{session.user.id}")
        await scoped_cleaner.clear_short_term()
        await MessageUtils.build_message("✅ 已成功清理你自己的记忆！").finish(
            reply_to=True
        )


@bym_cmd.assign("prompt.list")
async def _():
    img = await build_persona_list(PERSONAS_CACHE)
    await MessageUtils.build_message(img).finish(reply_to=True)


@bym_cmd.assign("prompt.reload")
async def _():
    try:
        load_prompts()
        await MessageUtils.build_message(
            f"✅ 重载人设成功，当前共有 {len(PERSONAS_CACHE)} 个人设"
        ).finish(reply_to=True)
    except Exception as e:
        logger.error("重载人设失败", "BYM_AI", e=e)
        await MessageUtils.build_message("重载人设失败...").finish(reply_to=True)


@bym_cmd.assign("prompt.add")
async def _(arp: Arparma):
    persona_name = arp.query("prompt.add.persona_name")
    if not isinstance(persona_name, str):
        await bym_cmd.finish("❌ 人设名称非法！")
    if persona_name in PERSONAS_CACHE:
        await bym_cmd.finish(
            f"❌ 人设 [{persona_name}] 已存在！如需修改请使用 edit 命令。"
        )

    cancel_words = {"取消", "0", "退出"}
    resp = await prompt(
        f"请发送新人设 [{persona_name}] 的提示词内容（支持原样多行结构）。\n回复「取消」或「0」终止。",
        timeout=120,
    )
    if resp is None:
        await bym_cmd.finish("⏳ 等待超时，已自动取消添加。")

    text = resp.extract_plain_text().strip()
    if text.lower() in cancel_words:
        await bym_cmd.finish("🛑 已取消添加操作。")

    PERSONAS_CACHE[persona_name] = text
    save_prompts()
    await MessageUtils.build_message(
        f"✅ 成功添加人设 [{persona_name}] 并已写入硬盘！"
    ).finish(reply_to=True)


@bym_cmd.assign("prompt.edit")
async def _(arp: Arparma):
    persona_name = arp.query("prompt.edit.persona_name")
    if not isinstance(persona_name, str):
        await bym_cmd.finish("❌ 人设名称非法！")
    if persona_name not in PERSONAS_CACHE:
        await bym_cmd.finish(
            f"❌ 人设 [{persona_name}] 不存在！请先使用 add 命令添加。"
        )

    cancel_words = {"取消", "0", "退出"}
    resp = await prompt(
        f"请发送人设 [{persona_name}] 的新提示词内容（将覆盖原内容，支持多行）。\n回复「取消」或「0」终止。",
        timeout=120,
    )
    if resp is None:
        await bym_cmd.finish("⏳ 等待超时，已自动取消修改。")

    text = resp.extract_plain_text().strip()
    if text.lower() in cancel_words:
        await bym_cmd.finish("🛑 已取消修改操作。")

    PERSONAS_CACHE[persona_name] = text
    save_prompts()
    await MessageUtils.build_message(
        f"✅ 成功修改人设 [{persona_name}] 并已写入硬盘！"
    ).finish(reply_to=True)


@bym_cmd.assign("prompt.del")
async def _(arp: Arparma):
    persona_name = arp.query("prompt.del.persona_name")
    if not isinstance(persona_name, str):
        await bym_cmd.finish("❌ 人设名称非法！")
    if persona_name not in PERSONAS_CACHE:
        await bym_cmd.finish(f"❌ 人设 [{persona_name}] 不存在！")

    default_persona = base_config.get("DEFAULT_PERSONA", "真寻")
    if persona_name == default_persona:
        await bym_cmd.finish(
            f"❌ [{persona_name}] 是当前的全局默认人设，为了防止不可预知的异常，禁止删除！请先在配置中更改 DEFAULT_PERSONA。"
        )

    resp = await prompt(
        f"⚠️ 确认要永久删除人设 [{persona_name}] 吗？\n确认请回复「Y」或「是」，回复其他内容取消。",
        timeout=30,
    )
    if resp is None:
        await bym_cmd.finish("⏳ 等待超时，已自动取消。")

    text = resp.extract_plain_text().strip().lower()
    if text not in {"y", "yes", "是", "1", "ok", "确认"}:
        await bym_cmd.finish("🛑 已取消删除操作。")

    del PERSONAS_CACHE[persona_name]
    save_prompts()
    await MessageUtils.build_message(
        f"✅ 成功删除人设 [{persona_name}]！正在使用此人设的群组将会自动无痕回退到默认人设。"
    ).finish(reply_to=True)


@bym_cmd.assign("show")
async def _(arp: Arparma, session: Uninfo):
    group_id = arp.query("show.group.group_id") or (
        session.group.id if session.group else None
    )
    if not group_id:
        await bym_cmd.finish("❌ 私聊环境下请使用 -g 显式指定群组号。")

    default_persona = base_config.get("DEFAULT_PERSONA", "真寻")
    current_persona = await group_settings_service.get(
        str(group_id), "bym_ai", "current_persona", default_persona
    )

    actual_persona = current_persona
    fallback_msg = ""
    if current_persona not in PERSONAS_CACHE:
        if default_persona in PERSONAS_CACHE:
            actual_persona = default_persona
            fallback_msg = f"\n⚠️ 文件中未找到 [{current_persona}]，已回退为默认: [{default_persona}]"
        else:
            actual_persona = "最终保底人设 (AI助手)"
            fallback_msg = "\n⚠️ 文件中未找到任何预设，已回退为极简保底人设"

    chat_enabled = await group_settings_service.get(
        str(group_id), "bym_ai", "random_reply_enable", False
    )
    chat_rate = await group_settings_service.get(
        str(group_id), "bym_ai", "random_reply_rate", 0.01
    )
    context_mode = await group_settings_service.get(
        str(group_id), "bym_ai", "context_mode", base_config.get("CONTEXT_MODE", "user")
    )

    msg = (
        f"📊 群组 {group_id} 的 BYM_AI 配置状态：\n"
        f"🔸 设定人设: [{current_persona}]\n"
        f"🔸 实际生效: [{actual_persona}]{fallback_msg}\n"
        f"🔸 随机回复: {'开启' if chat_enabled else '关闭'}\n"
        f"🔸 触发概率: {chat_rate}\n"
        f"🔸 记忆模式: {'群组共享(group)' if context_mode == 'group' else '用户隔离(user)'}"
    )
    await MessageUtils.build_message(msg).finish(reply_to=True)


for cmd_alias, key_name in [
    (r"(?:prompt|人设)", "current_persona"),
    (r"(?:rate|概率)", "random_reply_rate"),
    (r"(?:reply|回复)", "random_reply_enable"),
    (r"(?:mode|模式)", "context_mode"),
]:
    pconf_cmd.shortcut(
        rf"bym设置\s+{cmd_alias}\s+(?P<val>\S+)\s*(?P<targets>.*)",
        command="pconf",
        arguments=["set", f"{key_name}={{val}}", "-p", "bym_ai", "{targets}"],
        prefix=True,
    )
