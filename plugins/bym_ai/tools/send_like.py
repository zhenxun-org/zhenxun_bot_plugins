from nonebot import get_bot

from zhenxun.configs.utils import AbstractTool

class SendLike(AbstractTool):
    def __init__(self):
        super().__init__(
            name="send_like",
            description="如果你想为某人点赞，调用此方法",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "你想点赞的那个人QQ号"
                    },
                    "times": {
                        "type": "string",
                        "description": "你想点赞的次数，如果用户未指定，你默认填写1"
                    }
                },
                "required": [
                    "user_id",
                    "times"
                ]
            },
            func=self.send_like_func
        )

    async def send_like_func(self, user_id: str, times: int) -> str:
        try:
            await get_bot().send_like(user_id=int(user_id), times=times)
            return "点赞成功"
        except Exception as e:
            return f"点赞失败 {e}"
