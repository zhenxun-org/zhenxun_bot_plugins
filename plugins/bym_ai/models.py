import time
from pydantic import BaseModel, Field

from zhenxun.services.ai.context.memory.storage import AbstractMemoryRecord
from zhenxun.services.ai.context.rag import AbstractVectorRecord
from zhenxun.services.ai.core.messages import LLMMessage


class BymGroupConfig(BaseModel):
    """BYM_AI 专属的群组级动态配置模型"""

    current_persona: str = Field(default="真寻", description="当前群使用的 AI 人设名称")
    random_reply_enable: bool = Field(default=False, description="是否开启随机拟人插话")
    random_reply_rate: float = Field(
        default=0.01, description="随机插话触发概率(0.0-1.0)"
    )
    context_mode: str = Field(
        default="user", description="上下文记忆模式 (user 或 group)"
    )


class BymAiMemoryRecord(AbstractMemoryRecord):
    class Meta:  # type: ignore
        table = "bym_ai_memory"
        table_description = "Bym聊天记忆表"


class BymAiVectorRecord(AbstractVectorRecord):
    class Meta:  # type: ignore
        table = "bym_ai_vector_memory"
        table_description = "Bym长期向量记忆表"


class LtmConfig(BaseModel):
    """共有配置：长期向量记忆"""

    enable: bool = False
    """是否开启长期记忆"""
    embed_model: str = "siliconflow/BAAI/bge-m3"
    """向量嵌入模型名称"""
    auto_recall: bool = False
    """是否在每次对话前自动使用相似度搜索长期记忆"""


class LLMSummaryConfig(BaseModel):
    """局部大模型总结压缩配置"""

    enable: bool = True
    """是否开启局部大模型总结压缩"""
    trigger_threshold: float = 0.7
    """触发总结的阈值比例"""
    max_history_turns: int = 20
    """最大历史消息轮数"""
    keep_recent_turns: int = 3
    """触发总结后保留的最近消息轮数"""
    summarization_model: str = "DeepSeek/deepseek-v4-flash"
    """用于生成总结的 LLM 模型"""
    summarization_prompt: str = "请以客观、精炼的语言概括以下对话内容。重点保留：1. 核心讨论话题及重要决定；2. 用户的个性特征、核心偏好、提及的生活背景或特殊设定；3. 双方互动的温度与情感基调。无需保留寒暄等客套话。"
    """用于生成总结的提示词"""


class UserModeMemoryConfig(BaseModel):
    """私聊/单用户模式专属记忆配置"""

    vision_window: int = 2
    """多模态消息视窗限制轮数"""
    llm_summary: LLMSummaryConfig = Field(default_factory=LLMSummaryConfig)
    """局部大模型总结压缩配置"""


class GroupModeMemoryConfig(BaseModel):
    """群组共享模式专属记忆配置 (双缓冲配置)"""

    initial_load_turns: int = 10
    """群聊唤醒时初始加载的历史消息轮数"""
    vision_window: int = 1
    """多模态消息视窗限制轮数"""
    idle_timeout: int = 1800
    """主动会话的闲置超时时间（秒）"""
    llm_summary: LLMSummaryConfig = Field(
        default_factory=lambda: LLMSummaryConfig(
            max_history_turns=30,
            keep_recent_turns=10,
            summarization_prompt="请客观精炼地概括以下群聊对话。重点保留核心话题、用户特殊设定和AI的参与态度，忽略无意义的闲聊。",
        )
    )
    """局部大模型总结压缩配置"""


class BymMemorySettings(BaseModel):
    """插件全局 Memory 总配置根节点"""

    ltm_config: LtmConfig = Field(default_factory=LtmConfig)
    """共有配置：长期向量记忆"""
    user_mode: UserModeMemoryConfig = Field(default_factory=UserModeMemoryConfig)
    """私聊/单用户隔离模式专属配置"""
    group_mode: GroupModeMemoryConfig = Field(default_factory=GroupModeMemoryConfig)
    """群组双缓冲共享记忆专属配置"""


class GroupChatState(BaseModel):
    """群组聊天的双缓冲物理状态机"""

    is_active: bool = False
    """当前群组会话是否处于活跃状态"""
    last_active_time: float = Field(default_factory=time.time)
    """上一次活跃的时间戳"""
    passive_buffer: list[LLMMessage] = Field(default_factory=list)
    """被动嗅探消息缓冲区"""
    active_buffer: list[LLMMessage] = Field(default_factory=list)
    """主动会话消息缓冲区"""
    is_summarizing: bool = False
    """标记当前是否正在进行大模型后台压缩，用于防并发竞争"""
