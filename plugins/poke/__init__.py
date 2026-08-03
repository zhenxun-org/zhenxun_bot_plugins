import os
import random

import ujson as json
from nonebot import on_notice
from nonebot.adapters.onebot.v11 import Bot, PokeNotifyEvent
from nonebot.adapters.onebot.v11.message import MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import IMAGE_PATH, RECORD_PATH
from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.ban_console import BanConsole
from zhenxun.models.plugin_info import PluginInfo
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.rules import notice_rule
from zhenxun.utils.utils import CountLimiter, cn2py

__plugin_meta__ = PluginMetadata(
    name="戳一戳",
    description="戳一戳发送语音美图萝莉图不美哉？",
    usage="""
    戳一戳随机掉落语音或美图萝莉图
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        menu_type="其他",
        plugin_type=PluginType.NORMAL,
    ).to_dict(),
)

REPLY_MESSAGE = [
    "lsp你再戳？",
    "连个可爱美少女都要戳的肥宅真恶心啊。",
    "你再戳！",
    "？再戳试试？",
    "别戳了别戳了再戳就坏了555",
    f"{BotConfig.self_nickname}爪巴爪巴，球球别再戳了",
    "你戳你🐎呢？！",
    "那...那里...那里不能戳...绝对...",
    "(。´・ω・)ん?",
    f"有事恁叫{BotConfig.self_nickname}，别天天一个劲戳戳戳！",
    "欸很烦欸！你戳🔨呢",
    "?",
    "再戳一下试试？",
    "???",
    "正在关闭对您的所有服务...关闭成功",
    "啊呜，太舒服刚刚竟然睡着了。什么事？",
    "正在定位您的真实地址...定位成功。轰炸机已起飞",
    f"别戳了，别戳了，{BotConfig.self_nickname}的呆毛要掉拉！",
    f"{BotConfig.self_nickname}在呢！",
    f"你是来找{BotConfig.self_nickname}玩的嘛？",
    f"别急呀, {BotConfig.self_nickname}要宕机了!QAQ",
    "你好！Ov<",
    f"你再戳{BotConfig.self_nickname}要喊美波里给你下药了！",
    "别戳了，怕疼QwQ",
    f"再戳，{BotConfig.self_nickname}就要咬你了嗷~",
    "恶龙咆哮，嗷呜~",
    "生气(╯▔皿▔)╯",
    "不要这样子啦（*/ w \\*）",
    "戳坏了",
    "戳坏了，赔钱！",
    f"喂，110吗，有人老戳{BotConfig.self_nickname}",
    f"别戳{BotConfig.self_nickname}啦，您歇会吧~",
    f"喂(#`O′) 戳{BotConfig.self_nickname}干嘛！",
]

_clmt = CountLimiter(3)

poke_ = on_notice(priority=5, block=False, rule=notice_rule(PokeNotifyEvent) & to_me())
depend_image_management = "image_management"
depend_send_voice = "dinggong"
IMAGE_MANAGEMENT = IMAGE_PATH / "image_management"

text_data = {}


@poke_.handle()
async def _(bot: Bot, event: PokeNotifyEvent):
    if event.self_id != event.target_id:
        return
    uid = str(event.user_id) if event.user_id else None
    _clmt.increase(event.user_id)
    gid = str(event.group_id) if event.group_id else None
    if _clmt.check(event.user_id) or random.random() < 0.3:
        rst = ""
        if random.random() < 0.15:
            await BanConsole.ban(uid, gid, 1, "戳一戳封禁", 60)
            rst = "气死我了！"
        await poke_.finish(rst + random.choice(REPLY_MESSAGE), at_sender=True)
    rand = random.random()
    loaded_plugins = await PluginInfo.filter(load_status=True).values_list(
        "module", flat=True
    )
    dir_list = Config.get_config("image_management", "IMAGE_DIR_LIST")
    path = (IMAGE_MANAGEMENT / cn2py(random.choice(dir_list))) if dir_list else None
    if (
        depend_image_management in loaded_plugins
        and path
        and path.exists()
        and rand <= 0.3
        and len(os.listdir(path)) > 0
    ):
        index = random.randint(0, len(os.listdir(path)) - 1)
        await MessageUtils.build_message(
            [
                f"id: {index}",
                (path / f"{index}.jpg").read_bytes(),
            ]
        ).send()
        logger.info(
            "戳了戳我", "戳一戳", session=event.user_id, group_id=event.group_id
        )
    elif depend_send_voice in loaded_plugins and 0.3 < rand < 0.6:
        global text_data
        resource_path = RECORD_PATH / "dinggong"
        voice = random.choice(os.listdir(resource_path))
        result = MessageSegment.record((resource_path / voice).read_bytes())
        if not text_data:
            text_file = resource_path / "data.json"
            text_data = json.load(text_file.open("r", encoding="utf-8"))
        index = voice.split(".")[0]
        text = text_data.get(index, "")
        await poke_.send(result)
        await poke_.send(text)
        logger.info(
            f"戳了戳我 回复: {result} \n {text}",
            "戳一戳",
            session=event.user_id,
            group_id=event.group_id,
        )
    else:
        try:
            await poke_.send(MessageSegment("poke", {"qq": event.user_id}))
        except Exception:
            try:
                if event.group_id:
                    await bot.call_api(
                        "group_poke", user_id=event.user_id, group_id=event.group_id
                    )
                else:
                    await bot.call_api("friend_poke", user_id=event.user_id)
            except Exception:
                logger.warning(
                    "戳一戳发送失败，可能是协议端不支持...",
                    "戳一戳",
                    session=event.user_id,
                    group_id=event.group_id,
                )
