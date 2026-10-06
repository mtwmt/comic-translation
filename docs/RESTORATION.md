# 本機清字與排版

更新：2026-10-07。GUI 的修訂、補漏字、字級與保存操作見 [GUI 操作指南](GUI_GUIDE.md)。本頁只說明本機模型與合成規則。

## 模型與 CLI

```bash
.venv/bin/python offline.py prepare-models
.venv/bin/python offline.py prepare-restoration
.venv/bin/python offline.py analyze input/page.png --report offline-runs/page-analysis.json
.venv/bin/python offline.py review offline-runs/page-analysis.json
```

`prepare-models` 準備文字偵測與 manga-ocr，並下載 Noto 繁中粗體字型（SHA-256 驗證）；`prepare-restoration` 準備 Comic Text Detector ONNX 與 LaMa TorchScript（合計約 300 MB），存於 `models/restoration/`。來源、大小及 SHA-256 固定在 `src/offline/restoration.py`，推論不下載模型。

`analyze` 需要辨識與修補模型，只產生可編輯報告，不呼叫雲端翻譯。`review` 載入報告，預覽不寫檔；「儲存成品」才另存 PNG／遮罩／JSON，只有「翻譯此區」會呼叫所選翻譯引擎。分析報告沒有批次輸出目錄時，修訂檔案存於報告旁；批次報告沿用已記錄的成品／工作目錄。

GUI 與 CLI 的圖片處理統一使用 CTD 遮罩及 LaMa 局部修補管線，翻譯與分析都需要辨識、修補模型。已移除 `--restoration` 選項與舊白底管線；缺少或損壞的模型會報錯，請執行對應的準備指令。現行管線仍會依背景選擇純色填色或局部補畫。管線版本為 `comic-prototype-6`，先前版本的批次需重新建立；既有成品可保留並查看。

## 合成規則

- CTD 文字區塊、文字行及字形遮罩共同建立區域，保護長框線。安全排版範圍與清字遮罩分開。
- 純色背景填色；複雜背景以 LaMa 做局部裁切修補，推論最長邊上限 768，再映回原尺寸。LaMa 是推測背景，必須目視檢查。
- 先確認譯文能排入範圍，再清字；失敗保留該區原文。每區從原圖產生結果，只合成清字與繪字遮罩，重疊拒絕後一區。
- 對話框外的大字由補漏偵測補上（見 [GUI 操作指南](GUI_GUIDE.md#補漏偵測)）；報告的區域帶 `recovered`，並可含 `ocr_primary`／`ocr_alternatives`（其他辨識結果，翻譯時一併附上）。
- 清字前景周圍（遮罩外環）幾乎全白、只有少量框線／網點雜點時，用白色填平，不呼叫 LaMa；周圍有圖案或灰階時才補畫。
- 修改遮罩外逐像素保留，來源按 EXIF 正規化；保存前再確認來源雜湊。未完成任何貼字時只保存報告。

## 字型與字級

macOS 自動選用蘋方－繁 Semibold，Windows 選用微軟正黑體 Bold；缺字時使用 `assets/fonts/NotoSansCJKtc-Bold.otf`（不存在 git，由 `prepare-models` 下載；來源、SHA-256 與授權見同目錄 README／OFL）。TTC 按家族／字重選字面，缺字用該字型補上。

排版版本 `mask-lettering-5` 優先從原圖深色筆畫估計每區字級，排除框線、裁切筆畫與雜點；白字黑底反向分析。可靠估計保留原圖大小差異，估計不足時採同頁備用基準。手動字級優先，先換行／換欄再縮字，過度縮小標記待確認。

詞語換欄使用本機 jieba，固定角色譯名不拆開；明確換行可指定欄界。直排處理成組標點、波浪號及句尾符號，仍需核對長句與可讀性。

## 限制

遮罩外保真不代表遮罩內修補正確，也不代表 OCR／翻譯語意正確。漏偵測、藝術字、相連氣泡、振假名與長對白仍可能出錯。手動框選及白底加強可局部補救；實圖證據與未驗收範圍見 [VALIDATION](VALIDATION.md)。

模型來源：[Comic Text Detector](https://github.com/dmMaze/comic-text-detector)、[CTD 權重](https://github.com/zyddnys/manga-image-translator/releases/tag/beta-0.2.1)、[LaMa](https://github.com/advimman/lama)、[TorchScript 權重](https://github.com/enesmsahin/simple-lama-inpainting/releases/tag/v0.1.0)。推論介面自行實作，權重的發行授權整理仍待完成。
