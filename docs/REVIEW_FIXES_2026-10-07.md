# 修改報告:comic-translation code review 後續修復

## 背景與審查範圍

- 倉庫:`D:\comic-translation`,分支 `master`,**全部未 commit**。
- 注意:在這批修改之前,工作目錄已有大量未提交的變更(Windows 平台支援、模型目錄、Fast/思考強度等)。`git diff HEAD` 會同時包含那些既有變更與本次修改,無法用 commit 區分。本次修改只涉及下面列出的檔案與行為。
- 起因:對未提交變更做 code review 得到 10 項發現,使用者要求全部修掉、能收斂就收斂、刪除 legacy code;之後又追加修兩個既有問題(並行寫檔、測試編碼)。
- 只在 Windows 10(Python 3.11,`.venv311`)上執行與驗證,**macOS 完全沒有實測**。

## 驗證結果

指令(系統預設編碼 cp950,未設 `PYTHONUTF8`):

```
COMIC_GUI_TESTS=1 .venv311/Scripts/python.exe -m pytest -q -p no:cacheprovider
```

結果:287 passed, 3 skipped, 0 failed。`tests/test_storage.py` 另外連跑 30 次,0 次失敗(修改前 3 次中有 2 次失敗)。

沒有跑 linter(venv 裡沒有 pyflakes)。

## 逐項修改

### 1. 按「停止」後 GUI 卡在「停止中…」
- `src/platforms/windows.py`:`kill_process_tree` 吞掉 `OSError` 與 `subprocess.TimeoutExpired`(taskkill 5 秒逾時不再往外丟);`terminate` 在 taskkill 之後加 `process.kill()` 再 `communicate()`。
- `src/platforms/windows_worker.py`:`WindowsPipeline.close()` 在 `kill_process_tree` 後加 `process.kill()`。
- `src/gui/worker.py` 的 `finally` 沒有改,靠的是上游不再丟例外。

### 2. Claude Fast 的寫死模型 regex
- `src/offline/claude_provider.py`:刪除 `ClaudeTranslator.__init__` 裡的 regex 檢查與 `import re`。Fast 是否可用只由 CLI 回報、經 `effective_options` 過濾的 capability 決定。
- `tests/test_translators.py`:刪除 `test_unsupported_fast_never_silently_switches_claude_model`。

### 3. 沒勾 Fast 也送覆寫旗標
- `src/offline/codex_provider.py`:只有 `options.get("fast")` 為真才送 `-c service_tier="fast" -c features.fast_mode=true`;不再送 `service_tier="default"` / `fast_mode=false`。
- `src/offline/claude_provider.py`:只有 Fast 為真才送 `--settings {"fastMode": true}`。
- **行為變更**:取消勾選 Fast 現在代表「沿用使用者自己的 Codex 設定」,不再強制關閉。Claude 呼叫本來就帶 `--setting-sources ""`,所以不受影響。
- `tests/test_codex_provider.py`、`tests/test_claude_provider.py`:對應測試改為驗證「關閉時不送任何速度旗標」。

### 4. AGY 設定預檢逾時
- `src/platforms/windows_agy.py`:`CONFIG_ATTEMPTS = 5` / `CONFIG_TIMEOUT = 8` 改為 `CONFIG_TIMEOUTS = (8, 8, 45)`。最壞情況由 40 秒變 61 秒。
- `tests/test_windows_agy.py`、`docs/GUI_GUIDE.md` 已同步。`docs/VALIDATION.md` 裡的舊數字是歷史實測紀錄,沒有改。

### 5. Claude 模型清單查詢失敗時變空
- `src/gui/settings.py`:`_request_model_list` 不再於查詢前清空下拉選單;`show_model_list` 兩條平台分支合併,只有「有結果且無錯誤」才更新選單,失敗時保留原值。
- 沒有恢復靜態 opus/sonnet/haiku 清單,因為 `tests/test_model_catalog.py::test_missing_claude_never_returns_a_fabricated_catalog` 明確禁止虛構目錄。
- macOS 上切換引擎時清單仍會先變空(`cached_model_names` 回傳 `[]`),這是既有測試要求的行為。

### 6. 模型查詢 session 的清理
- `src/offline/model_catalog.py`:`process.stdin.close()` 包 `try/except OSError`;逾時後改為 `kill_process_tree` → `process.kill()` → `process.wait()`(無逾時)。

### 7. Codex 能力解析遇 JSON null
- `src/offline/codex_provider.py`:`supportedReasoningEfforts`、`additionalSpeedTiers`、`serviceTiers` 改用 `or []`;略過 `model` 不是字串或不在 `model_choices` 結果內的列(隱藏或名稱無效的模型不再寫進 capabilities)。

### 8. 全刪區域後輸出與原圖相同的修訂圖 —— **沒有修改**
- `docs/GUI_GUIDE.md` 明文記載「全部區域都刪除時,可明確另存恢復原圖的修訂」,判定為設計行為。`src/offline/review.py` 的 `save_revision` 與 `deleted_region_ids` 維持原樣。

### 9. 校對視窗高 DPI 被裁切
- `src/offline/review_gui.py`:
  - 視窗尺寸改為 `1200 × (920 或 850)` 乘上 `platform_support.window_scale(root)`,並限制在螢幕寬 −40、高 −80 以內。
  - 右側控制欄改放進 `tk.Canvas`,內容高度超過可見高度時才顯示垂直捲軸(`fit_side`)。
  - 五個 `wraplength` 依同一個 scale 縮放。
- 實測:3840×2160、縮放 1.75 下開啟,正常大小無捲軸且「儲存成品」可見;把視窗縮到 500 高後捲軸出現,恢復後消失。
- 限制:捲軸沒有綁滑鼠滾輪;Canvas 包裝在 macOS 也會生效,但 macOS 外觀未驗證。

### 10. Windows 每頁重複運算
- `src/offline/layout.py`:
  - 新增 `ink_components(image)`,回傳 `(gray, labels, stats)`(閾值 225、8 連通)。
  - `complete_character_mask` 多一個可選參數 `components`。
  - `prepare_masked_regions` 多一個可選參數 `refine`;整頁只算一次 `ink_components`,並傳給迴圈內每個區域的 `complete_character_mask`。
- `src/platforms/windows_layout.py`:原本包裝用的 `prepare_masked_regions` 改成 `refine_mask(image, detections, completed)`,只回傳修正後的遮罩。
- `src/offline/pipeline.py`:改為 `prepare_masked_regions(..., refine=getattr(self.region_layout, "refine_mask", None))`。
- 主張:運算序列與修改前逐步相同(complete → refine → complete → find_regions),所以沒有更動 `windows_layout.VERSION` 指紋。這點只由既有測試支撐,沒有新增新舊輸出逐像素比對的測試。

### 追加 A:並行寫 JSON 在 Windows 失敗
- `src/offline/storage.py`:新增 `_replace`,`os.replace` 遇 `PermissionError` 時以 0.01/0.02/0.05/0.1/0.2 秒重試,最後一次失敗才丟出。所有平台都生效。
- `tests/test_storage.py`:模擬的 `simultaneous_replace` 改為每個暫存檔只在第一次呼叫時等 barrier,否則重試會獨自卡在 barrier 上。

### 追加 B:測試依賴 UTF-8 模式
- `tests/` 下六個檔案共 16 處 `.read_text()` 補上 `encoding="utf-8"`(test_agy_integration、test_gui、test_manual_review、test_offline、test_offline_stress、test_restoration)。
- `src/offline/restoration.py`:讀 `manifest.json` 的一處同樣補上。

## 收斂與刪除

- 刪除 `agy_provider.MODEL` 相容別名(`tests/test_agy_provider.py` 改 import `DEFAULT_MODEL as MODEL`)。
- 刪除 `ReviewWindow.delete_manual` 相容入口(`tests/test_review_gui.py` 改呼叫 `delete_region`)。
- `src/offline/translators.py`:`translator_from_settings` 結尾的條件式改為單一呼叫 `create_translator(provider, model, options=options)`。
- 刻意保留:`--restoration legacy` 白底清字流程,以及 `models.py` 中舊 manifest 的字型雜湊;`docs/MAINTENANCE.md` 把兩者列為保留邊界。

## 請特別檢查的風險點

1. **第 10 項的等價性**:`refine` 掛勾與共用 `components` 是否真的與舊的雙層呼叫逐像素相同;若不同,就需要更動 `VERSION` 指紋。
2. **`terminate` 可能阻塞**:taskkill 失敗時只殺掉直接子行程,孫行程若仍握著 pipe,`process.communicate()` 可能卡住。`model_catalog` 的 `process.wait()` 同樣沒有逾時。
3. **Fast 關閉語意改變**(第 3 項):使用者在 Codex config.toml 設了 fast tier 時,GUI 未勾選也會用 fast。
4. **AGY 預檢時間**:預檢每頁至少跑一次(`pipeline.process` 與 `translate` 各呼叫一次 `preflight`),CLI 真的卡死時每次要等 61 秒才暫停批次。
5. **`_replace` 的重試範圍**:只攔 `PermissionError`,且 macOS/POSIX 上真正的權限錯誤會延遲約 0.4 秒。
6. **換行符號**:`tests/test_windows_agy.py`、`test_codex_provider.py`、`test_claude_provider.py`、`test_translators.py` 是用腳本以 LF 重寫的,若原本是 CRLF 則已被改掉(倉庫內兩種並存,未逐一確認)。
7. **macOS**:第 5、9、10 項與追加 A 都會影響 macOS 路徑,全部未實測。
