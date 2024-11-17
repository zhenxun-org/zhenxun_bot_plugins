from strenum import StrEnum


class KwType(StrEnum):
    """关键词类型"""

    KEYWORD = "KEYWORD"
    """关键词"""
    UID = "UID"
    """用户uid"""
    PID = "PID"
    """图片pid"""
    BLACK = "BLACK"
    """黑名单"""


class SeekType(StrEnum):
    """搜索类型"""

    KEYWORD = "KEYWORD"
    """关键词"""
    UID = "UID"
    """用户uid"""
    PID = "PID"
    """图片pid"""
    ALL = "ALL"
    """ALL"""


class KwHandleType(StrEnum):
    """关键词类型"""

    PASS = "PASS"
    """通过"""
    IGNORE = "IGNORE"
    """忽略"""
    FAIL = "FAIL"
    """未通过"""
    BLACK = "BLACK"
    """黑名单"""
