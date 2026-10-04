# Comic Translator

日文漫畫 → 台灣繁體中文。圖片辨識、清字、排版與修訂在本機執行，文字翻譯使用官方訂閱 CLI（agy、Claude Code 或 Codex，可選）。

## 啟動

使用 Python 3.11，在專案目錄執行：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python offline.py prepare-models
.venv/bin/python offline.py prepare-restoration
.venv/bin/python offline_gui.py
```

Windows 改用 `.venv\Scripts\python.exe`。既有 `.venv` 與模型可直接啟動最後一行；目前以原始碼使用，未提供經驗證的安裝包。

翻譯引擎與模型可在主畫面底部「翻譯引擎」選擇：`agy`、`claude`（Claude Code）或 `codex`，模型可從清單選或直接輸入；命令列用 `--provider`／`--model`。三者都只走官方訂閱登入（`claude.ai`／ChatGPT／agy 訂閱），程式會移除 API key 環境變數，登入方式不是訂閱就不傳送文字。換引擎或模型後，舊批次須沿用原設定，請建立新批次。

使用 `agy` 時，先在官方 CLI 登入訂閱並關閉 **Use G1 Credits**；找不到 `agy` 時 GUI 會詢問是否開啟官方安裝頁。GUI 加入圖片後，確認清單與角色對照，再按「開始翻譯」。圖片留在本機，只有辨識文字、角色對照及區域 ID 傳至所選引擎。字型自動使用系統繁中粗體；缺字時使用 Noto 繁中粗體，由 `prepare-models` 下載並驗證（不存在 git 內）。

成品預設存於來源旁的 `translated/final/`，修訂報告與遮罩存於 `translated/work/`；GUI 的「儲存至」可自選資料夾並記住設定，也可恢復預設。續跑沿用原批次位置，原圖與舊結果不覆寫。工作紀錄在 `.comic-translator/batches/`，模型在 `models/`。支援 PNG、JPEG、WebP，透明圖暫不支援，上限 4,000 萬像素。

`offline_gui.py` 是 GUI 入口（實作在 `src/gui/`），`offline.py` 是 CLI；檔名沿用，但翻譯需要所選引擎的網路連線。本機分析、預覽與自行填寫譯文不需要雲端。完整操作與 CLI 指令見 [GUI 操作指南](docs/GUI_GUIDE.md)。

## 開發

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q   # 首次執行會自動下載測試需要的字型
# 可用桌面視窗服務下，使用假模型驗證真實 Tk 操作
COMIC_GUI_TESTS=1 .venv/bin/python -m pytest tests/test_gui.py tests/test_review_gui.py -q
```

- [修補與排版](docs/RESTORATION.md)：模型、分析 CLI、合成規則。
- [驗證紀錄](docs/VALIDATION.md)：測試範圍與已知品質問題。
- [程式盤點](docs/MAINTENANCE.md)：模組責任與已移除項目。

本專案僅供學習和個人使用。© 2025 Mandy。
