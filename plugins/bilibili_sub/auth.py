import random
from typing import ClassVar

from bilireq.auth import Auth
from nonebot import get_driver
from nonebot.log import logger
import ujson as json

from .config import BASE_PATH, LOG_COMMAND

auth_file = BASE_PATH / "bili_auth.json"
auth_file.touch()


class AuthManager:
    grpc_auths: ClassVar[list[Auth]] = []

    @classmethod
    async def load_auths(cls) -> None:
        data: list[dict] | dict = json.loads(auth_file.read_bytes() or "[]")
        data = data if isinstance(data, list) else [data]
        cls.grpc_auths.clear()
        for raw_auth in data:
            auth = Auth(raw_auth)
            try:
                auth = await auth.refresh()
                cls.grpc_auths.append(auth)
                logger.success(f"{auth.uid} 缓存登录成功", LOG_COMMAND)
            except Exception as e:
                logger.error(
                    f"{auth.uid} 缓存登录失败，请使用二维码登录: {e}", LOG_COMMAND
                )
        cls.dump_auths()

    @classmethod
    def dump_auths(cls):
        auth_file.write_text(
            json.dumps(
                [auth.data for auth in cls.grpc_auths], indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )

    @classmethod
    def get_cookies(cls) -> dict[str, str]:
        if auths := cls.grpc_auths.copy():
            random.shuffle(auths)
            for auth in auths:
                if auth.cookies:
                    return auth.cookies.copy()
        logger.warning("没有可用的 bilibili cookies，请求可能风控", LOG_COMMAND)
        return {}

    @classmethod
    def get_auth(cls) -> Auth | None:
        return random.choice(cls.grpc_auths).copy() if cls.grpc_auths else None

    @classmethod
    def add_auth(cls, auth: Auth) -> None:
        for old_auth in cls.grpc_auths:
            if old_auth.uid == auth.uid:
                cls.grpc_auths.remove(old_auth)
                break
        cls.grpc_auths.append(auth)
        cls.dump_auths()

    @classmethod
    def remove_auth(cls, uid: int) -> str | None:
        for old_auth in cls.grpc_auths:
            if old_auth.uid == uid:
                cls.grpc_auths.remove(old_auth)
                cls.dump_auths()
                return
        logger.warning(f"没有找到 uid 为 {uid} 的账号")
        return f"没有找到 uid 为 {uid} 的账号"


driver = get_driver()


@driver.on_startup
async def _():
    await AuthManager.load_auths()
