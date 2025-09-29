import random
import time

from pydantic import BaseModel

EXPIRE_TIME = 30


class PlayerDeathException(Exception):
    """玩家死亡异常"""

    def __init__(
        self, player_id: str, player_name: str, weapon_name: str = "", message: str = ""
    ):
        self.player_id = player_id
        self.player_name = player_name
        self.weapon_name = weapon_name
        self.message = message or f"玩家 {player_name} 被 {weapon_name} 击中死亡！"
        super().__init__(self.message)


class Russian(BaseModel):
    at_user: str | None
    """指定决斗对象"""
    player1: tuple[str, str]
    """玩家1id, 昵称"""
    player2: tuple[str, str] | None = None
    """玩家2id, 昵称"""
    money: int
    """金额"""
    bullet_num: int
    """子弹数"""
    bullet_arr: list[int] = []
    """子弹排列"""
    bullet_index: int = 0
    """当前子弹下标"""
    next_user: str = ""
    """下一个开枪用户"""
    time: float = time.time()
    """创建时间"""
    win_user: str | None = None
    """胜利者"""
    is_ai: bool = False
    """是否是人机对局"""
    weapon: str = "standard"
    """武器类型"""

    def random_bullet(self):
        """随机排列剩余子弹"""
        bullet_arr = self.bullet_arr[self.bullet_index + 1 :]
        self.bullet_arr = self.bullet_arr[: self.bullet_index + 1]
        random.shuffle(bullet_arr)
        self.bullet_arr.extend(bullet_arr)


death_messages = [
    '"嘭！"，你被击中了，直接去世了',
    "眼前一黑，你直接穿越到了异世界...(死亡)",
    "终究还是你先走一步...",
]

live_messages = [
    "呼呼，没有爆裂的声响，你活了下来",
    "虽然黑洞洞的枪口很恐怖，但好在没有子弹射出来，你活下来了",
    '"咔"，你没死，看来运气不错',
]
