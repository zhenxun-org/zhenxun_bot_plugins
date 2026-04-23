from typing import Any, cast

from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, UniMessage, on_alconna
from nonebot_plugin_alconna import Image as alcImage
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_waiter import waiter

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from ._data_source import ImageManagementManage

base_config = Config.get("image_management")

CANCEL_WORDS = {"取消", "算了"}
CANCEL_TOKEN = "__cancel__"
WAIT_TIMEOUT = 60
WAIT_RETRY = 3

__plugin_meta__ = PluginMetadata(
    name="上传图片",
    description="上传图片至指定图库",
    usage="""
    指令：
        查看图库
        上传图片 [图库] [图片]
        连续上传图片 [图库]
        示例：上传图片 美图 [图片]
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.ADMIN,
        admin_level=base_config.get("UPLOAD_IMAGE_LEVEL"),
    ).to_dict(),
)


_upload_matcher = on_alconna(
    Alconna("上传图片", Args["name?", str]["img?", alcImage]),
    rule=to_me(),
    priority=5,
    block=True,
)

_continuous_upload_matcher = on_alconna(
    Alconna("连续上传图片", Args["name?", str]),
    rule=to_me(),
    priority=5,
    block=True,
)

_show_matcher = on_alconna(Alconna("查看公开图库"), priority=1, block=True)


def _build_gallery_list_text(image_dir_list: list[str]) -> str:
    return "\n".join(f"{i}. {name}" for i, name in enumerate(image_dir_list))


def _normalize_gallery_name(name: str, image_dir_list: list[str]) -> str | None:
    name = name.strip()
    if name.isdigit():
        index = int(name)
        return image_dir_list[index] if 0 <= index <= len(image_dir_list) - 1 else None
    return name if name in image_dir_list else None


def _create_wait_text():
    @waiter(waits=["message"], keep_session=True)
    async def _inner(event: Event):
        return event.get_message().extract_plain_text().strip()

    return _inner


def _create_wait_unimessage():
    @waiter(waits=["message"], keep_session=True)
    async def _inner(event: Event, bot: Bot):
        # NOTE: plugin-alconna 的类型提示未完整暴露 generate，运行时该方法存在
        return await cast(Any, UniMessage).generate(event=event, bot=bot)

    return _inner


def _extract_image_urls(message: UniMessage) -> list[str]:
    image_urls: list[str] = []
    image_urls.extend(
        seg.url for seg in message if isinstance(seg, alcImage) and seg.url
    )
    return image_urls


async def _ask_gallery_name(
    image_dir_list: list[str], prompt: str, wait_text
) -> str | None:
    await MessageUtils.build_message(prompt).send()
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


async def _ask_single_image_url(wait_unimessage) -> str | None:
    await MessageUtils.build_message("图呢图呢图呢图呢！GKD！").send()
    for _ in range(WAIT_RETRY):
        resp = await wait_unimessage.wait(timeout=WAIT_TIMEOUT, default=None)
        if resp is None:
            return None
        if resp.extract_plain_text().strip() in CANCEL_WORDS:
            return CANCEL_TOKEN
        if image_urls := _extract_image_urls(resp):
            return image_urls[0]
        await MessageUtils.build_message("未检测到图片，请重新发送图片").send()
    return None


async def _resolve_gallery_name(
    name: Match[str], image_dir_list: list[str], wait_text
) -> str | None:
    if name.available:
        return _normalize_gallery_name(name.result, image_dir_list)
    return await _ask_gallery_name(
        image_dir_list,
        "请选择要上传的图库(id 或 名称)【发送'取消', '算了'来取消操作】\n"
        f"{_build_gallery_list_text(image_dir_list)}",
        wait_text,
    )


@_show_matcher.handle()
async def _():
    image_dir_list = base_config.get("IMAGE_DIR_LIST")
    if not image_dir_list:
        await MessageUtils.build_message("未发现任何图库").finish()
    text = "公开图库列表：\n"
    for i, e in enumerate(image_dir_list):
        text += f"\t{i + 1}.{e}\n"
    await MessageUtils.build_message(text[:-1]).send()


@_upload_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    name: Match[str],
    img: Match[alcImage],
):
    image_dir_list = base_config.get("IMAGE_DIR_LIST")
    if not image_dir_list:
        await MessageUtils.build_message("未发现任何图库").finish()

    wait_text = _create_wait_text()
    wait_unimessage = _create_wait_unimessage()

    gallery_name = await _resolve_gallery_name(name, image_dir_list, wait_text)
    if gallery_name == CANCEL_TOKEN:
        await MessageUtils.build_message("已取消操作...").finish()
    if not gallery_name:
        await MessageUtils.build_message("输入超时或目录无效，操作已取消...").finish()

    if img.available and img.result.url:
        image_url = img.result.url
    else:
        image_url = await _ask_single_image_url(wait_unimessage)
        if image_url == CANCEL_TOKEN:
            await MessageUtils.build_message("已取消操作...").finish()
        if not image_url:
            await MessageUtils.build_message("等待图片超时，操作已取消...").finish()

    result = await AsyncHttpx.get(image_url)
    if file_name := await ImageManagementManage.upload_image(
        result.content,
        gallery_name,
        session.user.id,
        PlatformUtils.get_platform(session),
    ):
        logger.info(
            f"图库: {gallery_name} --- 名称: {file_name}",
            arparma.header_result,
            session=session,
        )
        await MessageUtils.build_message(
            f"上传图片成功!\n图库: {gallery_name}\n名称: {file_name}"
        ).finish()
    await MessageUtils.build_message("图片上传失败...").finish()


@_continuous_upload_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    name: Match[str],
):
    image_dir_list = base_config.get("IMAGE_DIR_LIST")
    if not image_dir_list:
        await MessageUtils.build_message("未发现任何图库").finish()

    wait_text = _create_wait_text()
    wait_unimessage = _create_wait_unimessage()

    gallery_name = await _resolve_gallery_name(name, image_dir_list, wait_text)
    if gallery_name == CANCEL_TOKEN:
        await MessageUtils.build_message("已取消操作...").finish()
    if not gallery_name:
        await MessageUtils.build_message("输入超时或目录无效，操作已取消...").finish()

    await MessageUtils.build_message(
        "请连续发送图片，发送 `stop` 结束上传，发送 `取消` 可退出"
    ).send()

    image_urls: list[str] = []
    async for resp in wait_unimessage(timeout=WAIT_TIMEOUT, default=None):
        if resp is None:
            if image_urls:
                break
            await MessageUtils.build_message("等待超时，未接收到任何图片...").finish()

        text = resp.extract_plain_text().strip()
        if text in CANCEL_WORDS:
            await MessageUtils.build_message("已取消操作...").finish()
        current_urls = _extract_image_urls(resp)
        image_urls.extend(current_urls)
        if text.lower() == "stop":
            break
        if current_urls:
            await MessageUtils.build_message(
                f"已收到 {len(current_urls)} 张图片，当前累计 {len(image_urls)} 张。\n"
                "继续发送图片，或发送 `stop` 结束上传。"
            ).send()
        else:
            await MessageUtils.build_message(
                "未检测到图片，请继续发送图片，或发送 `stop` 结束"
            ).send()

    if not image_urls:
        await MessageUtils.build_message("未检测到可上传图片...").finish()

    await MessageUtils.build_message("正在下载, 请稍后...").send()
    file_list: list[str] = []
    for image_url in image_urls:
        if file_name := await ImageManagementManage.upload_image(
            image_url,
            gallery_name,
            session.user.id,
            PlatformUtils.get_platform(session),
        ):
            file_list.append(file_name)
            logger.info(
                f"图库: {gallery_name} --- 名称: {file_name}",
                arparma.header_result,
                session=session,
            )

    if file_list:
        await MessageUtils.build_message(
            f"上传图片成功!共上传了{len(file_list)}张图片\n"
            f"图库: {gallery_name}\n名称: {', '.join(file_list)}"
        ).finish()
    await MessageUtils.build_message("图片上传失败...").finish()
