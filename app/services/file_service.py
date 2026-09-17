"""文件上传业务封装：目录白名单/类型/大小校验 → UUID 命名 → StorageProvider 持久化。

路由层不直接接触文件系统；所有存储操作经 StorageProvider 抽象接口完成。
key 格式为「目录/文件名」：目录来自 STORAGE_CATEGORIES 白名单，文件名为 UUID.hex + 扩展名。
"""

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.storage.base import StorageProvider

# 文件名部分：UUID.hex（32 位小写十六进制）+ 白名单扩展名
KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp)$")

# 扩展名 → MIME 类型（下载响应使用）
EXTENSION_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class FileService:
    """文件上传 / 读取业务。"""

    def __init__(self, storage: StorageProvider) -> None:
        self.storage = storage

    @staticmethod
    def default_category() -> str:
        """默认存储目录：STORAGE_CATEGORIES 列表第一个（默认 image）。"""
        return settings.STORAGE_CATEGORIES[0]

    @staticmethod
    def validate_category(category: str) -> bool:
        """校验目录分类是否在配置白名单 STORAGE_CATEGORIES 中。"""
        return category in settings.STORAGE_CATEGORIES

    @staticmethod
    def validate_key(key: str) -> bool:
        """校验文件名为「UUID.hex + 白名单扩展名」格式。"""
        return KEY_PATTERN.fullmatch(key) is not None

    async def save_upload(self, upload: UploadFile, category: str) -> str:
        """校验并保存上传文件到指定目录，返回 key（{category}/{uuid}.{ext}）。

        - 目录不在 STORAGE_CATEGORIES 白名单 → 422；
        - 文件类型（扩展名 + MIME）不在白名单 → 415；
        - 文件超过 MAX_FILE_SIZE → 413；
        - 校验通过则以 UUID.hex + 扩展名 命名保存，避免文件名冲突与路径注入。
        """
        if not self.validate_category(category):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"不允许的存储目录: {category}，仅支持 {settings.STORAGE_CATEGORIES}",
            )

        ext = Path(upload.filename or "").suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"不支持的文件类型: {ext or '未知'}，仅支持 jpg/jpeg/png/webp",
            )

        content_type = (upload.content_type or "").lower()
        if content_type not in settings.ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"不支持的 MIME 类型: {content_type or '未知'}，仅支持 image/jpeg、image/png、image/webp",
            )

        # 最多多读 1 字节用于判断超限，避免超大文件整体读入内存
        content = await upload.read(settings.MAX_FILE_SIZE + 1)
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"文件大小超过限制（{settings.MAX_FILE_SIZE // (1024 * 1024)}MB）",
            )

        key = f"{category}/{uuid.uuid4().hex}{ext}"
        self.storage.save(key, content)
        return key

    def media_type_for_key(self, key: str) -> str:
        """根据 key 扩展名返回下载响应的 MIME 类型。"""
        return EXTENSION_MEDIA_TYPES.get(Path(key).suffix.lower(), "application/octet-stream")
