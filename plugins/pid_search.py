from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo
from pydantic import BaseModel
from zhenxun.configs.config import Config
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.withdraw_manage import WithdrawManager

__plugin_meta__ = PluginMetadata(
    name="pid搜索",
    description="通过 pid 搜索图片",
    usage="""
    在群组中30s内撤回
    通过 pid 搜索图片
    指令：
        p搜 [pid]
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        configs=[
            RegisterConfig(
                module="pixiv",
                key="PIXIV_NGINX_URL",
                value="pixiv.re",
                help="PIXPixiv反向代理",
            )
        ],
    ).dict(),
)


headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.6;"
    " rv:2.0.1) Gecko/20100101 Firefox/4.0.1",
    "Referer": "https://www.pixiv.net",
}

_matcher = on_alconna(
    Alconna("p搜", Args["pid?", str]), aliases={"P搜"}, priority=5, block=True
)


class UserModel(BaseModel):
    id: int
    """用户id"""
    name: str
    """用户名"""


class PixivModel(BaseModel):
    id: int
    """作品id"""
    title: str
    """标题"""
    user: UserModel
    """用户"""
    meta_single_page: dict[str, str]
    """单图"""
    meta_pages: list[dict[str, dict[str, str]]]
    """多图"""


@_matcher.handle()
async def _(pid: Match[int]):
    if pid.available:
        _matcher.set_path_arg("pid", pid.result)


@_matcher.got_path("pid", prompt="需要查询的图片PID是？或发送'取消'结束搜索")
async def _(bot: Bot, session: Uninfo, arparma: Arparma, pid: str):
    url = Config.get_config("hibiapi", "HIBIAPI") + "/api/pixiv/illust"
    if pid in {"取消", "算了"}:
        await MessageUtils.build_message("已取消操作...").finish()
    if not pid.isdigit():
        await MessageUtils.build_message("pid必须为数字...").finish()
    try:
        res = await AsyncHttpx.get(url, params={"id": pid}, timeout=5)
    except Exception as e:
        logger.error("p搜请求接口失败", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("请求接口失败...").finish()
    if res.status_code != 200:
        await MessageUtils.build_message(
            f"请求接口失败 code: {res.status_code}..."
        ).finish()
    data = res.json()
    if data.get("error"):
        await MessageUtils.build_message(data["error"]["user_message"]).finish(
            reply_to=True
        )
    if not data.get("illust"):
        await MessageUtils.build_message("没有找到该图片...").finish(reply_to=True)
    try:
        model = PixivModel(**data["illust"])
        image_list = []
        if model.meta_single_page:
            image_list.append(model.meta_single_page["original_image_url"])
        else:
            await MessageUtils.build_message("正在下载多张图片，请稍等哦...").send()
            image_list.extend(
                image_url["image_urls"]["original"] for image_url in model.meta_pages
            )
    except Exception as e:
        logger.error("p搜解析数据失败", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("解析数据失败...").finish(reply_to=True)
    pixiv_nginx = Config.get_config("pixiv", "PIXIV_NGINX_URL")
    file_list = []
    for i, img_url in enumerate(image_list):
        img_type = img_url.rsplit(".")[-1]
        if len(image_list) == 1:
            img_url = f"https://{pixiv_nginx}/{model.id}.{img_type}"
        else:
            img_url = f"https://{pixiv_nginx}/{model.id}-{i+1}.{img_type}"
        file = TEMP_PATH / f"pid_search_{session.user.id}_{i}.{img_type}"
        if not await AsyncHttpx.download_file(img_url, file, headers=headers):
            file_list.append(f"图片{model.id}-{i+1}下载失败了...")
            continue
        file_list.append(file)
    tmp = "\n【注】将在30后撤回......" if session.group else ""
    message_list = [
        f"title：{model.title}\npid：{pid}\nauthor：{model.user.name}\nauthor_id：{model.user.id}\n",
        *file_list,
        tmp,
    ]
    receipt = await MessageUtils.build_message(message_list).send()
    logger.info(f" 查询图片 PID：{pid}", arparma.header_result, session=session)
    if session.group:
        await WithdrawManager.withdraw_message(
            bot,
            receipt.msg_ids[0]["message_id"],
            30,  # type: ignore
        )
