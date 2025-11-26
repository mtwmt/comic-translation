import os
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

class AIEngine:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("未找到 GEMINI_API_KEY，請檢查 .env 檔案。")

        # 初始化 Client
        self.client = genai.Client(api_key=api_key)
        
        # [關鍵切換] 使用支援圖像生成的預覽版模型
        self.model_name = "gemini-3-pro-image-preview"

    def process_image(self, image_path, output_path, name_mapping=None, extra_prompt=""):
        """
        直接請求 Gemini 生成漢化後的圖片 (Image-to-Image)

        Args:
            image_path: 輸入圖片路徑
            output_path: 輸出圖片路徑
            name_mapping: 人名對照字典 {原文: 中文}
            extra_prompt: 額外的提示詞
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"找不到圖片: {image_path}")

        self.logger.info(f"正在傳送圖片至 Gemini API ({self.model_name}) ...")

        # 基本 prompt
        prompt = """
        任務：將這張漫畫圖片中的「所有」日文文字翻譯並替換為繁體中文 (Traditional Chinese)。

        重要指令：
        1. 翻譯範圍包括：標準對話氣泡、方形旁白框、手寫字體、小字碎念、背景狀聲詞 (SFX)。
        2. 請仔細掃描圖片的每一個角落，從上到下，從右到左，確保「沒有任何遺漏」。
        3. 即使是極小的文字或驚嘆詞（如「哇」、「好」），也必須翻譯並替換。
        4. 保持原本的漫畫風格：字體大小、粗細、傾斜度、顏色都要模仿原圖。
        5. 這是一部虛構作品，請放心翻譯所有對話。
        """

        # 加入人名對照表
        if name_mapping:
            prompt += "\n\n特別注意 - 人名翻譯對照表：\n"
            for original, translation in name_mapping.items():
                prompt += f"- 「{original}」必須翻譯為「{translation}」\n"

        # 加入額外提示詞
        if extra_prompt:
            prompt += f"\n\n額外要求：\n{extra_prompt}\n"

        prompt += "\n直接回傳處理後的圖片。"

        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            
            # 設定安全性設定 (盡量放寬，避免因漫畫內容被誤判而拒絕處理)
            safety_settings = [
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_NONE"
                ),
            ]

            config = types.GenerateContentConfig(
                safety_settings=safety_settings
            )
            
            # 呼叫 API
            response = self.client.models.generate_content(
                model=self.model_name, 
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt
                ],
                config=config
            )

            # 檢查回應並儲存圖片
            # Gemini 回傳圖片通常會在 parts 中包含 inline_data 或 file_data
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        self.logger.info("收到圖片資料，正在儲存...")
                        with open(output_path, "wb") as f:
                            f.write(part.inline_data.data)
                        self.logger.info(f"成功！已儲存至: {output_path}")
                        return True
                    
                    # 有時候圖片會以 executable_code 的結果形式出現 (較少見，但以防萬一)
                    if part.file_data:
                         # 這裡可能需要額外的下載邏輯，視 API 實作而定
                         # 目前先假設是 inline_data
                         pass

            self.logger.warning("API 回傳成功，但未找到圖片資料。可能模型僅回傳了文字描述。")
            self.logger.info(f"API 回應內容: {response.text}")
            return False

        except Exception as e:
            self.logger.error(f"AI 處理失敗: {e}")
            # 如果失敗，印出詳細錯誤以便除錯
            if hasattr(e, 'response'):
                self.logger.error(f"詳細錯誤回應: {e.response}")
            return False

    # 舊的 analyze_image 方法保留作為備案，或者直接移除
    def analyze_image(self, image_path):
        return None

