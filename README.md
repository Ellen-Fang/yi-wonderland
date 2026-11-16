# 翊想樂園 · YI WONDERLAND

一座橘黃色的塔羅小樂園。帶著一個放在心上的問題，用自己的節奏洗牌、選出三張牌，收下一份屬於這次旅程的指引。

前端採用原生 HTML、CSS 與 JavaScript，後端使用 FastAPI，透過 Gemini 產生個人化解讀。占卜進度與結果存放在 SQLite，可用 Docker Compose 與 Caddy 啟動整個網站。

## 功能

- 自由輸入問題，限制 100 字並提示超限。
- 四種三張牌陣：過去／現在／未來、現況／阻礙／建議、現況／行動／可能結果、選項 A／選項 B／建議。
- 手勢洗牌：手機以手指滑動，電腦按住觸控板或滑鼠拖曳，也支援方向鍵操作。
- 逐張抽牌，顯示正逆位；後端以安全亂數產生牌序，不受問題內容影響。
- 解讀包含整體分析、逐張牌義、具體建議與反思問題。
- 同分頁重新整理可恢復進度，解讀失敗可保留原牌重試。
- 電腦與手機版面，以及列印／另存 PDF 樣式。

## 專案架構

```text
yi-wonderland/
├── frontend/                   # 所有前端檔案
│   ├── index.html              # 首頁、表單、洗牌與結果畫面
│   ├── styles.css              # 網站樣式與響應式版面
│   ├── shuffle.css             # 手勢洗牌桌樣式
│   ├── app.js                  # 前端互動與 API 串接
│   └── assets/                 # 自製摩天輪、遊樂園背景與牌背
├── app/
│   ├── main.py                 # FastAPI 入口、生命週期與 CORS
│   ├── config.py               # 環境設定
│   ├── errors.py               # 統一 API 錯誤
│   ├── models/reading.py       # SQLAlchemy 資料表映射
│   ├── crud/reading.py         # 占卜資料讀寫
│   ├── db/session.py           # SQLite 連線管理
│   ├── schemas/reading.py      # Pydantic 輸入與回應驗證
│   ├── routers/readings.py     # API 路由
│   ├── services/
│   │   ├── tarot.py            # 隨機洗牌與抽牌規則
│   │   └── interpreter.py      # Gemini 串接與解讀驗證
│   ├── prompts/tarot.txt       # 塔羅解讀 prompt
│   └── tests/                  # API 與核心邏輯測試
├── data/                       # 78 張牌與四種牌陣資料
├── public/cards/               # 偉特塔羅牌面
├── scripts/                    # 啟動、牌圖下載與手動 AI 檢查工具
├── docs/backend.md             # API 使用說明
├── storage/                    # SQLite 資料，不提交 Git
├── .env.example                # 可提交的設定範本
├── .gitignore
├── .dockerignore
├── Caddyfile                   # 前端靜態檔案與後端反向代理
├── Dockerfile                  # FastAPI 映像檔
├── docker-compose.yml          # FastAPI + Caddy
├── requirements.txt
└── requirements-dev.txt
```

想了解程式流程，可以從 `schemas/reading.py`、`routers/readings.py` 開始，再看 `services/` 與 `crud/`。前端細節見 [前端說明](frontend/README.md)。

## 環境設定

將 `.env.example` 複製為 `.env`，已有設定時不要覆蓋。從 [Google AI Studio](https://aistudio.google.com/apikey) 建立 API 金鑰，填入：

```dotenv
GEMINI_API_KEY=填入你的金鑰
GEMINI_MODEL=gemini-3.5-flash-lite
```

範本採用 Flash-Lite；模型須支援結構化 JSON 輸出，實際權限、額度與費用依 Google 帳戶及模型而定。未設定金鑰仍能建立占卜與抽牌，要求解讀時才會提示缺少設定。

| 變數 | 範本值 | 用途 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 空白 | Gemini API 金鑰，只放後端 |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | 解讀使用的模型 |
| `HOST` | `127.0.0.1` | Windows 啟動腳本的監聽位址 |
| `PORT` | `3000` | 啟動腳本的服務埠／Docker 後端主機埠 |
| `WEB_PORT` | `8080` | Docker Caddy 的主機埠 |
| `CORS_ORIGINS` | 空白 | 額外允許的前端來源，以逗號分隔；同源部署不需設定 |
| `DATABASE_URL` | 未設定 | 本機預設使用 `storage/readings.sqlite`；Compose 會指定容器內路徑 |

## Docker 啟動（Linux／Windows）

需要 Docker Engine 與 Compose plugin；Windows 可使用 Docker Desktop 的 Linux containers。

Linux 首次取得專案：

```bash
git clone https://github.com/Ellen-Fang/yi-wonderland.git
cd yi-wonderland
cp .env.example .env
```

編輯 `.env` 填入金鑰後，在專案根目錄啟動：

```bash
docker compose up --build -d
docker compose ps
```

- 網站（經 Caddy）：[http://127.0.0.1:8080/](http://127.0.0.1:8080/)
- API 文件：[http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs)
- 健康檢查：[http://127.0.0.1:8080/api/health](http://127.0.0.1:8080/api/health)
- 後端直連：[http://127.0.0.1:3000/](http://127.0.0.1:3000/)

Windows 首次設定可用 `Copy-Item .env.example .env`，其餘 Docker 指令相同。私人儲存庫需要先取得 GitHub 存取權限才能 clone。

常用指令：

```bash
docker compose logs -f backend caddy
docker compose restart backend
docker compose down
```

修改 `.env` 的金鑰或模型後，用以下指令重新建立後端容器，讓新環境設定生效：

```bash
docker compose up -d --force-recreate backend
```

更新程式後執行 `git pull`，再執行 `docker compose up --build -d`。

### Caddy 與對外存取

```text
瀏覽器 → Caddy :8080
           ├── /api/*、/cards/*、/docs → FastAPI :8000
           └── 其他路徑              → frontend/
```

目前 Compose 只綁定主機的 `127.0.0.1`，同網路的其他電腦也不能直接存取。部署在遠端 Linux 時，可先用 SSH tunnel 從自己的電腦預覽：

```bash
ssh -L 8080:127.0.0.1:8080 USER@SERVER_IP
```

再用本機瀏覽器開啟 `http://127.0.0.1:8080/`。`USER`、`SERVER_IP` 請替換成 Linux 帳號與位址。公開網域、HTTPS、對外埠與防火牆需依部署環境另外配置；目前沒有自動公開網站。

### 資料保存

SQLite 由 `./storage` 掛載到容器的 `/code/storage`。停止或重建容器後，占卜資料仍保存在主機，不需另外啟動資料庫服務。請勿刪除 `storage/`；備份資料庫時應使用 SQLite 備份工具，或停止後端後複製完整資料庫檔案。

### 單獨建置後端映像檔

```bash
docker build -t yi-wonderland:latest .
```

此映像檔包含 FastAPI、前端與牌圖；Caddy 使用 Compose 中的官方映像檔。`.env`、資料庫及本機測試環境不會包入映像檔。

## 本機開發（不使用 Docker）

建議使用 Python 3.12。前端不需 npm 安裝或編譯，由 FastAPI 一起提供。

Windows PowerShell：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
# 僅在沒有 .env 時執行下一行，再填入金鑰
Copy-Item .env.example .env
./scripts/start.ps1 -Reload
```

Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
# 僅在沒有 .env 時執行下一行，再填入金鑰
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 3000 --reload
```

網站在 `http://127.0.0.1:3000/`，API 文件在 `/docs`。直接執行 uvicorn 時，監聽位址及埠由命令列參數決定。不要直接以檔案方式開啟前端 HTML，因為抽牌功能需要後端。

## API

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 健康檢查 |
| GET | `/api/spreads` | 取得牌陣及牌位說明 |
| POST | `/api/readings` | 自填問題、選牌陣、建立占卜 |
| GET | `/api/readings/{id}` | 恢復進度或讀取結果 |
| POST | `/api/readings/{id}/shuffle` | 手勢洗牌結束後重新隨機排列 |
| POST | `/api/readings/{id}/draw` | 依序抽出第一、第二、第三張 |
| POST | `/api/readings/{id}/interpretation` | 產生並保存解讀 |

建立占卜後會取得 `id` 與 `accessToken`，後續讀取、洗牌、抽牌、解讀需帶上 `Authorization: Bearer <accessToken>`。前端只暫存本次占卜憑證，不包含 Gemini 金鑰。請求範例與錯誤格式見 [API 說明](docs/backend.md)。

實際牌序由 Python `secrets` 與 Fisher–Yates 洗牌決定，每張牌正逆位各 50%。手勢控制視覺混牌，按下完成時才要求後端重新洗牌；抽出任何一張後不能重洗。成功解讀會保存，重複請求沿用已完成結果。

## 測試

安裝 `requirements-dev.txt` 後執行：

```bash
python -m pytest -q
```

涵蓋輸入驗證、洗牌、逐張抽牌、重送與並行請求、資料保存、前端資產與 Gemini 回應處理。測試使用暫存資料庫及模擬模型，不會產生 API 費用。

需要真實驗證金鑰、模型與完整解讀時，先啟動本機服務，再手動執行：

```bash
python scripts/check_ai.py
```

這個檢查會建立測試占卜並使用 Gemini API 額度，輸出不包含金鑰；一般測試不會自動執行它。

## Git 與資料處理

`.gitignore` 已排除 `.env`、`storage/`、SQLite 資料檔、虛擬環境、日誌及本機備份。`.env.example` 可以提交，真正的金鑰應分別在開發機與部署機設定。已被 Git 追蹤的檔案不會因新增忽略規則而自動取消追蹤。

問題、牌序、抽牌與解讀保存在服務端 SQLite。只有要求解讀時，問題、選項與三張牌會送至 Google Gemini。請勿將真實使用者的問題、存取憑證或資料庫提交到儲存庫。

本版採單一服務程序；Docker 已固定一個 worker，不支援多程序之間的解讀鎖。公開上線前仍需補上流量與費用限制、資料保留／刪除機制與部署環境設定。塔羅解讀作為探索與反思的參考，不是確定的預言，也不能取代專業判斷。

## 圖像來源

- 遊樂園插畫、摩天輪標誌與牌背：本專案自製 SVG，集中於 `frontend/assets/`。
- 78 張偉特牌面：來自 Wikimedia Commons 的 [TaionWC 完整牌組](https://commons.wikimedia.org/wiki/Category:Rider-Waite-Smith_tarot_deck_(TaionWC))，包含 22 張大阿爾克那與 56 張小阿爾克那。
- 原畫作者為 Pamela Colman Smith；來源資料標記掃描出處 muzendo.jp、上傳者 TaionWC，每張牌的 Commons 資料標示 Public domain。
- 每張圖片的來源、授權標記與 SHA-256 保存在 `data/cards.json`，下載時的原始資料保存在 `commons-deck.json`。下載腳本為 `scripts/download-deck.ps1`。

圖片來源說明僅適用於對應圖片；本專案目前尚未替程式碼指定開源授權。
