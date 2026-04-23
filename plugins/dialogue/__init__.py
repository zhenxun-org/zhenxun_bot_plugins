from nonebot import on_command
from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import At, Target, Text, UniMsg
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import Command, PluginExtraData
from zhenxun.models.group_console import GroupConsole
from zhenxun.services.log import logger
from zhenxun.utils.depends import UserName
from zhenxun.utils.exception import NotFindSuperuser
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import get_entity_ids

from ._data_source import DialogueData, DialogueManager

__plugin_meta__ = PluginMetadata(
    name="联系管理员",
    description="跨越空间与时间跟管理员对话",
    usage="""
        滴滴滴- ?[文本] ?[图片]
        示例：滴滴滴- 我喜欢你
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        menu_type="联系管理员",
        superuser_help="""
            /t list [pending] [page] [size]: 分页查看未回复消息
            /t list all [page] [size]: 分页查看全部消息
            /t [user_id] [group_id] [文本]: 在group回复指定用户
            /t [user_id] [文本]: 私聊用户
            /t -1 [group_id] [文本]: 在group内发送消息
            /t [id] [文本]: 回复指定id的对话，id在 /t 中获取
            示例：/t list
            示例：/t list all 2 20
            示例：/t 73747222 32848432 你好啊
            示例：/t 73747222 你好不好
            示例：/t -1 32848432 我不太好
            示例：/t 0 我收到你的话了
        """.strip(),
        commands=[Command(command="滴滴滴- ?[文本] ?[图片]")],
    ).to_dict(),
)

_dialogue_matcher = on_command("滴滴滴-", priority=5, block=True)
_reply_matcher = on_command(
    "对话管理",
    aliases={"dialogue", "dm", "t", "/t"},
    priority=1,
    permission=SUPERUSER,
    block=True,
)


def _strip_manage_prefix(text: str) -> str:
    """移除管理命令本体，兼容多别名写法。"""
    raw = text.strip()
    for prefix in ("对话管理", "dialogue", "dm", "/t", "t"):
        if raw == prefix:
            return ""
        if raw.startswith(f"{prefix} "):
            return raw[len(prefix) :].strip()
    return raw


def _truncate_text(text: str, limit: int = 40) -> str:
    if text := text.replace("\n", " ").strip():
        return f"{text[:limit]}..." if len(text) > limit else text
    else:
        return ""


def _build_page_message(
    data_list: list[DialogueData],
    pending_only: bool,
    page: int,
    total_pages: int,
    total: int,
) -> str:
    status_text = "未回复" if pending_only else "全部"
    lines = [
        f"联系管理员消息列表（{status_text}）",
        f"第 {page}/{total_pages} 页，共 {total} 条",
    ]
    for data in data_list:
        msg_text = _truncate_text(data.message.extract_plain_text()) or "[非文本消息]"
        base = (
            f"[{data.id}] {'已回复' if data.is_replied else '未回复'}"
            f" {data.name}({data.user_id}) "
            f"群:{data.group_id or '私聊'} "
            f"时间:{data.create_time.strftime('%m-%d %H:%M')}"
        )
        lines.extend((base, f"留言: {msg_text}"))
        if data.is_replied and data.reply_text:
            lines.append(f"回复: {_truncate_text(data.reply_text)}")
        lines.append("")
    lines.append("用法: /t list [all|pending] [页码] [每页数量]")
    return "\n".join(lines).strip()


@_dialogue_matcher.handle()
async def _(
    bot: Bot,
    message: UniMsg,
    session: Uninfo,
    uname: str = UserName(),
):
    entity = get_entity_ids(session)
    if message:
        message[0] = Text(str(message[0]).replace("滴滴滴-", "", 1).strip())
    if not message.extract_plain_text().strip() and len(message) <= 1:
        await MessageUtils.build_message("请告诉管理员你想说什么吧~").finish(
            reply_to=True
        )
    platform = PlatformUtils.get_platform(bot)
    group_name = ""
    if entity.group_id:
        if g := await GroupConsole.get(group_id=entity.group_id):
            group_name = g.group_name
    logger.info(f"发送消息至{platform}管理员: {message}", "滴滴滴-", session=session)
    dialogue_id = await DialogueManager.add(
        uname, entity.user_id, entity.group_id, group_name, message, platform
    )
    dialogue_data = await DialogueManager.get(dialogue_id)
    if not dialogue_data:
        await MessageUtils.build_message("记录消息失败...").send(reply_to=True)
        return
    report_message = DialogueManager.build_report_message(dialogue_data)
    try:
        await PlatformUtils.send_superuser(bot, report_message)
        await MessageUtils.build_message("已成功发送给管理员啦!").send(reply_to=True)
    except NotFindSuperuser:
        await MessageUtils.build_message("管理员失联了...").send(reply_to=True)


@_reply_matcher.handle()
async def _(
    bot: Bot,
    message: UniMsg,
    session: Uninfo,
):
    plain_text = _strip_manage_prefix(message.extract_plain_text()) or "list"

    args = plain_text.split()
    first = args[0].lower()

    if first in {"list", "ls", "列表", "查看"}:
        pending_only = True
        index = 1
        if len(args) > 1:
            mode = args[1].lower()
            if mode in {"all", "全部", "a"}:
                pending_only = False
                index = 2
            elif mode in {"pending", "unreplied", "未回复", "u"}:
                pending_only = True
                index = 2

        page = 1
        page_size = 10
        if len(args) > index and args[index].isdigit():
            page = max(int(args[index]), 1)
            index += 1
        if len(args) > index and args[index].isdigit():
            page_size = max(int(args[index]), 1)

        platform = PlatformUtils.get_platform(bot)
        data, total, total_pages = await DialogueManager.list_by_platform_page(
            platform,
            pending_only=pending_only,
            page=page,
            page_size=page_size,
        )
        if not data:
            await MessageUtils.build_message("暂无符合条件的消息记录...").finish()
        msg = _build_page_message(
            data,
            pending_only=pending_only,
            page=min(page, total_pages),
            total_pages=total_pages,
            total=total,
        )
        await MessageUtils.build_message(msg).finish()

    first = args[0]
    if not first.replace("-", "", 1).isdigit():
        await MessageUtils.build_message("参数错误...").finish(at_sender=True)

    user_id: str | None = None
    group_id: str | None = None
    reply_start_index = 1
    resolved_dialogue_id: int | None = None

    if len(first) < 4:
        _id = int(first)
        if _id >= 0:
            model = await DialogueManager.get(_id)
            if not model:
                await MessageUtils.build_message("未获取此id数据").finish()
            user_id = model.user_id
            group_id = model.group_id
            resolved_dialogue_id = _id
        else:
            if len(args) < 3 or not args[1].isdigit():
                await MessageUtils.build_message("群组id错误...").finish(at_sender=True)
            group_id = args[1]
            reply_start_index = 2
    else:
        user_id = first
        if len(args) >= 3 and args[1].isdigit() and len(args[1]) > 5:
            group_id = args[1]
            reply_start_index = 2

    reply_text = " ".join(args[reply_start_index:]).strip()
    if not reply_text:
        await MessageUtils.build_message("回复内容为空...").finish(at_sender=True)

    send_message = MessageUtils.build_message(reply_text)
    if group_id:
        if user_id:
            send_message.insert(0, At("user", user_id))
            send_message.insert(1, Text("\n管理员回复\n=======\n"))
        await send_message.send(Target(group_id), bot)
    elif user_id:
        await send_message.send(Target(user_id, private=True), bot)
    else:
        await MessageUtils.build_message("群组id与用户id为空...").finish(at_sender=True)

    if resolved_dialogue_id is not None:
        await DialogueManager.mark_replied(
            resolved_dialogue_id,
            reply_text,
            session.user.id,
        )
    await MessageUtils.build_message("消息发送成功!").finish(at_sender=True)
