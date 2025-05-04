import json
import re
import uuid
import asyncio
from typing import Dict, Optional, Tuple

from nonebot import get_bots, get_driver
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot_plugin_apscheduler import scheduler

from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .config import WordCloudConfig
from .generators import ImageWordCloudGenerator
from .services import DataService, TextProcessor, TimeService
from .task_manager import task_manager, TaskPriority

SCHEDULE_FILE = WordCloudConfig.schedule_file_path
JOB_PREFIX = "wordcloud_schedule_"

_schedules: Dict[str, str] = {}

SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)

generator = ImageWordCloudGenerator()
text_processor = TextProcessor()
time_service = TimeService()


def _load_schedules():
    """加载计划任务"""
    global _schedules
    if SCHEDULE_FILE.exists():
        try:
            with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                _schedules = json.load(f)
            logger.debug(f"成功加载词云定时计划: {_schedules}")
        except Exception as e:
            logger.error(f"加载词云定时计划失败: {SCHEDULE_FILE}", e=e)
            _schedules = {}
    else:
        _schedules = {}
        logger.debug("未找到词云定时计划文件，将创建新的。")


def _save_schedules():
    """保存计划任务"""
    try:
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(_schedules, f, ensure_ascii=False, indent=4)
        logger.debug(f"成功保存词云定时计划: {SCHEDULE_FILE}")
    except Exception as e:
        logger.error(f"保存词云定时计划失败: {SCHEDULE_FILE}", e=e)


def _parse_time(time_str: str) -> Tuple[int, int]:
    """解析 HH:MM 或 HHMM 格式的时间"""
    match = re.match(r"^(?:([01]\d|2[0-3]):?([0-5]\d))$", time_str)
    if match:
        if ":" in time_str:
            hour, minute = map(int, time_str.split(":"))
        else:
            hour = int(time_str[:2])
            minute = int(time_str[2:])
        return hour, minute
    raise ValueError("时间格式不正确，请使用 HH:MM 或 HHMM 格式")


async def _generate_and_send_wordcloud(group_id: str):
    """生成并发送词云的实际执行函数"""
    logger.debug(f"开始为群 {group_id} 生成定时词云...")
    start, stop = time_service.get_time_range("今日")
    start_tz = time_service.convert_to_timezone(start, "Asia/Shanghai")
    stop_tz = time_service.convert_to_timezone(stop, "Asia/Shanghai")

    message_data = await DataService.get_messages(
        user_id=None,
        group_id=int(group_id),
        time_range=(start_tz, stop_tz),
    )

    msg_to_send = None
    if message_data and message_data.messages:
        bot = next(iter(get_bots().values()), None)
        if bot and isinstance(bot, V11Bot):
            from nonebot import get_driver

            config = get_driver().config
            command_start = tuple(i for i in config.command_start if i)

            processed_messages = await text_processor.preprocess(
                message_data.get_plain_text(), command_start
            )
            top_k = min(len(message_data.messages), 100000)
            word_frequencies = await text_processor.extract_keywords(
                processed_messages, top_k
            )

            if word_frequencies:
                image_bytes = await generator.generate(word_frequencies)
                if image_bytes:
                    msg_to_send = MessageUtils.build_message(image_bytes)
                else:
                    msg_to_send = MessageUtils.build_message("生成今日词云图片失败。")
            else:
                msg_to_send = MessageUtils.build_message("今天没有足够的数据生成词云。")
        else:
            logger.warning(f"无法找到合适的 Bot 实例为群 {group_id} 发送定时词云")
            return
    else:
        msg_to_send = MessageUtils.build_message("今天没有足够的数据生成词云。")

    if msg_to_send:
        bot = next(iter(get_bots().values()), None)
        if bot and isinstance(bot, V11Bot):
            target = PlatformUtils.get_target(group_id=group_id)
            if target:
                await msg_to_send.send(target=target, bot=bot)
                logger.info(f"已成功向群 {group_id} 发送定时词云。")
            else:
                logger.error(f"无法为群 {group_id} 创建发送目标 Target。")
        else:
            logger.warning(f"无法找到合适的 Bot 实例为群 {group_id} 发送定时词云")


async def _run_scheduled_wordcloud(group_id: str):
    """执行单个群的定时词云任务，通过任务管理器调度"""
    task_id = f"wordcloud_{group_id}_{uuid.uuid4().hex[:8]}"

    try:
        await task_manager.add_task(
            task_id=task_id,
            func=_generate_and_send_wordcloud,
            args=(group_id,),
            priority=TaskPriority.NORMAL,
            timeout=600,
        )
        logger.debug(f"已将群 {group_id} 的词云任务添加到队列，任务ID: {task_id}")
    except Exception as e:
        logger.error(f"为群 {group_id} 添加词云任务到队列失败", e=e)


def _add_job(group_id: str, hour: int, minute: int):
    """添加或更新 APScheduler 任务"""
    job_id = f"{JOB_PREFIX}{group_id}"
    try:
        scheduler.remove_job(job_id)
        logger.debug(f"已移除旧的定时词云任务: {job_id}")
    except Exception:
        pass
    try:
        scheduler.add_job(
            _run_scheduled_wordcloud,
            "cron",
            hour=hour,
            minute=minute,
            id=job_id,
            misfire_grace_time=300,
            args=[group_id],
        )
        logger.debug(
            f"已添加/更新群 {group_id} 的定时词云任务，时间: {hour:02d}:{minute:02d}"
        )
    except Exception as e:
        logger.error(f"添加/更新 APScheduler 任务失败 for {job_id}", e=e)


def _remove_job(group_id: str):
    """移除 APScheduler 任务"""
    job_id = f"{JOB_PREFIX}{group_id}"
    try:
        scheduler.remove_job(job_id)
        logger.debug(f"已成功移除定时词云任务: {job_id}")
        return True
    except Exception:
        logger.warning(f"尝试移除不存在的定时词云任务: {job_id}")
        return False


async def add_schedule(group_id: str, time_str: str) -> Tuple[bool, str]:
    """添加或更新群聊的定时计划"""
    try:
        hour, minute = _parse_time(time_str)
        _schedules[group_id] = f"{hour:02d}:{minute:02d}"
        _add_job(group_id, hour, minute)
        _save_schedules()
        return (
            True,
            f"已为群 {group_id} 设置定时词云，时间为每天 {hour:02d}:{minute:02d}。",
        )
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        logger.error(f"添加群 {group_id} 定时计划时出错", e=e)
        return False, "添加定时计划时发生内部错误。"


async def remove_schedule(group_id: str) -> Tuple[bool, str]:
    """移除群聊的定时计划"""
    removed_from_dict = _schedules.pop(group_id, None)
    removed_from_scheduler = _remove_job(group_id)

    if removed_from_dict or removed_from_scheduler:
        _save_schedules()
        return True, f"已取消群 {group_id} 的定时词云。"
    else:
        return False, f"群 {group_id} 未设置定时词云。"


async def get_schedule_time(group_id: str) -> Optional[str]:
    """获取群聊的定时时间"""
    return _schedules.get(group_id)


async def get_all_schedules() -> Dict[str, str]:
    """获取所有已设置定时任务的群组及其时间

    返回:
        Dict[str, str]: 群组ID到定时时间的映射
    """
    return _schedules.copy()


async def _get_all_bot_groups() -> set:
    """获取所有机器人所在的群组"""
    bot_groups = set()
    for bot in get_bots().values():
        if hasattr(bot, "get_group_list") and callable(bot.get_group_list):
            try:
                groups = await bot.get_group_list()
                for group in groups:
                    if "group_id" in group:
                        bot_groups.add(str(group["group_id"]))
            except Exception as e:
                logger.error("获取机器人群组列表失败", e=e)
    return bot_groups


async def add_schedule_for_all(time_str: str) -> Tuple[int, int, str]:
    """为所有机器人所在的群组添加定时计划"""
    added_count = 0
    failed_count = 0
    try:
        hour, minute = _parse_time(time_str)

        bot_groups = await _get_all_bot_groups()

        if not bot_groups:
            logger.warning("未能获取到机器人所在的群组列表")
            return 0, 0, "未能获取到机器人所在的群组列表，操作取消。"

        logger.debug(f"机器人共在 {len(bot_groups)} 个群组中")

        batch_size = 10
        total_groups = len(bot_groups)

        logger.info(
            f"开始批量添加定时词云任务，共 {total_groups} 个群组，每批 {batch_size} 个"
        )

        for i in range(0, total_groups, batch_size):
            batch_groups = list(bot_groups)[i : i + batch_size]
            logger.debug(
                f"处理第 {i // batch_size + 1} 批，共 {len(batch_groups)} 个群组"
            )

            for group_id in batch_groups:
                try:
                    _schedules[group_id] = f"{hour:02d}:{minute:02d}"
                    _add_job(group_id, hour, minute)
                    added_count += 1
                except Exception as e:
                    logger.error(f"为群 {group_id} 添加定时任务失败", e=e)
                    failed_count += 1

            if added_count > 0:
                _save_schedules()

            if i + batch_size < total_groups:
                await asyncio.sleep(0.5)

        return (
            added_count,
            failed_count,
            f"已为机器人所在的 {added_count} 个群组设置定时词云，时间为每天 {hour:02d}:{minute:02d}。"
            + (f"（{failed_count} 个群组设置失败）" if failed_count > 0 else ""),
        )

    except ValueError as e:
        return 0, 0, str(e)
    except Exception as e:
        logger.error("为所有群组添加定时计划时出错", e=e)
        return added_count, failed_count, "为所有群组设置定时计划时发生内部错误。"


async def remove_schedule_for_all() -> Tuple[int, str]:
    """移除所有已设置定时计划的群组"""
    removed_count = 0
    all_scheduled_groups = list(_schedules.keys())

    if not all_scheduled_groups:
        return 0, "当前没有任何群组设置了定时词云。"

    logger.debug(f"准备移除 {len(all_scheduled_groups)} 个群组的定时词云")

    batch_size = 10
    total_groups = len(all_scheduled_groups)

    logger.info(
        f"开始批量移除定时词云任务，共 {total_groups} 个群组，每批 {batch_size} 个"
    )

    for i in range(0, total_groups, batch_size):
        batch_groups = all_scheduled_groups[i : i + batch_size]
        logger.debug(f"处理第 {i // batch_size + 1} 批，共 {len(batch_groups)} 个群组")

        for group_id in batch_groups:
            if _schedules.pop(group_id, None):
                removed_count += 1
            _remove_job(group_id)

        if removed_count > 0:
            _save_schedules()

        if i + batch_size < total_groups:
            await asyncio.sleep(0.5)

    if removed_count > 0:
        return removed_count, f"已取消 {removed_count} 个群组的定时词云。"
    else:
        return 0, "没有找到需要取消的定时词云任务。"


async def load_and_schedule_on_startup():
    """在启动时加载计划并添加到调度器"""
    _load_schedules()

    all_groups = list(_schedules.items())
    total_groups = len(all_groups)

    if not total_groups:
        logger.debug("没有找到需要加载的定时词云任务")
        return

    logger.info(f"开始加载 {total_groups} 个群组的定时词云任务")

    batch_size = 10

    for i in range(0, total_groups, batch_size):
        batch_groups = all_groups[i : i + batch_size]
        logger.debug(f"处理第 {i // batch_size + 1} 批，共 {len(batch_groups)} 个群组")

        for group_id, time_str in batch_groups:
            try:
                hour, minute = _parse_time(time_str)
                _add_job(group_id, hour, minute)
                logger.debug(
                    f"已加载群 {group_id} 的定时词云任务: {hour:02d}:{minute:02d}"
                )
            except ValueError:
                logger.error(f"加载群 {group_id} 的无效定时时间 '{time_str}'，跳过。")
            except Exception as e:
                logger.error(f"启动时添加群 {group_id} 定时任务失败", e=e)

        if i + batch_size < total_groups:
            await asyncio.sleep(0.5)

    logger.info(f"定时词云任务加载完成，共 {total_groups} 个群组")


driver = get_driver()


@driver.on_startup
async def _():
    await load_and_schedule_on_startup()

    try:
        if hasattr(scheduler, "_scheduler") and hasattr(
            scheduler._scheduler, "executors"
        ):
            threadpool = scheduler._scheduler.executors.get("default")
            if threadpool and hasattr(threadpool, "_max_workers"):
                logger.info(f"当前 APScheduler 线程池大小: {threadpool._max_workers}")
            else:
                logger.debug("无法获取 APScheduler 线程池信息")
    except Exception as e:
        logger.error("获取 APScheduler 配置信息失败", e=e)
