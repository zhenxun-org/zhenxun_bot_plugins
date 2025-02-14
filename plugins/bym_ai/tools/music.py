from nonebot import get_bot
from nonebot.adapters.onebot.v11 import Event
from nonebot.compat import model_dump

from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.configs.utils import AbstractTool

class SearchMusic(AbstractTool):
    def __init__(self):
        super().__init__(
            name="search_music",
            description="如果你想搜索一首歌曲或者音乐，调用此方法",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "你想搜索音乐的标题或关键词, 可以是歌曲名或歌曲名+歌手名的组合"
                    }
                },
                "required": [
                    "keyword"
                ]
            },
            func=self.search_musci_func
        )

    async def search_musci_func(self, keyword: str) -> str:
        try:
            result = await AsyncHttpx.get(f"http://music.163.com/api/search/get/web?s={keyword}&type=1&offset=0&total=true&limit=6")
            print(result.json())
            return f"搜索结果： {result.json()}"
        except Exception as e:
            return f"搜索失败 {e}"
        
class SendMusic(AbstractTool):
    def __init__(self):
        super().__init__(
            name="send_music",
            description="如果你想发送一首歌曲或音乐，调用此方法",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "你想发送的歌曲id"
                    }
                },
                "required": [
                    "id"
                ]
            },
            func=self.send_music_func
        )

    async def send_music_func(self, event: Event, id: str) -> str:
        try:
            event_data = model_dump(event)
            if event_data.get("message_type") == "private":
                await get_bot().send_private_msg(user_id=event_data.get("user_id"), message=[{"type": "music", "data": {"type": "163", "id": id}}])
            else:
                await get_bot().send_group_msg(group_id=event_data.get("group_id"), message=[{"type": "music", "data": {"type": "163", "id": id}}])
            return "音乐发送成功"
        except Exception as e:
            return f"音乐发送失败 {e}"
