"""
Translation 相關的 Pydantic Schema
用於請求/回應驗證和序列化
"""
from pydantic import BaseModel, Field, field_validator


class TranslationConfig(BaseModel):
    """翻譯配置 Schema"""

    api_key: str = Field(..., min_length=1, description="Gemini API Key")
    name_mapping: dict[str, str] = Field(default_factory=dict, description="人名對照表")
    global_prompt: str = Field(default="", description="全域額外指示")

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """驗證 API Key 格式"""
        if not v or v.isspace():
            raise ValueError("API Key 不可為空")
        return v.strip()


class TranslationRequest(BaseModel):
    """翻譯請求 Schema"""

    extra_prompt: str = Field(default="", description="額外的提示詞")

    class Config:
        json_schema_extra = {
            "example": {
                "extra_prompt": "注意保留頁碼格式"
            }
        }


class TranslationResponse(BaseModel):
    """翻譯回應 Schema"""

    success: bool = Field(..., description="是否成功")
    filename: str = Field(..., description="檔案名稱")
    output_url: str | None = Field(None, description="輸出檔案 URL")
    error: str | None = Field(None, description="錯誤訊息")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "filename": "page_001.jpg",
                "output_url": "/outputs/page_001_translated.jpg",
                "error": None
            }
        }


class ConfigResponse(BaseModel):
    """配置回應 Schema"""

    ok: bool = Field(..., description="配置是否成功")
    message: str = Field(default="配置已更新", description="回應訊息")
