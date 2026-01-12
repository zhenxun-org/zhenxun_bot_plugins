import asyncio
from typing import Any

from httpx import AsyncClient, HTTPError

from zhenxun.services.log import logger

API_BASE = "https://www.kkrb.net"
URLS = {
    "MENU": f"{API_BASE}/getMenu",
    "OVERVIEW": f"{API_BASE}/getOVData",
    "HOME": f"{API_BASE}/?viewpage=view%2Foverview",
    "CPV": f"{API_BASE}/getCPVData",
}

# 战备值映射 (等级 -> 目标金额)
COST_MAPPING = {0: 112500, 1: 187500, 2: 550000, 3: 600000, 4: 780000}

# 地图代号映射
MAP_NAMES = {
    "db": "零号大坝",
    "cgxg": "长弓溪谷",
    "bks": "巴克什",
    "htjd": "航天基地",
    "cxjy": "潮汐监狱",
}

# 工作台类型映射
WORKSHOP_NAMES = {
    "tech": "技术中心",
    "workbench": "工作台",
    "pharmacy": "制药台",
    "armory": "防具台",
}

# 请求头
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": URLS["HOME"],
    "X-Requested-With": "XMLHttpRequest",
}

class DeltaService:
    """处理三角洲数据的服务类"""

    def __init__(self):
        self.client: AsyncClient | None = None
        self.version_cookie: str = ""
        # 共享 Session，复用连接
        self.client = AsyncClient(headers=DEFAULT_HEADERS, timeout=10.0)

    async def _ensure_cookies(self, force_refresh: bool = False):
        """确保 Cookie 有效，必要时刷新"""
        if (
            not force_refresh
            and self.version_cookie
            and self.client.cookies.get("PHPSESSID")
        ):
            return

        logger.info("正在获取/刷新三角洲 Cookie...")
        try:
            # 1. 访问主页获取 PHPSESSID
            await self.client.get(URLS["HOME"])

            # 2. 获取版本号
            resp = await self.client.post(URLS["MENU"])
            data = resp.json()
            self.version_cookie = data.get("built_ver", "")

            if not self.version_cookie:
                raise ValueError("未获取到版本号")

            logger.info(f"Cookie刷新成功: Ver={self.version_cookie}")
        except Exception as e:
            logger.error(f"获取Cookie失败: {e}")
            raise

    async def get_game_data(self) -> dict[str, Any]:
        """并发获取所有游戏数据"""
        await self._ensure_cookies()

        form_data = {"version": self.version_cookie, "globalData": "false"}

        try:
            # 并发请求 API，提高速度
            ov_task = self.client.post(URLS["OVERVIEW"], data=form_data)
            cpv_task = self.client.post(URLS["CPV"], data=form_data)

            ov_resp, cpv_resp = await asyncio.gather(ov_task, cpv_task)

            # 检查响应状态 (如果 Session 过期可能返回特定错误，这里简单处理)
            if ov_resp.status_code != 200 or cpv_resp.status_code != 200:
                raise HTTPError("API请求返回非200状态")

            return {
                "overview": ov_resp.json().get("data", {}),
                "cpv": cpv_resp.json().get("data", []),
            }
        except Exception:
            # 如果请求失败，尝试刷新 Cookie 后再试一次（简单的重试机制）
            logger.warning("数据请求失败，尝试刷新Cookie重试...")
            await self._ensure_cookies(force_refresh=True)
            # 更新 form_data 的 version
            form_data["version"] = self.version_cookie

            ov_resp = await self.client.post(URLS["OVERVIEW"], data=form_data)
            cpv_resp = await self.client.post(URLS["CPV"], data=form_data)

            return {
                "overview": ov_resp.json().get("data", {}),
                "cpv": cpv_resp.json().get("data", []),
            }

    def process_passwords(self, bd_data: dict) -> str:
        """处理地图密码"""
        lines = []
        for code, name in MAP_NAMES.items():
            pwd = bd_data.get(code, {}).get("password", "未知")
            lines.append(f"{name}: {pwd}")
        return "\n".join(lines)

    def process_profits(self, sp_data: dict) -> str:
        """处理特勤处利润"""
        lines = ["特勤处制作产物推荐:"]
        for code, name in WORKSHOP_NAMES.items():
            info = sp_data.get(code, {})
            item_name = info.get("itemName", "未知")
            profit = int(info.get("profit", 0))
            lines.append(f"{name}: {item_name}\n当前利润: {profit}")
        return "\n".join(lines)