from nonebot.params import Depends
from nonebot_plugin_alconna import At, Match

from zhenxun.utils.message import MessageUtils

from .config import CURRENT_SEASON


def CheckSeason():
    """
    检查赛季是否正确
    """

    async def dependency(target: Match[At | str], season: Match[str]):
        if not target.available and not season.available:
            return
        season_id = ""
        if season.available:
            season_id = season.result
        if (
            target.available
            and isinstance(target.result, str)
            and target.result.upper().startswith("S")
        ):
            season_id = target.result
        if season_id:
            if not season_id.upper().startswith("S"):
                await MessageUtils.build_message(
                    "赛季格式不正确！请确保是完美平台赛季，以S开头！例如：S20"
                ).finish()
            try:
                season_id = int(season_id[1:])
                if season_id < 1 or season_id > 20:
                    await MessageUtils.build_message(
                        "赛季不能小于S1，不能大于S20！"
                    ).finish()
            except ValueError:
                await MessageUtils.build_message(
                    "赛季格式不正确！请确保是完美平台赛季，以S开头！例如：S20"
                ).finish()

    return Depends(dependency)


def SeasonId():
    """
    获取赛季
    """

    async def dependency(target: Match[At | str], season: Match[str]):
        if season.available:
            return season.result.upper()
        if (
            target.available
            and isinstance(target.result, str)
            and target.result.upper().startswith("S")
        ):
            return target.result.upper()
        return CURRENT_SEASON

    return Depends(dependency)


def TargetId():
    """
    获取目标Id
    """

    async def dependency(target: Match[At | str]):
        if target.available and isinstance(target.result, At):
            return target.result.target
        return None

    return Depends(dependency)


def SteamId():
    """
    获取SteamId
    """

    async def dependency(target: Match[At | str]):
        if (
            target.available
            and isinstance(target.result, str)
            and not target.result.upper().startswith("S")
        ):
            return target.result
        return None

    return Depends(dependency)
