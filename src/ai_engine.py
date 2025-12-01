import os
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

class AIEngine:
    def __init__(self, config_file="translation_config.txt"):
        self.logger = logging.getLogger(__name__)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("未找到 GEMINI_API_KEY，請檢查 .env 檔案。")

        # 初始化 Client
        self.client = genai.Client(api_key=api_key)

        # [關鍵切換] 使用支援圖像生成的預覽版模型
        self.model_name = "gemini-3-pro-image-preview"

        # 載入翻譯配置（全域設定 + 全域 Prompt + 特定圖片）
        self.global_name_mapping, self.global_prompt, self.extra_prompts_map = self._load_translation_config(config_file)

        # 翻譯規則（精簡版，保留核心要求）
        self.translation_rules = """翻譯要求：
1. 準確理解日文原意，轉換為繁體中文台灣用語
2. 翻譯所有文字：對話框、旁白、註解、狀聲詞、小字
3. 語氣詞：ね→呢/啊、よ→喔、か→嗎、わ→呀（依語境調整）
4. 完美複製原圖字體風格（大小、顏色、位置、傾斜度、直橫排版）
5. 專有名詞保持原意，虛構內容可放心翻譯
6. 頁碼必須保留（如1,2,3或001,002不可改）"""

    def _load_translation_config(self, config_file):
        """載入翻譯配置（全域設定 + 全域 Prompt + 特定圖片）"""
        global_name_mapping = {}
        global_prompt = ""
        extra_prompts_map = {}

        if not os.path.exists(config_file):
            self.logger.info(f"未找到 {config_file}，將不使用自訂翻譯設定")
            return global_name_mapping, global_prompt, extra_prompts_map

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()

                # 分割三個區塊
                global_section = ""
                global_prompt_section = ""
                specific_section = ""

                # 依序切割區塊
                if "[全域設定]" in content:
                    parts = content.split("[全域 Prompt]")
                    global_section = parts[0].replace("[全域設定]", "").strip()

                    if len(parts) > 1:
                        # 有 [全域 Prompt] 區塊
                        remaining = parts[1]
                        if "[特定圖片]" in remaining:
                            prompt_parts = remaining.split("[特定圖片]")
                            global_prompt_section = prompt_parts[0].strip()
                            specific_section = prompt_parts[1].strip() if len(prompt_parts) > 1 else ""
                        else:
                            global_prompt_section = remaining.strip()
                    elif "[特定圖片]" in parts[0]:
                        # 沒有 [全域 Prompt]，但有 [特定圖片]
                        temp_parts = parts[0].split("[特定圖片]")
                        global_section = temp_parts[0].replace("[全域設定]", "").strip()
                        specific_section = temp_parts[1].strip() if len(temp_parts) > 1 else ""

                # 解析全域設定（人名對照）
                for line in global_section.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        try:
                            original, translation = line.split('=', 1)
                            original = original.strip()
                            translation = translation.strip()
                            if original and translation:
                                global_name_mapping[original] = translation
                        except:
                            pass

                # 解析全域 Prompt（簡潔合併，省 token）
                prompt_lines = []
                for line in global_prompt_section.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        prompt_lines.append(line)
                if prompt_lines:
                    global_prompt = "、".join(prompt_lines)  # 用頓號連接，省空間

                # 解析特定圖片設定
                for line in specific_section.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        try:
                            filename, prompt = line.split('=', 1)
                            filename = filename.strip()
                            prompt = prompt.strip()
                            if filename and prompt:
                                # 如果檔名已存在，用頓號合併多個指示
                                if filename in extra_prompts_map:
                                    extra_prompts_map[filename] += f"、{prompt}"
                                else:
                                    extra_prompts_map[filename] = prompt
                        except:
                            pass

                if global_name_mapping:
                    self.logger.info(f"已載入 {len(global_name_mapping)} 個全域人名對照")
                if global_prompt:
                    self.logger.info(f"已載入全域額外指示: {global_prompt[:50]}...")
                if extra_prompts_map:
                    self.logger.info(f"已載入 {len(extra_prompts_map)} 個特定圖片的額外要求")

        except Exception as e:
            self.logger.warning(f"無法讀取 {config_file}: {e}")

        return global_name_mapping, global_prompt, extra_prompts_map

    def _get_extra_prompt_for_file(self, image_path):
        """根據圖片檔名取得對應的額外要求"""
        if not self.extra_prompts_map:
            return ""

        # 取得檔名（含副檔名）
        filename = os.path.basename(image_path)

        # 精確匹配檔名
        if filename in self.extra_prompts_map:
            return self.extra_prompts_map[filename]

        # 嘗試匹配無副檔名的檔名
        filename_no_ext = os.path.splitext(filename)[0]
        if filename_no_ext in self.extra_prompts_map:
            return self.extra_prompts_map[filename_no_ext]

        return ""

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

        # 組合完整提示詞
        prompt = f"""將漫畫圖片的所有日文翻譯為繁體中文。

{self.translation_rules}"""

        # 合併全域和參數傳入的人名對照表
        merged_name_mapping = {}
        if self.global_name_mapping:
            merged_name_mapping.update(self.global_name_mapping)
        if name_mapping:
            merged_name_mapping.update(name_mapping)  # 參數優先

        # 加入人名對照表
        if merged_name_mapping:
            prompt += "\n\n人名對照（必須遵守）：\n"
            for original, translation in merged_name_mapping.items():
                prompt += f"{original}→{translation}\n"

        # 組合額外指示（全域 + 檔案特定 + 參數）
        extra_instructions = []
        if self.global_prompt:
            extra_instructions.append(self.global_prompt)

        file_specific_prompt = self._get_extra_prompt_for_file(image_path)
        if file_specific_prompt:
            extra_instructions.append(file_specific_prompt)
        elif extra_prompt:  # 參數傳入的 prompt 優先級最低
            extra_instructions.append(extra_prompt)

        if extra_instructions:
            combined = "、".join(extra_instructions)  # 用頓號連接省 token
            self.logger.info(f"套用指示: {combined[:100]}...")
            prompt += f"\n\n補充：{combined}\n"

        prompt += "\n直接輸出翻譯後圖片。"

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

