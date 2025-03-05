from collections.abc import Callable
import uuid

from ..models.bym_gift_store import GiftStore


class GiftRegister(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data: dict[str, Callable] = {}
        self._create_list: list[GiftStore] = []

    def get_func(self, name: str) -> Callable | None:
        return self._data.get(name)

    async def load_register(self):
        """加载注册函数

        参数:
            name: 名称
        """
        name_list = await GiftStore.all().values_list("name", flat=True)
        if self._create_list:
            await GiftStore.bulk_create(
                [a for a in self._create_list if a.name not in name_list],
                10,
                True,
            )

    def __call__(
        self,
        name: str,
        icon: str,
        description: str,
    ):
        """注册礼物

        参数:
            name: 名称
            icon: 图标
            description: 描述
        """
        if name in [s.name for s in self._create_list]:
            raise ValueError(f"礼物 {name} 已存在")
        self._create_list.append(
            GiftStore(
                uuid=str(uuid.uuid4()), name=name, icon=icon, description=description
            )
        )

        def add_register_item(func: Callable):
            self._data[name] = func
            return func

        return add_register_item

    def __setitem__(self, key, value):
        self._data[key] = value

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def __str__(self):
        return str(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


gift_register = GiftRegister()
