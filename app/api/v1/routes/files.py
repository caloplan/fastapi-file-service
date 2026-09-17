"""文件路由：上传（需登录，按目录路由）与下载（公开）。

- POST /api/v1/files            ：上传到默认目录（STORAGE_CATEGORIES 第一个，默认 image）；
- POST /api/v1/files/{dir}      ：上传到指定目录（dir 必须在 STORAGE_CATEGORIES 白名单中）；
- GET  /api/v1/files/{dir}/{key}：按目录 + key 返回文件，无需鉴权（随机 UUID URL 即访问凭证）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from app.core.dependencies import CurrentUser, get_current_user
from app.schemas.file import FileUploadResponse
from app.services.file_service import FileService
from app.storage import get_storage

router = APIRouter(prefix="/files", tags=["文件"])


async def _upload(request: Request, file: UploadFile, category: str) -> FileUploadResponse:
    """上传业务公共逻辑：保存文件并构造 {key, url}。"""
    file_service = FileService(get_storage())
    key = await file_service.save_upload(file, category)

    category_part, file_part = key.split("/", 1)
    url = str(request.url_for("get_file", category=category_part, key=file_part))
    return FileUploadResponse(key=key, url=url)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=FileUploadResponse,
    summary="上传图片到默认目录（需登录）",
)
async def upload_file_default(
    request: Request,
    file: Annotated[UploadFile, File(description="图片文件（jpg/jpeg/png/webp，单文件 ≤5MB）")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FileUploadResponse:
    """上传图片到默认目录（STORAGE_CATEGORIES 第一个，默认 image），返回 {key, url}。"""
    return await _upload(request, file, FileService.default_category())


@router.post(
    "/{category}",
    status_code=status.HTTP_201_CREATED,
    response_model=FileUploadResponse,
    summary="上传图片到指定目录（需登录）",
)
async def upload_file_to_category(
    request: Request,
    category: str,
    file: Annotated[UploadFile, File(description="图片文件（jpg/jpeg/png/webp，单文件 ≤5MB）")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FileUploadResponse:
    """上传图片到指定目录（category 必须在 STORAGE_CATEGORIES 白名单中），返回 {key, url}。"""
    if not FileService.validate_category(category):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"不允许的存储目录: {category}，仅支持 {FileService.default_category()} 等白名单目录",
        )
    return await _upload(request, file, category)


@router.get(
    "/{category}/{key}",
    summary="获取文件（无需登录）",
    responses={200: {"content": {"image/*": {}}}},
)
async def get_file(category: str, key: str) -> Response:
    """按目录 + key 返回文件内容；目录不在白名单或 key 非法 / 不存在返回 404。"""
    file_service = FileService(get_storage())

    # 目录白名单 + 文件名正则双重校验，杜绝路径注入（如 ../../etc/passwd）
    if not file_service.validate_category(category) or not file_service.validate_key(key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    handle = file_service.storage.open(f"{category}/{key}")
    if handle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    try:
        content = handle.read()
    finally:
        handle.close()

    return Response(
        content=content,
        media_type=file_service.media_type_for_key(key),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
