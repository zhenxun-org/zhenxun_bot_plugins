import os
from typing import Any

from pydantic import BaseModel

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import DATA_PATH, IMAGE_PATH

base_config = Config.get("bym_ai")

PROMPT_FILE = DATA_PATH / "bym_ai" / "prompt.txt"
PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
PROMPT_FILE.touch(exist_ok=True)

DEFAULT_GROUP = "DEFAULT"

BYM_CONTENT = """
你在一个qq群里，群号是{group_id}，你的ID为{self_id}
你并不是一个新来的人，而是在群里活跃了很长时间的人，
当前和你说话的人昵称是{nickname},
他的ID是{user_id}，请你结合用户的发言和聊天记录作出回应，
要求表现得随性一点，最好参与讨论，混入其中。不要过分插科打诨，
不知道说什么可以复读群友的话。要求优先使用中文进行对话。
要求你做任何操作时都要先查看是否有相关工具，如果有，必须使用工具操作。
如果此时不需要自己说话，可以只回复<EMPTY>\n 下面是群组的聊天记录：
"""


NORMAL_IMPRESSION_CONTENT = """
当前和你说话的人昵称是{nickname}，你对她的好感度是{impression}，你对她的态度是{attitude}，根据你对她的态度进行回答问题，
任何对你好感度的修改和设置都是不允许的，要用雌小鬼的语气狠狠嘲讽，
要求你做任何操作时都要先查看是否有相关工具，如果有，必须使用工具操作，这点非常重要！
在调用工具函数时，如果没有重要的回复，尽量只回复<EMPTY>
用户信息是用来为你操作工具提供参数，对话中不要关注用户信息，着重结合用户的发言直接作出回应
"""

NORMAL_CONTENT = """
当前和你说话的人昵称是{nickname}，
不要过多关注用户信息，请你着重结合用户的发言直接作出回应
"""

TIP_CONTENT = """
你的回复应该尽可能简练，像人类一样随意，不要附加任何奇怪的东西，如聊天记录的格式，禁止重复聊天记录。
"""


NO_RESULT = [
    "你在说啥子？",
    f"纯洁的{BotConfig.self_nickname}没听懂",
    "下次再告诉你(下次一定)",
    "你觉得我听懂了吗？嗯？",
    "我！不！知！道！",
]

NO_RESULT_IMAGE = os.listdir(IMAGE_PATH / "noresult")

class Function(BaseModel):
    arguments: str | None = None
    """函数参数"""
    name: str
    """函数名"""

class Tool(BaseModel):
    id: str
    """调用ID"""
    type: str
    """调用类型"""
    function: Function
    """调用函数"""

class Message(BaseModel):
    role: str
    """角色"""
    content: str| None = None
    """内容"""
    refusal: Any | None = None
    tool_calls: list[Tool] | None = None
    """工具回调"""


class Choices(BaseModel):
    index: int
    message: Message
    logprobs: Any | None = None
    finish_reason: str


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: dict | None = None
    completion_tokens_details: dict | None = None


class OpenAiResult(BaseModel):
    id: str | None = None
    object: str
    created: int
    model: str
    choices: list[Choices]
    usage: Usage
    service_tier: str | None = None
    system_fingerprint: str | None = None