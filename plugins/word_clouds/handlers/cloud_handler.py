from datetime import datetime
import uuid
import asyncio
from typing import Dict, Optional, Union, Any
from nonebot import get_driver, get_bots
from nonebot.adapters.onebot.v11 import Message, Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Arg
from nonebot.typing import T_State
from nonebot.exception import FinishedException
from nonebot_plugin_alconna import Arparma, Match
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.services.log import logger

from ..services.data_service import DataService
from ..services.text_processor import TextProcessor
from ..services.time_service import TimeService
from ..generators.image_generator import ImageWordCloudGenerator
from ..models.message_model import MessageData
from ..services.cache_service import word_cloud_cache
from ..task_manager import task_manager, TaskPriority


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
        state["date_type"] = select_data

        if select_data in [
            "今日",
            "昨日",
            "本周",
            "上周",
            "本月",
            "上月",
            "本季",
            "年度",
        ]:
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
        state: T_State,
        start: datetime,
        stop: datetime,
        my: bool,
        target_group_id: Optional[int] = None,
    ) -> None:
        """处理消息并生成词云"""
        try:
            user_id = int(event.user_id) if my else None
            group_id = (
                target_group_id if target_group_id is not None else int(event.group_id)
            )
            date_type = state.get("date_type")

            is_yearly = word_cloud_cache.is_yearly_request(start, stop)
            if is_yearly:
                logger.debug(
                    f"检测到年度词云请求: 用户={user_id}, 群组={group_id}, 时间范围={start}~{stop}"
                )

            if hasattr(event, "raw_command") and "年度词云" in event.raw_command:
                is_yearly = True
                logger.debug(f"根据命令名称强制设置为年度词云请求: {event.raw_command}")

            logger.debug(f"使用日期类型生成缓存键: {date_type}")
            cache_key = word_cloud_cache.generate_key(
                user_id, group_id, start, stop, is_yearly, date_type
            )
            logger.debug(f"生成缓存键: {cache_key}, 是否为年度请求: {is_yearly}")

            task_params = self._prepare_task_params(
                event,
                start,
                stop,
                my,
                target_group_id,
                event.group_id,
                event.user_id,
                cache_key,
                is_yearly,
                self._is_today_request(start, stop),
                date_type,
            )

            if await self._try_use_cache(task_params):
                return

            task_id = f"wordcloud_user_{event.user_id}_{uuid.uuid4().hex[:8]}"

            await task_manager.add_task(
                task_id=task_id,
                func=self._process_wordcloud_task,
                args=(
                    event,
                    start,
                    stop,
                    my,
                    target_group_id,
                    event.group_id,
                    event.user_id,
                    cache_key,
                    is_yearly,
                    task_params["is_today"],
                    date_type,
                ),
                priority=TaskPriority.HIGH,
                timeout=1800 if is_yearly else 1200,
            )

            logger.debug(
                f"已将用户 {event.user_id} 的词云生成任务添加到队列，任务ID: {task_id}, 缓存键: {cache_key}"
            )

        except Exception as e:
            if isinstance(e, FinishedException):
                pass
            else:
                logger.error(f"提交词云生成任务时发生错误: {e}", e=e)
                await self._send_error_message(
                    f"提交词云生成任务时发生错误: {str(e)}", at_sender=my
                )

    async def _process_wordcloud_task(
        self,
        event: GroupMessageEvent,
        start: datetime,
        stop: datetime,
        my: bool,
        target_group_id: Optional[int] = None,
        group_id: Optional[int] = None,
        user_id: Optional[int] = None,
        cache_key: Optional[str] = None,
        is_yearly: bool = False,
        is_today: bool = False,
        date_type: Optional[str] = None,
    ) -> None:
        """异步处理词云生成任务"""
        try:
            task_params = self._prepare_task_params(
                event,
                start,
                stop,
                my,
                target_group_id,
                group_id,
                user_id,
                cache_key,
                is_yearly,
                is_today,
                date_type,
            )

            logger.info(
                f"开始处理词云任务: 用户={task_params['user_id']}, 群组={task_params['group_id']}, "
                f"时间范围={start}~{stop}, 缓存键={task_params['cache_key']}"
            )

            if await self._try_use_cache(task_params):
                logger.info(
                    f"任务执行前发现缓存: {task_params['cache_key']}，直接使用缓存结果"
                )
                return

            message_data = await self._get_message_data(
                event, start, stop, my, target_group_id, is_task=True
            )
            if not message_data:
                logger.warning(
                    f"未获取到消息数据: 用户={task_params['user_id']}, 群组={task_params['group_id']}"
                )
                return

            word_frequencies = await self._extract_keywords_from_messages(
                message_data, task_params
            )
            if not word_frequencies:
                return

            image_bytes = await self._generate_word_cloud(word_frequencies)
            if not image_bytes:
                logger.warning(
                    f"生成词云图片失败: 用户={task_params['user_id']}, 群组={task_params['group_id']}"
                )
                return

            await self._cache_word_cloud_result(image_bytes, task_params)

            await self._send_word_cloud_result(image_bytes, task_params)

            logger.info(
                f"词云任务完成: 用户={task_params['user_id']}, 群组={task_params['group_id']}"
            )

        except Exception as e:
            if isinstance(e, FinishedException):
                pass
            else:
                logger.error(f"生成词云时发生错误: {e}", e=e)
                logger.error(f"生成词云过程中发生错误: {str(e)}")

    def _prepare_task_params(
        self,
        event: Optional[GroupMessageEvent],
        start: datetime,
        stop: datetime,
        my: bool,
        target_group_id: Optional[int] = None,
        group_id: Optional[int] = None,
        user_id: Optional[int] = None,
        cache_key: Optional[str] = None,
        is_yearly: bool = False,
        is_today: bool = False,
        date_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """准备任务参数"""
        actual_group_id = group_id or (event.group_id if event else None)
        actual_user_id = user_id or (event.user_id if event else None)

        is_today = self._is_today_request(start, stop)

        return {
            "event": event,
            "start": start,
            "stop": stop,
            "my": my,
            "target_group_id": target_group_id,
            "group_id": actual_group_id,
            "user_id": actual_user_id,
            "cache_key": cache_key,
            "is_yearly": is_yearly,
            "is_today": is_today,
            "date_type": date_type,
            "time_range": self._get_time_range_description(start, stop),
        }

    async def _try_use_cache(self, task_params: Dict[str, Any]) -> bool:
        """尝试使用缓存"""
        cache_key = task_params.get("cache_key")
        if not cache_key:
            return False

        return await self._check_and_use_cache(
            cache_key,
            task_params["my"],
            task_params["group_id"],
            task_params["user_id"],
            task_params["target_group_id"],
            task_params["start"],
            task_params["stop"],
            task_params["date_type"],
            task_params["user_id"],
            task_params["group_id"],
        )

    async def _extract_keywords_from_messages(
        self, message_data: MessageData, task_params: Dict[str, Any]
    ) -> Optional[Dict[str, float]]:
        """从消息中提取关键词"""
        logger.info(f"开始处理文本并提取关键词: 消息数量={len(message_data.messages)}")

        word_frequencies = await self._process_text_and_extract_keywords(message_data)

        if not word_frequencies:
            logger.warning(
                f"未能提取到关键词: 用户={task_params['user_id']}, 群组={task_params['group_id']}"
            )
            return None

        return word_frequencies

    async def _cache_word_cloud_result(
        self, image_bytes: bytes, task_params: Dict[str, Any]
    ) -> None:
        """缓存词云结果"""
        if not task_params["cache_key"]:
            logger.debug(f"任务中重新生成缓存键，日期类型: {task_params['date_type']}")
            task_params["cache_key"] = word_cloud_cache.generate_key(
                task_params["user_id"],
                task_params["group_id"],
                task_params["start"],
                task_params["stop"],
                task_params["is_yearly"],
                task_params["date_type"],
            )

        ttl = self._get_cache_ttl_by_date_type(
            task_params["date_type"], task_params["start"], task_params["stop"]
        )

        persist = not task_params["is_today"]

        word_cloud_cache.set(
            task_params["cache_key"], image_bytes, ttl=ttl, persist=persist
        )
        logger.info(
            f"已缓存词云结果: {task_params['cache_key']}, TTL={ttl}秒, "
            f"持久化={persist}, 日期类型={task_params['date_type']}"
        )

    def _get_cache_ttl_by_date_type(
        self, date_type: Optional[str], start: datetime, stop: datetime
    ) -> int:
        """根据日期类型获取缓存TTL"""
        if date_type in ["本月", "上月"]:
            ttl = word_cloud_cache.monthly_ttl
            logger.debug(f"使用月度缓存TTL: {ttl // 3600}小时")
        elif date_type in ["本周", "上周"]:
            ttl = word_cloud_cache.weekly_ttl
            logger.debug(f"使用周度缓存TTL: {ttl // 3600}小时")
        elif date_type in ["年度"]:
            ttl = word_cloud_cache.yearly_ttl
            logger.debug(f"使用年度缓存TTL: {ttl // 3600}小时")
        elif date_type in ["本季"]:
            ttl = word_cloud_cache.quarterly_ttl
            logger.debug(f"使用季度缓存TTL: {ttl // 3600}小时")
        else:
            ttl = word_cloud_cache.get_ttl(start, stop)
            logger.debug(f"根据时间范围判断使用缓存TTL: {ttl // 3600}小时")

        return ttl

    async def _send_word_cloud_result(
        self, image_bytes: bytes, task_params: Dict[str, Any]
    ) -> None:
        """发送词云结果"""
        logger.info(
            f"开始发送词云消息: 用户={task_params['user_id']}, "
            f"群组={task_params['group_id']}, 类型={task_params['date_type']}"
        )

        await self._send_word_cloud_message_direct(
            image_bytes,
            task_params["my"],
            task_params["group_id"],
            task_params["user_id"],
            task_params["target_group_id"],
            is_cached=False,
            date_type=task_params["date_type"],
            time_range=task_params["time_range"],
        )

    async def _get_message_data(
        self,
        event: GroupMessageEvent,
        start: datetime,
        stop: datetime,
        my: bool,
        target_group_id: Optional[int] = None,
        is_task: bool = False,
    ) -> Optional[MessageData]:
        """获取消息数据"""
        user_id = int(event.user_id) if my else None
        group_id = (
            target_group_id if target_group_id is not None else int(event.group_id)
        )

        start_tz = self.time_service.convert_to_timezone(start, self.timezone)
        stop_tz = self.time_service.convert_to_timezone(stop, self.timezone)

        logger.debug(
            f"开始获取消息数据: 用户={user_id}, 群组={group_id}, 时间范围={start_tz}~{stop_tz}"
        )

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

            if not is_task:
                try:
                    await self._send_error_message(msg, at_sender=my)
                except FinishedException:
                    return None
            else:
                logger.warning(f"任务中获取消息数据失败: {msg}")

            return None

        logger.debug(f"成功获取消息数据: {len(message_data.messages)} 条消息")
        return message_data

    async def _process_text_and_extract_keywords(
        self, message_data: MessageData
    ) -> Optional[Dict[str, float]]:
        """处理文本并提取关键词"""
        logger.debug(
            f"开始处理文本并提取关键词，消息数量: {len(message_data.messages)}"
        )

        config = get_driver().config
        command_start = tuple(i for i in config.command_start if i)

        processed_messages = await self.text_processor.preprocess(
            message_data.get_plain_text(), command_start
        )

        if not processed_messages:
            logger.warning("预处理后没有有效消息")
            return None

        logger.debug(f"预处理后的消息数量: {len(processed_messages)}")

        word_frequencies = await self.text_processor.extract_keywords(
            processed_messages
        )

        if not word_frequencies:
            logger.warning("未能提取到关键词")
            return None

        logger.debug(f"成功提取关键词，词汇数量: {len(word_frequencies)}")
        return word_frequencies

    async def _generate_word_cloud(
        self, word_frequencies: Dict[str, float]
    ) -> Optional[bytes]:
        """生成词云图片"""
        logger.debug(f"开始生成词云图片，词汇数量: {len(word_frequencies)}")

        image_bytes = await self.generator.generate(word_frequencies)

        if not image_bytes:
            logger.warning("生成词云图片失败")
            return None

        logger.debug(f"成功生成词云图片，大小: {len(image_bytes)} 字节")
        return image_bytes

    async def _send_word_cloud_message(
        self,
        event: GroupMessageEvent,
        image_bytes: bytes,
        my: bool,
        target_group_id: Optional[int] = None,
        is_task: bool = True,
    ) -> None:
        """发送词云消息（通过事件）"""
        logger.debug("准备通过事件发送词云消息")
        is_target_group = self._is_target_group(event, target_group_id)

        if is_target_group:
            msg = MessageUtils.build_message(
                [f"群 {target_group_id} 的词云：", image_bytes]
            )
        else:
            msg = MessageUtils.build_message(image_bytes)

        try:
            if is_task:
                await msg.send(at_sender=my)
                logger.debug("已通过任务发送词云消息")
            else:
                await msg.finish(at_sender=my)
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f"发送词云消息失败: {e}", e=e)

    async def _send_word_cloud_message_direct(
        self,
        image_bytes: bytes,
        my: bool,
        group_id: Optional[int],
        user_id: Optional[int],
        target_group_id: Optional[int] = None,
        is_cached: bool = False,
        date_type: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> None:
        """直接发送词云消息（不依赖事件）"""
        if not group_id:
            logger.error("无法发送词云消息：群组ID为空")
            return

        logger.debug(f"准备直接发送词云消息到群 {group_id}")

        try:
            bots = get_bots()
            if not bots:
                logger.error("无法获取任何Bot实例")
                return

            bot = next(iter(bots.values()), None)
            if not bot or not isinstance(bot, Bot):
                logger.error("无法获取有效的Bot实例")
                return

            _, content = self._prepare_word_cloud_message(
                date_type,
                time_range,
                target_group_id,
                group_id,
                my,
                user_id,
                image_bytes,
                is_cached,
            )

            if my and user_id:
                from nonebot_plugin_alconna import At

                content.insert(0, At(flag="user", target=str(user_id)))

            msg = MessageUtils.build_message(content)

            target = PlatformUtils.get_target(group_id=str(group_id))
            if not target:
                logger.error(f"无法为群 {group_id} 创建发送目标")
                return

            max_retries = 3
            for retry in range(max_retries):
                try:
                    await msg.send(target=target, bot=bot)
                    logger.info(
                        f"已成功直接发送{'缓存的' if is_cached else ''}词云消息到群 {group_id}"
                    )
                    return
                except Exception as e:
                    if retry < max_retries - 1:
                        logger.warning(
                            f"发送词云消息失败，将在1秒后重试 ({retry + 1}/{max_retries}): {e}"
                        )
                        await asyncio.sleep(1)
                    else:
                        raise

        except Exception as e:
            logger.error(f"直接发送词云消息失败: {e}", e=e)

            try:
                logger.info("尝试使用替代方法发送消息...")
                cache_status = "缓存的" if is_cached else ""
                await bot.send_group_msg(
                    group_id=group_id,
                    message=f"{cache_status}词云已生成，但发送图片失败: {str(e)}",
                )
                logger.info("已发送错误通知")
            except Exception as e2:
                logger.error(f"发送错误通知也失败: {e2}", e=e2)

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

    async def _send_info_message(
        self, message: str, at_sender: bool = False, reply_to: bool = False
    ) -> None:
        """发送信息消息"""
        try:
            await MessageUtils.build_message(message).send(
                at_sender=at_sender, reply_to=reply_to
            )
        except Exception as e:
            logger.error(f"发送信息消息失败: {e}", e=e)

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

    def _get_time_range_description(self, start: datetime, stop: datetime) -> str:
        """获取时间范围的描述"""
        start_str = start.strftime("%Y-%m-%d %H:%M")
        stop_str = stop.strftime("%Y-%m-%d %H:%M")

        if start.date() == stop.date():
            return f"{start.strftime('%Y-%m-%d')}"
        elif (stop - start).days <= 7:
            return f"{start.strftime('%Y-%m-%d')} 至 {stop.strftime('%Y-%m-%d')}"
        elif start.year == stop.year and start.month == stop.month:
            return f"{start.strftime('%Y-%m-%d')} 至 {stop.strftime('%Y-%m-%d')}"
        elif start.year == stop.year:
            return f"{start.strftime('%Y-%m-%d')} 至 {stop.strftime('%Y-%m-%d')}"
        else:
            return f"{start_str} 至 {stop_str}"

    def _prepare_word_cloud_message(
        self,
        date_type: Optional[str],
        time_range: Optional[str],
        target_group_id: Optional[int],
        group_id: Optional[int],
        my: bool,
        user_id: Optional[int],
        image_bytes: bytes,
        is_cached: bool = False,
    ) -> tuple[str, list]:
        """准备词云消息内容"""
        cloud_type = self._get_cloud_type_from_date_type(date_type)

        time_desc = ""
        if time_range:
            time_desc = f": {time_range}"

        if target_group_id and target_group_id != group_id:
            prefix = f"群 {target_group_id} 的{cloud_type}{time_desc}"
        elif my and user_id:
            prefix = f"{cloud_type}{time_desc}"
        else:
            prefix = f"{cloud_type}{time_desc}"

        if is_cached:
            content = [f"{prefix}(缓存)：", image_bytes]
        else:
            content = [f"{prefix}：", image_bytes]

        return prefix, content

    def _get_cloud_type_from_date_type(self, date_type: Optional[str]) -> str:
        """根据日期类型获取词云类型"""
        if not date_type:
            return "词云"

        cloud_type_map = {
            "今日": "今日词云",
            "昨日": "昨日词云",
            "本周": "本周词云",
            "上周": "上周词云",
            "本月": "本月词云",
            "上月": "上月词云",
            "本季": "本季词云",
            "年度": "年度词云",
            "历史": "历史词云",
        }

        return cloud_type_map.get(date_type, "词云")

    async def _check_and_use_cache(
        self,
        cache_key: str,
        my: bool,
        group_id: Optional[int],
        user_id: Optional[int],
        target_group_id: Optional[int],
        start: datetime,
        stop: datetime,
        date_type: Optional[str],
        log_user_id: Optional[int] = None,
        log_group_id: Optional[int] = None,
    ) -> bool:
        """检查并使用缓存"""
        cached_image = word_cloud_cache.get(cache_key)
        if not cached_image:
            return False

        logger.info(
            f"使用缓存的词云结果: 用户={log_user_id}, 群组={log_group_id}, 缓存键={cache_key}"
        )

        time_range_desc = self._get_time_range_description(start, stop)

        await self._send_word_cloud_message_direct(
            cached_image,
            my,
            group_id,
            user_id,
            target_group_id,
            is_cached=True,
            date_type=date_type,
            time_range=time_range_desc,
        )
        return True

    def _is_today_request(self, start: datetime, stop: datetime) -> bool:
        """检查是否为今日词云请求"""
        today = datetime.now().date()
        return start.date() == stop.date() == today
