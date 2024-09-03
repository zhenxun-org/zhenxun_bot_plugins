import os
import random

from nonebot import on_message
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.utils import cn2py
from zhenxun.utils.withdraw_manage import WithdrawManager

base_config = Config.get("image_management")

__plugin_meta__ = PluginMetadata(
    name="本地图库",
    description="让看看我的私藏，指[图片]",
    usage=f"""
    usage：
        发送指定图库下的随机或指定id图片
        指令：
            {base_config.get("IMAGE_DIR_LIST")} ?[id]
            示例：美图
            示例: 萝莉 2
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1", menu_type="来点好康的"
    ).dict(),
)


def rule(message: UniMsg) -> bool:
    """
    检测文本是否是关闭功能命令
    """
    if plain_text := message.extract_plain_text():
        for x in base_config.get("IMAGE_DIR_LIST"):
            if plain_text.startswith(x):
                text_list = plain_text.split()
                if len(text_list) > 1 and not text_list[1].isdigit():
                    return False
                return True
    return False


send_img = on_message(priority=5, rule=rule, block=True)


_path = IMAGE_PATH / "image_management"


@send_img.handle()
async def _(bot: Bot, message: UniMsg, session: EventSession):
    msg = message.extract_plain_text().split()
    gallery = msg[0]
    if gallery not in base_config.get("IMAGE_DIR_LIST"):
        return
    img_id = None
    if len(msg) > 1:
        img_id = msg[1]
    path = _path / cn2py(gallery)
    if gallery in base_config.get("IMAGE_DIR_LIST"):
        if not path.exists() and (path.parent.parent / cn2py(gallery)).exists():
            path = IMAGE_PATH / cn2py(gallery)
        else:
            path.mkdir(parents=True, exist_ok=True)
    length = len(os.listdir(path))
    if length == 0:
        logger.warning(f"图库 {cn2py(gallery)} 为空，调用取消！")
        await MessageUtils.build_message("该图库中没有图片噢").finish()
    index = img_id if img_id else str(random.randint(0, length - 1))
    if int(index) > length - 1 or int(index) < 0:
        await MessageUtils.build_message(f"超过当前上下限！({length - 1})").finish()
    result_image = path / f"{index}.jpg"
    if result_image.exists():
        message_list = []
        if base_config.get("SHOW_ID"):
            message_list.append(f"id：{index}")
        message_list.append(result_image)
        receipt = await MessageUtils.build_message(message_list).send()
        message_id = receipt.msg_ids[0]["message_id"]
        logger.info(
            f"发送{cn2py(gallery)}: {result_image}", "本地图库", session=session
        )
        withdraw = base_config.get("WITHDRAW_IMAGE_MESSAGE")
        await WithdrawManager.withdraw_message(bot, message_id, withdraw, session)
    else:
        logger.info(
            f"发送 {cn2py(gallery)} 失败: {result_image} 图片不存在",
            "本地图库",
            session=session,
        )
        await MessageUtils.build_message("不想给你看Ov|").send()
