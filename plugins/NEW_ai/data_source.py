import datetime
import os
import random

import ujson as json
from nonebot_plugin_alconna import UniMessage, UniMsg,Reply,Image
from nonebot.adapters.onebot.v11 import MessageEvent

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import DATA_PATH, IMAGE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

from .deepseek import DEEPSEEKManager
from .gemini_ai import GeminiManager
from .utils import ai_message_manager

url = "http://openapi.tuling123.com/openapi/api/v2"
url_gpt = "https://api.aigc2d.com"

check_url = "https://v3.alapi.cn/api/censor/text"

index = 0

manager = DEEPSEEKManager()



#anime_data = json.load(open(DATA_PATH / "anime.json", encoding="utf8"))
# key = "fdc8d9f9-d582-455c-8eb7-e79686284f54:82210e55845f80f10b20ee62d72774d6"  # https://fal.ai/models/fal-ai/fast-sdxl/api绘画ai的key如果没有请留空
# os.environ["FAL_KEY"] = key
json_forma = {"type": "功能名称", "source": "符合功能需要的内容"}#被废弃
fonction = "特殊能力(要调用特殊能力你要构造一个符合markdown格式的json代码块其中有且只有两个key分别为type和source不要使用多行注释，其中type允许四个值python、search、draw、gold当type的值为python时source的值应该为标准的python代码，当type的值为search时source的值应该是你要搜索的内容当type为draw时source的值应该是对要画的内容的描述详细点当type为gold时source的值应为小写阿拉伯数字值可正可负正代表添加用户金币负代表减少用户金币。注意python的语法和缩进缩进注意不要生成无限循环的代码)"  # noqa: E501
lunshu: int = 0


async def get_chat_result(
    message: UniMsg, user_id: str, nickname: str,image_url:str = '',reply_text:str = ''
) -> UniMessage | None:
    """获取 AI 返回值，顺序： 特殊回复 -> 图灵 -> 青云客

    参数:
        text: 问题
        img_url: 图片链接
        user_id: 用户id
        nickname: 用户昵称
        
    返回
        str: 回答
    """
    text = message.extract_plain_text()
    try:
        os.getenv("DEEPSEEK_API_KEY")  # 确保环境变量已加载
        os.getenv("GOOGLE_API_KEY")  # 确保环境变量已加载
        os.getenv("HUANZOU_API_KEY")  # 确保环境变量已加载
        os.getenv("SILICONFLOW_API_KEY")  # 确保环境变量已加载
    except Exception as e:
        with open('.env.dev','a') as f:
            f.write("DEEPSEEK_API_KEY=\n")
            f.write("GOOGLE_API_KEY=\n")
            f.write("HUANZOU_API_KEY=\n")
            f.write("SILICONFLOW_API_KEY=\n")
        await MessageUtils.build_message(f"api_key缺失\n请在.env.dev文件中补全\n环境变量加载失败: {e}").finish()
    rst = await AIS(text, user_id, user_name=nickname,image_url=image_url,reply_text=reply_text)
    if not rst:
        return None
    if nickname:
        if len(nickname) < 5:
            if random.random() < 0.5:
                nickname = "~".join(nickname) + "~"
                if random.random() < 0.2:
                    if nickname.find("大人") == -1:
                        nickname += "大~人~"
        rst = str(rst).replace("小主人", nickname).replace("小朋友", nickname)
    ai_message_manager.add_result(user_id, rst)
    for t in Config.get_config("ai", "TEXT_FILTER"):
        rst = rst.replace(t, "*")
    return MessageUtils.build_message(rst)



async def AIS(text: str, user_id: str, user_name,image_url,reply_text=None) -> str:
    # 角色扮演设定
    system_user = f"你是真寻,你的性格与演漫画 《别当欧尼酱了》中的蜀山真寻一样但你比她会的更多，在遇到比较困难的问题时可以尝试使用{fonction}。在用完特殊能力后记得加上?~~>,用中文回答用户,不要随意修改用户金币。每次对话后会有一个实时的时间戳结构为[年-月-日 具体时间]但注意你的回答不需要加时间戳！"  # noqa: E501
    if not text:
        return await hello().finish()  # type: ignore

    if user_id not in manager.sessions:
        manager.create_session(
            session_id=user_id,
            prompt=system_user,
            max_code_executions=5,
            max_chat_turns=10,
            request_delay=0,
        )

    session = manager.get_session(user_id)
    message= False,(user_name
        + ":"
        + text
        + f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
        )
    response = await session.send_message(
        message=message,user_id=user_id,image_url=image_url,reply_text=reply_text
    )
    return response


def hello() -> UniMessage:
    """一些打招呼的内容"""
    result = random.choice(
        (
            "哦豁？！",
            "你好！Ov<",
            f"库库库，呼唤{BotConfig.self_nickname}做什么呢",
            "我在呢！",
            "呼呼，叫俺干嘛",
        )
    )
    img = random.choice(os.listdir(IMAGE_PATH / "zai"))
    return MessageUtils.build_message([IMAGE_PATH / "zai" / img, result])


def no_result() -> UniMessage:
    """
    没有回答时的回复
    """
    return MessageUtils.build_message(
        [
            random.choice(
                [
                    "你在说啥子？",
                    f"纯洁的{BotConfig.self_nickname}没听懂",
                    "下次再告诉你(下次一定)",
                    "你觉得我听懂了吗？嗯？",
                    "我！不！知！道！",
                ]
            ),
            IMAGE_PATH
            / "noresult"
            / random.choice(os.listdir(IMAGE_PATH / "noresult")),
        ]
    )


async def check_text(text: str) -> str:
    """ALAPI文本检测，主要针对青云客API，检测为恶俗文本改为无回复的回答

    参数:
        text: 回复

    返回:
        str: 检测文本
    """
    if not Config.get_config("alapi", "ALAPI_TOKEN"):
        return text
    params = {"token": Config.get_config("alapi", "ALAPI_TOKEN"), "text": text}
    try:
        data = (await AsyncHttpx.get(check_url, timeout=2, params=params)).json()
        if data["code"] == 200:
            if data["data"]["conclusion_type"] == 2:
                return ""
    except Exception as e:
        logger.error("检测违规文本错误...", e=e)
    return text
