"""
俄罗斯轮盘装备系统
使用注册器模式管理装备类型和效果
"""

from collections.abc import Callable
import random

from pydantic import BaseModel

from .config import PlayerDeathException, Russian


class EquipmentEffect(BaseModel):
    """装备效果配置"""

    name: str  # 效果名称
    description: str  # 效果描述
    effect_func: Callable[[Russian, str], str | None]


class Weapon(BaseModel):
    """左轮枪配置"""

    name: str  # 武器名称
    special_effect: EquipmentEffect
    description: str  # 武器描述


class EquipmentRegistry:
    """装备注册器"""

    def __init__(self):
        self._weapons: dict[str, Weapon] = {}
        self._effect_functions: dict[str, dict] = {}  # 存储装饰器注册的效果函数
        self._default_weapon = "standard"

    def register_weapon(self, weapon_id: str, weapon: Weapon) -> None:
        """注册武器"""
        self._weapons[weapon_id] = weapon

    def register_effect(
        self, effect_name: str, func: Callable[[Russian, str], object], description: str
    ) -> None:
        """注册效果函数"""
        self._effect_functions[effect_name] = {"func": func, "description": description}

    def get_weapon(self, weapon_id: str) -> Weapon:
        """获取武器配置"""
        return self._weapons.get(weapon_id, self._weapons[self._default_weapon])

    def get_weapons(self) -> dict[str, str]:
        """获取武器列表"""
        return {weapon_id: weapon.name for weapon_id, weapon in self._weapons.items()}

    def get_effect_by_name(self, effect_name: str) -> EquipmentEffect:
        """根据效果名称获取EquipmentEffect对象"""
        if effect_name in self._effect_functions:
            effect_data = self._effect_functions[effect_name]
            return EquipmentEffect(
                name=effect_name,
                description=effect_data["description"],
                effect_func=effect_data["func"],
            )
        raise ValueError(f"效果 {effect_name} 不存在")


# 创建全局装备注册器
equipment_registry = EquipmentRegistry()


# 武器注册装饰器
def weapon_register(weapon_id: str, name: str, description: str, effect_name: str):
    """武器注册装饰器"""

    def decorator(func):
        # 先注册效果函数（将被装饰的函数作为效果实现）
        equipment_registry.register_effect(effect_name, func, description)

        # 创建武器对象
        special_effect = equipment_registry.get_effect_by_name(effect_name)

        weapon = Weapon(
            name=name, special_effect=special_effect, description=description
        )

        # 注册武器
        equipment_registry.register_weapon(weapon_id, weapon)

        # 直接返回原函数，不需要包装
        return func

    return decorator


# 注册武器
@weapon_register(
    "standard", "标准左轮", "平衡的经典左轮手枪，是最初始的左轮手枪", "普通射击"
)
def register_standard_weapon(russian: Russian, user_id: str):
    """注册标准左轮"""
    if russian.bullet_arr[russian.bullet_index] == 1:
        raise PlayerDeathException(
            user_id,
            russian.player1[1],
            "标准左轮",
            "你中弹了！",
        )
    return None


@weapon_register(
    "lucky",
    "幸运左轮",
    "据说能带来好运的左轮手枪，当下一颗弹仓中非空弹时，有10%概率使子弹重新排序",
    "幸运一击",
)
def register_lucky_weapon(russian: Russian, user_id: str):
    """注册幸运左轮"""
    trigger_chance = 0.2 if russian.is_ai else 0.1
    if russian.bullet_arr[russian.bullet_index] == 1:
        if random.random() < trigger_chance:
            russian.random_bullet()
        else:
            raise PlayerDeathException(
                user_id,
                russian.player1[1],
                "幸运左轮",
                "重新排列子弹后依旧中弹，天命不可违！",
            )
        if russian.bullet_arr[russian.bullet_index] == 1:
            # 下一发依旧有子弹
            raise PlayerDeathException(
                user_id,
                russian.player1[1],
                "幸运左轮",
                "重新排列子弹后依旧中弹，天命不可违！",
            )
        return "幸运女神在上，成功触发了幸运一击！重新排列了子弹，成功躲避了死亡！"
    return None


@weapon_register(
    "deceiver",
    "欺诈左轮",
    "使用该左轮开枪时，将不再按照子弹排列的顺序开枪，而是完全由概率决定是否命中",
    "欺诈轨迹",
)
def register_deceiver_weapon(russian: Russian, user_id: str):
    """注册欺诈左轮"""
    trigger_chance = (russian.bullet_index + russian.bullet_num + 1) / len(
        russian.bullet_arr
    )

    if random.random() < trigger_chance:
        raise PlayerDeathException(
            user_id,
            russian.player1[1],
            "欺诈左轮",
            "触发了欺诈轨迹！你中弹了！",
        )
    return None


@weapon_register(
    "gambler",
    "赌徒左轮",
    "每次射击后，都会随机打乱子弹排列",
    "混乱",
)
def register_gambler_weapon(russian: Russian, user_id: str):
    """注册欺诈左轮"""
    if russian.bullet_arr[russian.bullet_index] == 1:
        raise PlayerDeathException(
            user_id,
            russian.player1[1],
            "赌徒左轮",
            "你中弹了！",
        )
    russian.random_bullet()
    return "赌徒左轮触发了混乱！重新排列了剩余子弹！"


# 便捷函数
def get_weapon(weapon_id: str) -> Weapon:
    """获取武器配置"""
    return equipment_registry.get_weapon(weapon_id)


def get_weapons() -> dict[str, str]:
    """获取武器列表"""
    return equipment_registry.get_weapons()
