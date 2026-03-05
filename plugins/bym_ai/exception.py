class NotResultException(Exception):
    """没有结果"""

    pass


class GiftRepeatSendException(Exception):
    """礼物重复发送"""

    pass


__all__ = ["GiftRepeatSendException", "NotResultException"]
