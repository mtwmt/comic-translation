# 漫畫翻譯器圖示

原創漫畫頁搭配日文「あ」與中文「文」對話泡泡。新版 v2 由內建 imagegen 修改，移除人物、網點及細線，保留大色塊與粗輪廓，方便標題列與工作列的小尺寸辨識。外圍具有透明 alpha；PNG 原圖保留不變，以 Pillow 匯出平台圖示。

| 檔案 | 用途 |
| --- | --- |
| `comic-translator-v2.png` | 新版高解析透明原始圖 |
| `comic-translator-v2.ico` | Windows 視窗與之後封裝的執行檔；包含 16、20、24、28、32、40、48、56、64、128、256 px |
| `comic-translator-v2.icns` | 新版 macOS 應用程式封裝圖示，含最高 1024 px |

Windows 啟動時從程式根目錄的 `assets/icons/comic-translator-v2.ico` 載入圖示，亦作為後續子視窗的預設。ICO 以 Pillow `bitmap_format="bmp"` 匯出，避免這台 Tk 讀取 PNG 編碼的 ICO 時改用系統通用圖示。主視窗另外依 Windows 系統度量載入實際大小的小／大圖示，避免只放大 Tk 的 16／32 px 圖示；載入與釋放依 [Windows LoadImageW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-loadimagew) 規範處理。

之後封裝需將圖示資源納入相同相對目錄，並指定新版執行檔圖示；Tk 視窗圖示設定不會自動修改打包後的執行檔圖示。macOS 目前不改動 Tk 的 Dock 行為，封裝時指定新版 `.icns` 作為應用程式圖示。未帶 `-v2` 的檔案保留作為第一版比較，程式已改用 v2。

## v2 修改提示詞

Use case: precise-object-edit. Edit target: the attached desktop app icon for 漫畫翻譯器. Redesign it for real 16, 24, 28, 32, 40, 48, 56 pixel Windows title bar and taskbar readability, while retaining its recognizable blue Japanese speech bubble, green Chinese speech bubble, and white comic-page motif. Keep the exact glyphs あ and 文, bold white, each centered. Remove the manga character face, halftone dots, speed lines, all tiny details, all gradients, all highlights and bevels, all texture, and all soft shadows. Use just solid flat blue and green bubbles, strong very dark outlines, and a simple upright white comic page behind them with only one thick panel divider. Much bolder silhouette, very large simplified bubbles and minimal page exposure. Both glyphs should fill their bubbles comfortably with broad strokes. Make the page upright and square-on with no rotation or perspective. Clean restrained vector-like icon artwork, one finished app mark centered with about 6 percent transparent margin on all sides. Transparent outer background with real alpha. Crisp hard contours with smooth antialiasing only on actual edges. No surrounding app UI, no frame or mockup, no caption or extra text, no brands or Python logo. Square image. The essential silhouette must remain identifiable when reduced to 16 pixels; avoid intricate detail anywhere.

## 第一版產生提示詞

Use case: logo-brand. Asset type: a finished desktop application icon for a Traditional Chinese manga translation utility named 漫畫翻譯器, to be packaged for Windows and macOS. Create one original polished square icon, 1024 x 1024, centered, with actual transparent outer background. Subject: a simple comic page with two strong panel divisions, combined with two overlapping speech bubbles that communicate translation. One bubble contains a bold simple Japanese あ glyph and the other a bold 文 glyph, each glyph optically centered and clean; no other text. Use a restrained contemporary color treatment, strong silhouette, large bold shapes, simple crisp edges, enough contrast for both light and dark desktop backgrounds. Mild depth is acceptable but predominantly flat and vector-like. The icon should occupy about 85 percent of the square with safe margins. The page and bubbles must remain recognizable at 32 pixels and 16 pixels; prioritize the main shapes, avoid fine panel lines or small decorative details. Front view. A unified app mark, not a screenshot, no Python logo, no existing brands, no device mockup, no caption, no watermark, no external shadows extending beyond safe margins.
