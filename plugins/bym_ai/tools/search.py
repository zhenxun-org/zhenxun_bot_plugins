from zhenxun.configs.utils import AbstractTool
from zhenxun.utils.http_utils import AsyncHttpx

class Search(AbstractTool):
    def __init__(self):
        super().__init__(
            name="search",
            description="Useful when you want to search something from the Internet. If you don\'t know much about the user\'s question, prefer to search about it! If you want to know further details of a result, you can use website tool。",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "你想搜索的内容关键词"
                    },
                    "source": {
                        "type": "string",
                        "enum": ["google", "bing", "baidu"]
                    }
                },
                "required": [
                    "keyword"
                ]
            },
            func=self.search_func
        )

    async def search_func(self, keyword: str, source: str | None = None) -> str:
        try:
            if not source or source not in ("google", "bing", "baidu"):
                source = "bing"

            url = f"https://serp.ikechan8370.com/{source}?q={keyword}&lang=zh-CN&limit=5"
            result = await AsyncHttpx.get(url, headers={"X-From-Library": "ikechan8370"}, follow_redirects=True, verify=False)
            return f"搜索结果：{result.json()}"

        except Exception as e:
            return f"搜索失败 {e}"
