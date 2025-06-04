from datetime import datetime
from typing import Optional, Tuple
from zhenxun.models.chat_history import ChatHistory
from ..models.message_model import MessageData


class DataService:
    """数据服务"""

    @staticmethod
    async def get_messages(
        user_id: Optional[int], group_id: int, time_range: Tuple[datetime, datetime]
    ) -> Optional[MessageData]:
        """获取消息数据"""
        start, stop = time_range

        messages_list = await ChatHistory().get_message(
            uid=user_id,
            gid=group_id,
            type_="group",
            days=(start, stop),
        )

        if not messages_list:
            return None

        return MessageData(
            messages=[i.plain_text for i in messages_list],
            user_id=user_id,
            group_id=group_id,
            start_time=start,
            end_time=stop,
        )
