# 🎨 Comic Translator

使用 Google Gemini AI 自動將日文漫畫翻譯成繁體中文的工具。

## ✨ 功能特色

- 🖥️ **圖形化介面 (GUI)**：簡單易用，無需輸入指令
- 🤖 使用 Gemini AI 進行圖像到圖像的翻譯
- 📝 自動辨識並翻譯所有日文文字（對話框、旁白、狀聲詞等）
- 🎨 保持原本的漫畫風格（字體、顏色、大小）
- 📂 批次處理多張圖片
- ⏭️ 自動跳過已處理的檔案
- 📋 人名對照表功能：自訂角色名稱翻譯

## 📋 使用方式

### 方式一：執行檔版本（推薦給一般使用者）

**無需安裝 Python！**

1. 下載 `ComicTranslator` 資料夾
2. 雙擊執行 `ComicTranslator.exe`
3. 按照介面指示操作：
   - 輸入 Gemini API Key
   - 選擇輸入/輸出資料夾
   - 點擊「開始翻譯」

### 方式二：Python 原始碼版本（開發者）

**環境需求：**
- Python 3.8 或以上版本
- Google Gemini API Key

## 🚀 安裝步驟（開發者）

### 1. 下載或複製專案

將整個專案資料夾複製到您的電腦。

### 2. 安裝 Python 套件

在專案資料夾中開啟終端機（命令提示字元），執行：

```bash
pip install -r requirements.txt
```

### 3. 執行程式

#### GUI 圖形化介面（推薦）

```bash
python gui.py
```

#### 命令列模式

```bash
python main.py --input input --output output
```

## 🔑 取得 Gemini API Key

1. 前往 [Google AI Studio](https://makersuite.google.com/app/apikey)
2. 使用 Google 帳號登入
3. 點擊「Create API Key」建立新的 API Key
4. 複製產生的 API Key
5. 在 GUI 程式中貼上，或建立 `.env` 檔案儲存

### 支援的圖片格式

- PNG (.png)
- JPEG (.jpg, .jpeg)
- WebP (.webp)

## 📁 專案結構

```
comic-translation/
├── gui.py                      # 圖形化介面主程式
├── main.py                     # 命令列版本主程式
├── build.bat                   # 打包執行檔腳本（Windows）
├── src/
│   └── ai_engine.py           # AI 引擎核心邏輯
├── input/                     # 範例：放置待翻譯的圖片
├── output/                    # 範例：翻譯後的圖片輸出位置
├── requirements.txt           # Python 套件清單
├── README.md                  # 說明文件
└── README_使用說明.txt         # 詳細使用說明
```

## 📦 打包成執行檔（開發者）

如果你想將程式打包成 `.exe` 執行檔：

```bash
# 執行打包腳本（Windows）
build.bat
```

打包完成後，執行檔位於 `dist\ComicTranslator\ComicTranslator.exe`

## ⚠️ 注意事項

1. **API 使用費用**：Gemini API 可能會產生費用，請注意您的使用量
2. **安全性**：
   - ⚠️ **絕對不要**將 API Key 分享給他人
   - 不要將包含 API Key 的 `.env` 檔案上傳到 GitHub
3. **處理時間**：每張圖片的處理時間約 10-30 秒，視圖片複雜度而定
4. **圖片品質**：輸出為 JPEG 格式

## 🔧 常見問題

### Q1: GUI 程式無法開啟？
**A:**
- 確認已安裝 Python 和所有依賴套件
- 或使用打包好的 `ComicTranslator.exe` 執行檔版本

### Q2: API 回傳錯誤？
**A:** 可能原因：
- API Key 無效或過期
- 超出 API 使用額度
- 網路連線問題

### Q3: 翻譯結果不理想？
**A:** 可以嘗試：
- 使用解析度較高的圖片
- 確保原圖文字清晰可見
- 使用「人名對照表」功能自訂角色名稱

### Q4: 如何打包成執行檔？
**A:**
- Windows: 執行 `build.bat`
- 其他系統: 參考 `build.bat` 內容使用 PyInstaller

## 📝 授權

© 2025 Mandy | v0.1-beta

本專案僅供學習和個人使用。

## 🤝 分享給朋友

**執行檔版本：**
- 分享 `ComicTranslator` 資料夾
- 使用者無需安裝 Python

**原始碼版本：**
- 分享專案資料夾（不包含 `.env` 檔案）
- 使用者需自行申請 Gemini API Key
