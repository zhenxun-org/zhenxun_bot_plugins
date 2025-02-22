class NotResultException(Exception):
    """没有结果"""

    pass


class GiftRepeatSendException(Exception):
    """礼物重复发送"""

    pass


class CallApiParamException(Exception):
    """调用api参数错误"""

    pass
