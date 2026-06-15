import asyncio
import re
import time
from typing import Any, cast

from bilibili_api import bangumi, login_v2
from nonebot.adapters import Bot, Event, Message
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    MultiVar,
    Option,
    Query,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_session import EventSession
from nonebot_plugin_waiter import prompt_until

from zhenxun import ui
from zhenxun.models.group_console import GroupConsole
from zhenxun.ui.models import LayoutData, NotebookData, UserInfoBlock
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.rules import admin_check

from .config import clear_credential, get_credential, save_credential_to_file
from .data_source import (
    BiliSub,
    BiliSubTarget,
    Notification,
    _get_bangumi_status,
    add_bangumi_sub,
    add_live_sub,
    add_up_sub,
    get_season_id_from_ep,
    get_sub_status,
    search_bangumi,
)
from .utils import get_cached_avatar, get_cached_bangumi_cover, get_user_card


async def get_target_ids(session: EventSession, gids: Query[list[int]]) -> list[str]:
    """根据命令参数或会话上下文获取目标ID列表"""
    if gids.available and gids.result:
        return [f"group_{gid}" for gid in gids.result]

    target_id = f"group_{session.id2}" if session.id2 else f"private_{session.id1}"
    return [target_id] if target_id else []


def has_group_option(gids: Query[list[int]]) -> bool:
    return gids.available and bool(gids.result)


async def ensure_superuser(bot: Bot, event: Event, action: str = "该操作"):
    if not await SUPERUSER(bot, event):
        await MessageUtils.build_message(f"❌ 只有超级用户才能使用{action}。").finish()


def describe_target(target_id: str) -> str:
    if target_id.startswith("group_"):
        return f"群 {target_id.replace('group_', '')}"
    if target_id.startswith("private_"):
        return f"私聊 {target_id.replace('private_', '')}"
    return target_id


def normalize_config_setting(setting: str) -> str:
    setting = setting.strip().lower()
    if not setting:
        return ""
    if setting[0] in "+-":
        return setting

    compact = (
        setting.replace(" ", "")
        .replace("：", ":")
        .replace("＠", "@")
        .replace("艾特", "@")
        .replace("全体成员", "全体")
    )

    enable_words = ("开", "开启", "启用", "打开")
    disable_words = ("关", "关闭", "禁用", "取消", "停止")
    type_aliases = {
        "动态": "dynamic",
        "dynamic": "dynamic",
        "视频": "video",
        "投稿": "video",
        "剧集": "video",
        "番剧": "video",
        "video": "video",
        "直播": "live",
        "live": "live",
        "全部": "all",
        "全": "all",
        "all": "all",
    }

    def pick_type(text: str) -> str:
        for alias, key in type_aliases.items():
            if alias in text:
                return key
        return ""

    at_mode = "@" in compact
    key = pick_type(compact)
    if not key:
        return setting

    value = None
    if compact in ("全开", "全部开", "全部开启", "开启全部", "打开全部"):
        value = True
    elif compact in ("全关", "全部关", "全部关闭", "关闭全部", "取消全部"):
        value = False
    else:
        for word in disable_words:
            if compact.startswith(word) or compact.endswith(word):
                value = False
                break
        if value is None:
            for word in enable_words:
                if compact.startswith(word) or compact.endswith(word):
                    value = True
                    break
        if value is None and at_mode and not compact.startswith(("不", "取消", "关")):
            value = True

    if value is None:
        return setting

    prefix = "+" if value else "-"
    return f"{prefix}at:{key}" if at_mode else f"{prefix}{key}"


async def get_subs_by_targets(target_ids: list[str]) -> list[BiliSub]:
    targets = await BiliSubTarget.filter(target_id__in=target_ids).prefetch_related(
        "subscription"
    )
    subs: dict[int, BiliSub] = {}
    for target in targets:
        subs[target.subscription.id] = target.subscription
    return sorted(subs.values(), key=lambda sub: sub.id)


async def send_notification_to_targets(
    notification: Notification,
    bot: Bot,
    target_ids: list[str],
) -> int:
    success_count = 0
    for target_id in target_ids:
        try:
            if target_id.startswith("group_"):
                await PlatformUtils.send_message(
                    bot,
                    user_id=None,
                    group_id=target_id.replace("group_", ""),
                    message=MessageUtils.build_message(notification.content),
                )
                success_count += 1
            elif target_id.startswith("private_"):
                await PlatformUtils.send_message(
                    bot,
                    user_id=target_id.replace("private_", ""),
                    group_id=None,
                    message=MessageUtils.build_message(notification.content),
                )
                success_count += 1
        except Exception as e:
            logger.error(f"B站订阅定向推送失败: target={target_id}, 错误={e}")
    return success_count


bilisub_cmd = Alconna(
    "bilisub",
    Subcommand(
        "add",
        Option("--live|--直播"),
        Args["ids", MultiVar(str)],
        Option("-g|--group|--群", Args["gids", MultiVar(int)]),
        alias=["添加", "订阅", "新增"],
    ),
    Subcommand(
        "del",
        Args["db_ids", MultiVar(int)],
        Option("-g|--group|--群", Args["gids", MultiVar(int)]),
        alias=["删除", "取消", "退订"],
    ),
    Subcommand(
        "config",
        Args["params", MultiVar(str)],
        Option("-g|--group|--群", Args["gids", MultiVar(int)]),
        alias=["设置", "配置", "开关"],
    ),
    Subcommand(
        "list",
        Option("-g|--group|--群", Args["gids", MultiVar(int)]),
        alias=["列表", "查看"],
    ),
    Subcommand("targets", alias=["群列表"]),
    Subcommand(
        "clear",
        Option("--all|--全部"),
        Option("-g|--group|--群", Args["gids", MultiVar(int)]),
        alias=["清空"],
    ),
    Subcommand("login", alias=["登录"]),
    Subcommand("status", alias=["状态", "登录状态"]),
    Subcommand("logout", alias=["退出", "退出登录"]),
    Subcommand(
        "checkall",
        Option("-g|--group|--群", Args["gids", MultiVar(int)]),
        alias=["检查", "检查全部"],
    ),
    Subcommand(
        "forcepush",
        Args["db_ids", MultiVar(int)],
        Option("-g|--group|--群", Args["gids", MultiVar(int)]),
        alias=["补发", "强推", "强制推送"],
    ),
)


bilisub_matcher = on_alconna(
    bilisub_cmd,
    aliases={"B站订阅", "b站订阅", "哔站订阅", "B订阅"},
    priority=5,
    block=True,
    rule=admin_check("bilibili_sub", "GROUP_BILIBILI_SUB_LEVEL"),
)

login_sessions: dict[str, tuple[login_v2.QrCodeLogin, float]] = {}


@bilisub_matcher.assign("list")
async def handle_list(
    bot: Bot,
    event: Event,
    session: EventSession,
    gids: Query[list[int]] = Query("list.group.gids", []),
):
    if has_group_option(gids):
        await ensure_superuser(bot, event, "-g 参数")

    target_ids = await get_target_ids(session, gids)
    if not target_ids:
        await MessageUtils.build_message("未能确定操作目标，请检查指令。").finish()

    targets = await BiliSubTarget.filter(target_id__in=target_ids).prefetch_related(
        "subscription"
    )
    subs = [t.subscription for t in targets]

    if not subs:
        if len(target_ids) == 1:
            msg = "该群目前没有任何订阅..." if session.id2 else "您目前没有任何订阅..."
        else:
            msg = f"指定的 {len(target_ids)} 个目标群组目前没有任何订阅..."
        await MessageUtils.build_message(msg).finish()

    notebook = NotebookData(elements=[])
    if len(target_ids) == 1:
        notebook.head("B站订阅列表", level=1)
    else:
        notebook.head(f"B站订阅列表 ({len(target_ids)} 个目标群组)", level=1)
    notebook.text("使用 `bilisub del <ID>` 或 `bilisub config <ID> ...` 来管理订阅。")

    for sub in sorted(subs, key=lambda s: s.id):
        face_url = ""
        avatar_path = None
        if sub.uid < 0:
            try:
                b_obj = bangumi.Bangumi(ssid=-sub.uid)
                meta_info = await b_obj.get_overview()
                cover_url = meta_info.get("cover", "")
                if cover_url:
                    avatar_path = await get_cached_bangumi_cover(-sub.uid, cover_url)
            except Exception as e:
                logger.warning(f"获取番剧 {-sub.uid} 的信息失败: {e}")
        else:
            try:
                card_info = await get_user_card(sub.uid)
                if card_info:
                    face_url = card_info.get("face", "")
            except Exception as e:
                logger.warning(f"获取UID {sub.uid} 的用户信息失败: {e}")
            avatar_path = await get_cached_avatar(sub.uid, face_url)
        avatar_uri = avatar_path.absolute().as_uri() if avatar_path else ""

        if sub.uid < 0:
            subtitle = f"番剧 | Season ID: {-sub.uid}"
        else:
            subtitle = f"UID: {sub.uid} | 房间号: {sub.room_id or '无'}"

        user_block = UserInfoBlock(
            name=f"[{sub.id}] {sub.uname or '未知名称'}",
            avatar_url=avatar_uri,
            subtitle=subtitle,
        )
        notebook.add_component(user_block)

        status_layout = LayoutData.row(gap="8px", align_items="center")

        if sub.uid < 0:
            badge_text = "@ 剧集" if sub.at_all_video else "剧集推送"
            color_scheme = "success" if sub.push_video else "info"
            status_layout.add_item(ui.badge(badge_text, color_scheme=color_scheme))
        else:
            dynamic_text = "@ 动态" if sub.at_all_dynamic else "动态"
            dynamic_color = "success" if sub.push_dynamic else "info"
            status_layout.add_item(ui.badge(dynamic_text, color_scheme=dynamic_color))

            video_text = "@ 视频" if sub.at_all_video else "视频"
            video_color = "success" if sub.push_video else "info"
            status_layout.add_item(ui.badge(video_text, color_scheme=video_color))

            live_text = "@ 直播" if sub.at_all_live else "直播"
            live_color = "success" if sub.push_live else "info"
            status_layout.add_item(ui.badge(live_text, color_scheme=live_color))

        notebook.add_component(status_layout.build())
        # 创建一个自定义的分隔线组件并添加
        custom_divider = ui.divider(color="#fce4ec", thickness="1px", margin="25px 0")
        notebook.add_component(custom_divider)

    img_bytes = await ui.render(notebook, use_cache=False)
    await MessageUtils.build_message(img_bytes).finish()


@bilisub_matcher.assign("targets")
async def handle_targets(bot: Bot, event: Event):
    await ensure_superuser(bot, event)

    target_ids = cast(
        list[str],
        await BiliSubTarget.all().distinct().values_list("target_id", flat=True),
    )
    if not target_ids:
        await MessageUtils.build_message("目前没有任何群或私聊添加过B站订阅。").finish()

    group_ids = [
        target_id.replace("group_", "")
        for target_id in target_ids
        if target_id.startswith("group_")
    ]
    group_map = {}
    if group_ids:
        groups = await GroupConsole.filter(group_id__in=group_ids).all()
        group_map = {str(group.group_id): group.group_name for group in groups}

    lines = ["已添加B站订阅的目标："]
    total_sub_count = 0
    for target_id in sorted(target_ids):
        sub_count = await BiliSubTarget.filter(target_id=target_id).count()
        total_sub_count += sub_count
        if target_id.startswith("group_"):
            group_id = target_id.replace("group_", "")
            group_name = group_map.get(group_id) or "未知群名"
            lines.append(f"- 群 {group_id}（{group_name}）：{sub_count} 个订阅")
        elif target_id.startswith("private_"):
            user_id = target_id.replace("private_", "")
            lines.append(f"- 私聊 {user_id}：{sub_count} 个订阅")
        else:
            lines.append(f"- {target_id}：{sub_count} 个订阅")

    lines.append(f"\n合计：{len(target_ids)} 个目标，{total_sub_count} 个订阅关系。")
    await MessageUtils.build_message("\n".join(lines)).finish()


@bilisub_matcher.assign("add")
async def handle_add(
    bot: Bot,
    event: Event,
    session: EventSession,
    live: Query[Any] = Query("add.live"),
    ids: Query[list[str]] = Query("add.ids", []),
    gids: Query[list[int]] = Query("add.group.gids", []),
    matcher: Matcher = Matcher(),
):
    if has_group_option(gids):
        await ensure_superuser(bot, event, "-g 参数")

    target_ids = await get_target_ids(session, gids)
    if not target_ids:
        await MessageUtils.build_message("未能确定操作目标，请检查指令。").finish()

    if not ids.available:
        await MessageUtils.build_message(
            "请提供至少一个UP主UID、直播间ID、番剧ID(ss/ep)或番剧名称。"
        ).finish()

    results = []
    for target_id in target_ids:
        group_str = f" [目标: {describe_target(target_id)}]"
        for bilibili_id_str in ids.result:
            bilibili_id_str = bilibili_id_str.strip()

            if bilibili_id_str.lower().startswith("ss"):
                season_id = int(bilibili_id_str[2:])
                result = await add_bangumi_sub(season_id, target_id)
            elif bilibili_id_str.lower().startswith("ep"):
                ep_id = int(bilibili_id_str[2:])
                season_id = await get_season_id_from_ep(ep_id)
                if season_id:
                    result = await add_bangumi_sub(season_id, target_id)
                else:
                    result = f"❌ 未能找到 ep{ep_id} 对应的番剧信息。"
            elif not bilibili_id_str.isdigit():
                search_results = await search_bangumi(bilibili_id_str)
                if not search_results:
                    result = f"❌ 未搜索到名为「{bilibili_id_str}」的番剧。"
                elif len(search_results) == 1:
                    season_id = search_results[0]["season_id"]
                    result = await add_bangumi_sub(season_id, target_id)
                else:
                    notebook = NotebookData(elements=[])
                    notebook.head(
                        f"🔍 找到多个与「{bilibili_id_str}」相关的番剧", level=2
                    )
                    notebook.text(
                        "请在 60 秒内回复数字序号进行选择，或回复「退出」取消操作。"
                    )

                    for i, item in enumerate(search_results[:10]):
                        cover_path = await get_cached_bangumi_cover(
                            item["season_id"], item.get("cover", "")
                        )
                        cover_uri = cover_path.absolute().as_uri() if cover_path else ""
                        clean_title = re.sub(r"<em.*?>(.*?)</em>", r"\1", item["title"])
                        user_block = UserInfoBlock(
                            name=f"[{i + 1}] {clean_title}",
                            avatar_url=cover_uri,
                            subtitle=f"Season ID: {item['season_id']}",
                        )
                        notebook.add_component(user_block)

                    img_bytes = await ui.render(notebook, use_cache=False)
                    choice_msg = MessageUtils.build_message(img_bytes)

                    def check_choice(msg: Message):
                        text = msg.extract_plain_text().strip()
                        if text in ["退出", "取消"]:
                            return True
                        return text.isdigit() and 1 <= int(text) <= len(search_results)

                    choice = await prompt_until(
                        choice_msg,  # type: ignore
                        check_choice,
                        timeout=60,
                        retry=3,
                        retry_prompt="输入无效，请重新输入正确的数字序号或「退出」。",
                    )

                    if choice:
                        text = choice.extract_plain_text().strip()
                        if text.isdigit():
                            selected_index = int(text) - 1
                            season_id = search_results[selected_index]["season_id"]
                            result = await add_bangumi_sub(season_id, target_id)
                        else:
                            result = "ℹ️ 操作已取消。"
                    else:
                        result = "ℹ️ 操作超时，已取消选择。"
            else:
                bilibili_id = int(bilibili_id_str)
                if live.available:
                    result = await add_live_sub(bilibili_id, target_id)
                else:
                    result = await add_up_sub(bilibili_id, target_id)
            results.append(f"{result}{group_str}")

    await MessageUtils.build_message("\n---\n".join(results)).finish()


@bilisub_matcher.assign("del")
async def handle_del(
    bot: Bot,
    event: Event,
    session: EventSession,
    db_ids: Query[list[int]] = Query("del.db_ids"),
    gids: Query[list[int]] = Query("del.group.gids", []),
):
    if has_group_option(gids):
        await ensure_superuser(bot, event, "-g 参数")

    target_ids = await get_target_ids(session, gids)
    if not target_ids:
        await MessageUtils.build_message("未能确定操作目标，请检查指令。").finish()

    if not db_ids.available:
        await MessageUtils.build_message(
            "请提供至少一个要删除的订阅ID (通过 `bilisub list` 查看)。"
        ).finish()

    total_deleted_count = 0
    fail_list = []
    for db_id in db_ids.result:
        deleted_for_id = await BiliSubTarget.filter(
            subscription_id=db_id, target_id__in=target_ids
        ).delete()
        if deleted_for_id > 0:
            total_deleted_count += deleted_for_id
        else:
            fail_list.append(str(db_id))

    await BiliSubTarget.clean_orphaned_subs()

    msg = f"成功从 {len(target_ids)} 个目标中删除了 {total_deleted_count} 个订阅关系。"
    if fail_list:
        msg += f"\n未能删除对ID {', '.join(fail_list)} 的订阅关系 (可能ID错误或不属于目标群组)。"

    await MessageUtils.build_message(msg).finish()


@bilisub_matcher.assign("config")
async def handle_config(
    bot: Bot,
    event: Event,
    session: EventSession,
    params: Query[list[str]] = Query("config.params"),
    gids: Query[list[int]] = Query("config.group.gids", []),
):
    if has_group_option(gids):
        await ensure_superuser(bot, event, "-g 参数")

    target_ids = await get_target_ids(session, gids)
    if not target_ids:
        await MessageUtils.build_message("未能确定操作目标，请检查指令。").finish()

    if not params.available:
        await MessageUtils.build_message(
            "用法错误: `bilisub config <ID...> [+|-][类型...] [-g 群号...]`"
        ).finish()

    param_list = params.result
    db_ids = [int(p) for p in param_list if p.isdigit()]
    settings = [normalize_config_setting(p) for p in param_list if not p.isdigit()]

    if not db_ids or not settings:
        await MessageUtils.build_message(
            "用法错误: `bilisub config <ID...> [+|-][类型...] [-g 群号...]`"
        ).finish()

    owned_subs: list[int] = cast(
        list[int],
        await BiliSubTarget.filter(
            target_id__in=target_ids, subscription_id__in=db_ids
        ).values_list("subscription_id", flat=True),
    )
    valid_ids = set(owned_subs)
    invalid_ids = set(db_ids) - valid_ids

    if not valid_ids:
        await MessageUtils.build_message(
            f"你没有权限配置ID为 {', '.join(map(str, invalid_ids))} 的订阅。"
        ).finish()

    updates = {}
    for setting in settings:
        if not setting or setting[0] not in "+-":
            continue

        value = setting.startswith("+")

        if setting.startswith(("+at:", "-at:")):
            key = setting[4:]
            at_mapping = {
                "dynamic": "at_all_dynamic",
                "video": "at_all_video",
                "live": "at_all_live",
            }
            if key in at_mapping:
                updates[at_mapping[key]] = value
            elif key == "all":
                for field in at_mapping.values():
                    updates[field] = value
            continue

        key = setting[1:]
        bangumi_subs = await BiliSub.filter(id__in=list(valid_ids), uid__lt=0)
        is_bangumi_sub = len(bangumi_subs) > 0

        if key in ["动态", "dynamic"] and not is_bangumi_sub:
            updates["push_dynamic"] = value
        elif key in ["视频", "video", "剧集"]:
            updates["push_video"] = value
        elif key in ["直播", "live"] and not is_bangumi_sub:
            updates["push_live"] = value
        elif key in ["全部", "all"] and not is_bangumi_sub:
            updates.update(
                {"push_dynamic": value, "push_video": value, "push_live": value}
            )

    if not updates:
        await MessageUtils.build_message(
            "未提供有效的配置项（如: +live, -动态, +at:live）。"
        ).finish()

    await BiliSub.filter(id__in=list(valid_ids)).update(**updates)

    msg = (
        f"已为订阅ID {', '.join(map(str, valid_ids))} 更新了推送设置。\n"
        f"目标: {', '.join(describe_target(t) for t in target_ids)}"
    )
    if invalid_ids:
        msg += f"\n无法配置ID: {', '.join(map(str, invalid_ids))} (权限不足或ID错误)。"

    await MessageUtils.build_message(msg).finish()


@bilisub_matcher.assign("clear")
async def handle_clear(
    bot: Bot,
    event: Event,
    matcher: Matcher,
    session: EventSession,
    arp: Arparma,
):
    use_g = arp.query("clear.group") is not None
    use_all = arp.query("clear.all") is not None
    if use_g or use_all:
        if not await SUPERUSER(bot, event):
            await MessageUtils.build_message(
                "❌ 只有超级用户才能使用 --all 或 -g 参数。"
            ).finish()

    target_ids: list[str] = []
    description = ""
    if use_all:
        target_ids = [
            str(x)
            for x in await BiliSubTarget.all()
            .distinct()
            .values_list("target_id", flat=True)
        ]
        description = f"所有 {len(target_ids)} 个目标"
    else:
        gids_tuple = arp.query("clear.group.gids")
        if gids_tuple:
            target_ids = [f"group_{gid}" for gid in gids_tuple]
            description = f"{len(target_ids)} 个指定目标"
        else:
            target_id = (
                f"group_{session.id2}" if session.id2 else f"private_{session.id1}"
            )
            target_ids = [target_id] if target_id else []
            description = "当前会话"

    if not target_ids:
        await MessageUtils.build_message("未能确定操作目标，请检查指令。").finish()

    subs_to_delete_count = await BiliSubTarget.filter(target_id__in=target_ids).count()

    if subs_to_delete_count == 0:
        await MessageUtils.build_message("当前没有任何订阅可供清空。").finish()

    confirm_msg = f"⚠️ 你确定要清空「{description}」的 {subs_to_delete_count} 个订阅吗？\n请在30秒内回复【确认/是/yes】以继续，回复【否/取消/no】或其它内容将取消操作。"

    def check_confirm(msg: Message):
        reply_text = msg.extract_plain_text().strip().lower()
        return reply_text in ["确认", "是", "yes", "否", "取消", "no"]

    confirmed = await prompt_until(confirm_msg, check_confirm, timeout=30)

    if confirmed:
        reply_text = confirmed.extract_plain_text().strip().lower()
        if reply_text in ["确认", "是", "yes"]:
            deleted_count = await BiliSubTarget.filter(
                target_id__in=target_ids
            ).delete()
            await BiliSubTarget.clean_orphaned_subs()
            msg = f"✅ 已成功清空「{description}」的 {deleted_count} 个订阅。"
            await MessageUtils.build_message(msg).finish()
        else:
            await MessageUtils.build_message("ℹ️ 操作已取消。").finish()
    else:
        await MessageUtils.build_message("⌛ 操作超时，已自动取消。").finish()


@bilisub_matcher.assign("login")
async def handle_login(bot: Bot, event: Event, matcher: Matcher, session: EventSession):
    await ensure_superuser(bot, event)

    user_id = session.id1
    if not user_id:
        await MessageUtils.build_message("无法获取用户ID，无法开始登录。").finish()

    timeout_duration = 30

    if user_id in login_sessions:
        _, start_time = login_sessions[user_id]
        elapsed_time = time.time() - start_time

        if elapsed_time > timeout_duration:
            del login_sessions[user_id]
            await MessageUtils.build_message(
                f"您上一个登录会话已超时（超过{timeout_duration}秒），已自动取消。\n现在为您创建新的登录会话..."
            ).send()
        else:
            remaining_time = int(timeout_duration - elapsed_time)
            await MessageUtils.build_message(
                f"您已有一个登录会话正在进行中，请在 {remaining_time} 秒内完成或等待超时后重试。"
            ).finish()
            return

    try:
        login_handler = login_v2.QrCodeLogin(platform=login_v2.QrCodeLoginChannel.WEB)
        login_sessions[user_id] = (login_handler, time.time())
        await login_handler.generate_qrcode()

        qr_picture_obj = login_handler.get_qrcode_picture()
        if not qr_picture_obj or not qr_picture_obj.content:
            await MessageUtils.build_message("获取二维码图像失败，请重试。").finish()
            return

        msg_parts = ["请使用B站APP扫描二维码登录：", qr_picture_obj.content]
        await MessageUtils.build_message(msg_parts).send()

        asyncio.create_task(check_login_status(matcher, user_id))
    except Exception as e:
        login_sessions.pop(user_id, None)
        await MessageUtils.build_message(f"生成登录二维码失败: {e}").finish()


async def check_login_status(matcher: Matcher, user_id: str):
    """后台轮询检查二维码登录状态，并在成功或失败时通知用户"""
    if user_id not in login_sessions:
        return

    login_handler, start_time = login_sessions[user_id]
    timeout = 120
    scan_message_sent = False

    logger.info(f"开始为用户 {user_id} 自动检查登录状态...")

    while time.time() - start_time < timeout:
        try:
            status = await login_handler.check_state()

            if status == login_v2.QrCodeLoginEvents.DONE:
                credential = login_handler.get_credential()
                await save_credential_to_file(credential)
                dedeuserid = getattr(credential, "dedeuserid", "未知")
                await matcher.send(f"🎉 登录成功！账号UID {dedeuserid} 的凭证已保存。")
                break
            elif status == login_v2.QrCodeLoginEvents.TIMEOUT:
                await matcher.send("二维码已过期，请重新发送 `bilisub login` 获取。")
                break
            elif status == login_v2.QrCodeLoginEvents.SCAN and not scan_message_sent:
                await matcher.send("已扫码，请在手机上确认登录...")
                scan_message_sent = True

            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"检查用户 {user_id} 登录状态时出错", e=e)
            await matcher.send("检查登录状态时发生错误，流程已终止。")
            break

    login_sessions.pop(user_id, None)


@bilisub_matcher.assign("status")
async def handle_status(bot: Bot, event: Event, session: EventSession):
    await ensure_superuser(bot, event)

    user_id = session.id1
    if not user_id:
        await MessageUtils.build_message("无法获取用户ID，无法检查状态。").send()
        return

    if user_id in login_sessions:
        login_session, _ = login_sessions[user_id]
        try:
            status = await login_session.check_state()
            if status == login_v2.QrCodeLoginEvents.DONE:
                credential = login_session.get_credential()
                await save_credential_to_file(credential)
                del login_sessions[user_id]
                dedeuserid = getattr(credential, "dedeuserid", "未知")
                await MessageUtils.build_message(
                    f"🎉 登录成功！账号UID {dedeuserid} 的凭证已保存。"
                ).send()
                return
            elif status == login_v2.QrCodeLoginEvents.TIMEOUT:
                del login_sessions[user_id]
                await MessageUtils.build_message(
                    "二维码已过期，请重新发送 `bilisub login` 获取新的二维码。"
                ).send()
                return
            elif status == login_v2.QrCodeLoginEvents.SCAN:
                await MessageUtils.build_message("已扫码，请在手机上确认登录...").send()
                return
            else:
                await MessageUtils.build_message("等待扫码中...").send()
                return
        except Exception as e:
            login_sessions.pop(user_id, None)
            await MessageUtils.build_message(f"检查登录状态失败: {e}").send()
            return
        return

    credential = get_credential()
    if not credential:
        await MessageUtils.build_message(
            "当前未登录B站账号。\n请使用 `bilisub login` 扫码登录。"
        ).send()
        return

    status_lines = ["B站登录凭证状态："]
    try:
        is_valid = await credential.check_valid()
        if is_valid:
            uid = getattr(credential, "dedeuserid", "未知")
            status_lines.append(f"✅ 凭证有效，当前登录账号UID: {uid}")
            need_refresh = await credential.check_refresh()
            if need_refresh:
                status_lines.append("⚠️ 凭证即将过期，将在下次定时检查时自动刷新。")
        else:
            status_lines.append("❌ 凭证已失效，请使用 `bilisub login` 重新登录。")
    except Exception as e:
        logger.error("检查凭证有效性时出错", e=e)
        status_lines.append(f"❓ 凭证状态检查失败: {e}")

    await MessageUtils.build_message("\n".join(status_lines)).send()


@bilisub_matcher.assign("logout")
async def handle_logout(bot: Bot, event: Event):
    await ensure_superuser(bot, event)

    try:
        credential = get_credential()
        if not credential:
            await MessageUtils.build_message("当前没有已登录的账号。").send()
            return

        uid = getattr(credential, "dedeuserid", "未知")
        await clear_credential()
        await MessageUtils.build_message(f"账号 {uid} 已退出登录").send()

    except Exception as e:
        await MessageUtils.build_message(f"退出登录失败: {e}").finish()


@bilisub_matcher.assign("checkall")
async def handle_check_all(
    bot: Bot,
    event: Event,
    matcher: Matcher,
    gids: Query[list[int]] = Query("checkall.group.gids", []),
):
    await ensure_superuser(bot, event)

    from . import send_sub_msg

    target_ids: list[str] = []
    if has_group_option(gids):
        target_ids = [f"group_{gid}" for gid in gids.result]
        await matcher.send(
            f"开始主动检查 {len(target_ids)} 个指定群的B站订阅，请稍候..."
        )
    else:
        await matcher.send("开始主动检查所有B站订阅，请稍候...")

    if PlatformUtils.get_platform_scope(bot) != "qq_client":
        await MessageUtils.build_message(
            "B站订阅主动检查需要 OneBot 协议端执行，请在协议端使用。"
        ).finish()

    if target_ids:
        all_subs = await get_subs_by_targets(target_ids)
    else:
        all_subs = await BiliSub.all()

    if not all_subs:
        await MessageUtils.build_message("没有找到需要检查的订阅。").finish()

    async def _check_sub_and_send(sub: BiliSub) -> int:
        """检查单个订阅并发送更新，确保不强制推送。"""
        try:
            notifications: list[Notification] = []
            if sub.uid < 0:
                if not sub.push_video:
                    return 0
                notifications = await asyncio.wait_for(
                    _get_bangumi_status(sub, force_push=False), timeout=30
                )
            else:
                notifications = await asyncio.wait_for(
                    get_sub_status(sub, force_push=False), timeout=30
                )
            if notifications:
                for notification in notifications:
                    if target_ids:
                        sub_target_ids = cast(
                            list[str],
                            await BiliSubTarget.filter(
                                subscription_id=sub.id, target_id__in=target_ids
                            ).values_list("target_id", flat=True),
                        )
                        await send_notification_to_targets(
                            notification, bot, sub_target_ids
                        )
                    else:
                        await send_sub_msg(notification, sub, bot)
                return len(notifications)
        except Exception as e:
            logger.error(f"checkall 检查 UID={sub.uid} 时出错: {e}")
        return 0

    tasks = [_check_sub_and_send(sub) for sub in all_subs]
    results = await asyncio.gather(*tasks)
    update_count = sum(results)

    await MessageUtils.build_message(
        f"✅ 主动检查完成！\n共检查 {len(all_subs)} 个订阅，发现了 {update_count} 个更新并已推送。"
    ).finish()


@bilisub_matcher.assign("forcepush")
async def handle_force_push(
    bot: Bot,
    event: Event,
    matcher: Matcher,
    db_ids: Query[list[int]] = Query("forcepush.db_ids", []),
    gids: Query[list[int]] = Query("forcepush.group.gids", []),
):
    await ensure_superuser(bot, event)

    if not db_ids.available or not db_ids.result:
        await MessageUtils.build_message(
            "请提供至少一个要推送的订阅ID (通过 `bilisub list` 查看)。"
        ).finish()

    if PlatformUtils.get_platform_scope(bot) != "qq_client":
        await MessageUtils.build_message(
            "B站订阅强制推送需要 OneBot 协议端执行，请在协议端使用。"
        ).finish()

    target_ids = (
        [f"group_{gid}" for gid in gids.result] if has_group_option(gids) else []
    )

    results = []
    for db_id in db_ids.result:
        sub = await BiliSub.get_or_none(id=db_id)
        if not sub:
            results.append(f"❌ 未找到ID为 {db_id} 的订阅。")
            continue

        await matcher.send(f"正在为 [{db_id}] {sub.uname} 获取最新内容并强制推送...")

        try:
            notifications: list[Notification] = []
            if sub.uid < 0:
                notifications = await asyncio.wait_for(
                    _get_bangumi_status(sub, force_push=True), timeout=45
                )
            else:
                notifications = await asyncio.wait_for(
                    get_sub_status(sub, force_push=True), timeout=45
                )
            if notifications:
                total_sent = 0
                for notification in notifications:
                    if target_ids:
                        sub_target_ids = cast(
                            list[str],
                            await BiliSubTarget.filter(
                                subscription_id=sub.id, target_id__in=target_ids
                            ).values_list("target_id", flat=True),
                        )
                        if not sub_target_ids:
                            continue
                        total_sent += await send_notification_to_targets(
                            notification, bot, sub_target_ids
                        )
                    else:
                        await MessageUtils.build_message(notification.content).send()
                        total_sent += 1
                if target_ids:
                    if total_sent:
                        results.append(
                            f"✅ 已向 {total_sent} 个指定目标推送 [{db_id}] {sub.uname} 的最新内容。"
                        )
                    else:
                        results.append(
                            f"ℹ️ [{db_id}] {sub.uname} 不属于指定群，未推送。"
                        )
                else:
                    results.append(f"✅ 已成功推送 [{db_id}] {sub.uname} 的最新内容。")
            else:
                results.append(
                    f"ℹ️ 未能为 [{db_id}] {sub.uname} 获取到可推送的最新内容。"
                )
        except asyncio.TimeoutError:
            results.append(f"❌ 为 [{db_id}] {sub.uname} 获取内容超时。")
        except Exception as e:
            logger.error(f"强制推送时发生错误: ID={db_id}", e=e)
            results.append(f"❌ 为 [{db_id}] {sub.uname} 推送时发生内部错误: {e}")

    await MessageUtils.build_message("\n---\n".join(results)).finish()
