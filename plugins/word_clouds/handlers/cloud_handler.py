from datetime import datetime
from typing import Dict, Optional, Union, Any
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Arg
from nonebot.typing import T_State
from nonebot.exception import FinishedException
from nonebot_plugin_alconna import Arparma, Match
from zhenxun.utils.message import MessageUtils
from zhenxun.services.log import logger

from ..services.data_service import DataService
from ..services.text_processor import TextProcessor
from ..services.time_service import TimeService
from ..generators.image_generator import ImageWordCloudGenerator
from ..models.message_model import MessageData


class CloudHandler:
    """词云命令处理器"""

    def __init__(self):
        self.text_processor = TextProcessor()
        self.generator = ImageWordCloudGenerator()
        self.time_service = TimeService()
        self.timezone = "Asia/Shanghai"

    async def handle_first_receive(
        self,
        state: T_State,
        date: Match[str],
        arparma: Arparma,
        z_date: Match[str],
    ) -> Optional[Any]:
        """处理命令并解析参数"""
        state["my"] = arparma.find("my")

        select_data = date.result if date.available else "今日"

        if select_data in ["今日", "昨日", "本周", "本月", "上月", "本季", "年度"]:
            start, stop = self.time_service.get_time_range(select_data)
            state["start"] = start
            state["stop"] = stop
        elif select_data == "历史":
            if z_date.available:
                time_range = self.time_service.parse_time_range(z_date.result)
                if time_range:
                    state["start"], state["stop"] = time_range
                else:
                    return await self._send_error_message(
                        "请输入正确的日期，不然我没法理解呢！", reply_to=True
                    )

        return None

    def parse_datetime(self, key: str):
        """创建日期时间解析器"""

        async def _key_parser(
            matcher: Matcher,
            state: T_State,
            input_: Union[datetime, Message] = Arg(key),
        ):
            if isinstance(input_, datetime):
                return

            plaintext = input_.extract_plain_text()
            try:
                state[key] = self.time_service.get_datetime_fromisoformat_with_timezone(
                    plaintext
                )
            except ValueError:
                await matcher.reject_arg(key, "请输入正确的日期，不然我没法理解呢！")

        return _key_parser

    async def handle_message(
        self,
        event: GroupMessageEvent,
        start: datetime,
        stop: datetime,
        my: bool,
        target_group_id: Optional[int] = None,
    ) -> None:
        """处理消息并生成词云"""
        try:
            message_data = await self._get_message_data(
                event, start, stop, my, target_group_id
            )
            if not message_data:
                return

            word_frequencies = await self._process_text_and_extract_keywords(
                message_data
            )
            if not word_frequencies:
                return

            image_bytes = await self._generate_word_cloud(word_frequencies)
            if not image_bytes:
                return

            await self._send_word_cloud_message(event, image_bytes, my, target_group_id)

        except Exception as e:
            if isinstance(e, FinishedException):
                pass
            else:
                logger.error(f"生成词云时发生错误: {e}", e=e)
                await self._send_error_message(
                    f"生成词云过程中发生错误: {str(e)}", at_sender=my
                )

    async def _get_message_data(
        self,
        event: GroupMessageEvent,
        start: datetime,
        stop: datetime,
        my: bool,
        target_group_id: Optional[int] = None,
    ) -> Optional[MessageData]:
        """获取消息数据"""
        user_id = int(event.user_id) if my else None
        group_id = (
            target_group_id if target_group_id is not None else int(event.group_id)
        )

        start_tz = self.time_service.convert_to_timezone(start, self.timezone)
        stop_tz = self.time_service.convert_to_timezone(stop, self.timezone)

        message_data = await DataService.get_messages(
            user_id,
            group_id,
            (start_tz, stop_tz),
        )

        is_target_group = self._is_target_group(event, target_group_id)

        if not message_data:
            msg = self._format_message(
                "没有获取到{}词云数据", is_target_group, target_group_id
            )
            try:
                await self._send_error_message(msg, at_sender=my)
            except FinishedException:
                return None

        return message_data

    async def _process_text_and_extract_keywords(
        self, message_data: MessageData
    ) -> Optional[Dict[str, float]]:
        """处理文本并提取关键词"""
        config = get_driver().config
        command_start = tuple(i for i in config.command_start if i)

        processed_messages = await self.text_processor.preprocess(
            message_data.get_plain_text(), command_start
        )

        word_frequencies = await self.text_processor.extract_keywords(
            processed_messages
        )

        return word_frequencies

    async def _generate_word_cloud(
        self, word_frequencies: Dict[str, float]
    ) -> Optional[bytes]:
        """生成词云图片"""
        return await self.generator.generate(word_frequencies)

    async def _send_word_cloud_message(
        self,
        event: GroupMessageEvent,
        image_bytes: bytes,
        my: bool,
        target_group_id: Optional[int] = None,
    ) -> None:
        """发送词云消息"""
        is_target_group = self._is_target_group(event, target_group_id)

        if is_target_group:
            msg = MessageUtils.build_message(
                [f"群 {target_group_id} 的词云：", image_bytes]
            )
        else:
            msg = MessageUtils.build_message(image_bytes)

        try:
            await msg.finish(at_sender=my)
        except FinishedException:
            raise

    async def _send_error_message(
        self, message: str, at_sender: bool = False, reply_to: bool = False
    ) -> None:
        """发送错误消息"""
        try:
            await MessageUtils.build_message(message).finish(
                at_sender=at_sender, reply_to=reply_to
            )
        except FinishedException:
            raise

    def _is_target_group(
        self, event: GroupMessageEvent, target_group_id: Optional[int]
    ) -> bool:
        """检查目标群"""
        return target_group_id is not None and target_group_id != int(event.group_id)

    def _format_message(
        self, template: str, is_target_group: bool, target_group_id: Optional[int]
    ) -> str:
        """格式化消息"""
        prefix = f"目标群 {target_group_id} 的" if is_target_group else ""
        return template.format(prefix)
