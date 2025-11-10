from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from nonebot.adapters.onebot.v11.event import GroupMessageEvent


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
        """获取消息列表"""
        return self.messages

    @property
    def time_range_str(self) -> str:
        """时间范围字符串"""
        return f"{self.start_time.strftime('%Y-%m-%d')} ~ {self.end_time.strftime('%Y-%m-%d')}"


class WordCloudTaskParams(BaseModel):
    """封装一个词云生成任务所需的所有参数"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    start_time: datetime
    end_time: datetime
    group_id: int
    destination_group_id: int

    my: bool = False
    user_id: Optional[int] = None

    event: Optional[GroupMessageEvent] = None
    is_scheduled_task: bool = False

    date_type: Optional[str] = None

    is_yearly: bool = Field(default=False)
    is_today: bool = Field(default=False)

    @property
    def time_range_description(self) -> str:
        """获取时间范围的描述"""
        start_str = self.start_time.strftime("%Y-%m-%d %H:%M")
        stop_str = self.end_time.strftime("%Y-%m-%d %H:%M")

        if self.start_time.date() == self.end_time.date():
            return self.start_time.strftime("%Y-%m-%d")
        return f"{start_str} 至 {stop_str}"


__all__ = ["MessageData", "WordCloudTaskParams"]
