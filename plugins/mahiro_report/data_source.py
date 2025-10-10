import asyncio
from datetime import datetime
from pathlib import Path

import xml.etree.ElementTree as ET
from zhdate import ZhDate

from zhenxun import ui
from zhenxun.configs.config import Config
from zhenxun.utils.http_utils import AsyncHttpx

from .config import REPORT_PATH, Anime, Hitokoto, SixData
from .date import get_festivals_dates


class Report:
    hitokoto_url = "https://v1.hitokoto.cn/?c=a"
    alapi_url = "https://v3.alapi.cn/api/zaobao"
    six_url = "https://60s.viki.moe/v2/60s"  # 如域名无法访问，可使用公共实例: https://docs.60s-api.viki.moe/7306811m0
    bili_url = "https://s.search.bilibili.com/main/hotword"
    it_url = "https://www.ithome.com/rss/"
    anime_url = "https://api.bgm.tv/calendar"

    week = {  # noqa: RUF012
        0: "一",
        1: "二",
        2: "三",
        3: "四",
        4: "五",
        5: "六",
        6: "日",
    }

    @classmethod
    async def get_report_image(cls) -> Path:
        """获取数据"""
        now = datetime.now()
        file = REPORT_PATH / f"{now.date()}.png"
        if file.exists():
            return file
        for f in REPORT_PATH.iterdir():
            f.unlink()
        zhdata = ZhDate.from_datetime(now)
        hitokoto, bili, six, it, anime = await asyncio.gather(
            *[
                cls.get_hitokoto(),
                cls.get_bili(),
                cls.get_six(),
                cls.get_it(),
                cls.get_anime(),
            ]
        )
        data = {
            "data_festival": get_festivals_dates(),
            "data_hitokoto": hitokoto,
            "data_bili": bili,
            "data_six": six,
            "data_anime": anime,
            "data_it": it,
            "week": cls.week[now.weekday()],
            "date": now.date(),
            "zh_date": zhdata.chinese().split()[0][5:],
            "full_show": Config.get_config("mahiro_report", "full_show"),
        }
        template_path = Path(__file__).parent / "mahiro_report" / "main.html"
        component = ui.template(template_path, data=data)
        image_bytes = await ui.render(
            component, viewport={"width": 578, "height": 1885}, wait=2
        )
        with open(file, "wb") as f:
            f.write(image_bytes)
        return file

    @classmethod
    async def get_hitokoto(cls) -> str:
        """获取一言"""
        res = await AsyncHttpx.get(cls.hitokoto_url)
        data = Hitokoto(**res.json())
        return data.hitokoto

    @classmethod
    async def get_bili(cls) -> list[str]:
        """获取哔哩哔哩热搜"""
        res = await AsyncHttpx.get(cls.bili_url)
        data = res.json()
        return [item["keyword"] for item in data["list"]]

    @classmethod
    async def get_alapi_data(cls) -> list[str]:
        """获取alapi数据"""
        token = Config.get_config("alapi", "ALAPI_TOKEN")  # 从配置中获取alapi
        payload = {"token": token, "format": "json"}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        res = await AsyncHttpx.post(cls.alapi_url, data=payload, headers=headers)
        if res.status_code != 200:
            return ["Error: Unable to fetch data"]
        data = res.json()
        news_items = data.get("data", {}).get("news", [])
        return news_items[:11] if len(news_items) > 11 else news_items

    @classmethod
    async def get_six(cls) -> list[str]:
        """获取60s数据"""
        if Config.get_config("alapi", "ALAPI_TOKEN"):
            return await cls.get_alapi_data()
        res = await AsyncHttpx.get(cls.six_url)
        data = SixData(**res.json())
        return data.data.news[:11] if len(data.data.news) > 11 else data.data.news

    @classmethod
    async def get_it(cls) -> list[str]:
        """获取it数据"""
        res = await AsyncHttpx.get(cls.it_url)
        root = ET.fromstring(res.text)
        titles = []
        for item in root.findall("./channel/item"):
            title_element = item.find("title")
            if title_element is not None:
                titles.append(title_element.text)
        return titles[:11] if len(titles) > 11 else titles

    @classmethod
    async def get_anime(cls) -> list[tuple[str, str]]:
        """获取动漫数据"""
        res = await AsyncHttpx.get(cls.anime_url)
        data_list = []
        week = datetime.now().weekday()
        try:
            anime = Anime(**res.json()[week])
        except IndexError:
            anime = Anime(**res.json()[-1])
        data_list.extend(
            (data.name_cn or data.name, data.image) for data in anime.items
        )
        return data_list[:8] if len(data_list) > 8 else data_list
