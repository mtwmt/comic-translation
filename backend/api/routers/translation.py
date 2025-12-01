"""
翻譯相關的路由
遵循 RESTful API 設計原則
"""
import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from ..core.config import Settings, get_settings
from ..schemas.translation import (
    ConfigResponse,
    TranslationConfig,
    TranslationResponse
)
from ..services.translation_service import translation_service


router = APIRouter(prefix="/api", tags=["translation"])
logger = logging.getLogger(__name__)


@router.post("/config", response_model=ConfigResponse, status_code=status.HTTP_200_OK)
async def set_config(
    config: TranslationConfig,
    settings: Annotated[Settings, Depends(get_settings)]
) -> ConfigResponse:
    """
    設定翻譯配置

    Args:
        config: 翻譯配置
        settings: 應用程式設定

    Returns:
        配置回應
    """
    try:
        translation_service.configure(config)
        return ConfigResponse(ok=True, message="配置已成功更新")

    except Exception as e:
        logger.error(f"設定配置失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"配置失敗: {str(e)}"
        )


@router.post("/translate", response_model=TranslationResponse, status_code=status.HTTP_200_OK)
async def translate_image(
    file: Annotated[UploadFile, File(description="要翻譯的圖片")],
    extra_prompt: str = "",
    settings: Annotated[Settings, Depends(get_settings)] = None
) -> TranslationResponse:
    """
    翻譯單張圖片

    Args:
        file: 上傳的圖片檔案
        extra_prompt: 額外的提示詞
        settings: 應用程式設定

    Returns:
        翻譯結果
    """
    # 檢查服務是否已配置
    if not translation_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="請先設定翻譯配置（呼叫 /api/translation/config）"
        )

    # 驗證檔案格式
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的檔案格式: {file_ext}。允許的格式: {settings.allowed_extensions}"
        )

    # 驗證檔案大小
    file_size = 0
    content = await file.read()
    file_size = len(content)

    if file_size > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"檔案過大（{file_size / 1024 / 1024:.2f}MB）。最大限制: {settings.max_file_size / 1024 / 1024}MB"
        )

    # 重置檔案指標
    await file.seek(0)

    try:
        # 建立暫存目錄
        upload_dir = Path(settings.upload_dir)
        output_dir = Path(settings.output_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 儲存上傳的檔案
        input_path = upload_dir / file.filename
        with open(input_path, "wb") as f:
            f.write(content)

        # 設定輸出路徑
        output_filename = f"{Path(file.filename).stem}_translated{file_ext}"
        output_path = output_dir / output_filename

        # 執行翻譯
        success = translation_service.translate_image(
            input_path=str(input_path),
            output_path=str(output_path),
            extra_prompt=extra_prompt
        )

        if success:
            return TranslationResponse(
                success=True,
                filename=file.filename,
                output_url=f"/api/outputs/{output_filename}"
            )
        else:
            return TranslationResponse(
                success=False,
                filename=file.filename,
                error="AI 處理失敗，未能生成翻譯圖片"
            )

    except Exception as e:
        logger.error(f"翻譯圖片時發生錯誤: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"翻譯失敗: {str(e)}"
        )
    finally:
        # 清理暫存檔案
        try:
            if input_path.exists():
                input_path.unlink()
        except Exception as e:
            logger.warning(f"清理暫存檔案失敗: {e}")


@router.get("/outputs/{filename}", response_class=FileResponse)
async def get_output(
    filename: str,
    settings: Annotated[Settings, Depends(get_settings)]
) -> FileResponse:
    """
    取得翻譯後的圖片

    Args:
        filename: 檔案名稱
        settings: 應用程式設定

    Returns:
        圖片檔案
    """
    output_path = Path(settings.output_dir) / filename

    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到檔案: {filename}"
        )

    return FileResponse(
        path=output_path,
        media_type=f"image/{output_path.suffix.lstrip('.')}",
        filename=filename
    )
