"""文件服务 API 集成测试：上传（鉴权/目录路由/类型/大小校验）与下载。"""

import pytest

from tests.conftest import create_test_token

# 1x1 像素的合法 PNG 字节（真实可解码）
_VALID_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\xff\xff\xff"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00\x10\x00\x00\x00\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"


def _headers(user_id: int = 1, username: str = "testuser"):
    return {"Authorization": f"Bearer {create_test_token(user_id=user_id, username=username)}"}


def _upload(client, *, category: str | None = None, files=None):
    """上传 helper：默认 POST /files（默认目录），category 非空时 POST /files/{category}。"""
    url = "/api/v1/files" if category is None else f"/api/v1/files/{category}"
    return client.post(url, headers=_headers(), files=files)


# ── 鉴权 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_without_token_unauthorized(client):
    """测试无 token 上传返回 401。"""
    response = await client.post(
        "/api/v1/files",
        files={"file": ("avatar.png", _VALID_PNG, "image/png")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_invalid_token_unauthorized(client):
    """测试伪造 token 上传返回 401。"""
    response = await client.post(
        "/api/v1/files",
        headers={"Authorization": "Bearer invalid.token.here"},
        files={"file": ("avatar.png", _VALID_PNG, "image/png")},
    )
    assert response.status_code == 401


# ── 上传成功 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_default_category_success(client, storage_dir):
    """测试上传到默认目录成功：key 带 image/ 前缀，文件落盘，可下载还原。"""
    response = await _upload(client, files={"file": ("avatar.png", _VALID_PNG, "image/png")})
    assert response.status_code == 201
    data = response.json()
    key = data["key"]
    assert key.startswith("image/")
    file_part = key.split("/", 1)[1]
    assert file_part.endswith(".png")
    assert len(file_part) == 32 + 4  # uuid4().hex + .png

    url = data["url"]
    assert url.endswith(f"/api/v1/files/{key}")

    # 文件确实落盘在 storage/image/ 下
    assert (storage_dir / "image" / file_part).is_file()
    assert (storage_dir / "image" / file_part).read_bytes() == _VALID_PNG

    # 下载验证：无需 token，内容一致
    download = await client.get(f"/api/v1/files/{key}")
    assert download.status_code == 200
    assert download.headers["content-type"] == "image/png"
    assert download.content == _VALID_PNG


@pytest.mark.asyncio
async def test_upload_custom_category_success(client, storage_dir):
    """测试上传到白名单中的自定义目录（avatar）成功。"""
    response = await _upload(client, category="avatar", files={"file": ("avatar.png", _VALID_PNG, "image/png")})
    assert response.status_code == 201
    key = response.json()["key"]
    assert key.startswith("avatar/")
    file_part = key.split("/", 1)[1]

    # 落盘在独立子目录
    assert (storage_dir / "avatar" / file_part).is_file()
    assert (storage_dir / "image" / file_part).exists() is False

    # 按目录下载
    download = await client.get(f"/api/v1/files/{key}")
    assert download.status_code == 200
    assert download.content == _VALID_PNG


@pytest.mark.asyncio
async def test_upload_jpeg_success(client):
    """测试合法 JPEG 上传成功。"""
    response = await _upload(client, files={"file": ("photo.jpg", JPEG_BYTES, "image/jpeg")})
    assert response.status_code == 201
    assert response.json()["key"].endswith(".jpg")


@pytest.mark.asyncio
async def test_upload_webp_success(client):
    """测试合法 WebP 上传成功。"""
    response = await _upload(client, files={"file": ("image.webp", WEBP_BYTES, "image/webp")})
    assert response.status_code == 201
    assert response.json()["key"].endswith(".webp")


@pytest.mark.asyncio
async def test_upload_uppercase_extension_success(client):
    """测试大写扩展名（.PNG）上传成功（扩展名归一化为小写）。"""
    response = await _upload(client, files={"file": ("avatar.PNG", _VALID_PNG, "image/png")})
    assert response.status_code == 201
    assert response.json()["key"].endswith(".png")


# ── 目录路由校验 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_unknown_category_422(client):
    """测试上传到白名单外的目录（video）返回 422。"""
    response = await _upload(client, category="video", files={"file": ("avatar.png", _VALID_PNG, "image/png")})
    assert response.status_code == 422
    assert "不允许的存储目录" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_unknown_category_404(client):
    """测试下载白名单外的目录返回 404。"""
    response = await client.get("/api/v1/files/video/00000000000000000000000000000000.png")
    assert response.status_code == 404


# ── 校验失败 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_unsupported_extension_415(client):
    """测试不支持的文件扩展名返回 415。"""
    response = await _upload(client, files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 415
    assert "不支持的文件类型" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_unsupported_mime_415(client):
    """测试扩展名合法但 MIME 类型不匹配返回 415。"""
    response = await _upload(client, files={"file": ("avatar.png", _VALID_PNG, "text/plain")})
    assert response.status_code == 415
    assert "不支持的 MIME 类型" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_oversize_413(client):
    """测试超过大小限制返回 413（6MB 内容）。"""
    big_bytes = b"a" * (6 * 1024 * 1024)
    response = await _upload(client, files={"file": ("big.png", big_bytes, "image/png")})
    assert response.status_code == 413
    assert "超过限制" in response.json()["detail"]


# ── 下载 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_file_not_found(client):
    """测试下载不存在的 key 返回 404。"""
    response = await client.get("/api/v1/files/image/00000000000000000000000000000000.png")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_file_invalid_key_404(client):
    """测试非法 key（路径注入 / 非白名单格式）返回 404 而非文件系统错误。"""
    for bad_key in (
        "image/../../etc/passwd",
        "image/..%2F..%2Fetc%2Fpasswd",
        "image/abc.png",           # 非 UUID.hex
        "image/0000.xyz",          # 非法扩展名
        "image/00000000000000000000000000000000",  # 缺扩展名
        "../image/00000000000000000000000000000000.png",  # 目录越界
    ):
        response = await client.get(f"/api/v1/files/{bad_key}")
        assert response.status_code == 404, f"key={bad_key!r} 应返回 404"


@pytest.mark.asyncio
async def test_get_file_no_auth_ok(client):
    """测试下载无需 JWT（随机 UUID URL 即访问凭证）。"""
    upload = await _upload(client, files={"file": ("avatar.png", _VALID_PNG, "image/png")})
    key = upload.json()["key"]

    response = await client.get(f"/api/v1/files/{key}")
    assert response.status_code == 200
    assert response.content == _VALID_PNG
    assert "cache-control" in response.headers
