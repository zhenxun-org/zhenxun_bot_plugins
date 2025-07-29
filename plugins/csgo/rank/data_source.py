from zhenxun.services.log import logger

from ..config import LOG_COMMAND
from ..models.csgo_user import CsgoUser


class CsgoRankManager:
    @classmethod
    async def get_group_user_rank(
        cls, user_id: str, user_id_list: list[str], rank_type: str, num: int = 10
    ):
        """获取用户分数排名

        参数:
            user_id: 用户ID
            user_id_list: 用户ID列表
            num: 数量，默认10，最大50

        异常:
            SteamIdNotBoundException: 用户未绑定Steam ID

        返回:
            list: 排序后的用户分数列表，每项包含用户ID、用户名、分数等信息
        """
        try:
            # 限制返回数量
            num = min(num, 50)

            # 获取用户及其最新赛季的完美统计数据
            result = []

            # 使用 prefetch_related 一次性获取所有相关数据
            users = await CsgoUser.filter(user_id__in=user_id_list).prefetch_related(
                "perfect_stats"
            )

            for user in users:
                # 获取最新赛季的统计数据（按创建时间降序排序）
                if not user.perfect_stats:
                    continue

                # 找到最新的统计数据
                latest_stats = max(user.perfect_stats, key=lambda x: x.create_time)

                # 添加到结果列表
                result.append(
                    {
                        "user_id": user.user_id,
                        "name": user.perfect_name or user.official_name or user.user_id,
                        "avatar": user.perfect_avatar_url
                        or user.official_avatar_url
                        or "",
                        "rating": latest_stats.rating,
                        "pw_rating": latest_stats.pw_rating,
                        "season_id": latest_stats.season_id,
                        "kd_ratio": latest_stats.kd_ratio,
                        "win_rate": latest_stats.win_rate,
                        "total_matches": latest_stats.total_matches,
                        "pvp_rank": latest_stats.pvp_rank,
                        "pvp_score": latest_stats.pvp_score,
                        "stars": latest_stats.stars,
                    }
                )

            if rank_type == "score":
                # 按评分降序排序
                result.sort(key=lambda x: x["pvp_score"], reverse=True)
            elif rank_type == "rt":
                # 按评分降序排序
                result.sort(key=lambda x: x["pw_rating"], reverse=True)

            r_list = [r["user_id"] for r in result]
            user_index = (r_list.index(user_id) + 1) if user_id in r_list else -1

            # 返回指定数量
            return result[:num], user_index

        except Exception as e:
            logger.error("获取用户分数排名时发生错误", LOG_COMMAND, e=e)
            return [], -1
