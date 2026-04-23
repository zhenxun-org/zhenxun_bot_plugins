from pathlib import Path
import random

import aiofiles

from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.utils import cn2py

from .image_management_log import ImageHandleType, ImageManagementLog

BASE_PATH = IMAGE_PATH / "image_management"


class ImageManagementManage:
    @staticmethod
    def _get_sorted_image_ids(path: Path) -> list[int]:
        """获取目录下按升序排列的 jpg 数字文件名 id 列表。"""
        if not path.exists():
            return []
        image_ids = [
            int(file.stem)
            for file in path.iterdir()
            if file.is_file() and file.suffix.lower() == ".jpg" and file.stem.isdigit()
        ]
        image_ids.sort()
        return image_ids

    @classmethod
    async def random_image(cls, name: str, file_id: int | None = None) -> Path | None:
        """随机图片

        参数:
            name: 图库名称
            file_id: 图片id.

        返回:
            Path | None: 图片路径
        """
        path = BASE_PATH / cn2py(name)
        image_ids = cls._get_sorted_image_ids(path)
        if not image_ids:
            return None
        target_id = file_id if file_id is not None else random.choice(image_ids)
        if target_id not in image_ids:
            return None
        return path / f"{target_id}.jpg"

    @classmethod
    async def upload_image(
        cls,
        image_data: bytes | str,
        name: str,
        user_id: str,
        platform: str | None = None,
    ) -> str | None:
        """上传图片

        参数:
            image_data: 图片bytes
            name: 图库名称
            user_id: 用户id
            platform: 所属平台

        返回:
            str | None: 文件名称
        """
        path = BASE_PATH / cn2py(name)
        path.mkdir(exist_ok=True, parents=True)
        image_ids = cls._get_sorted_image_ids(path)
        _file_name = image_ids[-1] + 1 if image_ids else 0
        _file_path = path / f"{_file_name}.jpg"
        try:
            await ImageManagementLog.create(
                user_id=user_id,
                path=_file_path,
                handle_type=ImageHandleType.UPLOAD,
                platform=platform,
            )
            if isinstance(image_data, str):
                await AsyncHttpx.download_file(image_data, _file_path)
            else:
                async with aiofiles.open(_file_path, "wb") as f:
                    await f.write(image_data)
                    logger.info(
                        f"上传图片至 {name}, 路径: {_file_path}",
                        "上传图片",
                        session=user_id,
                    )
            return f"{_file_name}.jpg"
        except Exception as e:
            logger.error("上传图片错误", "上传图片", e=e)
        return None

    @classmethod
    async def delete_image(
        cls, name: str, file_id: int, user_id: str, platform: str | None = None
    ) -> bool:
        """删除图片

        参数:
            name: 图库名称
            file_id: 图片id
            user_id: 用户id
            platform: 所属平台.

        返回:
            bool: 是否删除成功
        """
        path = BASE_PATH / cn2py(name)
        if not path.exists():
            return False
        _file_path = path / f"{file_id}.jpg"
        if not _file_path.exists():
            return False
        try:
            await ImageManagementLog.create(
                user_id=user_id,
                path=_file_path,
                handle_type=ImageHandleType.DELETE,
                platform=platform,
            )
            _file_path.unlink()
            logger.info(
                f"图库: {name}, 删除图片路径: {_file_path}", "删除图片", session=user_id
            )
            image_ids = cls._get_sorted_image_ids(path)
            if image_ids:
                _file_name = image_ids[-1]
                if _file_name == file_id:
                    return True
                _move_file = path / f"{_file_name}.jpg"
                _move_file.rename(_file_path)
                logger.info(
                    f"图库: {name}, 移动图片名称: {_file_name}.jpg -> {file_id}.jpg",
                    "删除图片",
                    session=user_id,
                )
        except Exception as e:
            logger.error("删除图片错误", "删除图片", e=e)
            return False
        return True

    @classmethod
    async def move_image(
        cls,
        a_name: str,
        b_name: str,
        file_id: int,
        user_id: str,
        platform: str | None = None,
    ) -> str | None:
        """移动图片

        参数:
            a_name: 源图库
            b_name: 模板图库
            file_id: 图片id
            user_id: 用户id
            platform: 所属平台.

        返回:
            bool: 是否移动成功
        """
        source_path = BASE_PATH / cn2py(a_name)
        if not source_path.exists():
            return None
        destination_path = BASE_PATH / cn2py(b_name)
        destination_path.mkdir(exist_ok=True, parents=True)
        source_file = source_path / f"{file_id}.jpg"
        if not source_file.exists():
            return None
        destination_ids = cls._get_sorted_image_ids(destination_path)
        _destination_name = destination_ids[-1] + 1 if destination_ids else 0
        destination_file = destination_path / f"{_destination_name}.jpg"
        try:
            await ImageManagementLog.create(
                user_id=user_id,
                path=source_file,
                move=destination_file,
                handle_type=ImageHandleType.MOVE,
                platform=platform,
            )
            source_file.rename(destination_file)
            logger.info(
                f"图库: {a_name} -> {b_name}, 移动图片路径: {source_file} -> {destination_file}",
                "移动图片",
                session=user_id,
            )
            source_ids = cls._get_sorted_image_ids(source_path)
            if source_ids:
                _file_name = source_ids[-1]
                if _file_name == file_id:
                    return f"{source_file} -> {destination_file}"
                _move_file = source_path / f"{_file_name}.jpg"
                _move_file.rename(source_file)
                logger.info(
                    f"图库: {a_name}, 移动图片名称: {_file_name}.jpg -> {file_id}.jpg",
                    "移动图片",
                    session=user_id,
                )
        except Exception as e:
            logger.error("移动图片错误", "移动图片", e=e)
            return None
        return f"{source_file} -> {destination_file}"
