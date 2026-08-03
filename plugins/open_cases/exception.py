class NotLoginRequired(Exception):
    """未登录异常"""


class CallApiError(Exception):
    """调用api异常"""

    def __ini__(self, info: str):
        self.info = info

    def get_info(self) -> str:
        return self.info
