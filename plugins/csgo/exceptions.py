class CsgoDataQueryException(Exception):
    """CSGO数据查询失败异常"""

    def __init__(self, message: str = "CSGO数据查询失败", *args):
        self.message = message
        super().__init__(message, *args)

    def __str__(self) -> str:
        return self.message


class SteamIdNotBoundException(Exception):
    """Steam ID未绑定异常"""

    def __init__(self, message: str | None = None, *args):
        self.message = message or "未绑定Steam ID，请先使用'绑定steam'命令绑定"
        super().__init__(self.message, *args)

    def __str__(self) -> str:
        return self.message
