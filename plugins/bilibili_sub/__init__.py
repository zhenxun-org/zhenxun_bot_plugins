import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import List, cast

import nonebot
from nonebot.drivers import Driver
from nonebot.internal.adapter import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_apscheduler import scheduler

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.models.group_console import GroupConsole
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .config import (AVATAR_CACHE_DIR, BANGUMI_COVER_CACHE_DIR, base_config,
                     check_and_refresh_credential, load_credential_from_file)
from .data_source import (BiliSub, BiliSubTarget, Notification,
                          NotificationType, _get_bangumi_status,
                          get_sub_status)

__plugin_meta__ = PluginMetadata(
    name="B站订阅",
    description="非常便利的B站订阅通知",
    usage="""
## B站订阅
一个功能强大且易于使用的B站订阅插件，支持UP主、直播和番剧。

### 📖 通用指令 (需要群管或更高权限)

*   **`bilisub list`**
    查看当前会话（群聊或私聊）的所有订阅。

*   **`bilisub add [--live] <内容...>`**
    为当前会话添加一个或多个订阅。
    - `<内容>`: **UP主UID**、**直播间ID**、**番剧名称** 或 **番剧ID (ss/ep)**。
    - `--live`: 添加直播间ID时必须使用此参数。
    - **示例**:
        - `bilisub add 732482333` (订阅UP主)
        - `bilisub add --live 21452505` (订阅直播间)
        - `bilisub add 葬送的芙莉莲` (通过名称订阅番剧)

*   **`bilisub del <ID...>`**
    从当前会话删除一个或多个订阅。ID通过 `bilisub list` 查看。

*   **`bilisub config <ID...> <设置...>`**
    为当前会话中的指定订阅ID批量配置推送选项。
    - **推送类型**:
        - `+dynamic` / `-dynamic`: 开启/关闭 **动态** 推送
        - `+video` / `-video`: 开启/关闭 **视频/剧集** 推送
        - `+live` / `-live`: 开启/关闭 **直播** 推送
        - `+all` / `-all`: 开启/关闭 **全部** 推送
    - **艾特全体**:
        - `+at:dynamic` / `-at:dynamic`: 动态推送时@全体
        - `+at:video` / `-at:video`: 视频/剧集推送时@全体
        - `+at:live` / `-at:live`: 直播推送时@全体
        - `+at:all` / `-at:all`: 所有推送都@全体
    - **示例**: `bilisub config 3 4 +live -dynamic +at:live`

*   **`bilisub clear`**
    **[危险]** 清空当前会话的所有订阅，操作前会请求确认。

### 🛠️ 超级用户指令

*   **跨群管理与清空**
    - 在 `add`, `del`, `list` 命令后附加 `-g, --group <群号...>` 参数，可以跨群管理订阅。
    - `bilisub clear -g <群号...>`: 清空**指定群组**的订阅。
    - `bilisub clear --all`: **[高危]** 清空**所有**目标（所有群和私聊）的订阅。

*   **账号与全局管理**
    - `bilisub login`: 通过扫描二维码登录B站账号，以获取和保存凭证。
    - `bilisub status`: 检查当前B站账号凭证的有效状态。
    - `bilisub logout`: 清除已保存的B站凭证，退出登录。
    - `bilisub checkall`: 立即对所有已订阅的项目进行一次更新检查。
    - `bilisub forcepush <ID...>`: 强制推送指定ID订阅的最新内容，无论之前是否已推送。

### ⚙ 配置文件

*   **下面的功能需要在配置文件或WebUI中修改**
    - 检测时间间隔（分钟）
    - 是否开启B站订阅定时休眠
    - 是否开启广告过滤
    - 是否推送动态中的图片

""".strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="1.2",
        configs=[
            RegisterConfig(
                module="bilibili_sub",
                key="ENABLE_AT_ALL",
                value=False,
                help="是否开启B站订阅@全体功能总开关",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="CHECK_TIME",
                value=15,
                help="检测时间间隔（分钟）",
                default_value=15,
                type=int,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="ENABLE_SLEEP_MODE",
                value=True,
                help="是否开启B站订阅定时休眠",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="SLEEP_TIME_RANGE",
                value="01:00-07:30",
                help="休眠时间段 (格式 HH:MM-HH:MM)，例如 '01:00-07:30'",
                default_value="01:00-07:30",
                type=str,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="ENABLE_AD_FILTER",
                value=True,
                help="是否开启广告过滤",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="DEFAULT_UP_PUSH_TYPES",
                value=["dynamic", "video"],
                help="UP主类型订阅默认推送的内容 (可选: dynamic, video, live)",
                default_value=["dynamic", "video", "live"],
                type=list[str],
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="DEFAULT_LIVE_PUSH_TYPES",
                value=["live"],
                help="主播类型订阅默认推送的内容 (可选: dynamic, video, live)",
                default_value=["live"],
                type=list[str],
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="BATCH_SIZE",
                value=8,
                help="每次检查的订阅批次大小",
                default_value=8,
                type=int,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="CACHE_TTL_DAYS",
                value=15,
                help="头像和封面等缓存的有效期(天)",
                default_value=15,
                type=int,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="ENABLE_DYNAMIC_IMAGE",
                value=False,
                help="是否推送动态中的图片",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="BiliBili",
                key="COOKIES",
                value="",
                default_value="",
                help="B站cookies数据，由系统自动管理，请勿手动修改",
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="GROUP_BILIBILI_SUB_LEVEL",
                value="4",
                default_value="4",
                help="群内bilibili订阅需要管理的权限",
            ),
        ],
    ).to_dict(),
)


driver: Driver = nonebot.get_driver()


_current_sub_index = 0
_subs_lock = asyncio.Lock()


@driver.on_startup
async def _():
    await load_credential_from_file()


@scheduler.scheduled_job("cron", hour=4, minute=0)
async def cleanup_bilibili_sub_cache():
    """定时清理B站订阅插件的图片缓存"""
    logger.info("开始执行B站订阅缓存清理任务...")
    ttl_days = base_config.get("CACHE_TTL_DAYS", 30)
    ttl_seconds = ttl_days * 24 * 60 * 60
    now = time.time()
    deleted_count = 0

    async def clean_dir(directory: Path):
        nonlocal deleted_count
        if not directory.exists():
            return
        for f in directory.iterdir():
            if f.is_file():
                try:
                    if now - f.stat().st_mtime > ttl_seconds:
                        f.unlink()
                        deleted_count += 1
                except OSError as e:
                    logger.warning(f"删除缓存文件 {f} 失败: {e}")

    await clean_dir(AVATAR_CACHE_DIR)
    await clean_dir(BANGUMI_COVER_CACHE_DIR)

    logger.info(f"B站订阅缓存清理完成，共删除 {deleted_count} 个过期文件。")


async def _check_and_send_update(
    sub: BiliSub, bot: Bot, force_push: bool = False
) -> int:
    """检查单个订阅并发送更新"""
    update_count = 0
    try:
        logger.info(f"B站订阅检查任务开始检测: UID={sub.uid}, 名称={sub.uname}")

        if sub.uid < 0:
            if not sub.push_video:
                return 0
            notifications = await asyncio.wait_for(
                _get_bangumi_status(sub, force_push=force_push), timeout=30
            )
        else:
            notifications = await asyncio.wait_for(
                get_sub_status(sub, force_push=force_push), timeout=30
            )

        if notifications:
            logger.info(
                f"B站订阅检查任务检测到更新: UID={sub.uid}, 更新数量={len(notifications)}"
            )
            for notification in notifications:
                await send_sub_msg(notification, sub, bot)
            update_count += len(notifications)

    except asyncio.TimeoutError:
        logger.error(f"B站订阅检查任务超时: UID={sub.uid}, 名称={sub.uname}")
    except Exception as e:
        logger.error(
            f"B站订阅检查任务异常: UID={sub.uid}, 错误类型={type(e).__name__}, 错误信息={e}"
        )
        import traceback

        logger.debug(f"B站订阅检查任务异常详细信息:\n{traceback.format_exc()}")
    return update_count


def should_run():
    """判断当前时间是否在运行时间段内"""
    time_range_str = Config.get_config(
        "bilibili_sub", "SLEEP_TIME_RANGE", "01:00-07:30"
    )
    now = datetime.now().time()

    try:
        parts = time_range_str.split("-")
        if len(parts) != 2:
            raise ValueError("时间范围格式错误")

        start_time = datetime.strptime(parts[0].strip(), "%H:%M").time()
        end_time = datetime.strptime(parts[1].strip(), "%H:%M").time()

        if start_time > end_time:
            return end_time <= now < start_time
        else:
            return not (start_time <= now < end_time)

    except (ValueError, IndexError) as e:
        logger.error(f"解析休眠时间配置 '{time_range_str}' 失败: {e}，将默认允许运行。")
        return True


semaphore = asyncio.Semaphore(200)


@scheduler.scheduled_job(
    "interval",
    seconds=Config.get_config("bilibili_sub", "CHECK_TIME", 1) * 60,
    max_instances=500,
    misfire_grace_time=40,
)
async def check_subscriptions():
    """定时任务：检查订阅并发送消息"""
    global _current_sub_index
    start_time = time.time()
    logger.debug(
        f"B站订阅检查任务开始执行 - 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    async with semaphore:
        if base_config.get("ENABLE_SLEEP_MODE") and not should_run():
            logger.debug(
                f"B站订阅检查任务处于休眠时间段，跳过执行 - 当前时间: {datetime.now().strftime('%H:%M:%S')}"
            )
            return

        bots = nonebot.get_bots()
        if not bots:
            logger.warning("B站订阅检查任务未找到可用的机器人实例")
            return

        bot_id, bot_instance = next(iter(bots.items()))
        if not bot_instance:
            logger.warning("B站订阅检查任务未找到有效的机器人实例")
            return

        try:
            await check_and_refresh_credential()

            total_subs = await BiliSub.all().count()

            if total_subs == 0:
                logger.debug("B站订阅检查：数据库中没有订阅，跳过本次检查。")
                return

            batch_size = base_config.get("BATCH_SIZE", 5)
            batch_to_check = []

            async with _subs_lock:
                start_index = _current_sub_index
                end_index = start_index + batch_size

                batch_to_check = (
                    await BiliSub.all().offset(start_index).limit(batch_size)
                )

                _current_sub_index = end_index if end_index < total_subs else 0

                logger.info(
                    f"B站订阅检查任务: "
                    f"本次检查批次 {start_index}-{end_index - 1} (共 {total_subs} 个), "
                    f"批次大小: {len(batch_to_check)}"
                )

            if not batch_to_check:
                logger.info("B站订阅检查任务：当前批次为空，可能是由于索引回绕。")
                return

            tasks = [
                _check_and_send_update(sub, bot_instance) for sub in batch_to_check
            ]
            await asyncio.gather(*tasks)

        except Exception as e:
            logger.error(
                f"B站订阅检查任务批次处理异常: 错误类型={type(e).__name__}, 错误信息={e}"
            )
            import traceback

            logger.debug(
                f"B站订阅检查任务批次处理异常详细信息:\n{traceback.format_exc()}"
            )

    total_duration = time.time() - start_time
    logger.debug(f"B站订阅检查任务执行完成 - 总耗时: {total_duration:.2f}秒")


async def send_sub_msg(notification: Notification, sub: BiliSub, bot: Bot):
    """推送信息"""
    start_time = time.time()
    logger.debug(f"B站订阅推送开始: UID={sub.uid}, 名称={sub.uname}")
    msg_list = notification.content

    temp_group = []
    if not msg_list:
        logger.warning(f"B站订阅推送收到空消息列表: UID={sub.uid}")
        return

    sub_targets: List[str] = cast(
        List[str],
        await BiliSubTarget.filter(subscription_id=sub.id).values_list(
            "target_id", flat=True
        ),
    )
    logger.debug(f"B站订阅推送目标用户数量: {len(sub_targets)}, UID={sub.uid}")

    success_count = 0
    error_count = 0

    for target_id in sub_targets:
        try:
            if target_id.startswith("group_"):
                group_id = target_id.replace("group_", "")
                if group_id in temp_group:
                    continue
                temp_group.append(group_id)
                logger.debug(f"B站订阅推送准备发送到群: {group_id}, UID={sub.uid}")

                try:
                    role_info = await bot.get_group_member_info(
                        group_id=int(group_id),
                        user_id=int(bot.self_id),
                        no_cache=True,
                    )
                    bot_role = role_info["role"]
                    logger.debug(
                        f"B站订阅推送机器人在群 {group_id} 中的角色: {bot_role}"
                    )

                    at_all_msg = None
                    if base_config.get("ENABLE_AT_ALL", True) and bot_role in [
                        "owner",
                        "admin",
                    ]:
                        should_at = False
                        if (
                            notification.type == NotificationType.LIVE
                            and sub.at_all_live
                        ):
                            should_at = True
                        elif (
                            notification.type == NotificationType.VIDEO
                            and sub.at_all_video
                        ):
                            should_at = True
                        elif (
                            notification.type == NotificationType.DYNAMIC
                            and sub.at_all_dynamic
                        ):
                            should_at = True

                        if should_at:
                            at_all_msg = UniMessage.at_all() + "\n"
                            logger.debug(
                                f"B站订阅推送将在群 {group_id} 中@全体成员: UID={sub.uid}"
                            )
                            msg_list.insert(0, at_all_msg)
                except Exception as role_err:
                    logger.warning(
                        f"B站订阅推送获取机器人在群 {group_id} 中的角色失败: {type(role_err).__name__}, {role_err}"
                    )

                if await GroupConsole.is_block_plugin(group_id, "bilibili_sub"):
                    logger.debug(
                        f"B站订阅推送在群 {group_id} 中被禁用，跳过发送: UID={sub.uid}"
                    )
                    continue

                logger.debug(f"B站订阅推送正在发送到群 {group_id}: UID={sub.uid}")
                await PlatformUtils.send_message(
                    bot,
                    user_id=None,
                    group_id=group_id,
                    message=MessageUtils.build_message(msg_list),
                )
                logger.debug(f"B站订阅推送成功发送到群 {group_id}: UID={sub.uid}")
                success_count += 1

                if at_all_msg:
                    msg_list.remove(at_all_msg)

            elif target_id.startswith("private_"):
                user_id = target_id.replace("private_", "")
                logger.debug(f"B站订阅推送准备发送到私聊用户: {user_id}, UID={sub.uid}")
                await PlatformUtils.send_message(
                    bot,
                    user_id=user_id,
                    group_id=None,
                    message=MessageUtils.build_message(msg_list),
                )
                logger.debug(f"B站订阅推送成功发送到私聊用户: {user_id}, UID={sub.uid}")
                success_count += 1

        except Exception as e:
            error_count += 1
            logger.error(
                f"B站订阅推送发生错误: UID={sub.uid}, 错误类型={type(e).__name__}, 错误信息={e}"
            )
            import traceback

            logger.debug(f"B站订阅推送错误详细信息:\n{traceback.format_exc()}")

    total_duration = time.time() - start_time
    logger.info(
        f"B站订阅推送完成: UID={sub.uid}, 成功={success_count}, 失败={error_count}, 耗时={total_duration:.2f}秒"
    )


from . import commands  # noqa: E402, F401
