import re
from zhenxun.services.log import logger

from .utils import get_user_dynamics


async def is_ad(uid: int, dynamic_id: str) -> bool:
    """使用 Bilibili API 检查动态内容是否为广告"""
    try:
        logger.info(f"[广告过滤-API] 开始检查动态: UID={uid}, 动态ID={dynamic_id}")

        logger.debug(f"[广告过滤-API] 正在获取用户动态数据: UID={uid}")
        dynamics_data = await get_user_dynamics(uid)
        if not dynamics_data or not dynamics_data.get("cards"):
            logger.warning(
                f"[广告过滤-API] 未获取到动态数据: UID={uid}, 数据为空或无cards字段"
            )
            return False

        logger.debug(
            f"[广告过滤-API] 成功获取动态数据: UID={uid}, 动态数量={len(dynamics_data.get('cards', []))}"
        )

        logger.debug(f"[广告过滤-API] 正在查找指定动态: UID={uid}, 动态ID={dynamic_id}")
        target_dynamic = None
        available_ids = []
        for card in dynamics_data["cards"]:
            card_dynamic_id = str(card["desc"]["dynamic_id"])
            available_ids.append(card_dynamic_id)
            if card_dynamic_id == str(dynamic_id):
                target_dynamic = card
                break

        if not target_dynamic:
            logger.warning(
                f"[广告过滤-API] 未找到指定动态: UID={uid}, 动态ID={dynamic_id}, 可用动态ID={available_ids[:5]}..."
            )
            return False

        logger.debug(f"[广告过滤-API] 成功找到目标动态: UID={uid}, 动态ID={dynamic_id}")

        dynamic_type = target_dynamic["desc"].get("type", 0)
        logger.debug(
            f"[广告过滤-API] 动态类型检查: UID={uid}, 动态ID={dynamic_id}, 类型={dynamic_type}"
        )

        goods_types = {
            19: "商品分享",
            64: "专栏文章（可能包含商品）",
        }

        if dynamic_type in goods_types:
            logger.warning(
                f"[广告过滤-API] 检测到商品类型动态: UID={uid}, 动态ID={dynamic_id}, 类型={dynamic_type}({goods_types[dynamic_type]})"
            )
            return True

        logger.debug(
            f"[广告过滤-API] 动态类型检查通过: UID={uid}, 动态ID={dynamic_id}, 类型={dynamic_type}"
        )

        logger.debug(f"[广告过滤-API] 开始检查动态内容: UID={uid}, 动态ID={dynamic_id}")
        card_data = target_dynamic.get("card", "")
        if isinstance(card_data, str):
            try:
                import json

                card_json = json.loads(card_data)
                logger.debug(
                    f"[广告过滤-API] 成功解析动态卡片JSON: UID={uid}, 动态ID={dynamic_id}"
                )
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    f"[广告过滤-API] 动态卡片JSON解析失败: UID={uid}, 动态ID={dynamic_id}, 错误={e}"
                )
                card_json = {}
        else:
            card_json = card_data
            logger.debug(
                f"[广告过滤-API] 动态卡片数据为字典格式: UID={uid}, 动态ID={dynamic_id}"
            )

        text_content = ""
        content_sources = []

        if "item" in card_json:
            item = card_json["item"]
            if "description" in item:
                text_content += item["description"]
                content_sources.append("item.description")
            if "content" in item:
                text_content += item["content"]
                content_sources.append("item.content")

        if "user" in card_json and "description" in card_json["user"]:
            text_content += card_json["user"]["description"]
            content_sources.append("user.description")

        logger.debug(
            f"[广告过滤-API] 提取文本内容: UID={uid}, 动态ID={dynamic_id}, 来源={content_sources}, 长度={len(text_content)}"
        )

        logger.debug(f"[广告过滤-API] 开始关键词检查: UID={uid}, 动态ID={dynamic_id}")
        ad_keywords = [
            "商品",
            "购买",
            "链接",
            "店铺",
            "优惠",
            "折扣",
            "带货",
            "种草",
            "好物",
            "推荐",
            "下单",
            "抢购",
            "限时",
            "特价",
            "促销",
            "¥",
            "￥",
            "元",
            "价格",
            "原价",
            "现价",
            "到手价",
            "淘宝",
            "天猫",
            "京东",
            "拼多多",
            "抖音",
            "小红书",
            "直播间",
            "橱窗",
            "购物车",
            "加购",
            "收藏",
        ]

        text_lower = text_content.lower()
        found_keywords = []
        for keyword in ad_keywords:
            if keyword in text_content or keyword.lower() in text_lower:
                found_keywords.append(keyword)

        if found_keywords:
            logger.warning(
                f"[广告过滤-API] 检测到广告关键词: UID={uid}, 动态ID={dynamic_id}, 关键词={found_keywords}"
            )
            return True

        logger.debug(f"[广告过滤-API] 关键词检查通过: UID={uid}, 动态ID={dynamic_id}")

        logger.debug(f"[广告过滤-API] 开始商品卡片检查: UID={uid}, 动态ID={dynamic_id}")
        goods_fields = []
        if "goods" in card_json:
            goods_fields.append("goods")
        if "mall" in card_json:
            goods_fields.append("mall")

        if goods_fields:
            logger.warning(
                f"[广告过滤-API] 检测到商品卡片: UID={uid}, 动态ID={dynamic_id}, 字段={goods_fields}"
            )
            return True

        logger.debug(f"[广告过滤-API] 商品卡片检查通过: UID={uid}, 动态ID={dynamic_id}")

        logger.debug(f"[广告过滤-API] 开始商品链接检查: UID={uid}, 动态ID={dynamic_id}")
        url_patterns = {
            r"item\.taobao\.com": "淘宝商品",
            r"detail\.tmall\.com": "天猫商品",
            r"item\.jd\.com": "京东商品",
            r"yangkeduo\.com": "拼多多商品",
            r"haohuo\.jinritemai\.com": "抖音好货",
        }

        for pattern, platform in url_patterns.items():
            if re.search(pattern, text_content, re.IGNORECASE):
                logger.warning(
                    f"[广告过滤-API] 检测到商品链接: UID={uid}, 动态ID={dynamic_id}, 平台={platform}, 模式={pattern}"
                )
                return True

        logger.debug(f"[广告过滤-API] 商品链接检查通过: UID={uid}, 动态ID={dynamic_id}")
        logger.info(
            f"[广告过滤-API] 动态内容检查完成，未发现广告: UID={uid}, 动态ID={dynamic_id}"
        )
        return False

    except Exception as e:
        logger.error(
            f"[广告过滤-API] API方式检查动态内容失败: UID={uid}, 动态ID={dynamic_id}, 错误类型={type(e).__name__}, 错误={e}"
        )
        import traceback

        logger.debug(f"[广告过滤-API] 详细错误信息:\n{traceback.format_exc()}")
        return False
