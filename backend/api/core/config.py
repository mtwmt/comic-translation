"""
應用程式配置管理
使用 Pydantic Settings 進行環境變數驗證和管理
"""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """應用程式設定"""

    # API 設定
    app_name: str = "Comic Translation API"
    app_version: str = "1.0.0"
    debug: bool = False

    # CORS 設定
    allowed_origins: list[str] = ["http://localhost:4200"]

    # 檔案上傳設定
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    upload_dir: str = "uploads"
    output_dir: str = "outputs"
    allowed_extensions: set[str] = {".png", ".jpg", ".jpeg", ".webp"}

    # Gemini API 設定
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3-pro-image-preview"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


@lru_cache
def get_settings() -> Settings:
    """取得應用程式設定（單例模式）"""
    return Settings()
