import time

from pydantic import BaseModel, Field
import ujson as json

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import DATA_PATH

base_config = Config.get("mute_setting")


class GroupData(BaseModel):
    count: int
    """次数"""
    time: int
    """检测时长"""
    duration: int
    """禁言时长"""
    message_data: dict = Field(default_factory=dict)
    """消息存储"""


class MuteManager:
    file = DATA_PATH / "group_mute_data.json"

    def __init__(self) -> None:
        self._group_data: dict[str, GroupData] = {}
        if self.file.exists():
            with open(self.file, encoding="utf-8") as f:
                _data = json.load(f)
            for gid, gdata in _data.items():
                self._group_data[gid] = GroupData(
                    count=gdata["count"],
                    time=gdata["time"],
                    duration=gdata["duration"],
                )

    def get_group_data(self, group_id: str) -> GroupData:
        """获取群组数据

        参数:
            group_id: 群组id

        返回:
            GroupData: GroupData
        """
        if group_id not in self._group_data:
            self._group_data[group_id] = GroupData(
                count=base_config.get("MUTE_DEFAULT_COUNT", 10) or 10,
                time=base_config.get("MUTE_DEFAULT_TIME", 7) or 7,
                duration=base_config.get("MUTE_DEFAULT_DURATION", 10) or 10,
            )
        return self._group_data[group_id]

    def reset(self, user_id: str, group_id: str):
        """重置用户检查次数

        参数:
            user_id: 用户id
            group_id: 群组id
        """
        if group_data := self._group_data.get(group_id):
            if user_id in group_data.message_data:
                group_data.message_data[user_id]["count"] = 0

    def save_data(self):
        """保存数据"""
        data = {
            gid: {
                "count": gdata.count,
                "time": gdata.time,
                "duration": gdata.duration,
            }
            for gid, gdata in self._group_data.items()
        }
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def add_message(self, user_id: str, group_id: str, message: str) -> int:
        """添加消息

        参数:
            user_id: 用户id
            group_id: 群组id
            message: 消息内容

        返回:
            int: 禁言时长
        """
        group_data = self.get_group_data(group_id)
        if group_data.duration == 0:
            return 0

        message_data = group_data.message_data
        user_data = message_data.get(user_id)
        now = time.time()

        if not user_data:
            message_data[user_id] = {
                "time": now,
                "count": 1,
                "message": message,
            }
            return 0

        # 超过检测时间窗口，重置计数
        if now - user_data["time"] > group_data.time:
            user_data["time"] = now
            user_data["count"] = 1
            user_data["message"] = message
            return 0

        # 消息内容相似（包含之前的消息），累加计数
        if user_data["message"] in message:
            user_data["count"] += 1
        else:
            user_data["time"] = now
            user_data["count"] = 1

        user_data["message"] = message

        # 检测是否触发刷屏
        if user_data["count"] > group_data.count:
            return group_data.duration

        return 0


mute_manager = MuteManager()
