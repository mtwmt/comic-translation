# 程式盤點

更新：2026-10-04。以現行訂閱 CLI 桌面流程為範圍，保留本機分析／修訂及核心回歸測試。

## 維護位置

| 模組 | 職責 |
| --- | --- |
| `offline_gui.py`、`offline.py` | GUI 入口、CLI 操作與雲端文字同意 |
| `src/gui/` | GUI 實作，以 mixin 組成 `OfflineGUI`：`app`（組裝、還原上次批次）、`view`（畫面）、`staging`（清單與勾選）、`worker`（執行緒、事件、主按鈕）、`settings`（輸出位置、名稱、翻譯引擎）、`actions`（下載、修訂、關閉）、`theme`、`widgets` |
| `src/offline/batch.py` | 發現、排序、工作紀錄、停止／續跑／重試 |
| `pipeline.py`、`providers.py`、`recovery.py` | 單頁流程、本機偵測／OCR、補漏偵測（大字／擬聲字） |
| `translators.py` | 翻譯引擎選擇與建立、模型查詢分派、使用者設定載入 |
| `agy_provider.py`、`claude_provider.py`、`codex_provider.py` | 各引擎的預設模型、模型清單、訂閱檢查、CLI 呼叫與回應解析 |
| `translation_common.py` | 各引擎共用的提示詞、輸入限制、輸出 schema、繁簡轉換與譯文驗證 |
| `cli_common.py` | 共用的 CLI 尋找與執行（UTF-8 stdin、Windows 官方 npm 入口解析、移除付費 API 變數、暫存工作目錄、逾時清理） |
| `models.py`、`restoration.py` | 固定辨識／修補模型、完整性與明確準備 |
| `images.py`、`composition.py`、`storage.py` | 圖片政策、合成與狀態、檔名預約及原子保存 |
| `layout.py`、`fonts.py`、`linebreak.py`、`source_size.py` | 字型、字級、詞語換欄與繪字 |
| `review.py`、`review_gui.py`、`manual_review.py`、`report_lookup.py` | 草稿／預覽、補漏字、另存修訂、原圖索引 |
| `tests/`、`tools/create_agy_smoke_fixture.py` | 核心與 Tk 回歸、原創合成輸入 |

表內未列前綴的程式都位於 `src/offline/`。

## 已移除

- 舊圖片 API GUI／CLI、引擎、API key 範例、舊設定樣板及打包腳本。
- Qwen 本機翻譯推論、llama.cpp 依賴、候選下載、文字 benchmark／評分工具與其專用測試／題庫。
- 手動字型匯入／設定，以及已被主按鈕取代的 GUI JSON 選擇器／重轉入口。
- 重複的純本機操作、候選比較、階段執行計畫、版本追加日誌與文字版 README。保留的實測證據合併到 [VALIDATION](VALIDATION.md)。

依賴只維護 `requirements.txt` 與引用它的 `requirements-dev.txt`。字型使用系統繁中粗體；缺字用的 Noto 繁中粗體不放在 git，由 `prepare-models` 下載並驗 SHA-256（`fonts.ensure_bundled_font`），測試由 `tests/conftest.py` 自動下載；舊 Serif 字型不再下載。辨識準備只下載 detector／OCR／Noto 字型，保留既有完整模型 manifest；舊 manifest 中已記錄字型仍納入 AGY 雜湊，避免無故改變既有批次指紋。已淘汰的本機翻譯批次不續跑。

## 保留邊界

保守白底流程仍是未準備修補模型時的可用路徑；從原圖合成、重疊拒絕、修改遮罩、來源雜湊與續跑完整性都是現行保護，不因刪除舊功能移除。保存提供逐檔原子性，尚非 PNG／遮罩／報告整組交易。

漫畫原檔、模型權重、使用者設定及既有成果未刪除，且不納入 git（見 `.gitignore`）。AGY 官方模型 ID 本身仍含 `gemini`，屬現行 CLI 的模型識別，並非舊圖片 API 路徑。

測試結果見 [VALIDATION](VALIDATION.md)。
