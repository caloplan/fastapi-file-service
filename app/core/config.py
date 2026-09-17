from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，从环境变量 / .env 加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "File Service"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # 服务
    HOST: str = "0.0.0.0"
    PORT: int = 9094

    # user-service 对接（JWT 消费方）
    # user-service 的基础 URL，用于拉取 JWKS 公钥（Docker 网络内用服务名，本地用 localhost）
    USER_SERVICE_URL: str = "http://localhost:8000"
    # JWKS 缓存 TTL（秒），到期后强制从 user-service 刷新；kid 未命中时也会立即刷新
    JWKS_CACHE_TTL_SECONDS: int = 3600
    # JWT 签名算法（与 user-service 一致）
    ALGORITHM: str = "RS256"

    # 文件存储
    STORAGE_DIR: str = "storage"                 # 本地存储根目录（LocalStorageProvider）
    STORAGE_CATEGORIES: List[str] = ["image"]    # 允许的存储目录分类（白名单，上传/下载按此路由）
    MAX_FILE_SIZE: int = 5 * 1024 * 1024         # 单文件大小上限（字节，默认 5MB）
    ALLOWED_CONTENT_TYPES: List[str] = [         # 允许的 MIME 类型
        "image/jpeg",
        "image/png",
        "image/webp",
    ]
    ALLOWED_EXTENSIONS: List[str] = [            # 允许的文件扩展名（小写）
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    ]

    # 日志
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/file_service.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:9094"]

    @field_validator(
        "ALLOWED_ORIGINS",
        "ALLOWED_CONTENT_TYPES",
        "ALLOWED_EXTENSIONS",
        "STORAGE_CATEGORIES",
        mode="before",
    )
    @classmethod
    def _parse_list(cls, v):
        """支持从 .env 读取 JSON 数组字符串。"""
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [item.strip() for item in v.split(",") if item.strip()]
        return v


settings = Settings()
