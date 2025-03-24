import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import jmcomic
import pyminizip
from jmcomic import JmAlbumDetail
from nonebot.adapters.onebot.v11 import Bot
from pikepdf import Encryption, Pdf
from zhenxun.configs.path_config import DATA_PATH, TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import ResourceDirManager

IMAGE_OUTPUT_PATH = TEMP_PATH / "jmcomic"
IMAGE_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

PDF_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_pdf"
ZIP_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_zip"
PDF_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
ZIP_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

OPTION_FILE = Path(__file__).parent / "option.yml"


ResourceDirManager.add_temp_dir(PDF_OUTPUT_PATH)


option = jmcomic.create_option_by_file(str(OPTION_FILE.absolute()))


@dataclass
class DetailInfo:
    bot: Bot
    user_id: str
    group_id: str | None
    album_id: str


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
        self.encrypt_pdf()
        self.create_password_protected_zip()
        return self.zip_path


class JmDownload:
    _data: ClassVar[dict[str, list[DetailInfo]]] = {}

    @classmethod
    async def upload_file(cls, data: DetailInfo):
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
        if f"{album_id}.zip" in os.listdir(ZIP_OUTPUT_PATH):
            await cls.upload_file(
                DetailInfo(
                    bot=bot, user_id=user_id, group_id=group_id, album_id=album_id
                )
            )
        else:
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
