# 漫畫翻譯器 Windows 免安裝版

適用於 Windows 10／11、64 位元。解壓整個 ZIP 到有寫入權限的資料夾（例如桌面），再雙擊 `ComicTranslator.exe`。不需安裝 Python 或 Python 套件。請勿直接在 ZIP 內啟動，也不要只複製 exe；`_internal`、`models` 都是執行所需內容。

目前未加上數位簽章，Windows 可能顯示「未知的發行者」。

已內附日文辨識、文字偵測、清字修補模型與 Noto 繁中粗體。模型在 `models`，程式依賴在 `_internal`；首次啟動會載入模型，時間取決於 CPU、記憶體與磁碟速度。

## 開始使用

1. 選擇翻譯引擎。雲端文字翻譯需要該引擎的官方 CLI 與使用者自己的訂閱登入，帳號與登入資料不包含在此包。
2. 按「加入圖片」或將圖片拖入清單，選擇引擎、模型與思考強度。
3. 按「開始翻譯」。辨識、清字與排版在本機；只有辨識文字及角色對照送到所選翻譯引擎。
4. 成品預設儲存在來源圖片旁的 `translated/final`；可用「儲存至」更改位置。

官方 CLI 安裝／登入說明：

- AGY：https://antigravity.google/docs/cli
- Claude Code：https://code.claude.com/docs/en/setup
- Codex：https://developers.openai.com/codex/cli

電腦已安裝並登入其中一個引擎，就可選用該引擎，不需要三個都安裝。本程式使用訂閱 CLI，不會自行改走付費 API。

## 設定與更新

設定、批次紀錄及錯誤日誌保存在 exe 同層的 `.comic-translator`。辨識套件暫存位於 `.cache`。移動程式時請移動整個資料夾；更新時保留 `.comic-translator` 與 `models`，重新解壓新版程式到原資料夾。批次內的圖片與輸出位置為完整路徑，移動來源圖片會影響續跑。

本機辨識與預覽不需要雲端帳號；按「翻譯此區」仍需上述登入。發生問題時可提供 `.comic-translator/logs` 的錯誤日誌。日誌可能含圖片路徑或辨識文字，分享前請檢查內容。

## 開發者重新打包

在已安裝 `requirements.txt` 且備妥模型的 Windows Python 3.11 環境執行：

```powershell
.\.venv311\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv311\Scripts\python.exe tools\build_windows.py
```

產物：`dist/ComicTranslator/ComicTranslator.exe` 與 `dist/ComicTranslator-Windows-x64.zip`。分發 ZIP 即可。

精簡版（約 500 MB、不含模型，使用者首次使用須按「下載／檢查所需檔案…」）：

```powershell
.\.venv311\Scripts\python.exe tools\build_windows.py --without-models
```

包內的 `使用說明.txt` 來自給一般使用者看的 [USER_GUIDE.txt](USER_GUIDE.txt)；精簡版會把其中「下載翻譯所需檔案」步驟換成下載指示（文字在 `tools/build_windows.py`）。

若已有打包完成的執行檔，可加上 `--skip-build`，直接產生精簡 ZIP。
產物為 `dist/ComicTranslator-Windows-x64-Lite.zip`，完整 ZIP 會保留。
精簡版只減少首次分發容量；模型下載後仍需相同的磁碟空間。

診斷模式（只建立合成圖片、測試本機模型，不呼叫雲端翻譯）：

```powershell
ComicTranslator.exe --self-test D:\新的測試資料夾
```

結果在指定資料夾的 `result.json`。也可用 `ComicTranslator.exe --cli --help` 存取原有命令列功能，日誌會記錄在 `.comic-translator/logs`。

此 Windows 包不包含 macOS 執行檔，也不改動 macOS 的執行方式。第三方授權資訊在 `licenses`，辨識模型附有來源 README 及版本／雜湊 manifest。
