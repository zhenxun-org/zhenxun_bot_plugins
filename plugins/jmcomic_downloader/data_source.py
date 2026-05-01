import asyncio
from dataclasses import dataclass
from pathlib import Path
import time
from typing import ClassVar

import jmcomic
from jmcomic import JmAlbumDetail
from nonebot.adapters.onebot.v11 import Bot
from pikepdf import Encryption, Pdf
import pyminizip
import yaml

from zhenxun.configs.path_config import DATA_PATH, TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

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

# 检查并创建option.yml配置文件
if not OPTION_FILE.exists():
    original_option_content = """# 开启jmcomic的日志输出，默认为true
# PDF 加密开关，默认为 false
# 设置为 true 会对生成的 PDF 进行密码加密（密码为本子 id）后再打包
# 设置为 false 则直接打包未加密的 PDF
encrypt_pdf: false

# jmcomic 模块官方配置

log: true

# 下载配置
download:
  cache: true
  image:
    decode: true
    suffix: .jpg
  threading:
    image: 30
    photo: 16

# 文件夹规则配置
dir_rule:
  base_dir: ./resources/temp/jmcomic
  rule: Bd_Ptitle

# 插件的配置示例
plugins:
  after_photo:
    - plugin: img2pdf
      kwargs:
        pdf_dir: ./data/jmcomic/jmcomic_pdf
        filename_rule: Pid

  after_album:
    - plugin: img2pdf
      kwargs:
        pdf_dir: ./data/jmcomic/jmcomic_pdf
        filename_rule: Aname
"""
    with open(OPTION_FILE, "w", encoding="utf-8") as f:
        f.write(original_option_content)
else:
    # 已存在 option.yml 时，检查并追加 encrypt_pdf 开关
    try:
        with open(OPTION_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        if "encrypt_pdf:" not in content:
            updated_content = "# PDF 加密开关\nencrypt_pdf: false\n\n" + content
            with open(OPTION_FILE, "w", encoding="utf-8") as f:
                f.write(updated_content)
            logger.info("已在现有的 option.yml 中追加 encrypt_pdf 开关配置", "jmcomic")
    except Exception as e:
        logger.error(f"更新 option.yml 配置失败: {e}", "jmcomic")


# 读取 option.yml 获取自定义参数
try:
    with open(OPTION_FILE, "r", encoding="utf-8") as f:
        custom_config = yaml.safe_load(f) or {}
    ENCRYPT_PDF_ENABLED = custom_config.get("encrypt_pdf", True)
except Exception as e:
    logger.warning(f"读取 encrypt_pdf 配置失败，默认关闭加密: {e}", "jmcomic")
    ENCRYPT_PDF_ENABLED = False

# 剔除自定义参数传递给 jmcomic，防止解析报错
try:
    with open(OPTION_FILE, "r", encoding="utf-8") as f:
        clean_config = yaml.safe_load(f) or {}

    clean_config.pop("encrypt_pdf", None)

    from jmcomic.jm_option import JmOption

    option = JmOption.construct(clean_config)

except Exception as e:
    logger.warning(
        f"使用 JmOption.construct 加载配置失败，尝试回退官方读取: {e}", "jmcomic"
    )
    option = jmcomic.create_option_by_file(str(OPTION_FILE.absolute()))


@dataclass
class DetailInfo:
    bot: Bot
    user_id: str
    group_id: str | None
    album_id: str


class BlacklistManager:
    _config = None
    _config_path = CONFIG_FILE
    _synced_at = None

    @classmethod
    def _load_config(cls):
        if cls._config is None:
            if not cls._config_path.exists():
                cls._sync_nonebot_superusers()
            with open(cls._config_path, encoding="utf-8") as f:
                cls._config = yaml.safe_load(f) or {
                    "super_users": [],
                    "blacklist": [],
                }
        return cls._config

    @classmethod
    def _sync_nonebot_superusers(cls):
        try:
            from nonebot import get_driver

            driver = get_driver()
            if nonebot_superusers := getattr(driver.config, "superusers", set()):
                if cls._config_path.exists():
                    with open(cls._config_path, encoding="utf-8") as f:
                        existing_config = yaml.safe_load(f) or {
                            "super_users": [],
                            "blacklist": [],
                        }
                else:
                    existing_config = {"super_users": [], "blacklist": []}

                nonebot_superusers_list = [str(uid) for uid in nonebot_superusers]
                existing_superusers = existing_config.get("super_users", [])
                all_superusers = list(
                    set(existing_superusers + nonebot_superusers_list)
                )

                existing_config["super_users"] = all_superusers

                with open(cls._config_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        existing_config, f, default_flow_style=False, allow_unicode=True
                    )
        except Exception as e:
            logger.error(f"同步NoneBot超级用户失败: {e}", "jmcomic")

    @classmethod
    def _save_config(cls):
        with open(cls._config_path, "w", encoding="utf-8") as f:
            yaml.dump(cls._config, f, default_flow_style=False, allow_unicode=True)

    @classmethod
    def _clear_cache(cls):
        cls._config = None

    @classmethod
    def is_super_user(cls, user_id: str) -> bool:
        if not cls._synced_at or time.time() - cls._synced_at > 300:
            cls._sync_nonebot_superusers()
            cls._synced_at = time.time()

        config = cls._load_config()
        try:
            from nonebot import get_driver

            driver = get_driver()
            nonebot_superusers = getattr(driver.config, "superusers", set())
            if user_id in [str(uid) for uid in nonebot_superusers]:
                return True
        except Exception as e:
            logger.error(f"检查NoneBot超级用户失败: {e}", "jmcomic")
        return user_id in [str(uid) for uid in config.get("super_users", [])]

    @classmethod
    def is_blacklisted(cls, album_id: str) -> bool:
        config = cls._load_config()
        return album_id in [str(aid) for aid in config.get("blacklist", [])]

    @classmethod
    def add_to_blacklist(cls, album_id: str):
        config = cls._load_config()
        blacklist = config.get("blacklist", [])
        if album_id not in [str(aid) for aid in blacklist]:
            blacklist.append(album_id)
            config["blacklist"] = blacklist
            cls._save_config()
            cls._clear_cache()

    @classmethod
    def remove_from_blacklist(cls, album_id: str):
        config = cls._load_config()
        blacklist = config.get("blacklist", [])
        if album_id in [str(aid) for aid in blacklist]:
            blacklist = [aid for aid in blacklist if str(aid) != album_id]
            config["blacklist"] = blacklist
            cls._save_config()
            cls._clear_cache()

    @classmethod
    def get_blacklist(cls) -> list:
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
        with Pdf.open(self.pdf_path) as pdf:
            pdf.save(
                self.encrypted_pdf_path,
                encryption=Encryption(user=self.password, owner=self.password, R=6),
            )
            logger.info(f"PDF 已加密并保存到: {self.encrypted_pdf_path}", "jmcomic")

    def create_password_protected_zip(self, file_to_compress: Path):
        pyminizip.compress(
            str(file_to_compress.absolute()),
            None,
            str(self.zip_path.absolute()),
            self.password,
            5,
        )
        logger.info(f"ZIP 文件已创建并加密: {self.zip_path}", "jmcomic")

    def create(self) -> Path:
        if self.pdf_path.exists():
            if ENCRYPT_PDF_ENABLED:
                self.encrypt_pdf()
                self.create_password_protected_zip(self.encrypted_pdf_path)
                if self.encrypted_pdf_path.exists():
                    self.encrypted_pdf_path.unlink()
            else:
                logger.info("PDF 加密已关闭，直接压缩原始 PDF 文件", "jmcomic")
                self.create_password_protected_zip(self.pdf_path)

        return self.zip_path


class JmDownload:
    _data: ClassVar[dict[str, list[DetailInfo]]] = {}

    @classmethod
    async def upload_file(cls, data: DetailInfo, zip_path: Path | None = None):
        if not zip_path:
            # 压缩加密属于 CPU 密集型操作，放入线程池避免主线程卡顿
            zip_path = await asyncio.to_thread(CreateZip(data).create)
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
    async def send_album_metadata(
        cls, bot: Bot, user_id: str, group_id: str | None, album: JmAlbumDetail
    ):
        """
        统一的元数据提取和发送函数
        """
        try:
            keywords_str = (
                ", ".join([f"'{k}'" for k in album.tags]) if album.tags else ""
            )
            msg = (
                f"本子获取成功: {album.id}\n"
                f"作者: {album.author} 章节数: {len(album.episode_list)}\n"
                f"标题: {album.title}\n关键词: {keywords_str}"
            )
            await PlatformUtils.send_message(
                bot=bot, user_id=user_id, group_id=group_id, message=msg
            )
        except Exception as e:
            logger.warning(f"发送本子 {album.id} 的元数据失败: {e}", "jmcomic")

    @classmethod
    def call_send(cls, album: JmAlbumDetail, dler):
        data_list = cls._data.get(album.id)
        if not data_list:
            return
        try:
            loop = asyncio.get_running_loop()
        except Exception:
            loop = None

        # 异步发送任务：先传文件，后发文字
        async def upload_and_send_msg(data):
            try:
                # 直接调用发送函数
                await cls.upload_file(data)
                await cls.send_album_metadata(
                    data.bot, data.user_id, data.group_id, album
                )
            except Exception as e:
                logger.error(f"发送文件或文字消息失败: {e}", "jmcomic")

        # 使用 gather 等待任务跑完
        async def run_all_tasks():
            tasks = [upload_and_send_msg(data) for data in data_list]
            await asyncio.gather(*tasks)
            # 最后删除上下文
            if album.id in cls._data:
                del cls._data[album.id]

        # 提交给已有的事件循环
        if loop:
            loop.create_task(run_all_tasks())
        else:
            asyncio.run(run_all_tasks())

    @classmethod
    async def download_album(
        cls, bot: Bot, user_id: str, group_id: str | None, album_id: str
    ):
        zip_path = ZIP_OUTPUT_PATH / f"{album_id}.zip"

        if zip_path.exists():
            try:
                # 获取本子元数据
                client = option.build_jm_client()
                album = await asyncio.to_thread(client.get_album_detail, album_id)

                if album:
                    keywords_str = (
                        ", ".join([f"'{k}'" for k in album.tags]) if album.tags else ""
                    )
                    msg = (
                        f"本子获取成功: {album.id}\n"
                        f"作者: {album.author} 章节数: {len(album.episode_list)}\n"
                        f"标题: {album.title}\n关键词: {keywords_str}"
                    )
                    # 发送元数据消息
                    await PlatformUtils.send_message(
                        bot=bot, user_id=user_id, group_id=group_id, message=msg
                    )
                    # 防止文件发送冲突
                    await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"获取缓存本子 {album_id} 的元数据失败: {e}", "jmcomic")

            # 发送已有的 ZIP 文件
            await cls.upload_file(
                DetailInfo(
                    bot=bot, user_id=user_id, group_id=group_id, album_id=album_id
                ),
                zip_path=zip_path,
            )
        else:
            # ZIP 不存在时去下载
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
            album_detail = await asyncio.to_thread(client.get_album_detail, album_id)
            return album_detail is not None
        except Exception as e:
            # 捕获jmcomic库抛出的异常（通常是404或请求失败）
            logger.warning(f"检查本子 {album_id} 存在性失败: {e!s}", "jmcomic")

            # 尝试使用 requests 直接请求网页
            try:
                url = f"https://18comic.vip/album/{album_id}/"
                r = await AsyncHttpx.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    },
                )
                return (
                    r.status_code == 200
                    and "404" not in r.text
                    and "不存在" not in r.text
                )
            except Exception as req_e:
                logger.warning(
                    f"使用AsyncHttpx检查本子 {album_id} 存在性也失败: {req_e!s}",
                    "jmcomic",
                )
                return False
