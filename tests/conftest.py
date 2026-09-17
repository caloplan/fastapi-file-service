"""Pytest 共享 fixtures：测试用 RSA 密钥对、JWT 签发、JWKS mock、存储隔离与客户端。"""

import base64
import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jose import jwt

# ── 测试配置（在导入 app 前设置环境变量）──────────────
os.environ["USER_SERVICE_URL"] = "http://localhost:8000"
os.environ["ALGORITHM"] = "RS256"
# 存储使用临时目录（每个测试由 storage_dir fixture 覆盖），避免污染真实 storage/
os.environ["STORAGE_DIR"] = "storage/test"
# 测试目录白名单：含默认 image + 自定义 avatar
os.environ["STORAGE_CATEGORIES"] = '["image", "avatar"]'

from app.main import app  # noqa: E402
import app.storage as storage_mod  # noqa: E402
from app.storage.local import LocalStorageProvider  # noqa: E402

# ── 测试用 RSA 密钥对（模块级生成一次）────────────────────
_TEST_KID = "test-kid-001"
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_public_numbers = _public_key.public_numbers()


def _int_to_base64url(n: int) -> str:
    """将整数转为 base64url 编码（JWK 格式）。"""
    return base64.urlsafe_b64encode(
        n.to_bytes((n.bit_length() + 7) // 8, "big")
    ).rstrip(b"=").decode()


_TEST_JWK = {
    "kty": "RSA",
    "kid": _TEST_KID,
    "use": "sig",
    "alg": "RS256",
    "n": _int_to_base64url(_public_numbers.n),
    "e": _int_to_base64url(_public_numbers.e),
}

_TEST_PRIVATE_PEM = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)


def create_test_token(
    *,
    user_id: int = 1,
    username: str = "testuser",
    service_name: str = "caloplan",
    role: str = "user",
    token_type: str = "access",
    expires_minutes: int = 30,
) -> str:
    """签发测试用 JWT（使用测试私钥，RS256，携带 kid）。"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": username,
        "user_id": user_id,
        "service_name": service_name,
        "role": role,
        "type": token_type,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        _TEST_PRIVATE_PEM,
        algorithm="RS256",
        headers={"kid": _TEST_KID},
    )


@pytest.fixture(autouse=True)
def mock_jwks(monkeypatch):
    """mock JWKS 拉取，返回测试公钥（避免真实请求 user-service）。"""

    async def _fake_fetch_jwks():
        return {_TEST_KID: _TEST_JWK}

    monkeypatch.setattr("app.core.security._fetch_jwks", _fake_fetch_jwks)
    # 清空 JWKS 缓存
    import app.core.security as sec

    sec._jwks_cache = {}
    sec._jwks_cache_expires_at = 0.0


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    """每个测试使用独立临时存储目录，并重置全局存储实例。"""
    storage_mod.reset_storage()
    monkeypatch.setattr(storage_mod, "_storage", LocalStorageProvider(tmp_path / "storage"))
    yield tmp_path / "storage"
    storage_mod.reset_storage()


@pytest_asyncio.fixture
async def client():
    """提供异步测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
