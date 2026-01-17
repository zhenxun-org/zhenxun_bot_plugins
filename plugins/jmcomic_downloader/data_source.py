import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
import yaml
import time
import jmcomic
from jmcomic import JmAlbumDetail
from nonebot.adapters.onebot.v11 import Bot
from pikepdf import Encryption, Pdf
import pyminizip

from zhenxun.configs.path_config import DATA_PATH, TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.http_utils import AsyncHttpx


IMAGE_OUTPUT_PATH = TEMP_PATH / "jmcomic"
IMAGE_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

PDF_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_pdf"
ZIP_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_zip"
PDF_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
ZIP_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

OPTION_FILE = DATA_PATH / "jmcomic" / "option.yml"
CONFIG_FILE = DATA_PATH / "jmcomic" / "blacklist_config.yml"

# 确保配置文件所在目录存在
OPTION_FILE.parent.mkdir(parents=True, exist_ok=True)

# 检查并创建option.yml配置文件，使用原始配置内容
if not OPTION_FILE.exists():
    original_option_content = """# 开启jmcomic的日志输出，默认为true
# 对日志有需求的可进一步参考文档 → https://jmcomic.readthedocs.io/en/latest/tutorial/11_log_custom/
log: true

# 下载配置
download:
  cache: true # 如果要下载的文件在磁盘上已存在，不用再下一遍了吧？默认为true
  image:
    decode: true # JM的原图是混淆过的，要不要还原？默认为true
    suffix: .jpg # 把图片都转为.jpg格式，默认为null，表示不转换。
  threading:
    # image: 同时下载的图片数，默认是30张图
    # 数值大，下得快，配置要求高，对禁漫压力大
    # 数值小，下得慢，配置要求低，对禁漫压力小
    # PS: 禁漫网页一次最多请求50张图
    image: 30
    # photo: 同时下载的章节数，不配置默认是cpu的线程数。例如8核16线程的cpu → 16.
    photo: 16

# 文件夹规则配置，决定图片文件存放在你的电脑上的哪个文件夹
dir_rule:
  # base_dir: 根目录。
  # 此配置也支持引用环境变量，例如
  # base_dir: ${JM_DIR}/下载文件夹/
  base_dir: ./resources/temp/jmcomic

  # rule: 规则dsl。
  # 本项只建议了解编程的朋友定制，实现在这个类: jmcomic.jm_option.DirRule
  # 写法:
  # 1. 以'Bd'开头，表示根目录
  # 2. 文件夹每增加一层，使用 '_' 或者 '/' 区隔
  # 3. 用Pxxx或者Ayyy指代文件夹名，意思是 JmPhotoDetail.xxx / JmAlbumDetail的.yyy。xxx和yyy可以写什么需要看源码。
  #
  # 下面演示如果要使用禁漫网站的默认下载方式，该怎么写:
  # 规则: 根目录 / 本子id / 章节序号 / 图片文件
  # rule: 'Bd  / Aid   / Pindex'
  # rule: 'Bd_Aid_Pindex'

  # 默认规则是: 根目录 / 章节标题 / 图片文件
  rule: Bd_Ptitle

# 插件的配置示例
plugins:
  after_photo:
    # 把章节的所有图片合并为一个pdf的插件
    # 使用前需要安装依赖库: [pip install img2pdf]
    - plugin: img2pdf
      kwargs:
        pdf_dir: ./data/jmcomic/jmcomic_pdf # pdf存放文件夹
        filename_rule: Pid # pdf命名规则，P代表photo, id代表使用photo.id也就是章节id

  after_album:
    # img2pdf也支持合并整个本子，把上方的after_photo改为after_album即可。
    # https://github.com/hect0x7/JMComic-Crawler-Python/discussions/258
    # 配置到after_album时，需要修改filename_rule参数，不能写Pxx只能写Axx示例如下
    - plugin: img2pdf
      kwargs:
        pdf_dir: /data/jmcomic/jmcomic_pdf # pdf存放文件夹
        filename_rule: Aname # pdf命名规则，A代表album, name代表使用album.name也就是本子名称
"""
    with open(OPTION_FILE, "w", encoding="utf-8") as f:
        f.write(original_option_content)

# 在配置文件存在后再加载选项
option = jmcomic.create_option_by_file(str(OPTION_FILE.absolute()))


@dataclass
class DetailInfo:
    bot: Bot
    user_id: str
    group_id: str | None
    album_id: str


class BlacklistManager:
    # 黑名单管理器
    _config = None
    _config_path = CONFIG_FILE
    _synced_at = None  # 记录上次同步时间

    @classmethod
    def _load_config(cls):
        # 加载配置文件
        if cls._config is None:
            if cls._config_path.exists():
                with open(cls._config_path, "r", encoding="utf-8") as f:
                    cls._config = yaml.safe_load(f) or {
                        "super_users": [],
                        "blacklist": [],
                    }
            else:
                # 初始化配置文件并同步NoneBot超级用户
                cls._sync_nonebot_superusers()
                # 重新加载配置
                with open(cls._config_path, "r", encoding="utf-8") as f:
                    cls._config = yaml.safe_load(f) or {
                        "super_users": [],
                        "blacklist": [],
                    }
        return cls._config

    @classmethod
    def _sync_nonebot_superusers(cls):
        # 同步NoneBot配置中的超级用户到插件配置文件
        try:
            from nonebot import get_driver

            driver = get_driver()
            nonebot_superusers = getattr(driver.config, "superusers", set())
            if nonebot_superusers:
                # 加载现有配置
                if cls._config_path.exists():
                    with open(cls._config_path, "r", encoding="utf-8") as f:
                        existing_config = yaml.safe_load(f) or {
                            "super_users": [],
                            "blacklist": [],
                        }
                else:
                    existing_config = {"super_users": [], "blacklist": []}

                # 获取NoneBot超级用户列表
                nonebot_superusers_list = [str(uid) for uid in nonebot_superusers]

                # 合并现有的超级用户和NoneBot超级用户
                existing_superusers = existing_config.get("super_users", [])
                all_superusers = list(
                    set(existing_superusers + nonebot_superusers_list)
                )

                # 更新配置
                existing_config["super_users"] = all_superusers

                # 保存配置文件
                with open(cls._config_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        existing_config, f, default_flow_style=False, allow_unicode=True
                    )
        except Exception as e:
            logger.error(f"同步NoneBot超级用户失败: {e}", "jmcomic")

    @classmethod
    def _save_config(cls):
        # 保存配置文件
        with open(cls._config_path, "w", encoding="utf-8") as f:
            yaml.dump(cls._config, f, default_flow_style=False, allow_unicode=True)

    @classmethod
    def _clear_cache(cls):
        # 清除配置缓存
        cls._config = None

    @classmethod
    def is_super_user(cls, user_id: str) -> bool:
        # 只在必要时同步（5分钟内不重复）
        if not cls._synced_at or time.time() - cls._synced_at > 300:
            cls._sync_nonebot_superusers()
            cls._synced_at = time.time()

        config = cls._load_config()
        # 检查用户是否在NoneBot配置中
        try:
            from nonebot import get_driver

            driver = get_driver()
            nonebot_superusers = getattr(driver.config, "superusers", set())
            if str(user_id) in [str(uid) for uid in nonebot_superusers]:
                return True
        except Exception as e:
            logger.error(f"检查NoneBot超级用户失败: {e}", "jmcomic")
        # 检查用户是否在插件配置文件中
        return str(user_id) in [str(uid) for uid in config.get("super_users", [])]

    @classmethod
    def is_blacklisted(cls, album_id: str) -> bool:
        # 检查album_id是否在黑名单中
        config = cls._load_config()
        return str(album_id) in [str(aid) for aid in config.get("blacklist", [])]

    @classmethod
    def add_to_blacklist(cls, album_id: str):
        # 添加到黑名单
        config = cls._load_config()
        blacklist = config.get("blacklist", [])
        if str(album_id) not in [str(aid) for aid in blacklist]:
            blacklist.append(str(album_id))
            config["blacklist"] = blacklist
            cls._save_config()
            # 添加后清除缓存，确保下次访问获取最新数据
            cls._clear_cache()

    @classmethod
    def remove_from_blacklist(cls, album_id: str):
        # 从黑名单中移除
        config = cls._load_config()
        blacklist = config.get("blacklist", [])
        if str(album_id) in [str(aid) for aid in blacklist]:
            blacklist = [aid for aid in blacklist if str(aid) != str(album_id)]
            config["blacklist"] = blacklist
            cls._save_config()
            # 移除后清除缓存，确保下次访问获取最新数据
            cls._clear_cache()

    @classmethod
    def get_blacklist(cls) -> list:
        # 获取黑名单列表
        config = cls._load_config()
        return config.get("blacklist", [])


class CreateZip:
    def __init__(self, data: DetailInfo):
        self.data = data
        self.password = data.album_id
        self.pdf_path = PDF_OUTPUT_PATH / f"{data.album_id}.pdf"
        self.zip_path = ZIP_OUTPUT_PATH / f"{data.album_id}.zip"
        self.encrypted_pdf_path = PDF_OUTPUT_PATH / f"encrypted_{data.album_id}.pdf"

    def encrypt_pdf(self):
        # 加密PDF文件
        with Pdf.open(self.pdf_path) as pdf:
            # 设置加密选项
            pdf.save(
                self.encrypted_pdf_path,
                encryption=Encryption(user=self.password, owner=self.password, R=6),
            )
            logger.info(f"PDF 已加密并保存到: {self.encrypted_pdf_path}", "jmcomic")

    def create_password_protected_zip(self):
        # 创建带密码的ZIP文件
        pyminizip.compress(
            str(self.encrypted_pdf_path.absolute()),
            None,
            str(self.zip_path.absolute()),
            self.password,
            5,
        )
        logger.info(f"ZIP 文件已创建并加密: {self.zip_path}", "jmcomic")

    def create(self) -> Path:
        if self.pdf_path.exists():
            self.encrypt_pdf()
            self.create_password_protected_zip()
        return self.zip_path


class JmDownload:
    _data: ClassVar[dict[str, list[DetailInfo]]] = {}

    @classmethod
    async def upload_file(cls, data: DetailInfo, zip_path: Path | None = None):
        if not zip_path:
            zip_path = CreateZip(data).create()
        try:
            if not zip_path.exists():
                await PlatformUtils.send_message(
                    bot=data.bot,
                    user_id=data.user_id,
                    group_id=data.group_id,
                    message="ZIP文件生成失败或已不存在...",
                )
            elif data.group_id:
                await data.bot.call_api(
                    "upload_group_file",
                    group_id=data.group_id,
                    file=f"file:///{zip_path.absolute()}",
                    name=f"{data.album_id}.zip",
                )
            else:
                await data.bot.call_api(
                    "upload_private_file",
                    user_id=data.user_id,
                    file=f"file:///{zip_path.absolute()}",
                    name=f"{data.album_id}.zip",
                )
        except Exception as e:
            logger.error(
                "上传文件失败",
                "jmcomic",
                session=data.user_id,
                group_id=data.group_id,
                e=e,
            )
            await PlatformUtils.send_message(
                bot=data.bot,
                user_id=data.user_id,
                group_id=data.group_id,
                message="上传文件失败...",
            )

    @classmethod
    def call_send(cls, album: JmAlbumDetail, dler):
        data_list = cls._data.get(album.id)
        if not data_list:
            return
        try:
            loop = asyncio.get_running_loop()
        except Exception:
            loop = None
        for data in data_list:
            if loop:
                loop.create_task(cls.upload_file(data))
            else:
                asyncio.run(cls.upload_file(data))
        del cls._data[album.id]

    @classmethod
    async def download_album(
        cls, bot: Bot, user_id: str, group_id: str | None, album_id: str
    ):
        zip_path = ZIP_OUTPUT_PATH / f"{album_id}.zip"

        if zip_path.exists():
            await cls.upload_file(
                DetailInfo(
                    bot=bot, user_id=user_id, group_id=group_id, album_id=album_id
                ),
                zip_path=zip_path,
            )
        else:
            # 检查本子是否存在
            exists = await cls.check_album_exists(album_id)
            if not exists:
                await MessageUtils.build_message(
                    f"本子 {album_id} 飞到天堂去了喵~"
                ).send(reply_to=True)
                return

            if album_id not in cls._data:
                cls._data[album_id] = []
            cls._data[album_id].append(
                DetailInfo(
                    bot=bot, user_id=user_id, group_id=group_id, album_id=album_id
                )
            )
            await asyncio.to_thread(
                jmcomic.download_album, album_id, option, callback=cls.call_send
            )

    @classmethod
    async def check_album_exists(cls, album_id: str) -> bool:
        try:
            # 使用 jmcomic.JmClient 直接请求
            client = option.build_jm_client()
            # 尝试获取本子详情页面
            album_detail = client.get_album_detail(album_id)
            return album_detail is not None
        except Exception as e:
            # 捕获jmcomic库抛出的异常（通常是404或请求失败）
            logger.warning(f"检查本子 {album_id} 存在性失败: {str(e)}", "jmcomic")

            # 尝试使用 requests 直接请求网页
            try:
                url = f"https://18comic.vip/album/{album_id}/"
                r = await AsyncHttpx.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    },
                )
                if (
                    r.status_code == 200
                    and "404" not in r.text
                    and "不存在" not in r.text
                ):
                    return True
                else:
                    return False
            except Exception as req_e:
                logger.warning(
                    f"使用AsyncHttpx检查本子 {album_id} 存在性也失败: {str(req_e)}",
                    "jmcomic",
                )
                return False
