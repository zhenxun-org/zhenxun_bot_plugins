from collections import defaultdict
from datetime import datetime
import time
from typing import Any

from pydantic import BaseModel, Field

from zhenxun.services.ai.context.memory.compression import (
    MultimodalPlaceholderReducer,
    LLMSummarizerReducer,
)

from zhenxun.builtin_plugins.sign_in.utils import (
    get_level_and_next_impression,
    level2attitude,
)
from zhenxun.models.group_console import GroupConsole
from zhenxun.models.sign_user import SignUser
from zhenxun.services.ai.capabilities import AbstractCapability, WrapRunHandler
from zhenxun.services.ai.context.memory import (
    Isolation,
    MemoryBuilder,
)
from zhenxun.services.ai.context.memory.storage import (
    get_orm_chat_context,
)
from zhenxun.services.ai.context.rag.backends import TortoiseStorageBackend
from zhenxun.services.ai.core.exceptions import AbortException
from zhenxun.services.ai.core.messages import ChatResponse, LLMMessage
from zhenxun.services.ai.core.templates import PromptTemplate
from zhenxun.services.ai.flow.agent import Agent
from zhenxun.services.ai.flow.agent.models import AgentConfig
from zhenxun.services.ai.flow.base import ConcurrencyPolicy, ConcurrencyScope
from zhenxun.services.ai.guardrails import (
    GuardrailAction,
    GuardrailResult,
    output_guardrail,
)
from zhenxun.services.ai.llm.api import generate_structured
from zhenxun.services.ai.run import RunContext, Inject
from zhenxun.services.group_settings_service import group_settings_service
from zhenxun.services.log import logger
from zhenxun.utils.utils import infer_plugin_namespace

from .config import (
    JINJA2_PROMPT_TEMPLATE,
    PERSONAS_CACHE,
    ULTIMATE_FALLBACK_PERSONA,
    base_config,
)
from .models import (
    BymAiMemoryRecord,
    BymAiVectorRecord,
    GroupChatState,
    GroupModeMemoryConfig,
)

GROUP_NAME_CACHE = {}

bym_memory_backend = get_orm_chat_context(BymAiMemoryRecord)


async def get_effective_persona_text(group_id: str | None) -> str:
    """辅助方法：统一获取当前生效的人设文本"""
    default_persona = base_config.get("DEFAULT_PERSONA", "真寻")
    persona_name = default_persona
    if group_id:
        persona_name = await group_settings_service.get(
            str(group_id), "bym_ai", "current_persona", default_persona
        )
    return (
        PERSONAS_CACHE.get(persona_name)
        or PERSONAS_CACHE.get(default_persona)
        or ULTIMATE_FALLBACK_PERSONA
    )


class BymDynamicMemoryCapability(AbstractCapability):
    """针对 BYM 运行时的动态长期记忆工具挂载能力"""

    async def get_tools(self, context: RunContext) -> list[Any]:
        mode = context.state.get("__bym_effective_mode__", "user")
        memory_cfg = get_memory_config(effective_mode=mode).build()

        if memory_cfg.long_term.enable and memory_cfg.long_term.agentic:
            from zhenxun.services.ai.context.memory.capabilities import (
                AgenticMemoryCapability,
            )

            cap = AgenticMemoryCapability(memory_cfg, infer_plugin_namespace())
            return await cap.get_tools(context)
        return []


def get_memory_config(effective_mode: str = "user", *args, **kwargs):
    """获取状态化内存配置"""
    builder = (
        MemoryBuilder()
        .with_base_isolation(Isolation.AGENT_USER())
        .with_short_term(
            enable=True,
            backend=bym_memory_backend,
        )
    )

    memory_settings = base_config.get("memory_settings", {})
    ltm_cfg = memory_settings.get("ltm_config", {})
    if ltm_cfg.get("enable", False) and effective_mode == "user":
        ltm_instructions = """\
## 🧠 长期记忆管理系统 (Long-Term Memory)
作为陪伴型聊天机器人，该系统是你的「无限档案馆」。⚠️注意：系统默认不会提供所有历史，你必须主动搜索。

### 📝 何时保存记忆 (save_memory)？
1. **用户核心设定**：当用户提及自己的真实姓名、住址、职业、年龄、生日、亲际关系等事实时。
2. **喜好与雷区**：当用户表达对某些事物强烈的喜恶（喜欢吃什么、讨厌什么话题）时。
3. **重大经历或约定**：用户分享的重大经历或与你的特殊约定。
**【⚠️ 单人隔离存储规范】**：
当前处于「单用户独立隔离记忆」模式。保存内容时，**必须且只能以“用户”作为主语**，绝对禁止使用该用户的具体昵称（如禁止存入“张三住在苏州”，必须存入“用户住在苏州”）。因为用户昵称随时改变，带入昵称会导致以后永久丢失该记忆！

### 🔍 何时搜索记忆 (search_memory)？
当遇到以下情况，必须主动检索历史库：
1. 用户直接询问：“我住哪”、“我之前说过什么”、“你还记得我的生日吗”。
2. 对话中出现未知的前置设定（如用户突然说“我明天要去那里面试”，你需要搜索他提过的公司或地点）。
**【⚠️ 检索规范】**：
提取查询词(query)时，请**只提取动词、名词实体或事件的核心关键词**（如：“居住地 住址 城市”或“喜欢 讨厌 偏好”），**严禁使用人称代词或具体昵称**作为搜索词，以确保高召回率。

### 🔄 更新与删除 (update/delete_memory)
如果发现用户的某项旧设定发生改变（如搬家了、换工作了），请先搜索出原记忆的 ID，再使用 `update_memory` 或 `delete_memory` 进行维护。\
"""
        builder.with_long_term(
            enable=True,
            backend=TortoiseStorageBackend(BymAiVectorRecord),
            embedder=ltm_cfg.get("embed_model", "siliconflow/BAAI/bge-m3"),
            agentic=True,
            auto_recall=ltm_cfg.get("auto_recall", False),
            instructions=ltm_instructions,
        )

    if effective_mode == "user":
        user_mode_cfg = memory_settings.get("user_mode", {})
        builder.with_multimodal_window(
            window_size=user_mode_cfg.get("vision_window", 2)
        )

        llm_summary_cfg = user_mode_cfg.get("llm_summary", {})
        if llm_summary_cfg and llm_summary_cfg.get("enable", True):
            summary_kwargs = {}
            if "trigger_threshold" in llm_summary_cfg:
                val = llm_summary_cfg["trigger_threshold"]
                summary_kwargs["trigger_tokens"] = int(val) if val > 1.0 else 4000
            mapping = {
                "max_history_turns": "max_turns",
                "keep_recent_turns": "keep_recent_turns",
                "summarization_model": "summarization_model",
                "summarization_prompt": "summarization_prompt",
            }
            for cfg_key, kwarg_key in mapping.items():
                if cfg_key in llm_summary_cfg:
                    summary_kwargs[kwarg_key] = llm_summary_cfg[cfg_key]
            builder.with_llm_summary(**summary_kwargs)
        else:
            builder.unlimited()
    else:
        builder.unlimited()

    return builder


def get_chat_model():
    return base_config.get("BYM_AI_CHAT_MODEL")


class PersonaJudge(BaseModel):
    """用于大模型裁判结构化输出的数据模型"""

    passed: bool = Field(description="回复是否完全符合给定的人设特征、语气和规则限制")
    reason: str = Field(
        description="如果不符合，请指出具体违反了哪一条人设规则，并给出严厉的修改建议"
    )


@output_guardrail
async def persona_guardrail(
    response: ChatResponse, context: RunContext
) -> GuardrailResult:
    """大模型人设风控护栏"""
    advanced_settings = base_config.get("advanced_settings", {})
    guardrail_cfg = advanced_settings.get("guardrail", {})
    if not guardrail_cfg.get("enable", False):
        return GuardrailResult(action=GuardrailAction.PASS)

    max_attempts = guardrail_cfg.get("max_attempts", 1)
    counts = context.state.setdefault("__bym_persona_guardrail_counts__", 0)
    if counts >= max_attempts:
        return GuardrailResult(action=GuardrailAction.PASS)
    context.state["__bym_persona_guardrail_counts__"] += 1

    persona_text = await get_effective_persona_text(context.get_group_id())
    judge_model = guardrail_cfg.get("model", "DeepSeek/deepseek-v4-flash")

    prompt = f"""你是一个严格的人设审核裁判。
请阅读以下【角色人设】和【AI的回复】，判断该回复是否严重偏离了人设（例如：语气完全不对、字数超过了严格限制、或者承认了自己是AI等）。

【角色人设】：
{persona_text}

【AI的回复】：
{response.text}

请严格判断。如果符合人设，passed 设为 true。如果不符合，passed 设为 false，并
在 reason 中写出要求其修改的具体建议（例如：
“你的回复字数超过了15字，并且语气太温柔了，请改用毒舌语气并缩短字数！”）。"""

    try:
        judge_res = await generate_structured(
            prompt,
            response_model=PersonaJudge,
            model=judge_model,
            instruction="你是一个客观严格的风控裁判。",
        )
        if judge_res.passed:
            return GuardrailResult(action=GuardrailAction.PASS)
        return GuardrailResult(
            action=GuardrailAction.REFLECT,
            feedback=f"你的回复未能通过人设风控护栏！裁判反馈：{judge_res.reason}\n请务必严格遵循你的人设系统提示词重新生成回复！",
        )
    except Exception as e:
        logger.warning(f"BYM_AI 人设护栏裁判执行异常，已放行: {e}", "BYM_AI")
        return GuardrailResult(action=GuardrailAction.PASS)


class TimingDecision(BaseModel):
    """门控决策的结构化输出数据契约"""

    should_reply: bool = Field(
        description="基于人设和当前语境，是否应当积极发言/插话/回复"
    )
    reason: str = Field(description="做出该决定的内在原因分析")


class TimingGateCapability(AbstractCapability):
    """洋葱模型中间件：大模型语境与人设评估门控"""

    async def wrap_run(self, context: RunContext, handler: WrapRunHandler) -> Any:
        advanced_settings = base_config.get("advanced_settings", {})
        config = advanced_settings.get("timing_gate", {})
        if not config.get("enable", False):
            return await handler()

        group_id = context.get_group_id()
        if not group_id:
            return await handler()

        only_on_random = config.get("only_on_random", True)
        is_random_triggered = context.state.get("__bym_is_random_triggered__", False)
        if only_on_random and not is_random_triggered:
            return await handler()

        persona_text = await get_effective_persona_text(group_id)

        memory_settings = base_config.get("memory_settings", {})
        group_mode = memory_settings.get("group_mode", {})
        idle_timeout = group_mode.get("idle_timeout", 1800)

        platform = context.get_platform()
        history = group_buffer_manager.get_messages(
            f"{platform}_{group_id}", idle_timeout
        )
        history_text = "\n".join([f"{msg.role}: {msg.extract_text}" for msg in history])
        user_input = context.run.user_input or ""

        prompt = f"""你是一个群聊语境门控评估器。
请根据以下<persona>（角色人设）</persona>、<context>（最近群聊上下文）</context>和<latest_message>（最新消息）</latest_message>，判断该角色当前是否应该发言插话。
参考条件：
1. 话题是否是该角色感兴趣的？
2. 是否有人@提及了该角色（提及优先级高，但如果不符合人设也可以不回）？
3. 结合角色的性格（如高冷可能不理人，话痨可能随时插嘴）做出符合逻辑的判断。

<persona>
{persona_text}
</persona>

<context>
{history_text}
</context>

<latest_message>
{user_input}
</latest_message>"""

        model = config.get("model", "DeepSeek/deepseek-v4-flash")
        try:
            decision = await generate_structured(
                prompt,
                response_model=TimingDecision,
                model=model,
                instruction="你是一个客观的语境评估器。",
            )
            if not decision.should_reply:
                logger.info(f"Timing Gate 决定静默，原因：{decision.reason}", "BYM_AI")
                raise AbortException(reason=f"Timing Gate Ignore: {decision.reason}")
        except AbortException:
            raise
        except Exception as e:
            logger.warning(f"Timing Gate 评估异常，放行处理: {e}", "BYM_AI")

        return await handler()


bym_agent = Agent(
    name="bym_ai_agent",
    model=get_chat_model,
    tools=[],
    config=AgentConfig(
        stateless=True,
        concurrency_policy=ConcurrencyPolicy.QUEUE,
        concurrency_scope=ConcurrencyScope.GROUP,
        enable_hitl=False,
    ),
    capabilities=[TimingGateCapability(), BymDynamicMemoryCapability()],
    guardrails=[persona_guardrail],
)


@bym_agent.system_prompt
async def build_bym_system_prompt(
    bot: Inject.Bot,
    event: Inject.Event,
    user_id: Inject.UserId,
    group_id: Inject.GroupId,
    context: RunContext,
) -> list[str]:
    """利用原生 Agent 动态提示词系统注入人设与群聊状态 (通过 DI 自动解析参数)"""
    try:
        nickname = getattr(event, "sender", None) if event else None
        nickname = getattr(nickname, "nickname", user_id) if nickname else user_id

        is_tome = getattr(event, "is_tome", lambda: False)() if event else False
        is_bym = not is_tome

        group_name = ""
        if group_id:
            if group_id not in GROUP_NAME_CACHE:
                if group := await GroupConsole.get_group(str(group_id)):
                    GROUP_NAME_CACHE[group_id] = group.group_name
            group_name = GROUP_NAME_CACHE.get(group_id, "")

        enable_impression = bool(base_config.get("ENABLE_IMPRESSION"))
        impression_value = 0.0
        attitude = ""
        if enable_impression and user_id:
            sign_user = await SignUser.get_user(user_id)
            if sign_user:
                impression_value = float(sign_user.impression)
                level, _, _ = get_level_and_next_impression(impression_value)
                level = "1" if level in ["0"] else level
                attitude = level2attitude[str(level)]

        effective_mode = context.state.get("__bym_effective_mode__", "user")

        render_kwargs = {
            "is_bym": is_bym,
            "group_id": group_id or "DEFAULT",
            "group_name": group_name,
            "self_id": bot.self_id if bot else "",
            "enable_impression": enable_impression,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "nickname": nickname,
            "user_id": user_id,
            "impression": impression_value,
            "max_impression": impression_value + 30,
            "attitude": attitude,
            "effective_mode": effective_mode,
        }

        jinja_str = PromptTemplate(JINJA2_PROMPT_TEMPLATE).render(**render_kwargs)

        persona_text = await get_effective_persona_text(group_id)

        return [persona_text, jinja_str]
    except Exception as e:
        logger.error(f"构建动态人设 System Prompt 失败: {e}", "BYM_AI")
        return [ULTIMATE_FALLBACK_PERSONA]


class VolatileGroupBufferManager:
    """易失性群组双缓冲管理器：分离被动嗅探池与主动会话池"""

    def __init__(self):
        self._states: dict[str, GroupChatState] = defaultdict(GroupChatState)

    def get_state(self, key: str) -> GroupChatState:
        """获取指定键的状态机对象"""
        return self._states[key]

    def get_messages(self, key: str, idle_timeout: int) -> list[LLMMessage]:
        """获取指定键的历史消息副本：严格根据活跃状态与超时判定决定返回哪个池子"""
        state = self._states[key]
        if state.is_active and (time.time() - state.last_active_time <= idle_timeout):
            return state.active_buffer.copy()
        return state.passive_buffer.copy()

    async def add_messages(
        self,
        key: str,
        new_msgs: list[LLMMessage],
        config: GroupModeMemoryConfig,
        is_active_trigger: bool = False,
        model_name: str | None = None,
    ):
        """双缓冲状态机核心：处理消息追加、超时降级、唤醒跃迁和主动总结"""
        state = self._states[key]
        current_time = time.time()

        if state.is_active and (
            current_time - state.last_active_time > config.idle_timeout
        ):
            recent = (
                state.active_buffer[-config.initial_load_turns :]
                if config.initial_load_turns > 0
                else []
            )
            state.passive_buffer = recent
            state.active_buffer.clear()
            state.is_active = False

        if is_active_trigger:
            state.last_active_time = current_time
            if not state.is_active:
                state.active_buffer.extend(state.passive_buffer)
                state.passive_buffer.clear()
                state.is_active = True

        reducer = MultimodalPlaceholderReducer(window_size=config.vision_window)

        if state.is_active:
            state.active_buffer.extend(new_msgs)
            if config.vision_window >= 0:
                state.active_buffer, _, _ = await reducer.reduce(
                    state.active_buffer, 0, "", 0
                )

            if config.llm_summary.enable and model_name:
                user_turns = sum(
                    1
                    for m in state.active_buffer
                    if m.role == "user"
                    and not (m.metadata and m.metadata.get("is_summary", False))
                )
                if user_turns > config.llm_summary.max_history_turns:
                    if state.is_summarizing:
                        logger.debug("⏳ 正在后台总结压缩中，跳过本次触发...", "BYM_AI")
                    else:
                        working_msgs = [
                            m
                            for m in state.active_buffer
                            if not (m.metadata and m.metadata.get("is_summary", False))
                            and m.role != "system"
                        ]
                        has_recent_assistant = any(
                            m.role == "assistant" for m in working_msgs
                        )

                        if has_recent_assistant:
                            state.is_summarizing = True
                            try:
                                summarizer = LLMSummarizerReducer(
                                    keep_recent_turns=config.llm_summary.keep_recent_turns,
                                    trigger_tokens=9999999,
                                    max_turns=config.llm_summary.max_history_turns,
                                    summarization_model=config.llm_summary.summarization_model,
                                    summarization_prompt=config.llm_summary.summarization_prompt,
                                )
                                state.active_buffer, _, _ = await summarizer.reduce(
                                    state.active_buffer, 9999999, model_name, 0
                                )
                            finally:
                                state.is_summarizing = False
                        else:
                            logger.debug(
                                "群聊中AI近期未参与互动，触发水群刷屏超限，已执行静默降级...",
                                "BYM_AI",
                            )
                            recent = (
                                state.active_buffer[-config.initial_load_turns :]
                                if config.initial_load_turns > 0
                                else []
                            )
                            state.passive_buffer = recent
                            state.active_buffer.clear()
                            state.is_active = False
        else:
            state.passive_buffer.extend(new_msgs)
            if len(state.passive_buffer) > config.initial_load_turns:
                state.passive_buffer = state.passive_buffer[
                    -config.initial_load_turns :
                ]
            if config.vision_window >= 0:
                state.passive_buffer, _, _ = await reducer.reduce(
                    state.passive_buffer, 0, "", 0
                )

    def clear_group(self, key: str):
        """清理指定群组/用户的记忆，销毁状态"""
        if key in self._states:
            state = self._states[key]
            state.passive_buffer.clear()
            state.active_buffer.clear()
            state.is_active = False
            self._states.pop(key, None)

    def clear_all(self):
        """清理整个插件的所有临时记忆"""
        self._states.clear()


group_buffer_manager = VolatileGroupBufferManager()
