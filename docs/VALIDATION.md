# 驗證範圍與品質限制

更新：2026-10-04。開發環境為 macOS Apple Silicon、32 GiB RAM、Python 3.11。以下記錄使用者實機試用、程式回歸與歷史實圖證據。

## 實機試用

2026-10-04，使用者確認已完成實機試用，並要求移除待辦驗收計畫。下列自動測試結果與已知品質限制保留供維護參考。

## 回歸測試

涵蓋來源發現／排序／去重、批次停止／續跑／重試、輸出位置選擇／記憶／恢復預設、輸出碰撞與完整性、模型損壞、雲端文字同意與各引擎登入檢查（含 AGY 額外 credits 關閉）、補漏偵測、配額停止、子程序清理、遮罩／排版／像素保真、手動區域與修訂、並行保存及失敗清理。桌面測試使用真實 Tk 和假模型，不傳送使用者文字。

執行指令集中於 [README](../README.md#開發)。2026-10-04 本輪結果：

- 全部回歸：216 項通過（含 39 項真實 Tk 操作）、1 項 Windows 專用測試在 macOS 略過。桌面測試使用 macOS 視窗服務、假模型與暫存資料，未呼叫雲端翻譯，並驗證名稱編輯區可拖曳調整高度、翻譯引擎／模型選擇與保存、筆刷游標與大小、偵測區域可調整框。三家翻譯引擎拆為獨立模組後，另驗證引擎建立、預設模型、保存設定載入、模型查詢分派及批次指紋相容性。
- 6 份 Markdown 的本機連結、Python 語法、CLI 說明與 Git whitespace 檢查通過。
- 新環境模型準備只下載 detector／OCR、不下載字型或本機翻譯權重；損壞模型包、無雲端同意、純本機分析與保存失敗皆有回歸驗證。
- 現有 AGY 模型包雜湊與整理前算法完全相同；12 份歷史 AGY 批次中 2 份符合目前版本指紋，其他較早版本仍按原有版本檢查要求新批次，未改寫紀錄。

移除舊功能時，同時移除只驗證該功能的測試；測試數量下降不表示現行功能免於回歸。

## 本輪新增的驗證（2026-10-04）

- 補漏偵測（大字、擬聲字）：以馬力歐頁及烏龍派出所 12、14、15 頁實跑偵測＋OCR（假翻譯器貼字）。馬力歐頁的大標題與擬聲字「はいくくっ」被框出且清乾淨；其他頁補到擬聲字與一個原漏掉的對話框。標題左上仍殘留兩個與爆炸框相連的小黑點，需用筆刷清除；標題的 OCR 仍不準，須用「重新辨識」或手動輸入。這只是少量頁面，不是漏字率。
- 翻譯引擎：agy、Claude Code（haiku）、Codex（gpt-5.5）各用一句測試文字實際呼叫一次，皆成功並通過同一套譯文驗證；登入方式檢查、工具拒絕、環境變數移除以假子程序測試。未比較三者的翻譯品質。
- 內附字型改為下載：真實下載與 SHA-256 驗證通過。
- 翻譯 CLI 的整頁 prompt 改走 UTF-8 stdin：AGY 使用單筆 `stream-json` 訊息、Claude 使用 `-p`、Codex 使用 `exec -`。三個 adapter 各以真實本機假 CLI 子程序跑過 100 區／12,000 字、名稱表與 OCR 替代讀法；沒有把 prompt 放入 argv，登入檢查也不帶來源文字。另驗證大量 stdin／stdout／stderr 不死鎖、Unicode／特殊字元、無輸入時 EOF、逾時回收及錯誤訊息不暴露 CLI 輸出。本次沒有重跑雲端翻譯。
- Windows 啟動解析涵蓋官方 npm 的全域與本機安裝布局（Codex／Claude）、相鄰原生 `.exe` 及缺件拒絕；直接啟動 Node／原生程式，不經 `cmd.exe`。不明 `.cmd`／`.bat` 不執行，提示改裝官方版本。已加入需 Windows＋Node 的實際啟動測試（`tests/test_cli_common.py`）；本輪自動測試在 macOS 略過此項。

stdin 用法依 [AGY headless](https://www.antigravity.google/docs/cli/headless/)、[Claude CLI reference](https://code.claude.com/docs/en/cli-reference) 與 [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) 核對。

## 保留的實測摘要

- 2026-09-19 原創雙欄圖以真實 OCR → AGY → 排版完成 2/2 區，輸出 760×560 PNG；process 單次 25.7 秒、AGY 回報 9.03 秒。修改遮罩外像素一致，續跑略過已完成頁。這不是漫畫每頁速度保證。
- 同日 AGY Medium 的 20 句開發題與 12 句保留題，助理初校合計 25 可接受、5 用詞需修整、2 原文情境不足，未發現明確重大錯誤；不是獨立日文審校或跨作品準確率。舊本機翻譯模型已因語意錯誤淘汰，相關推論及審核原始結果保留在本機 `offline-runs/quality/`。
- 2026-10-03 本機遮罩／排版診斷的三張漫畫分別完成 2、10、8 區；提供的測試譯文為 2、11、8 區。沒有新雲端翻譯，不能當成 AGY 成績；PNG 尺寸一致、遮罩外差異像素為 0。結果在 `offline-runs/restoration-2026-10-03/`。
- 同日沿用實際 AGY 譯文重排烏龍派出所第 13 張與馬力歐，完成 9/9 與 8/8 個已有區域；修改遮罩外零差異。這沒有解決漏偵測或語意問題，結果在 `offline-runs/fix-2026-10-03/`。

歷史單次耗時不作 P95、支援規格或品質承諾。本輪整理沒有重新呼叫 AGY、推論真實漫畫或量測模型效能。

## 已知品質限制

OCR 曾將「いかん」讀成「いやん」、將「曲芸」讀成「由芸」，並漏讀「エビ天」。大型藝術字、招牌、相連氣泡與長譯文仍有漏偵測／排不下；局部修補可能傷及遮罩內畫線。

程式 `success` 只描述已偵測區域通過技術檢查，不能代表沒有漏字或誤譯。

## 2026-10-05 Windows AGY 初始化逾時

- 真實 `/config` 查詢重現 AGY 登入後初始化不再回傳結果；本輪未修改 AGY 安裝、使用者設定或憑證。Windows 加入只限設定查詢的有界重啟（最多 5 次，每次 8 秒），設定仍須通過訂閱與 credits 檢查。正式翻譯不自動重送；macOS 保留原設定檢查流程。
- 修正後連續三次真實設定檢查成功，耗時 26.22、2.11、19.59 秒。同一個 `gemini-3.8-flash-high` 模型完成兩句合成日文翻譯測試，總耗時 21.86 秒。
- 實際 Windows GUI 子程序以新繪製的 760×560 日文雙欄圖完成 OCR → AGY → 清字排版 → PNG，2/2 區成功；總耗時 126.69 秒，AGY 回報推論 14.03 秒。否定句分別譯為「不能在這裡等。」與「不用在這裡等。」；遮罩外像素完全一致。結果在 `.comic-translator/diagnostics/agy-synthetic-result.*`。這是初始化復原的實測，不代表 AGY 自身的間歇性卡住已被根治。
- 相關回歸測試 195 passed、3 skipped，包含設定查詢重啟上限、登入錯誤不重試、翻譯不重送、Windows 子程序錯誤序列化及 macOS 行為隔離。
- 原始 `002.jpg` 的完整雲端重測遭自動核准審查拒絕，未執行；本輪完整流程的雲端測試只使用自製文字，未傳送使用者漫畫或名稱表。

### Windows 模型清單與修訂區域回歸

Windows 模型清單按引擎保存、重開載入、首次自動查詢及失敗保留舊清單均以本機 Tk 測試驗證。修訂器測試包含自動區域刪除、全刪後恢復原圖並另存、自動區域改字級、不受既有失敗區域阻擋，以及 macOS 保留原行為。

本輪主畫面與修訂器 Tk 回歸 49 項通過；相關區域、遮罩、字級、原圖保留與平台隔離測試通過。測試間在主執行緒清理 Tk 物件，避免 Windows 背景預覽執行緒代為回收舊視窗。

以既有馬力歐 139 頁報告進行本機重新排版（沿用已有譯文，無雲端呼叫）：大框 r011 與 r012 日文重複，停用後 r012、r013 均可貼字；兩區指定 20 px 後實際字級均為 20。原始報告未改動，診斷輸出位於 `.comic-translator/diagnostics/review-overlap-fixed.png` 與 `review-font-20.png`。r010 的框線遮罩問題仍保留原文，需修訂該遮罩。

### Windows CLI 安裝位置搜尋

2026-10-05 實機確認：Claude Code 2.1.289 位於 VS Code 官方擴充套件的 `resources/native-binary/claude.exe`，Codex CLI 0.160.0 位於使用者 `AppData/Local/OpenAI/Codex/bin/<版本目錄>/codex.exe`。一般使用者 PATH 未包含後者，前者也不在 PATH；Windows 搜尋加入原生／npm 安裝、桌面 CLI 與官方擴充套件目錄，macOS 保留 PATH-only。

模擬 PATH 同時找不到兩個 CLI，仍成功查得 Claude 4 個、Codex 8 個實際模型。查詢僅送 metadata 初始化與 model/list，不送漫畫或提示詞。Codex 訂閱登入有效；Claude 原生 CLI 的 `auth status` 回報 `loggedIn=false`、`authMethod=none`，模型清單可取得不代表已有翻譯權限，仍須先登入。相關測試 47 項通過；逾時子程序清理測試須在允許 taskkill 的環境執行。

### Windows 引擎／模型欄位操作

主畫面底部三個控制項統一實際高度；模型欄位空白點選可展開原生清單，選取後仍會保存，模型文字可繼續輸入，處理中不會展開。沒有清單時點空白觸發查詢。主畫面 Tk 回歸 27 項通過，使用合成圖片與假查詢器，沒有雲端翻譯；macOS 的平台掛鉤為空操作。

模型清單展開後量測選項與欄位文字的螢幕座標，確認左緣一致；空白點選、箭頭重新展開及長清單出現捲軸均維持對齊，不修改實際模型值。主畫面 Tk 回歸再次 27 項通過。

2026-10-06 簡化留白設定：移除清單展開事件與座標調整程式，改用模型欄位 padding 與清單 flat border 共用 12 px。清單外圍四邊皆有留白，每列文字高度維持原生設定；有無捲軸及重複展開的文字左緣一致，主畫面 Tk 測試 27 項通過。

### Windows 思考強度與 Fast

2026-10-06 以官方文件及已安裝的 Codex／Claude CLI metadata 確認選項。Codex `model/list` 回傳 `supportedReasoningEfforts` 與 Fast tier；Claude SDK 回傳 `supportedEffortLevels`／`supportsFastMode`，Haiku 無兩者、Sonnet 無 Fast。清單能力與各模型選擇會保存，既有快取缺少能力資料時自動補查。

CLI／主畫面／平台回歸 80 項通過；Windows 子程序、修訂器與 AGY 流程另一組 81 項通過、2 項略過（兩組包含重複測試）。涵蓋強度與 Fast 真正進入參數、環境變數不覆蓋明確強度、指紋保存、預設／關閉維持既有批次指紋、模型切換、重開、儲存失敗與 Mac 原行為。Codex app-server 僅 initialize 實測接受 xhigh 及 Fast 開／關設定，沒有開始推論。

正式 DPI 的隔離測試 GUI 確認控制列完整可見，截圖位於 `.comic-translator/diagnostics/generation-controls.png`。所有翻譯測試使用假回應，未傳送漫畫或開啟 usage credits；本輪未實測服務端的加速效果或帳號 Fast 權限。Claude Fast 須自行啟用額外計費 credits，程式僅在使用者勾選後傳入設定；不自動改模型或切換 API 登入。

### AGY 思考強度

2026-10-06 實機 `agy models` 回傳 18 個模型：Gemini 3.8／3.7／3.6 Flash 各輕、中、高；Gemini 3.1 Pro 只有輕、高；Claude Opus／Sonnet 5.5 各輕、中、高；GPT-OSS 120B 只有中。GUI 從回傳的同系列完整模型 ID 建立強度選項，選強度直接保存該模型，管線與修訂器沿用既有模型參數、指紋及訂閱檢查，不額外覆寫 effort。

CLI `--help` 接受的 effort 語法範圍比模型清單廣，不據此虛構可選模型。這台 CLI 未提供獨立 Fast 旗標；官方 execution modes 說明舊 `/fast` 已移除。帶 xhigh／max 的內建 `/model` 查詢均結束碼 1，未進行推論，不將其當作可用組合。

AGY、主畫面、模型清單、翻譯器、平台及整合回歸 103 項通過、2 項略過，涵蓋僅提供真實變體、模型／強度雙向同步、舊快取、保存失敗保留原模型、處理中停用、原模型參數與指紋，以及 Mac 原流程。全部翻譯測試為假回應，未傳送漫畫或更改 AGY 訂閱／credits 設定。

### Windows 單行模型控制列

2026-10-06 將引擎、模型、思考強度、可用的 Fast 與查詢按鈕整合為一行；先保留選項與按鈕空間，模型欄位隨剩餘寬度伸縮。沒有獨立 Fast 能力時隱藏勾選框與說明，不占空間。修改僅在 Windows 平台控制項，Mac 原布局不變。

主畫面 Tk 回歸 33 項通過，涵蓋最小視窗尺寸、控制項等高與同列、Fast 隨模型切換顯示／隱藏、保存及處理中停用。實際 DPI 的隔離 GUI 亦確認 AGY 與 Codex 最小視窗完整顯示，截圖位於 `.comic-translator/diagnostics/compact-layout-agy.png` 與 `compact-layout-codex-minimum.png`；僅使用假模型清單，沒有雲端翻譯。

### 應用程式圖示

2026-10-06 使用內建 imagegen 製作透明漫畫頁與日／中對話泡泡圖示，保留 PNG 原圖，匯出 Windows 多尺寸 ICO 與 Mac ICNS 至 `assets/icons/`。ICO 的 7 種尺寸與 ICNS 的 8 個表示均成功解碼，透明 alpha 保留。Windows 明確設定主視窗圖示、後續視窗預設圖示及獨立 AppUserModelID，原生 WM_GETICON 回傳有效圖示句柄；Mac 掛鉤不修改現有視窗行為，ICNS 留待應用程式封裝使用。

主畫面 Tk 回歸 33 項通過；未建立安裝包或實測 macOS 封裝。產生提示詞及資源包含方式見 `assets/icons/README.md`。

### Claude 模型別名的思考強度

2026-10-06 確認 Claude Code 2.1.289 實際回傳 `sonnet`／`claude-sonnet-5-5` 及 low、medium、high、xhigh、max；程式舊能力快取只以完整 ID 儲存，而已選模型仍是 `sonnet`，造成強度選單停用。修正為保存 CLI 實際回傳的別名與完整 ID 兩者能力，Windows 初始化遇到當前 Claude 模型缺能力時自動補查。未按名稱猜模型，也不改動已選別名、原批次模型或 Mac 的預設參數。

模型清單、GUI、翻譯器、Claude adapter 與平台隔離共 64 項測試通過，包含別名強度保存、管線參數、舊快取補查一次，以及未知模型不借用其他能力。隔離 GUI 以 CLI 實際 metadata 與舊快取重現，`sonnet` 自動恢復五級強度並成功保存「高」至管線選項，截圖位於 `.comic-translator/diagnostics/claude-alias-effort.png`。只查模型 metadata，未開始推論或傳送漫畫。

### Windows 圖示載入與 DPI 修正

2026-10-06 使用者回報圖示模糊後，讀取原生 HICON 的實際像素，確認第一版的 PNG 編碼 ICO 在這台 Tk 觸發通用圖示替代；小／大圖示皆是相同的 56 px 系統圖案。前輪只確認句柄有效，未確認實際圖案，無法證明正確載入。

以 imagegen 製作簡化 v2，保留原版比較，ICO 改用 BMP 編碼並提供 11 種尺寸。Windows 主視窗以 LoadImageW 載入系統所需尺寸，再設定 WM_SETICON；關閉時釋放自建 HICON。這台實際 DPI 下取得小圖示 28 px、大圖示 56 px，其不透明像素與 v2 資源完全一致，診斷圖位於 `.comic-translator/diagnostics/native-icon-v2-dpi-28.png` 與 `native-icon-v2-dpi-56.png`。

GUI 回歸 35 項通過，新增原生小／大圖示尺寸與分別載入檢查。Mac 平台掛鉤維持不動；新版 ICNS 僅作封裝資源，尚未實測 Mac 應用程式封裝。
## Windows 免安裝封裝（2026-10-06）

另新增精簡封裝 `--without-models`，使用已驗證的同一執行檔與依賴，不包含 `models`。`ComicTranslator-Windows-x64-Lite.zip` 為 499,942,441 bytes；已驗證全部 ZIP CRC、SHA256、執行檔與完整版逐位元一致、內附字型、精簡版使用說明，且沒有模型或使用者紀錄。精簡版首次使用須透過既有「下載／檢查所需檔案…」流程下載模型；此次未重新下載模型或重跑雲端翻譯。SHA256：`1fe7f7eaebf244305fb9fb45bf718b157f0d18b91af134ba31f729be2dcfafbd`。

使用 Windows x64 Python 3.11.9、PyInstaller 6.22.3／hooks 2026.8 建立 windowed folder bundle，內附約 750 MB 的固定偵測／OCR／修補模型、Noto 字型、Python 依賴與授權檔。入口為 `ComicTranslator.exe`，分發 `ComicTranslator-Windows-x64.zip`。PE 已確認為 AMD64、GUI subsystem、11 個 icon 尺寸及 0.1.0 產品版本。

原始碼驗證：GUI、平台隔離、路徑、Windows worker 與修補的 65 項測試通過；修補／平台／路徑在最後模型讀取調整後再跑 28 項通過（範圍重疊，不相加）。命令列／模型查詢相關檢查通過；Windows 子程序清理測試須在允許 taskkill 的環境執行，UTF-8 報告測試使用 `PYTHONUTF8=1`。

真正的 frozen exe 搬到含中文及空白的資料夾，PATH 只保留 Windows 系統目錄，移除 PYTHONHOME／PYTHONPATH。`build/frozen-final-success/result.json` 的 7 項診斷均通過：模型／字型雜湊、Tk GUI／圖示／拖放、spawn worker 內真正的 Paddle 偵測與 Manga OCR／本機假譯文貼字、LaMa 修補、即時停止、外部程序 DLL 隔離、內附下載 CLI 入口。合成輸入與結果留在 build 診斷目錄，不使用私人漫畫、不送雲端文字、不查詢真實帳號。CLI `prepare-restoration` 也確認可使用內附完整模型，不重新下載。

搬移測試實際發現 OpenCV、Paddle PIR、TorchScript 的 Windows 窄字元檔名限制；Windows adapter 分別改用 ONNX buffer、相對 ASCII 檔名及 Python 檔案串流，macOS adapter 保留原本檔名讀取。PaddleX 的依賴檢查還需要 distribution metadata，spec 已收集執行期套件資訊；診斷會強制驗證 Paddle，避免 enhanced 流程的容錯掩蓋缺失。打包快取曾保留舊程式，已強制重編 PYZ，並檢查 exe 內含 `load_repair_model` 後重新驗證。[OpenCV buffer 介面](https://docs.opencv.org/4.10.0/d6/d0f/group__dnn.html)；[PyInstaller 多程序／外部 DLL 文件](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)。

使用者設定、批次、圖片、帳號與暫存不進分發包；builder 遇到 dist 內的執行期資料會拒絕重建，避免刪掉設定。正式雲端訂閱翻譯與另一台乾淨 Windows 電腦尚未驗證；exe 尚未數位簽章。此包不包含 macOS app。

最終 ZIP 共有 12,251 個檔案，1,167,782,604 bytes（約 1.09 GiB），解壓內容 2,238,343,332 bytes。全部 CRC、SHA-256、包內 exe 與已測 exe 的位元組一致性檢查通過，頂層只有 exe、`_internal`、`models`、`licenses`、使用說明。SHA-256：`4978fd5cdb74d143a5145e5cdd002ccdf6541f2ce70cf1d3f74b6ee8f61410ee`，另存於 ZIP 旁的 `.sha256` 檔。
