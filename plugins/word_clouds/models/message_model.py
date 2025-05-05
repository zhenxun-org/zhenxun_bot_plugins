from typing import List, Optional
from datetime import datetime


class MessageData:
    """消息数据模型"""

    def __init__(
        self,
        messages: List[str],
        group_id: int,
        start_time: datetime,
        end_time: datetime,
        user_id: Optional[int] = None,
    ):
        self.messages = messages
        self.user_id = user_id
        self.group_id = group_id
        self.start_time = start_time
        self.end_time = end_time

    def get_plain_text(self) -> List[str]:
        """获取纯文本消息列表"""
        return self.messages

    @property
    def time_range_str(self) -> str:
        """获取时间范围字符串"""
        return f"{self.start_time.strftime('%Y-%m-%d')} ~ {self.end_time.strftime('%Y-%m-%d')}"
