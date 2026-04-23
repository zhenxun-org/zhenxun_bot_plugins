from datetime import datetime, timedelta
import time
from typing import Any

from nonebot.adapters import Bot
from nonebot_plugin_alconna import Image, UniMessage

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

EPIC_PROMO_URL = (
    "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
    "?locale=zh-CN&country=CN&allowCountries=CN"
)
EPIC_CONTENT_URL = (
    "https://store-content-ipv4.ak.epicgames.com/api/zh-CN/content/products/{}"
)
EPIC_STORE_BASE = "https://store.epicgames.com/zh-CN"
REQUEST_HEADERS = {
    "Referer": "https://www.epicgames.com/store/zh-CN/",
    "Content-Type": "application/json; charset=utf-8",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36"
    ),
}

_GAME_CACHE_TTL_SECONDS = 60
_GAME_CACHE: tuple[float, list[dict[str, Any]]] | None = None
_DESP_CACHE_TTL_SECONDS = int(timedelta(hours=6).total_seconds())
_DESP_CACHE: dict[str, tuple[float, str]] = {}


def _parse_utc_time(raw_time: str | None) -> str:
    if not raw_time:
        return "未知"
    try:
        return datetime.fromisoformat(raw_time.replace("Z", "+00:00")).strftime(
            "%b.%d %H:%M"
        )
    except ValueError:
        return "未知"


def _pick_thumbnail(game: dict[str, Any]) -> str | None:
    for image in game.get("keyImages", []):
        if image.get("url") and image.get("type") in {
            "Thumbnail",
            "VaultOpened",
            "DieselStoreFrontWide",
            "OfferImageWide",
        }:
            return image["url"]
    return None


def _pick_dev_pub(game: dict[str, Any], default: str) -> tuple[str, str]:
    game_dev, game_pub = default, default
    for pair in game.get("customAttributes", []):
        if pair.get("key") == "developerName":
            game_dev = pair.get("value") or default
        elif pair.get("key") == "publisherName":
            game_pub = pair.get("value") or default
    return game_dev, game_pub


def _build_game_url(game: dict[str, Any]) -> str:
    if slug := game.get("productSlug"):
        return f"{EPIC_STORE_BASE}/p/{str(slug).replace('/home', '')}"
    if url := game.get("url"):
        return str(url)

    slugs = (
        [
            x.get("pageSlug")
            for x in game.get("offerMappings", [])
            if x.get("pageType") == "productHome"
        ]
        + [
            x.get("pageSlug")
            for x in game.get("catalogNs", {}).get("mappings", [])
            if x.get("pageType") == "productHome"
        ]
        + [
            x.get("value")
            for x in game.get("customAttributes", [])
            if "productSlug" in str(x.get("key", ""))
        ]
    )
    slugs = [s for s in slugs if s]
    return f"{EPIC_STORE_BASE}/p/{slugs[0]}" if slugs else EPIC_STORE_BASE


async def get_epic_game() -> list[dict[str, Any]] | None:
    """获取 Epic 免费/即将免费游戏列表（带短缓存）。"""
    global _GAME_CACHE
    now_ts = time.time()
    if _GAME_CACHE and now_ts - _GAME_CACHE[0] <= _GAME_CACHE_TTL_SECONDS:
        return _GAME_CACHE[1]

    try:
        res = await AsyncHttpx.get(EPIC_PROMO_URL, headers=REQUEST_HEADERS, timeout=10)
        games = res.json()["data"]["Catalog"]["searchStore"]["elements"]
        if isinstance(games, list):
            _GAME_CACHE = (now_ts, games)
            return games
    except Exception as e:
        logger.error("Epic 访问接口错误", e=e)
    return None


async def get_epic_game_desp(slug: str) -> str:
    """获取并缓存游戏简介。"""
    now_ts = time.time()
    if slug in _DESP_CACHE and now_ts - _DESP_CACHE[slug][0] <= _DESP_CACHE_TTL_SECONDS:
        return _DESP_CACHE[slug][1]

    try:
        res = await AsyncHttpx.get(
            EPIC_CONTENT_URL.format(slug),
            headers={
                **REQUEST_HEADERS,
                "Referer": f"{EPIC_STORE_BASE}/p/{slug}",
            },
            timeout=10,
        )
        about = res.json().get("pages", [{}])[0].get("data", {}).get("about", {})
        if isinstance(about, dict):
            desc = (
                about.get("shortDescription") or about.get("description") or ""
            ).strip()
            _DESP_CACHE[slug] = (now_ts, desc)
            return desc
    except Exception as e:
        logger.error("Epic 访问简介接口错误", e=e)
    return ""


def _upcoming_text(
    game_name: str, game_corp: str, game_price: str, start: str, end: str
) -> str:
    return (
        f"\n由 {game_corp} 公司发行的游戏 {game_name} ({game_price}) "
        f"在 UTC 时间 {start} 即将推出免费游玩，预计截至 {end}。"
    )


def _free_text(
    game_name: str,
    game_price: str,
    game_desp: str,
    game_dev: str,
    game_pub: str,
    end_date: str,
    game_url: str,
) -> str:
    return (
        f"\nFREE now :: {game_name} ({game_price})\n"
        f"{game_desp}\n"
        f"此游戏由 {game_dev} 开发、{game_pub} 发行，"
        f"将在 UTC 时间 {end_date} 结束免费游玩，"
        f"戳链接速度加入你的游戏库吧~\n{game_url}\n"
    )


async def get_epic_free(
    bot: Bot, type_event: str
) -> tuple[UniMessage | list | str, int]:
    """
    获取 Epic 免费游戏信息。

    返回:
        tuple[UniMessage | list | str, int]:
            - list: 群聊合并转发数据
            - UniMessage: 普通消息
            - str: 错误文本
    """
    games = await get_epic_game()
    if not games:
        return "Epic 可能又抽风啦，请稍后再试（", 404

    can_forward = type_event == "Group" and PlatformUtils.is_forward_merge_supported(
        bot
    )
    forward_messages: list[Any] = []
    normal_messages: list[Any] = []

    for game in games:
        try:
            game_name = game.get("title", "未知游戏")
            game_corp = game.get("seller", {}).get("name", "未知厂商")
            game_price = (
                game.get("price", {})
                .get("totalPrice", {})
                .get("fmtPrice", {})
                .get("originalPrice", "未知价格")
            )
            promotions = game.get("promotions") or {}
            current_promos = promotions.get("promotionalOffers") or []
            upcoming_promos = promotions.get("upcomingPromotionalOffers") or []

            # 即将免费
            if not current_promos and upcoming_promos:
                promo = (
                    upcoming_promos[0].get("promotionalOffers", [{}])[0]
                    if upcoming_promos[0].get("promotionalOffers")
                    else {}
                )
                start_date = _parse_utc_time(promo.get("startDate"))
                end_date = _parse_utc_time(promo.get("endDate"))
                text = _upcoming_text(
                    game_name, game_corp, game_price, start_date, end_date
                )
                if can_forward:
                    forward_messages.append(text)
                else:
                    normal_messages.extend((text, "\n"))
                continue

            # 当前免费
            game_thumbnail = _pick_thumbnail(game)
            game_dev, game_pub = _pick_dev_pub(game, game_corp)
            game_desp = (game.get("description") or "").strip()
            if slug := game.get("productSlug"):
                # 有 slug 则尝试拉取更完整简介（带缓存）
                better_desp = await get_epic_game_desp(str(slug))
                if better_desp:
                    game_desp = better_desp
            if not game_desp:
                game_desp = "暂无简介"

            try:
                end_date_raw = current_promos[0]["promotionalOffers"][0].get("endDate")
            except (IndexError, KeyError, TypeError):
                end_date_raw = None
            end_date = _parse_utc_time(end_date_raw)
            game_url = _build_game_url(game)
            text = _free_text(
                game_name, game_price, game_desp, game_dev, game_pub, end_date, game_url
            )

            if can_forward:
                message_block: list[Any] = [text]
                if game_thumbnail:
                    message_block.insert(0, Image(url=game_thumbnail))
                forward_messages.append(message_block)
            else:
                if game_thumbnail:
                    normal_messages.append(Image(url=game_thumbnail))
                normal_messages.extend((text, "\n"))
        except Exception as e:
            logger.warning(f"Epic 解析单个游戏失败: {e}")

    if can_forward:
        if not forward_messages:
            return "暂时没有可展示的免费游戏信息。", 404
        return MessageUtils.template2forward(forward_messages, bot.self_id), 200

    if not normal_messages:
        return "暂时没有可展示的免费游戏信息。", 404
    return MessageUtils.build_message(normal_messages), 200
