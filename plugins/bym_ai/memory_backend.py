from typing import ClassVar

from zhenxun.services.llm import LLMMessage
from zhenxun.services.llm.memory import BaseMemory
from zhenxun.services.log import logger

from .config import PROMPT_FILE, base_config
from .models.bym_chat import BymChat


def _parse_session_key(session_id: str) -> tuple[str | None, str | None]:
    """
    将 session_id 解析为 (user_id, group_id)。
    约定:
        - "bym:user:group" -> (user, group)
        - "bym:user"       -> (user, None)
    """
    # 去掉命名空间前缀，避免与其他模块的 session_id 冲突
    prefix = "bym:"
    session_id = session_id.removeprefix(prefix)
    if ":" in session_id:
        user_id, group_id = session_id.split(":", 1)
        return user_id or None, group_id or None
    return session_id or None, None


class BymMemory(BaseMemory):
    """
    BYM 专用记忆实现.

    - 读取历史时复用原有 `Conversation.get_conversation`（含数据库 + 内存缓存）
    - 写入历史时通过 `Conversation.set_history` 维护滑动窗口
    """

    async def get_history(self, session_id: str) -> list[LLMMessage]:
        user_id, group_id = _parse_session_key(session_id)
        # 复用旧逻辑：群聊伪人使用 group_id，私聊/个人使用 user_id
        if group_id:
            history = await Conversation.get_conversation(None, group_id)
        else:
            history = await Conversation.get_conversation(user_id, None)
        # 返回一份新的列表，避免外部修改内部缓存
        return list(history)

    async def add_messages(self, session_id: str, messages: list[LLMMessage]) -> None:
        user_id, group_id = _parse_session_key(session_id)
        if not user_id:
            logger.warning(
                "BymMemory.add_messages: session_id 解析不到 user_id，已忽略"
            )
            return

        # 先拉取现有历史，再追加新消息，最后交给 Conversation 处理裁剪
        if group_id:
            history = await Conversation.get_conversation(None, group_id)
        else:
            history = await Conversation.get_conversation(user_id, None)

        history.extend(messages)
        Conversation.set_history(user_id, group_id, history)

    async def clear_history(self, session_id: str) -> None:
        user_id, group_id = _parse_session_key(session_id)
        if not user_id:
            return
        await Conversation.reset(user_id, group_id)


class Conversation:
    """BYM 会话管理（数据库 + 内存缓存）"""

    history_data: ClassVar[dict[str, list[LLMMessage]]] = {}
    chat_prompt: str = ""

    @classmethod
    async def reload_prompt(cls):
        """重载prompt"""
        cls.chat_prompt = PROMPT_FILE.open(encoding="utf8").read()

    @classmethod
    def add_system(cls) -> LLMMessage:
        """添加系统预设"""
        if not cls.chat_prompt:
            cls.chat_prompt = PROMPT_FILE.open(encoding="utf8").read()
        return LLMMessage.system(cls.chat_prompt)

    @classmethod
    async def get_db_data(
        cls, user_id: str | None, group_id: str | None = None
    ) -> list[LLMMessage]:
        """从数据库获取记录"""
        conversation: list[LLMMessage] = []
        enable_group_chat = base_config.get("ENABLE_GROUP_CHAT")
        if enable_group_chat and group_id:
            db_filter = BymChat.filter(group_id=group_id)
        elif enable_group_chat:
            db_filter = BymChat.filter(user_id=user_id, group_id=None)
        else:
            db_filter = BymChat.filter(user_id=user_id)
        db_data_list = (
            await db_filter.order_by("-id")
            .limit(int(base_config.get("CACHE_SIZE") / 2))
            .all()
        )
        for db_data in db_data_list:
            if db_data.is_reset:
                break
            conversation.extend(
                [
                    LLMMessage.assistant_text_response(db_data.result),
                    LLMMessage.user(db_data.plain_text),
                ]
            )
        conversation.reverse()
        return conversation

    @classmethod
    async def get_conversation(
        cls, user_id: str | None, group_id: str | None
    ) -> list[LLMMessage]:
        """获取预设（内存优先，空则回退到数据库）"""
        conversation: list[LLMMessage] = []
        if (
            base_config.get("ENABLE_GROUP_CHAT")
            and group_id
            and group_id in cls.history_data
        ):
            conversation = cls.history_data[group_id]
        elif user_id and user_id in cls.history_data:
            conversation = cls.history_data[user_id]
        # 尝试从数据库中获取历史对话
        if not conversation:
            conversation = await cls.get_db_data(user_id, group_id)
        # 必须带有人设
        conversation = [c for c in conversation if c.role != "system"]
        conversation.insert(0, cls.add_system())
        return conversation

    @classmethod
    def set_history(
        cls, user_id: str, group_id: str | None, conversation: list[LLMMessage]
    ):
        """设置历史预设（仅内存缓存，数据库写入由其他逻辑负责）"""
        cache_size = base_config.get("CACHE_SIZE")
        group_cache_size = base_config.get("GROUP_CACHE_SIZE")
        size = group_cache_size if group_id else cache_size
        if len(conversation) > size:
            conversation = conversation[-size:]
        if base_config.get("ENABLE_GROUP_CHAT") and group_id:
            cls.history_data[group_id] = conversation
        else:
            cls.history_data[user_id] = conversation

    @classmethod
    async def reset_all(cls) -> int:
        """重置所有会话（在数据库中打 is_reset 标记，并清空内存缓存）"""
        update_list = []
        distinct_pairs = await BymChat.all().distinct().values("user_id", "group_id")
        for pair in distinct_pairs:
            user_id = pair["user_id"]
            group_id = pair["group_id"]

            latest_chat = (
                await BymChat.filter(user_id=user_id, group_id=group_id)
                .order_by("-create_time")
                .first()
            )

            if latest_chat and not latest_chat.is_reset:
                latest_chat.is_reset = True
                update_list.append(latest_chat)
        await BymChat.bulk_update(update_list, ["is_reset"])
        cls.history_data = {}
        return len(update_list)

    @classmethod
    async def reset(cls, user_id: str, group_id: str | None):
        """重置指定用户/群组的预设"""
        if base_config.get("ENABLE_GROUP_CHAT") and group_id:
            # 群组内重置
            db_data = await BymChat.filter(group_id=group_id).order_by("-id").first()
            if db_data:
                db_data.is_reset = True
                await db_data.save(update_fields=["is_reset"])
            if group_id in cls.history_data:
                del cls.history_data[group_id]
        elif user_id:
            # 个人重置
            db_data = (
                await BymChat.filter(user_id=user_id, group_id=None)
                .order_by("-id")
                .first()
            )
            if db_data:
                db_data.is_reset = True
                await db_data.save(update_fields=["is_reset"])
            if user_id in cls.history_data:
                del cls.history_data[user_id]
