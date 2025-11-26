import os
import argparse
import logging
from dotenv import load_dotenv
from src.ai_engine import AIEngine

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    # 載入環境變數
    load_dotenv()
    
    # 檢查 API Key
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("未設定 GEMINI_API_KEY，請檢查 .env 檔案。")
        return

    parser = argparse.ArgumentParser(description="AI 漫畫漢化工具 (One-Shot)")
    parser.add_argument("--input", required=True, help="輸入圖片資料夾")
    parser.add_argument("--output", required=True, help="輸出圖片資料夾")
    
    args = parser.parse_args()
    
    input_dir = args.input
    output_dir = args.output
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # 初始化 AI 引擎
    logger.info("正在初始化 AI 引擎 (Gemini 3 Pro Image Preview)...")
    try:
        ai_engine = AIEngine()
    except Exception as e:
        logger.error(f"初始化失敗: {e}")
        return

    # 取得所有圖片檔案
    image_files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    
    if not image_files:
        logger.warning(f"在 {input_dir} 找不到圖片檔案。")
        return

    logger.info(f"找到 {len(image_files)} 張圖片待處理。")

    for i, filename in enumerate(image_files):
        input_path = os.path.join(input_dir, filename)
        
        # [修改] 保持原檔名，不加後綴
        # 注意：AI 回傳通常是 JPG 格式，所以副檔名建議維持 .jpg 或與原圖相同(若原圖非jpg可能會被轉檔)
        # 這裡我們使用原檔名，但副檔名強制為 .jpg 以確保格式正確
        output_filename = os.path.splitext(filename)[0] + ".jpg"
        output_path = os.path.join(output_dir, output_filename)
        
        # [新增] 檢查檔案是否已存在，若存在則跳過
        if os.path.exists(output_path):
            logger.info(f"[{i+1}/{len(image_files)}] 檔案已存在，跳過: {output_path}")
            continue

        logger.info(f"[{i+1}/{len(image_files)}] 正在處理: {input_path}")
        
        try:
            # [核心邏輯] 直接呼叫 AI 進行一鍵漢化
            success = ai_engine.process_image(input_path, output_path)
            
            if success:
                logger.info(f"成功！已儲存至: {output_path}")
            else:
                logger.error(f"處理失敗: {filename}")
                
        except Exception as e:
            logger.error(f"發生未預期的錯誤: {e}")
            continue

    logger.info("所有批次任務已完成。")

if __name__ == "__main__":
    main()
