from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11.message import Message
from nonebot_plugin_uninfo import Uninfo, get_interface
from zhenxun.configs.utils import BaseBlock, PluginCdBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.path_config import DATA_PATH
from .data_source import JmDownload, BlacklistManager
import re

__plugin_meta__ = PluginMetadata(
    name="Jm下载器",
    description="懂的都懂，密码是id号，黑名单列表在插件目录",
    usage="""
    指令：
        jm [本子id] - 下载本子
        jm add [album_id] - 添加到黑名单（仅超级用户）
        jm del [album_id] - 从黑名单删除（仅超级用户）
        jm list - 查看黑名单
    示例：
        jm 114514
        jm add 114514
        jm del 114514
        jm list
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier、inventling",
        version="0.6",
        menu_type="一些工具",
        limits=[
            BaseBlock(result="当前有本子正在下载喵，请稍等..."),
            PluginCdBlock(result="Jm下载器冷却中喵（5s）..."),
        ],
    ).to_dict(),
)

from pathlib import Path
import yaml

# 检查并创建DATA_PATH下的配置文件
config_path = DATA_PATH / "jmcomic" / "blacklist_config.yml"
config_path.parent.mkdir(parents=True, exist_ok=True)

if not config_path.exists():
    # 创建默认配置文件
    default_config = {
        "super_users": [],  # 超级用户QQ号列表
        "blacklist": [
			'114514',
            '637857',
            '350234',
            '136494',
            '405848',
            '481481',
            '568070',
            '628539',
            '627898',
            '628555',
            '627899',
            '323666',
            '363848',
            '454278',
            '559716',
            '629252',
            '626487',
            '400002',
            '208092',
            '253199',
            '382596',
            '418600',
            '565616',
            '222458',
            '636531',
            '553350',
            '1087303',
            '392645',
            '433651',
            '642039',
            '1193291',
            '139818',
            '279464',
            '285644',
            '287786',
            '287836',
            '287837',
            '288302',
            '288303',
            '288304',
            '288448',
            '288449',
            '331189',
            '333204',
            '333024',
            '348899',
            '350235',
            '354788',
            '383386',
            '427909',
            '452452',
            '497544',
            '517803',
            '547917',
            '559722',
            '574868',
            '599879',
            '599880',
            '599890',
            '611650',
            '611674',
            '630643',
            '640301',
            '640557',
            '642012',
            '643162',
            '644152',
            '652338',
            '652339',
            '1024176',
            '1026836',
            '1026906',
            '1027120',
            '1027637',
            '1027669',
            '1045798',
            '1049076',
            '1052890',
            '1053769',
            '1068396',
            '1070826',
            '1075778',
            '1076266',
            '1078262',
            '1092441',
            '1117798',
            '1187635',
            '1205492',
            '1191294',
            '1228476',
            '1229478',
            '1239341'
		]     # 默认黑名单album_id列表
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

# 使用传统命令处理器
jm_cmd = on_command("jm", priority=5, block=True, rule=to_me())

@jm_cmd.handle()
async def _(bot: Bot, event: MessageEvent, arg: Message = CommandArg(), session: Uninfo = get_interface):
    try:
        # 使用 uninfo 获取用户和群组信息
        user_id = str(session.user.id)
        group_id = str(session.scene.id) if session.scene and session.scene.type == "group" else None
    except Exception as e:
        logger.warning(f"获取uninfo失败: {e}")
        # uninfo获取失败，则直接返回错误
        await MessageUtils.build_message("获取用户信息失败，请稍后再试").send(reply_to=True)
        return
    
    raw_arg = arg.extract_plain_text().strip()
    
    if not raw_arg:
        await jm_cmd.finish("请输入命令或JM号喵，格式：jm [album_id] 或 jm [命令] [参数]")
        return

    
    # 检查是否为纯数字（下载命令）
    if raw_arg.isdigit():
        album_id = raw_arg
        # 检查是否在黑名单中
        if BlacklistManager.is_blacklisted(album_id):
            await MessageUtils.build_message(f"本子 {album_id} 已被扔进垃圾桶里了喵").send(reply_to=True)
            return
        
        await MessageUtils.build_message("正在翻阅中，请稍后...").send(reply_to=True)
        await JmDownload.download_album(bot, user_id, group_id, album_id)
        logger.info(f"下载了本子 {album_id}", "jmcomic", session=user_id)
    else:
        # 解析指令
        parts = raw_arg.split(' ', 1)
        cmd = parts[0].lower()
        
        if cmd == 'add':
            if len(parts) < 2 or not parts[1].isdigit():
                await MessageUtils.build_message("添加黑名单格式错误：jm add [album_id]").send(reply_to=True)
                return
            
            album_id = parts[1]
            if BlacklistManager.is_super_user(user_id):
                BlacklistManager.add_to_blacklist(album_id)
                await MessageUtils.build_message(f"已将本子 {album_id} 添加到小本本").send(reply_to=True)
            else:
                await MessageUtils.build_message("权限不足，只有超级用户才能添加黑名单").send(reply_to=True)
        
        elif cmd == 'del':
            if len(parts) < 2 or not parts[1].isdigit():
                await MessageUtils.build_message("删除黑名单格式错误：jm del [album_id]").send(reply_to=True)
                return
            
            album_id = parts[1]
            if BlacklistManager.is_super_user(user_id):
                BlacklistManager.remove_from_blacklist(album_id)
                await MessageUtils.build_message(f"已将本子 {album_id} 从小本本中移除").send(reply_to=True)
            else:
                await MessageUtils.build_message("权限不足，只有超级用户才能删除黑名单").send(reply_to=True)
        
        elif cmd == 'list':
            blacklist = BlacklistManager.get_blacklist()
            if blacklist:
                blacklist_str = '\n'.join(blacklist)
                await MessageUtils.build_message(f"当前小本本列表：\n{blacklist_str}").send(reply_to=True)
            else:
                await MessageUtils.build_message("当前黑名单为空").send(reply_to=True)
        
        else:
            await MessageUtils.build_message("未知命令，支持的命令：[id],add, del, list").send(reply_to=True)
