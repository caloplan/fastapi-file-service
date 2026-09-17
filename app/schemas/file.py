from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """文件上传成功响应。"""

    key: str = Field(..., description="文件唯一标识（UUID.hex + 扩展名，不含路径）")
    url: str = Field(..., description="文件访问 URL（GET /files/{key}）")


__all__ = ["FileUploadResponse"]
