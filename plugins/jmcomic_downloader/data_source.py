# data_source.py
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
import yaml

import jmcomic
from jmcomic import JmAlbumDetail
from nonebot.adapters.onebot.v11 import Bot
from pikepdf import Encryption, Pdf
import pyminizip

from zhenxun.configs.path_config import DATA_PATH, TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import ResourceDirManager
from zhenxun.utils.message import MessageUtils

IMAGE_OUTPUT_PATH = TEMP_PATH / "jmcomic"
IMAGE_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

PDF_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_pdf"
ZIP_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_zip"
PDF_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
ZIP_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

OPTION_FILE = Path(__file__).parent / "option.yml"
CONFIG_FILE = Path(__file__).parent / "blacklist_config.yml"

ResourceDirManager.add_temp_dir(PDF_OUTPUT_PATH)

option = jmcomic.create_option_by_file(str(OPTION_FILE.absolute()))

@dataclass
class DetailInfo:
    bot: Bot
    user_id: str
    group_id: str | None
    album_id: str


class BlacklistManager:
    """黑名单管理器"""
    _config = None
    _config_path = CONFIG_FILE

    @classmethod
    def _load_config(cls):
        """加载配置文件"""
        if cls._config is None:
            if cls._config_path.exists():
                with open(cls._config_path, 'r', encoding='utf-8') as f:
                    cls._config = yaml.safe_load(f) or {"super_users": [], "blacklist": []}
            else:
                cls._config = {"super_users": [], "blacklist": []}
        return cls._config

    @classmethod
    def _save_config(cls):
        """保存配置文件"""
        with open(cls._config_path, 'w', encoding='utf-8') as f:
            yaml.dump(cls._config, f, default_flow_style=False, allow_unicode=True)

    @classmethod
    def _clear_cache(cls):
        """清除配置缓存"""
        cls._config = None

    @classmethod
    def is_super_user(cls, user_id: str) -> bool:
        """检查是否为超级用户"""
        config = cls._load_config()
        return str(user_id) in [str(uid) for uid in config.get("super_users", [])]

    @classmethod
    def is_blacklisted(cls, album_id: str) -> bool:
        """检查album_id是否在黑名单中"""
        config = cls._load_config()
        return str(album_id) in [str(aid) for aid in config.get("blacklist", [])]

    @classmethod
    def add_to_blacklist(cls, album_id: str):
        """添加到黑名单"""
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
        """从黑名单中移除"""
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
        """获取黑名单列表"""
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
        """加密 PDF 文件"""
        with Pdf.open(self.pdf_path) as pdf:
            # 设置加密选项
            pdf.save(
                self.encrypted_pdf_path,
                encryption=Encryption(user=self.password, owner=self.password, R=6),
            )
            logger.info(f"PDF 已加密并保存到: {self.encrypted_pdf_path}", "jmcomic")

    def create_password_protected_zip(self):
        """创建带密码的 ZIP 文件"""
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
            exists = await asyncio.to_thread(cls.check_album_exists, album_id)
            if not exists:
                await MessageUtils.build_message(f"本子 {album_id} 飞到天堂去了喵~").send(reply_to=True)
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
    def check_album_exists(cls, album_id: str) -> bool:
        """检查本子是否存在 - 使用 jmcomic.JmClient 直接请求替代 get_album_detail"""
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
                import requests
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                url = f"https://18comic.vip/album/{album_id}/"
                response = requests.get(url, headers=headers)
                # 检查是否返回404或错误页面
                if response.status_code == 200 and "404" not in response.text and "不存在" not in response.text:
                    return True
                else:
                    return False
            except Exception as req_e:
                logger.warning(f"使用requests检查本子 {album_id} 存在性也失败: {str(req_e)}", "jmcomic")
                return False




