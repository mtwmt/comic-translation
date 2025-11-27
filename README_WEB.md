# 漫畫翻譯器 - 網頁版

這是基於原有桌面應用程式開發的網頁版本，採用前後端分離架構。

## 技術棧

### 後端（Backend）
- **FastAPI** - 現代化的 Python Web 框架
- **Pydantic** - 資料驗證和設定管理
- **Gemini AI** - Google 的 AI 圖片翻譯引擎

### 前端（Frontend）
- **Angular 17+** - 使用 Standalone Components
- **TypeScript** - 型別安全
- **RxJS** - 反應式程式設計
- **Signals** - Angular 最新的狀態管理

## 專案結構

```
comic-translation/
├── backend/                    # 後端 API
│   ├── api/
│   │   ├── core/              # 核心配置
│   │   │   ├── config.py      # 環境變數和設定
│   │   │   └── __init__.py
│   │   ├── schemas/           # Pydantic Schema
│   │   │   ├── translation.py # 翻譯相關資料模型
│   │   │   └── __init__.py
│   │   ├── services/          # 業務邏輯層
│   │   │   ├── translation_service.py  # 翻譯服務
│   │   │   └── __init__.py
│   │   ├── routers/           # API 路由
│   │   │   ├── translation.py # 翻譯路由
│   │   │   └── __init__.py
│   │   └── main.py            # FastAPI 應用程式進入點
│   └── requirements.txt       # Python 依賴
│
├── frontend/                   # 前端應用
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/          # 核心模組
│   │   │   │   ├── models/    # TypeScript 資料模型
│   │   │   │   ├── services/  # 共用服務
│   │   │   │   │   ├── api.service.ts     # API 呼叫
│   │   │   │   │   └── config.service.ts  # 配置管理
│   │   │   │   └── interceptors/  # HTTP 攔截器
│   │   │   ├── features/      # 功能模組
│   │   │   │   ├── translator/  # 翻譯器頁面
│   │   │   │   └── settings/    # 設定頁面
│   │   │   ├── app.component.ts
│   │   │   ├── app.config.ts
│   │   │   └── app.routes.ts
│   │   ├── environments/      # 環境配置
│   │   ├── main.ts
│   │   └── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── angular.json
│
└── src/                        # 原有的 Python 模組
    └── ai_engine.py           # AI 引擎（後端會使用）
```

## 安裝與執行

### 1. 安裝後端依賴

```bash
cd backend
pip install -r requirements.txt
```

### 2. 設定環境變數

建立 `.env` 檔案（可選，也可透過網頁介面設定）：

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
npm start
```

前端應用會在 http://localhost:4200 啟動

## 使用方式

1. 開啟瀏覽器訪問 http://localhost:4200
2. 首次使用先進入「設定」頁面
3. 輸入 Gemini API Key
4. （可選）設定人名對照表和全域指示
5. 返回「翻譯器」頁面
6. 拖曳或選擇圖片檔案
7. 等待翻譯完成後下載結果

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
- ✅ Standalone Components（Angular 最新架構）
- ✅ Signals 狀態管理
- ✅ 依賴注入（使用 inject()）
- ✅ Reactive Forms
- ✅ 路徑別名（Path Aliases）
- ✅ Lazy Loading
- ✅ HTTP 攔截器
- ✅ 型別安全（TypeScript）

## 開發注意事項

### 後端
- 使用 `@lru_cache` 實現單例模式
- 所有 Schema 使用 Pydantic BaseModel
- 路由使用 APIRouter 模組化
- 服務層封裝業務邏輯

### 前端
- 使用 Signal 而非傳統的 Observable（性能更好）
- 組件全部使用 Standalone 模式
- 使用 `inject()` 取代構造函數注入
- 遵循 Angular Style Guide

## 生產部署

### 後端
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 前端
```bash
npm run build
# 輸出在 dist/comic-translator
```

## 授權

與原專案相同
