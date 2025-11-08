from datetime import datetime as dt
import uuid
import asyncio
from collections import Counter
from typing import Dict, Optional, Union, Any, cast
from nonebot import get_driver, get_bots
from nonebot.adapters.onebot.v11 import Message, Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Arg
from nonebot.typing import T_State
from nonebot.exception import FinishedException
from nonebot_plugin_alconna import Arparma, Match, At
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.services.log import logger

from .services import (
    DataService,
    TextProcessor,
    TimeService,
    word_cloud_cache,
)
from .generators import WordCloudGenerator
from .models import MessageData, WordCloudTaskParams

_wordcloud_semaphore = asyncio.Semaphore(5)


async def dispatch_wordcloud_task(params: WordCloudTaskParams) -> None:
    """
    统一的词云任务创建与分发函数。
    负责处理缓存检查和调用核心生成逻辑。
    """
    params.is_yearly = word_cloud_cache.is_yearly_request(
        params.start_time, params.end_time
    )

    cache_key = word_cloud_cache.generate_key(params)

    cached_image = word_cloud_cache.get(cache_key)
    if cached_image:
        logger.info(
            f"使用缓存的词云结果: 用户={params.user_id}, 群组={params.group_id}, "
            f"缓存键={cache_key}"
        )
        handler = CloudHandler()
        await handler._send_word_cloud_message_direct(
            cached_image,
            params.my,
            params.destination_group_id,
            params.user_id,
            target_group_id=params.group_id
            if params.group_id != params.destination_group_id
            else None,
            is_cached=True,
            date_type=params.date_type,
            time_range=params.time_range_description,
        )
        return

    handler = CloudHandler()
    await handler._generate_wordcloud_core(params, cache_key)


class CloudHandler:
    """词云命令处理器"""

    def __init__(self):
        self.text_processor = TextProcessor()
        self.generator = WordCloudGenerator()
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
            input_: Union[dt, Message] = Arg(key),
        ):
            if isinstance(input_, dt):
                return

            plaintext = cast(Message, input_).extract_plain_text().strip()
            try:
                # 只接受 YYYY-MM-DD 格式
                parsed_dt = dt.strptime(plaintext, "%Y-%m-%d")
                # 转换为带时区的datetime对象
                state[key] = parsed_dt.astimezone()
            except ValueError:
                await matcher.reject_arg(
                    key, "日期格式不正确，请使用 YYYY-MM-DD 格式，例如 2023-01-15"
                )

        return _key_parser

    async def handle_message(
        self,
        event: GroupMessageEvent,
        state: T_State,
        start: dt,
        stop: dt,
        my: bool,
        target_group_id: Optional[int] = None,
    ) -> None:
        """处理消息并生成词云"""
        group_id = (
            target_group_id if target_group_id is not None else int(event.group_id)
        )

        params = WordCloudTaskParams(
            start_time=start,
            end_time=stop,
            group_id=group_id,
            destination_group_id=event.group_id,
            my=my,
            user_id=int(event.user_id) if my else None,
            event=event,
            date_type=state.get("date_type"),
        )
        await dispatch_wordcloud_task(params)

    async def _generate_wordcloud_core(
        self, params: WordCloudTaskParams, cache_key: str
    ) -> None:
        """统一的词云生成核心逻辑，包含并发控制。"""
        task_id = f"wordcloud_task_{uuid.uuid4().hex[:8]}"
        try:
            group_id = params.group_id
            user_id = params.user_id
            start = params.start_time
            stop = params.end_time
            is_yearly = params.is_yearly
            my = params.my

            logger.info(
                f"开始处理词云任务 {task_id}: 用户={user_id}, 群组={group_id}, "
                f"时间范围={start}~{stop}, 缓存键={cache_key}"
            )

            timeout = 1800 if is_yearly else 1200
            async with _wordcloud_semaphore:
                logger.debug(f"任务 {task_id} 已获取信号量，开始执行。")

                cached_image = word_cloud_cache.get(cache_key)
                if cached_image:
                    logger.info(f"任务 {task_id} 在执行前发现缓存，直接使用。")
                    return

                query_user_id = user_id if my else None
                query_group_id = group_id

                start_tz = self.time_service.convert_to_timezone(start, self.timezone)
                stop_tz = self.time_service.convert_to_timezone(stop, self.timezone)

                if query_group_id is None:
                    logger.error(f"任务 {task_id} 中群组ID为空，无法继续。")
                    return

                word_frequencies: Counter = Counter()
                total_messages_processed = 0
                chunk_size = 50000
                logger.info(f"任务 {task_id}，启动流式处理，批次大小: {chunk_size}")

                stream = DataService.get_messages_stream(
                    query_user_id,
                    query_group_id,
                    (start_tz, stop_tz),
                    chunk_size=chunk_size,
                )

                async for message_chunk in stream:
                    if not message_chunk:
                        continue

                    total_messages_processed += len(message_chunk)
                    logger.debug(
                        f"任务 {task_id} 正在处理消息批次，数量: {len(message_chunk)}，累计: {total_messages_processed}"
                    )

                    config = get_driver().config
                    command_start = tuple(i for i in config.command_start if i)
                    processed_chunk = await self.text_processor.preprocess(
                        message_chunk, command_start
                    )

                    if processed_chunk:
                        chunk_freqs = await self.text_processor.extract_keywords(
                            processed_chunk
                        )
                        word_frequencies.update(chunk_freqs)

                logger.info(
                    f"任务 {task_id} 流式处理完成，共处理 {total_messages_processed} 条消息。"
                )

                if not word_frequencies:
                    logger.warning(f"任务 {task_id} 未能从消息中提取任何关键词。")
                    await self._send_word_cloud_result(None, params)
                    return

                word_frequencies_dict = {
                    k: float(v) for k, v in word_frequencies.items()
                }
                image_bytes = await self._generate_word_cloud(word_frequencies_dict)

                if not image_bytes:
                    logger.warning(f"任务 {task_id} 生成词云图片失败")
                    await self._send_word_cloud_result(None, params)
                    return

                await self._cache_word_cloud_result(image_bytes, params, cache_key)
                await self._send_word_cloud_result(image_bytes, params)
                logger.info(f"词云任务 {task_id} 完成")

        except asyncio.TimeoutError:
            logger.warning(f"词云生成任务 {task_id} 执行超时 ({timeout}秒)")
            if not params.is_scheduled_task:
                await self._send_error_message(
                    "词云生成超时，请稍后再试或缩小时间范围。", at_sender=params.my
                )

        except Exception as e:
            logger.error(f"生成词云任务 {task_id} 发生错误: {e}", e=e)
            if not params.is_scheduled_task:
                await self._send_error_message(
                    f"生成词云时发生错误: {str(e)}", at_sender=params.my
                )

    async def _cache_word_cloud_result(
        self, image_bytes: bytes, params: WordCloudTaskParams, cache_key: str
    ) -> None:
        """缓存词云结果"""
        word_cloud_cache.set(cache_key, image_bytes, params=params)
        logger.info(f"已缓存词云结果: {cache_key}, 日期类型={params.date_type}")

    async def _send_word_cloud_result(
        self, image_bytes: Optional[bytes], params: WordCloudTaskParams
    ) -> None:
        """发送词云结果"""
        logger.info(
            f"开始发送词云消息: 用户={params.user_id}, "
            f"群组={params.group_id}, 类型={params.date_type}"
        )
        is_scheduled = params.is_scheduled_task

        if image_bytes:
            await self._send_word_cloud_message_direct(
                image_bytes,
                params.my,
                params.destination_group_id,
                params.user_id,
                target_group_id=params.group_id
                if params.group_id != params.destination_group_id
                else None,
                is_cached=False,
                date_type=params.date_type,
                time_range=params.time_range_description,
            )
        else:
            if is_scheduled:
                logger.warning(
                    f"定时词云任务失败，群组 {params.group_id} 没有足够数据或生成失败。"
                )
            else:
                msg = MessageUtils.build_message("今天没有足够的数据生成词云。")
                target = PlatformUtils.get_target(
                    group_id=str(params.destination_group_id)
                )
                bots = get_bots()
                bot = next(iter(bots.values()), None)
                if target and bot:
                    await msg.send(target=target, bot=bot, at_sender=params.my)

    async def _get_message_data(
        self,
        event: GroupMessageEvent,
        start: dt,
        stop: dt,
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
        image_bytes: Optional[bytes],
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

            if image_bytes:
                _, content = self._prepare_word_cloud_message(
                    date_type,
                    time_range,
                    target_group_id,
                    my,
                    user_id,
                    image_bytes,
                    is_cached,
                )
            else:
                content = [
                    self._get_cloud_type_from_date_type(date_type) + "：",
                    "今天没有足够的数据生成词云。",
                ]

            msg_content = content
            if my and user_id:
                msg_content = [At(flag="user", target=str(user_id)), *content]

            msg = MessageUtils.build_message(msg_content)  # type: ignore

            target = PlatformUtils.get_target(group_id=str(group_id))
            if not target:
                logger.error(f"无法为群 {group_id} 创建发送目标")
                return

            await msg.send(target=target, bot=bot)
            logger.info(
                f"已成功直接发送{'缓存的' if is_cached else ''}词云消息到群 {group_id}"
            )

        except Exception as e:
            logger.error(f"直接发送词云消息失败: {e}", e=e)

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

    def _get_time_range_description(self, start: dt, stop: dt) -> str:
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

        if my and user_id:
            prefix = f"你的{cloud_type}{time_desc}"
        elif target_group_id:
            prefix = f"群 {target_group_id} 的{cloud_type}{time_desc}"
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
        start: dt,
        stop: dt,
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


__all__ = ["CloudHandler", "dispatch_wordcloud_task"]
