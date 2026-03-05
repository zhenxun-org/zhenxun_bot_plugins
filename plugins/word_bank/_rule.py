from io import BytesIO

import imagehash
from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import At as alcAt
from nonebot_plugin_alconna import Text as alcText
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_session import EventSession
from PIL import Image

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from ._data_source import get_img_and_at_list
from ._model import WordBank

_IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 8.0


async def check(
    bot: Bot,
    event: Event,
    message: UniMsg,
    session: EventSession,
    state: T_State,
) -> bool:
    group_id = session.id3 or session.id2
    text = message.extract_plain_text().strip()
    img_list, at_list = get_img_and_at_list(message)
    problem = text
    if not text and len(img_list) == 1 and not at_list:
        if not await WordBank.has_image_word_enabled(group_id):
            return False
        try:
            content = await AsyncHttpx.get_content(
                img_list[0],
                timeout=_IMAGE_DOWNLOAD_TIMEOUT_SECONDS,
            )
            with Image.open(BytesIO(content)) as image:
                problem = str(imagehash.average_hash(image))
        except Exception as e:
            logger.warning("获取图片失败", "词条检测", session=session, e=e)
    if at_list:
        temp = ""
        # TODO: 支持更多消息类型
        for msg in message:
            if isinstance(msg, alcAt):
                temp += f"[at:{msg.target}]"
            elif isinstance(msg, alcText):
                temp += msg.text
        problem = temp
    if event.is_tome() and bot.config.nickname:
        if isinstance(message[0], alcAt) and message[0].target == bot.self_id:
            problem = f"[at:{bot.self_id}]{problem}"
        elif problem and bot.config.nickname:
            nickname = [nk for nk in bot.config.nickname if str(message).startswith(nk)]
            problem = nickname[0] + problem if nickname else problem
    if problem and (await WordBank.check_problem(group_id, problem) is not None):
        state["problem"] = problem  # type: ignore
        return True
    return False
