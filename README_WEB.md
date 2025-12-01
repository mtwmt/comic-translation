# 漫畫翻譯器 - 網頁版

這是基於原有桌面應用程式開發的網頁版本，採用前後端分離架構。

## 技術棧

### 後端（Backend）

- **FastAPI** - 現代化的 Python Web 框架
- **Pydantic** - 資料驗證和設定管理
- **Gemini AI** - Google 的 AI 圖片翻譯引擎

### 前端（Frontend）

- **React 19.2** - 使用 Vite 6 建構（最新穩定版）
- **TypeScript** - 型別安全
- **TailwindCSS** - Utility-first CSS 框架
- **DaisyUI** - UI 元件庫（高質感預設樣式）
- **Zustand** - 輕量級全域狀態管理
- **React 19 新特性**:
  - Actions - 用於表單提交和資料變更
  - useActionState - 自動處理表單狀態
  - useOptimistic - 樂觀更新（即時反饋）
  - use API - 條件式讀取 Promise 和 Context

## 專案結構

```
comic-translation/
├── backend/                   # 後端 API (FastAPI)
│   ├── api/
│   │   ├── core/             # 核心配置
│   │   ├── schemas/          # Pydantic Schema
│   │   ├── services/         # 業務邏輯
│   │   ├── routers/          # API 路由
│   │   └── main.py
│   └── requirements.txt
│
├── frontend/                  # 前端應用 (React 19 + TypeScript)
│   ├── src/
│   │   ├── pages/            # 頁面模組 (Colocation 架構)
│   │   │   ├── HomePage/
│   │   │   │   ├── HomePage.tsx
│   │   │   │   ├── image-upload/
│   │   │   │   │   ├── ImageUploader.tsx
│   │   │   │   │   ├── useImageUpload.ts
│   │   │   │   │   ├── upload.types.ts
│   │   │   │   │   └── index.ts
│   │   │   │   ├── translation/
│   │   │   │   │   ├── TranslationResult.tsx
│   │   │   │   │   ├── useTranslation.ts
│   │   │   │   │   ├── translationApi.ts
│   │   │   │   │   ├── translation.types.ts
│   │   │   │   │   └── index.ts
│   │   │   │   └── index.ts
│   │   │   └── SettingsPage/
│   │   │       ├── SettingsPage.tsx
│   │   │       ├── SettingsForm.tsx
│   │   │       ├── useSettings.ts
│   │   │       ├── settingsStore.ts
│   │   │       ├── settings.types.ts
│   │   │       └── index.ts
│   │   ├── shared/
│   │   │   ├── components/
│   │   │   │   ├── ui/       # Button, Input, Card
│   │   │   │   └── layout/   # MainLayout, Header
│   │   │   ├── hooks/        # useToast
│   │   │   ├── utils/        # validators, fileHelpers
│   │   │   └── constants/    # config
│   │   ├── api/              # API 客戶端
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── .env.example
│   ├── package.json
│   └── vite.config.ts
│
└── src/                       # 原有的 Python 模組
```

## 安裝與執行

### 1. 安裝後端依賴

```bash
cd backend
pip install -r requirements.txt
```

### 2. 設定環境變數

建立 `.env` 檔案：

```env
GEMINI_API_KEY=your_api_key_here
```

### 3. 啟動後端 API

```bash
cd backend/api
python main.py
```

或使用 uvicorn：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

後端 API 會在 http://localhost:8000 啟動

### 4. 安裝前端依賴

```bash
cd frontend
npm install
```

### 5. 啟動前端開發伺服器

```bash
npm run dev
```

前端應用會在 http://localhost:5173 啟動

## 使用方式

1. 開啟瀏覽器訪問 http://localhost:5173
2. 首次使用先進入「設定」頁面輸入 Gemini API Key
3. 在首頁拖曳或選擇圖片檔案進行翻譯
4. 下載翻譯結果

## API 文件

啟動後端後，可訪問：

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## 最佳實踐特點

### 後端

- ✅ 依賴注入（Dependency Injection）
- ✅ 分層架構（Routers → Services → Core）
- ✅ Pydantic 資料驗證
- ✅ 環境變數管理
- ✅ CORS 和安全性設定
- ✅ 生命週期管理（Lifespan）
- ✅ 工廠模式（Factory Pattern）

### 前端

- ✅ **Colocation 架構**（頁面相關代碼集中，易於維護）
- ✅ React 19 最新特性（Actions, useActionState, useOptimistic）
- ✅ Functional Components + Hooks
- ✅ Form Actions 簡化表單處理
- ✅ Zustand 全域狀態管理
- ✅ TailwindCSS + DaisyUI 現代化 UI
- ✅ TypeScript 強型別開發
- ✅ Vite 6 極速開發體驗
- ✅ 錯誤處理機制（ErrorBoundary + Toast）
- ✅ 模組化 API 客戶端（Axios）

## 開發注意事項

### 後端

- 使用 `@lru_cache` 實現單例模式
- 所有 Schema 使用 Pydantic BaseModel
- 路由使用 APIRouter 模組化
- 服務層封裝業務邏輯

### 前端

#### Colocation 架構原則

- **就近放置**：相關的代碼放在同一個頁面資料夾內（Components + Hooks + Types + API）
- **頁面自包含**：每個頁面包含該頁面專用的所有檔案
- **共用資源分離**：只有真正多個頁面使用的才放 `shared/`
- **模組匯出**：每個頁面使用 `index.ts` 統一匯出
- **類似 Angular Module**：每個頁面資料夾就像一個 Angular Feature Module

#### React 19 最佳實踐

- 使用 React 19 Form Actions 處理表單
- 優先使用 `useActionState` 而非手動管理 loading/error 狀態
- 使用 `useOptimistic` 提供即時反饋
- 狀態管理優先級：**Local State > Zustand > Context**

#### 代碼組織

- **元件與 Hook 共置**：相關的 Hook 放在同一個頁面資料夾內
- **型別定義完整**：每個頁面定義自己專用的型別
- **API 層封裝**：統一的錯誤處理和請求配置
- 樣式優先使用 Tailwind Utility Classes
- **Colocation 原則**：把一起改變的東西放在一起

#### 檔案命名規範

- 元件：`PascalCase.tsx` (如 `ImageUploader.tsx`)
- Hooks：`camelCase.ts` 且以 `use` 開頭 (如 `useImageUpload.ts`)
- 型別：`camelCase.types.ts` (如 `upload.types.ts`)
- API：`camelCase.ts` 且以 `Api` 結尾 (如 `translationApi.ts`)

## 生產部署

### 後端

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 前端

```bash
npm run build
# 輸出在 dist/ 目錄
```

## 授權

與原專案相同
