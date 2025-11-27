"""
翻譯服務層
封裝 AI 引擎的業務邏輯
"""
import logging
import os
from pathlib import Path
from typing import Optional

import sys
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from src.ai_engine import AIEngine
from ..schemas.translation import TranslationConfig


logger = logging.getLogger(__name__)


class TranslationService:
    """翻譯服務類別（單例模式）"""

    _instance: Optional['TranslationService'] = None
    _ai_engine: Optional[AIEngine] = None
    _config: Optional[TranslationConfig] = None

    def __new__(cls):
        """確保單例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def configure(self, config: TranslationConfig) -> None:
        """
        配置 AI 引擎

        Args:
            config: 翻譯配置
        """
        try:
            # 設定環境變數
            os.environ["GEMINI_API_KEY"] = config.api_key

            # 重新初始化 AI 引擎
            self._ai_engine = AIEngine()

            # 更新全域設定
            if config.name_mapping:
                self._ai_engine.global_name_mapping = config.name_mapping

            if config.global_prompt:
                self._ai_engine.global_prompt = config.global_prompt

            self._config = config
            logger.info("翻譯服務配置成功")

        except Exception as e:
            logger.error(f"配置翻譯服務失敗: {e}")
            raise

    def is_configured(self) -> bool:
        """檢查服務是否已配置"""
        return self._ai_engine is not None and self._config is not None

    def translate_image(
        self,
        input_path: str,
        output_path: str,
        extra_prompt: str = ""
    ) -> bool:
        """
        翻譯單張圖片

        Args:
            input_path: 輸入圖片路徑
            output_path: 輸出圖片路徑
            extra_prompt: 額外的提示詞

        Returns:
            是否成功

        Raises:
            RuntimeError: 如果服務未配置
        """
        if not self.is_configured():
            raise RuntimeError("翻譯服務尚未配置，請先呼叫 configure()")

        try:
            # 確保輸出目錄存在
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # 呼叫 AI 引擎處理圖片
            success = self._ai_engine.process_image(
                image_path=input_path,
                output_path=output_path,
                extra_prompt=extra_prompt
            )

            return success

        except Exception as e:
            logger.error(f"翻譯圖片失敗 ({input_path}): {e}")
            raise

    def get_config(self) -> Optional[TranslationConfig]:
        """取得當前配置"""
        return self._config


# 建立服務單例
translation_service = TranslationService()
