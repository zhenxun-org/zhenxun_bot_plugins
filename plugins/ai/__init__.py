from pathlib import Path
import shutil

from nonebot import on_message
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import DATA_PATH
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.models.friend_user import FriendUser
from zhenxun.models.group_member_info import GroupInfoUser
from zhenxun.services.log import logger
from zhenxun.utils.depends import UserName
from zhenxun.utils.message import MessageUtils

from .data_source import get_chat_result, hello, no_result

__plugin_meta__ = PluginMetadata(
    name="AI",
    description="屑Ai",
    usage=f"""
    与{BotConfig.self_nickname}普普通通的对话吧！
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.3",
        ignore_prompt=True,
        configs=[
            RegisterConfig(
                module="alapi",
                key="ALAPI_TOKEN",
                value=None,
                help="在 https://admin.alapi.cn/user/login 登录后获取token",
            ),
            RegisterConfig(key="TL_KEY", value=[], help="图灵Key", type=list[str]),
            RegisterConfig(
                key="ALAPI_AI_CHECK",
                value=False,
                help="是否检测青云客骂娘回复",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                key="TEXT_FILTER",
                value=["鸡", "口交"],
                help="文本过滤器，将敏感词更改为*",
                type=list[str],
            ),
        ],
    ).to_dict(),
)


ai = on_message(rule=to_me(), priority=998)


@ai.handle()
async def _(message: UniMsg, session: Uninfo, uname: str = UserName()):
    text = message.extract_plain_text()
    if not text or text in [
        "你好啊",
        "你好",
        "在吗",
        "在不在",
        "您好",
        "您好啊",
        "你好",
        "在",
    ]:
        await hello().finish(reply_to=True)
    if not session.user.id:
        await MessageUtils.build_message("用户id不存在...").finish(reply_to=True)
    group = session.group
    if group:
        nickname = await GroupInfoUser.get_user_nickname(session.user.id, group.id)
    else:
        nickname = await FriendUser.get_user_nickname(session.user.id)
    if not nickname:
        nickname = uname
    result = await get_chat_result(text, session.user.id, nickname)
    logger.info(f"问题：{text} ---- 回答：{result}", "ai", session=session)
    if result:
        result = str(result)
        for t in Config.get_config("ai", "TEXT_FILTER"):
            result = result.replace(t, "*")
        await MessageUtils.build_message(result).finish(reply_to=True)
    else:
        await no_result().finish(reply_to=True)


# >>>>>>> 自动移动 anime.json 到 DATA_PATH 目录 >>>>>>>


current_dir = Path(__file__).parent
anime_json_src = current_dir / "anime.json"
anime_json_dst = DATA_PATH / "anime.json"

if anime_json_src.exists() and not anime_json_dst.exists():
    try:
        shutil.move(str(anime_json_src), str(anime_json_dst))
        logger.info(f"anime.json 已移动到 {anime_json_dst}", "ai")
    except Exception as e:
        logger.error(f"anime.json 移动失败: {e}", "ai")
