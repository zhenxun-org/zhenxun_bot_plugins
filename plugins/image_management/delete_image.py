from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, on_alconna
from nonebot_plugin_session import EventSession
from nonebot_plugin_waiter import waiter

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

from ._data_source import ImageManagementManage

base_config = Config.get("image_management")

CANCEL_WORDS = {"取消", "算了"}
CANCEL_TOKEN = "__cancel__"
WAIT_TIMEOUT = 60
WAIT_RETRY = 3

__plugin_meta__ = PluginMetadata(
    name="删除图片",
    description="不好看的图片删掉删掉！",
    usage="""
    指令：
        删除图片 [图库] [id]
        查看公开图库
        示例：删除图片 美图 666
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.ADMIN,
        admin_level=base_config.get("DELETE_IMAGE_LEVEL"),
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna("删除图片", Args["name?", str]["index?", str]),
    rule=to_me(),
    priority=5,
    block=True,
)


def _build_gallery_list_text(image_dir_list: list[str]) -> str:
    return "\n".join(f"{i}. {name}" for i, name in enumerate(image_dir_list))


def _normalize_gallery_name(name: str, image_dir_list: list[str]) -> str | None:
    name = name.strip()
    if name.isdigit():
        idx = int(name)
        if 0 <= idx <= len(image_dir_list) - 1:
            return image_dir_list[idx]
        return None
    return name if name in image_dir_list else None


def _create_wait_text():
    @waiter(waits=["message"], keep_session=True)
    async def _inner(event: Event):
        return event.get_message().extract_plain_text().strip()

    return _inner


async def _ask_gallery_name(image_dir_list: list[str], wait_text) -> str | None:
    await MessageUtils.build_message(
        "请输入要删除的目标图库(id 或 名称)【发送'取消', '算了'来取消操作】\n"
        f"{_build_gallery_list_text(image_dir_list)}"
    ).send()
    for _ in range(WAIT_RETRY):
        resp = await wait_text.wait(timeout=WAIT_TIMEOUT, default=None)
        if resp is None:
            return None
        if resp in CANCEL_WORDS:
            return CANCEL_TOKEN
        if normalized := _normalize_gallery_name(resp, image_dir_list):
            return normalized
        await MessageUtils.build_message("此目录不正确，请重新输入目录！").send()
    return None


async def _ask_image_index(wait_text) -> int | str | None:
    await MessageUtils.build_message(
        "请输入要删除的图片id？【发送'取消', '算了'来取消操作】"
    ).send()
    for _ in range(WAIT_RETRY):
        resp = await wait_text.wait(timeout=WAIT_TIMEOUT, default=None)
        if resp is None:
            return None
        if resp in CANCEL_WORDS:
            return CANCEL_TOKEN
        if resp.isdigit():
            return int(resp)
        await MessageUtils.build_message("图片id需要输入数字...").send()
    return None


@_matcher.handle()
async def _(
    session: EventSession,
    arparma: Arparma,
    name: Match[str],
    index: Match[str],
):
    image_dir_list = base_config.get("IMAGE_DIR_LIST")
    if not image_dir_list:
        await MessageUtils.build_message("未发现任何图库").finish()

    wait_text = _create_wait_text()

    if name.available:
        gallery_name = _normalize_gallery_name(name.result, image_dir_list)
    else:
        gallery_name = await _ask_gallery_name(image_dir_list, wait_text)

    if gallery_name == CANCEL_TOKEN:
        await MessageUtils.build_message("已取消操作...").finish()
    if not gallery_name:
        await MessageUtils.build_message("输入超时或目录无效，操作已取消...").finish()

    if index.available:
        if not index.result.isdigit():
            await MessageUtils.build_message("图片id需要输入数字...").finish()
        image_index: int | str | None = int(index.result)
    else:
        image_index = await _ask_image_index(wait_text)

    if image_index == CANCEL_TOKEN:
        await MessageUtils.build_message("已取消操作...").finish()
    if image_index is None:
        await MessageUtils.build_message("输入超时或图片id无效，操作已取消...").finish()

    if not session.id1:
        await MessageUtils.build_message("用户id为空...").finish()

    if await ImageManagementManage.delete_image(
        gallery_name, int(image_index), session.id1, session.platform
    ):
        logger.info(
            f"删除图片成功 图库: {gallery_name} --- 名称: {image_index}.jpg",
            arparma.header_result,
            session=session,
        )
        await MessageUtils.build_message(
            f"删除图片成功!\n图库: {gallery_name}\n名称: {image_index}.jpg"
        ).finish()

    await MessageUtils.build_message("图片删除失败...").finish()
