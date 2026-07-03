import random
import time

from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage, Voice
from nonebot_plugin_alconna.uniseg import Image
from nonebot_plugin_uninfo import Uninfo
from pydantic import TypeAdapter

from zhenxun import ui
from zhenxun.configs.utils import (
    PluginExtraData,
    RegisterConfig,
)
from zhenxun.services.ai.core.exceptions import ControlFlowExit, LLMException
from zhenxun.services.ai.core.messages import LLMMessage
from zhenxun.services.ai.flow.agent.models import AgentConfig
from zhenxun.services.ai.llm import create_speech
from zhenxun.services.ai.run import NoneBotDeps, RunContext
from zhenxun.services.group_settings_service import group_settings_service
from zhenxun.services.log import logger
from zhenxun.ui.models import TextCell
from zhenxun.utils.depends import CheckConfig, UserName
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .data_source import base_config, bym_agent, group_buffer_manager
from .goods_register import driver as goods_driver  # noqa: F401
from .models import BymGroupConfig, GroupModeMemoryConfig

__plugin_meta__ = PluginMetadata(
    name="BYM_AI",
    description="基于大语言模型的 AI 伪人聊天与人设管理插件，支持长期记忆总结、多轮对话与人设切换。",
    usage="""AI 聊天插件，支持以下功能：
1. 自动回复：在群聊中被 @ 或以设定概率随机回复，支持多轮对话与记忆。
2. 人设切换：使用 `bym设置 人设 <人设> [-g <群号>/--all]` 切换不同群组的 AI 人设。
3. 记忆管理：管理员可通过 bym clear 清理或重置对话记忆。
""",
    extra=PluginExtraData(
        author="Chtholly & HibiKier",
        version="1.0",
        superuser_help="""### 记忆管理
- `bym clear [@user...] [-g] [-a]`：清理记忆（指定用户/当前群/整个插件）

### 状态与配置查询
- `bym show [-g <群号>]` / `查看配置`：查看指定群组生效的人设与状态

### 属性配置快捷词
- `bym设置 prompt/人设 <人设名> [-g 群号/--all]`：为指定群组设置 AI 人设
- `bym设置 rate/概率 <0.0-1.0> [-g 群号/--all]`：修改拟人触发概率
- `bym设置 reply/回复 <on/off> [-g 群号/--all]`：开启或关闭随机插话
- `bym设置 mode/模式 <user/group> [-g 群号/--all]`：设置当前群的独立/共享记忆模式

### 人设管理
- `bym prompt list` / `查看人设`：查看所有可用人设
- `bym prompt reload` / `重载人设`：重新从本地读取人设文件
- `bym prompt add <人设>` / `添加人设`：交互式添加新的人设
- `bym prompt del <人设>` / `删除人设`：删除指定人设
- `bym prompt edit <人设>` / `修改人设`：交互式修改已有的人设
""",
        ignore_prompt=True,
        group_config_model=BymGroupConfig,
        configs=[
            RegisterConfig(
                key="BYM_AI_CHAT_MODEL",
                value="DeepSeek/deepseek-v4-flash",
                help="ai聊天接口模型，具体参考 AI 模块",
            ),
            RegisterConfig(
                key="RANDOM_REPLY",
                value={"enable": False, "rate": 0.01},
                help="群组内随机拟人回复配置。enable: 是否开启，rate: 触发概率 (0.0 - 1.0)",
                default_value={"enable": False, "rate": 0.01},
                type=dict,
            ),
            RegisterConfig(
                key="CONTEXT_MODE",
                value="user",
                help="上下文记忆模式。'user': 单独用户隔离的会话存储 (默认)；'group': 群聊公共上下文模式 ",
                default_value="user",
                type=str,
            ),
            RegisterConfig(
                key="DEFAULT_PERSONA",
                value="真寻",
                help="默认的全局人设名称",
                default_value="真寻",
                type=str,
            ),
            RegisterConfig(
                key="TTS_CONFIG",
                value={"enable": False, "model": "MiMo/mimo-v2.5-tts", "voice_id": ""},
                help="TTS 语音生成配置。enable: 是否开启，model: 生成模型，voice_id: 指定音色（留空使用模型默认）",
                default_value={
                    "enable": False,
                    "model": "MiMo/mimo-v2.5-tts",
                    "voice_id": "",
                },
                type=dict,
            ),
            RegisterConfig(
                key="ENABLE_IMPRESSION",
                value=True,
                help="使用签到数据作为基础好感度",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="memory_settings",
                value={
                    "ltm_config": {
                        "enable": False,
                        "embed_model": "siliconflow/BAAI/bge-m3",
                        "auto_recall": False,
                    },
                    "user_mode": {
                        "vision_window": 2,
                        "llm_summary": {
                            "enable": True,
                            "trigger_threshold": 0.7,
                            "max_history_turns": 20,
                            "keep_recent_turns": 3,
                            "summarization_model": "DeepSeek/deepseek-v4-flash",
                            "summarization_prompt": "请以客观、精炼的语言概括以下对话内容。重点保留：1. 核心讨论话题及重要决定；2. 用户的个性特征、核心偏好、提及的生活背景或特殊设定；3. 双方互动的温度与情感基调。无需保留寒暄等客套话。",
                        }
                    },
                    "group_mode": {
                        "initial_load_turns": 10,
                        "vision_window": 1,
                        "idle_timeout": 1800,
                        "llm_summary": {
                            "enable": True,
                            "trigger_threshold": 0.7,
                            "max_history_turns": 30,
                            "keep_recent_turns": 10,
                            "summarization_model": "DeepSeek/deepseek-v4-flash",
                            "summarization_prompt": "请客观精炼地概括以下群聊对话。重点保留核心话题、用户特殊设定和AI的参与态度，忽略无意义的闲聊。",
                        }
                    }
                },
                help=(
                    "记忆与上下文分离配置。\n"
                    "- ltm_config: 共有配置，长期向量记忆 RAG。\n"
                    "- user_mode: 私聊及单用户隔离模式专属配置，包含 vision_window 视窗限制和 llm_summary 总结截断策略。\n"
                    "- group_mode: 群组双缓冲共享记忆专属配置。包含 initial_load_turns(AI被唤醒时携带的被动群聊消息数), idle_timeout(主动会话闲置超时秒数), vision_window 和 llm_summary。"
                ),
                default_value={
                    "ltm_config": {
                        "enable": False,
                        "embed_model": "siliconflow/BAAI/bge-m3",
                        "auto_recall": False,
                    },
                    "user_mode": {
                        "vision_window": 2,
                        "llm_summary": {
                            "enable": True,
                            "trigger_threshold": 0.7,
                            "max_history_turns": 20,
                            "keep_recent_turns": 3,
                            "summarization_model": "DeepSeek/deepseek-v4-flash",
                            "summarization_prompt": "请以客观、精炼的语言概括以下对话内容。重点保留：1. 核心讨论话题及重要决定；2. 用户的个性特征、核心偏好、提及的生活背景或特殊设定；3. 双方互动的温度与情感基调。无需保留寒暄等客套话。",
                        }
                    },
                    "group_mode": {
                        "initial_load_turns": 10,
                        "vision_window": 1,
                        "idle_timeout": 1800,
                        "llm_summary": {
                            "enable": True,
                            "trigger_threshold": 0.7,
                            "max_history_turns": 30,
                            "keep_recent_turns": 10,
                            "summarization_model": "DeepSeek/deepseek-v4-flash",
                            "summarization_prompt": "请客观精炼地概括以下群聊对话。重点保留核心话题、用户特殊设定和AI的参与态度，忽略无意义的闲聊。",
                        }
                    }
                },
                type=dict,
            ),
            RegisterConfig(
                key="advanced_settings",
                value={
                    "guardrail": {
                        "enable": False,
                        "model": "DeepSeek/deepseek-v4-flash",
                        "max_attempts": 1,
                    },
                    "timing_gate": {
                        "enable": False,
                        "model": "DeepSeek/deepseek-v4-flash",
                        "only_on_random": True,
                    },
                },
                help=(
                    "高级控制流与护栏配置，管理智能体行为逻辑、风控和发言决策。\n"
                    "- guardrail: 人设护栏配置，开启后将使用大模型检查回复是否符合人设，不符合则触发反思重试。包含: enable(是否开启)、model(裁判模型)、max_attempts(最大重试次数)。注意：开启此功能会显著增加 Token 消耗\n"
                    "- timing_gate: 发言门控决策配置，开启后会使用大模型判断是否应当插话。包含: enable(是否开启)、model(决策模型)、only_on_random(True 表示仅在随机概率命中时触发门控，False 表示所有发言前包括主动@都需经过门控)"
                ),
                default_value={
                    "guardrail": {
                        "enable": False,
                        "model": "DeepSeek/deepseek-v4-flash",
                        "max_attempts": 1,
                    },
                    "timing_gate": {
                        "enable": False,
                        "model": "DeepSeek/deepseek-v4-flash",
                        "only_on_random": True,
                    },
                },
                type=dict,
            ),
        ],
    ).to_dict(),
)

_PROCESSED_MSG_IDS: dict[str, float] = {}
_MSG_DEDUP_TTL = 10.0


async def build_persona_list(personas: dict[str, str]) -> bytes:
    table = ui.table("Persona List", "人设列表概览")
    table.set_headers(["人设名称", "提示词预览"])
    rows = []
    for name, prompt in personas.items():
        preview = prompt.replace("\n", " ")
        if len(preview) > 50:
            preview = preview[:50] + "..."
        rows.append([name, TextCell(content=preview)])

    table.add_rows(rows)
    table.set_column_widths(["150px", "auto"])
    return await ui.render(table, viewport={"width": 800, "height": 10})


async def bym_ai_rule(event: Event, session: Uninfo, state: T_State) -> bool:
    event_time = getattr(event, "time", None)
    if event_time is not None:
        try:
            if time.time() - float(event_time) > 5.0:
                logger.debug(
                    "BYM AI 拦截到过期事件 (TTL > 5s)，判定为被前端挂起漏过的幽灵事件，跳过处理。",
                    "BYM_AI",
                )
                return False
        except (ValueError, TypeError):
            pass

    msg_id = getattr(event, "message_id", None)
    if msg_id is not None:
        msg_id_str = str(msg_id)
        current_time = time.time()
        for k in list(_PROCESSED_MSG_IDS.keys()):
            if current_time - _PROCESSED_MSG_IDS[k] > _MSG_DEDUP_TTL:
                del _PROCESSED_MSG_IDS[k]
        if msg_id_str in _PROCESSED_MSG_IDS:
            return False

    is_tome = event.is_tome()
    group_id = session.group.id if session.group else None

    default_context_mode = base_config.get("CONTEXT_MODE", "user")
    context_mode = (
        await group_settings_service.get(
            str(group_id), "bym_ai", "context_mode", default_context_mode
        )
        if group_id
        else "user"
    )
    effective_mode = "user" if not group_id else context_mode

    should_reply = False
    is_random_triggered = False

    if is_tome:
        should_reply = True
    elif group_id and effective_mode == "group":
        global_reply_cfg = base_config.get("RANDOM_REPLY") or {}
        global_enabled = global_reply_cfg.get("enable", True)

        chat_enabled = await group_settings_service.get(
            str(group_id), "bym_ai", "random_reply_enable", global_enabled
        )
        if isinstance(chat_enabled, str):
            chat_enabled = chat_enabled.lower() in ("true", "on", "1", "yes")

        if chat_enabled:
            global_rate = float(global_reply_cfg.get("rate", 0.05))
            rate_val = await group_settings_service.get(
                str(group_id), "bym_ai", "random_reply_rate", global_rate
            )
            try:
                rate_val = float(rate_val)
            except (ValueError, TypeError):
                rate_val = global_rate

            if rate_val > 0:
                group_id_str = str(group_id)

                if group_id_str not in RANDOM_TRIGGER_STATE:
                    expected = int(1.0 / rate_val) if rate_val < 1.0 else 1
                    jitter = max(1, int(expected * 0.3))
                    RANDOM_TRIGGER_STATE[group_id_str] = {
                        "count": 0,
                        "target": max(
                            1, random.randint(expected - jitter, expected + jitter)
                        ),
                    }

                state_dict = RANDOM_TRIGGER_STATE[group_id_str]
                state_dict["count"] += 1

                if state_dict["count"] >= state_dict["target"]:
                    should_reply = True
                    is_random_triggered = True
                    state_dict["count"] = 0
                    expected = int(1.0 / rate_val) if rate_val < 1.0 else 1
                    jitter = max(1, int(expected * 0.3))
                    state_dict["target"] = max(
                        1, random.randint(expected - jitter, expected + jitter)
                    )

    state["should_reply"] = should_reply
    state["is_random_triggered"] = is_random_triggered

    will_process = should_reply or (effective_mode == "group" and group_id)
    if will_process and msg_id is not None:
        _PROCESSED_MSG_IDS[str(msg_id)] = time.time()

    if should_reply:
        return True
    if effective_mode == "group" and group_id:
        return True
    return False


_matcher = on_message(priority=998, block=False, rule=bym_ai_rule)

RANDOM_TRIGGER_STATE: dict[str, dict[str, int]] = {}


@_matcher.handle(parameterless=[CheckConfig(config="BYM_AI_CHAT_MODEL")])
async def _(
    bot: Bot,
    event: Event,
    session: Uninfo,
    state: T_State,
    uname: str = UserName(),
):
    user_input = UniMessage.of(event.get_message(), bot=bot)
    raw_text = user_input.extract_plain_text().strip()
    has_image = user_input.has(Image)
    if not raw_text and not has_image:
        return

    group_id = session.group.id if session.group else None
    is_tome = event.is_tome()
    is_bym = not is_tome

    should_reply = state.get("should_reply", False)
    is_random_triggered = state.get("is_random_triggered", False)

    default_context_mode = base_config.get("CONTEXT_MODE", "user")
    context_mode = (
        await group_settings_service.get(
            str(group_id), "bym_ai", "context_mode", default_context_mode
        )
        if group_id
        else "user"
    )
    effective_mode = "user" if not group_id else context_mode
    platform = PlatformUtils.get_platform(bot)
    group_key = (
        f"{platform}_{group_id}"
        if group_id
        else f"{platform}_private_{session.user.id}"
    )
    memory_settings = base_config.get("memory_settings", {})
    try:
        group_config = TypeAdapter(GroupModeMemoryConfig).validate_python(memory_settings.get("group_mode", {}))
    except Exception:
        group_config = GroupModeMemoryConfig()
        
    chat_model = base_config.get("BYM_AI_CHAT_MODEL", "DeepSeek/deepseek-v4-flash")

    if effective_mode == "group" and group_id:
        at_hint = "[@了你] " if is_tome else ""
        prefix = f"[{uname}]: {at_hint}"
        final_input = UniMessage.text(prefix) + user_input
    else:
        final_input = user_input

    from zhenxun.services.ai.message_builder import MessageBuilder

    llm_msgs = await MessageBuilder.normalize_to_llm_messages(
        final_input, bot=bot, event=event
    )
    user_llm_msg = (
        llm_msgs[-1]
        if llm_msgs
        else LLMMessage.user(final_input.extract_plain_text() or "[图片]")
    )

    if not should_reply:
        if effective_mode == "group" and group_id:
            await group_buffer_manager.add_messages(
                group_key, [user_llm_msg], group_config, is_active_trigger=False, model_name=chat_model
            )
        return

    ctx = RunContext(deps=NoneBotDeps(bot=bot, event=event))
    if effective_mode == "group":
        ctx.state["__bym_history__"] = group_buffer_manager.get_messages(group_key, group_config.idle_timeout)
    ctx.state["__bym_is_random_triggered__"] = is_random_triggered
    ctx.state["__bym_effective_mode__"] = effective_mode

    try:
        from .data_source import get_memory_config

        if effective_mode == "group":
            current_history = group_buffer_manager.get_messages(group_key, group_config.idle_timeout)
            response = await bym_agent.run(
                final_input,
                context=ctx,
                config=AgentConfig(message_history=current_history),
            )
        else:
            response = await bym_agent.run(
                final_input,
                context=ctx,
                config=AgentConfig(
                    memory=get_memory_config(effective_mode=effective_mode)
                ),
            )
        result_text = str(response.output).strip()

        if effective_mode == "group" and group_id:
            msgs_to_add = [user_llm_msg]
            if response.llm_messages:
                msgs_to_add.extend(response.llm_messages)
            await group_buffer_manager.add_messages(
                group_key, msgs_to_add, group_config, is_active_trigger=True, model_name=chat_model
            )

        if result_text:
            should_reply_msg = bool(group_id) if not is_bym else False
            await MessageUtils.build_message(result_text).send(
                reply_to=should_reply_msg
            )

            tts_cfg = base_config.get("TTS_CONFIG", {})
            if tts_cfg.get("enable", False) and tts_cfg.get("model"):
                tts_model = tts_cfg.get("model")
                voice_id = tts_cfg.get("voice_id")
                try:
                    audio_res = await create_speech(
                        result_text, voice=voice_id or None, model=tts_model
                    )
                    if audio_res and audio_res.audio_bytes:
                        await MessageUtils.build_message(
                            Voice(raw=audio_res.audio_bytes)
                        ).send()
                except Exception as e:
                    logger.error(f"BYM AI TTS生成失败: {e}", "BYM_AI", session=session)

            logger.info(
                f"BYM AI 问题: {raw_text or '[多模态图片消息]'} | 回答: {result_text}",
                "BYM_AI",
                session=session,
            )
    except ControlFlowExit as e:
        logger.info(f"BYM AI 门控静默拦截: {e}", "BYM_AI", session=session)
        if effective_mode == "group" and group_id:
            await group_buffer_manager.add_messages(
                group_key, [user_llm_msg], group_config, is_active_trigger=False, model_name=chat_model
            )
    except LLMException as e:
        logger.error(f"BYM AI LLM异常: {e}", "BYM_AI", session=session)
        if not is_bym:
            await MessageUtils.build_message(e.user_friendly_message).send(
                reply_to=True
            )
    except Exception as e:
        logger.error("BYM AI 其他错误", "BYM_AI", session=session, e=e)
        if not is_bym:
            await MessageUtils.build_failure_message().finish(reply_to=True)


from . import command  # noqa: E402, F401
