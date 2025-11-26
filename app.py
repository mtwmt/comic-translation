import os
import logging
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from src.ai_engine import AIEngine
import uuid
from pathlib import Path

# 載入環境變數
load_dotenv()

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制 16MB
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# 建立必要的資料夾
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs('static', exist_ok=True)

# 允許的檔案格式
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    # 檢查 API Key
    if not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "YOUR_API_KEY_HERE":
        return jsonify({'error': '請先在 .env 檔案中設定 GEMINI_API_KEY'}), 400

    if 'file' not in request.files:
        return jsonify({'error': '沒有選擇檔案'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': '沒有選擇檔案'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '不支援的檔案格式，請使用 PNG, JPG, JPEG 或 WebP'}), 400

    try:
        # 生成唯一的檔案名稱
        file_ext = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_ext}"

        # 儲存上傳的檔案
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(input_path)

        # 輸出檔案路徑（固定為 jpg）
        output_filename = f"{uuid.uuid4().hex}.jpg"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        # 初始化 AI 引擎並處理圖片
        logger.info(f"開始處理圖片: {unique_filename}")
        ai_engine = AIEngine()
        success = ai_engine.process_image(input_path, output_path)

        if success:
            logger.info(f"處理成功: {output_filename}")
            return jsonify({
                'success': True,
                'output_file': output_filename,
                'message': '翻譯完成！'
            })
        else:
            # 清理上傳的檔案
            if os.path.exists(input_path):
                os.remove(input_path)
            return jsonify({'error': 'AI 處理失敗，請稍後再試'}), 500

    except Exception as e:
        logger.error(f"處理失敗: {e}")
        # 清理檔案
        if os.path.exists(input_path):
            os.remove(input_path)
        return jsonify({'error': f'處理失敗: {str(e)}'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
        if os.path.exists(output_path):
            return send_file(output_path, as_attachment=True, download_name=f'translated_{filename}')
        else:
            return jsonify({'error': '檔案不存在'}), 404
    except Exception as e:
        logger.error(f"下載失敗: {e}")
        return jsonify({'error': '下載失敗'}), 500

@app.route('/check_api_key')
def check_api_key():
    api_key = os.getenv("GEMINI_API_KEY")
    has_key = bool(api_key and api_key != "YOUR_API_KEY_HERE")
    return jsonify({'has_api_key': has_key})

if __name__ == '__main__':
    # 檢查 API Key
    if not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "YOUR_API_KEY_HERE":
        logger.warning("⚠️  警告：尚未設定 GEMINI_API_KEY")
        logger.warning("請在 .env 檔案中設定您的 API Key")

    logger.info("🚀 啟動漫畫翻譯網頁服務...")
    logger.info("📱 請開啟瀏覽器前往: http://127.0.0.1:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)