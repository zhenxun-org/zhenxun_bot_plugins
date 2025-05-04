from datetime import datetime, timedelta
import pytz
import re
from typing import Tuple, Optional


class TimeService:
    """时间处理服务"""

    @staticmethod
    def get_datetime_now_with_timezone() -> datetime:
        """获取当前时间，并包含时区信息"""
        return datetime.now().astimezone()

    @staticmethod
    def get_datetime_fromisoformat_with_timezone(date_string: str) -> datetime:
        """从 iso8601 格式字符串中获取时间，并包含时区信息"""
        return datetime.fromisoformat(date_string).astimezone()

    @staticmethod
    def get_time_range(time_type: str) -> Tuple[datetime, datetime]:
        """根据时间类型获取时间范围"""
        dt = TimeService.get_datetime_now_with_timezone()

        if time_type == "今日":
            start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            stop = dt
        elif time_type == "昨日":
            stop = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            start = stop - timedelta(days=1)
        elif time_type == "本周":
            start = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                days=dt.weekday()
            )
            stop = dt
        elif time_type == "本月":
            start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            stop = dt
        elif time_type == "年度":
            start = dt.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            stop = dt
        else:
            start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            stop = dt

        return start, stop

    @staticmethod
    def parse_time_range(time_str: str) -> Optional[Tuple[datetime, datetime]]:
        """解析时间范围字符串，格式如: 2022-01-01~2022-02-22"""
        if match := re.match(r"^(.+?)(?:~(.+))?$", time_str):
            start_str = match[1]
            stop_str = match[2]

            try:
                start = TimeService.get_datetime_fromisoformat_with_timezone(start_str)
                if stop_str:
                    stop = TimeService.get_datetime_fromisoformat_with_timezone(
                        stop_str
                    )
                else:
                    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
                    stop = start + timedelta(days=1)
                return start, stop
            except ValueError:
                return None

        return None

    @staticmethod
    def convert_to_timezone(
        dt: datetime, timezone_str: str = "Asia/Shanghai"
    ) -> datetime:
        """将时间转换到指定时区"""
        return dt.astimezone(pytz.timezone(timezone_str))
