"""
FastAPI 主應用程式
遵循最佳實踐：依賴注入、中介軟體、路由模組化
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core.config import get_settings
from .routers import translation_router


# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    應用程式生命週期管理
    啟動時執行初始化，關閉時執行清理
    """
    # 啟動時
    settings = get_settings()
    logger.info(f"啟動 {settings.app_name} v{settings.app_version}")

    # 建立必要的目錄
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

    yield

    # 關閉時
    logger.info("應用程式關閉")


def create_app() -> FastAPI:
    """
    建立 FastAPI 應用程式實例
    工廠模式，方便測試和多環境部署
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="漫畫翻譯 API - 使用 Gemini AI 進行圖片翻譯",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # 設定 CORS 中介軟體
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 設定 GZip 壓縮中介軟體
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # 註冊路由
    app.include_router(translation_router)

    @app.get("/api/health")
    async def health_check():
        """健康檢查端點"""
        return {
            "status": "healthy",
            "app_name": settings.app_name,
            "version": settings.app_version
        }

    return app


# 建立應用程式實例
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )
