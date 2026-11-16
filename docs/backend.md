# 後端 API 說明

啟動方式與目錄介紹請見專案 README。後端使用 FastAPI、Pydantic 與 SQLAlchemy，資料保存在 SQLite。

## API

所有帶內容的 POST 使用 `Content-Type: application/json`。建立占卜後取得 `accessToken`，往後讀取、抽牌、解讀都必須加上 `Authorization: Bearer <accessToken>`。請妥善保存此憑證，持有人可以讀取問題與結果。前端不得記錄或外傳憑證。

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 確認服務正常 |
| GET | `/api/spreads` | 牌陣名稱、說明及三個牌位定義 |
| POST | `/api/readings` | 自填問題、選牌陣、洗牌 |
| GET | `/api/readings/{id}` | 恢復目前進度與已完成解讀 |
| POST | `/api/readings/{id}/draw` | 一次抽一張，共三張 |
| POST | `/api/readings/{id}/shuffle` | 手勢洗牌完成後，重新隨機排列牌組 |
| POST | `/api/readings/{id}/interpretation` | 三張抽齊後取得個人化解讀，無需 body |
| GET | `/cards/rider-waite-smith/{cardId}.jpg` | 顯示牌面 |

### 建立占卜

```json
{
  "question": "我最近考慮轉職，接下來三個月如何準備？",
  "spreadId": "situation-obstacle-advice"
}
```

回傳 201：

```json
{
  "id": "占卜 UUID",
  "accessToken": "僅建立時回傳，請保存",
  "question": "我最近考慮轉職，接下來三個月如何準備？",
  "options": null,
  "spread": {
    "id": "situation-obstacle-advice",
    "name": "現況／阻礙／建議",
    "description": "適合釐清困境，以及思考下一步。",
    "positions": [
      { "id": "situation", "label": "現況", "meaning": "問題目前的狀態" },
      { "id": "obstacle", "label": "阻礙", "meaning": "可能需要面對的阻力或盲點" },
      { "id": "advice", "label": "建議", "meaning": "使用者可以考慮的具體行動" }
    ]
  },
  "status": "drawing",
  "deckSize": 78,
  "drawnCount": 0,
  "remainingDraws": 3,
  "selectedPositions": [],
  "cards": [],
  "interpretation": null,
  "createdAt": "ISO 8601 UTC 時間"
}
```

問題為使用者自由輸入，去除頭尾空白後限制 1–100 個 Unicode 碼點（一般中文字、標點、空白各算一字；部分組合 emoji 可能算多字）。牌陣可選：

| spreadId | 三個牌位 | 建議用途 |
| --- | --- | --- |
| `past-present-future` | 過去／現在／未來 | 理解背景、現況與可能趨勢 |
| `situation-obstacle-advice` | 現況／阻礙／建議 | 釐清困境並探索下一步 |
| `situation-action-outcome` | 現況／行動／可能結果 | 思考行動可能帶來的發展 |
| `choice-comparison` | 選項 A／選項 B／建議 | 比較兩個明確選擇 |

比較牌陣另需 `"options": {"a": "留任", "b": "轉職"}`，每個選項最多 300 個 Unicode 碼點。其他牌陣不接受 options。

三張牌的位置意義可以有不同組合，沒有唯一固定形式。前三種的組合可參考 [Labyrinthos](https://labyrinthos.co/blogs/learn-tarot-with-labyrinthos-academy/3-card-tarot-spreads-simple-tarot-spreads-organized-by-layout) 及 [Biddy Tarot](https://biddytarot.com/blog/easy-three-card-tarot-spreads/)；此專案的說明文字為自行撰寫，選項比較是產品提供的另一種讀法。未來／結果以可能發展解讀，不視為確定預言。

### 逐張抽牌

前端先讓使用者以手指、滑鼠或觸控板按住拖曳混牌，完成後呼叫 `POST /api/readings/{id}/shuffle`（需 Bearer 憑證，不需 body）。後端重新產生完整牌序與正逆位，回傳不含牌序的占卜進度。手勢不作為唯一亂數來源，以確保抽牌隨機。已抽出任何一張牌後不能重洗，回傳 409 `SHUFFLE_LOCKED`；洗牌不呼叫 AI。原有客戶端仍可直接使用建立占卜時已隨機產生的牌組抽牌。

第一張：

```json
{ "position": 12, "drawIndex": 0 }
```

第二張：

```json
{ "position": 45, "drawIndex": 1 }
```

第三張：

```json
{ "position": 7, "drawIndex": 2 }
```

`position` 是最初洗牌後牌背的固定位置 0–77，`drawIndex` 是這次要抽第幾張（0–2）。前端抽掉牌後不可重新編號剩餘位置。點選順序決定牌陣位置。

每次回傳完整占卜進度，`cards` 只包含已揭露的牌；每張包含 `cardId`、`nameZh`、`nameEn`、`image`、`orientation`（`upright`／`reversed`）、`deckPosition` 及 `position`（牌位定義）。未抽中的牌序不會傳給前端。

相同 drawIndex 與 position 的重試會取得原結果，不會多抽一張。已完成的 drawIndex 改選其他位置、重複選已抽位置或跳號會得到 409。三張抽齊後狀態變為 `drawn`。

建立時以 `crypto.randomInt` 進行 Fisher–Yates 洗牌，所有 78 張牌均不重複；每張以獨立亂數決定正逆位，各 50%。不使用問題、時間或模型結果決定牌序。牌序建立後固定，使用者每次選牌時揭露該位置已確定的牌。重新整理或重送請求不會重新洗牌；要重新占卜請建立新的 reading。

### 解讀

可選的 `GEMINI_FALLBACK_MODEL` 使用同一把金鑰；建議先在 AI Studio 確認專案為 Free tier、備援模型有免費額度，再設定 `gemini-3.1-flash-lite`。程式不會檢查或變更 Google 帳戶計費層級，付費專案仍可能計費。未設定、留空或與主模型相同時不使用備援。

主模型暫時無法使用（包括連線失敗／逾時），延遲重試一次後仍失敗，第三次呼叫改用備援；所有呼叫、格式修復與等待合計最多三次且共用 45 秒。啟用備援時前兩次各以 13 秒為限，替備援保留時間。金鑰、設定、額度錯誤及安全拒絕不觸發切換。備援仍使用原問題與牌組並驗證結果；日誌僅記錄切換模型，不記錄問題或金鑰。

三張抽完後呼叫解讀 API。後端從資料庫取得原問題、選項、牌陣與實際抽牌，不接受前端指定牌面。使用 Gemini generateContent API 的 [Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output)，並另外驗證三張牌 ID、牌位及順序。

成功回傳完整占卜，狀態為 `completed`，`interpretation` 結構如下：

```json
{
  "summary": "綜合問題與三張牌的整體解讀",
  "cards": [
    { "positionId": "situation", "cardId": "實際第一張牌 ID", "interpretation": "第一個牌位的個人化解讀" },
    { "positionId": "obstacle", "cardId": "實際第二張牌 ID", "interpretation": "第二個牌位的個人化解讀" },
    { "positionId": "advice", "cardId": "實際第三張牌 ID", "interpretation": "第三個牌位的個人化解讀" }
  ],
  "advice": ["具體建議一", "具體建議二", "具體建議三"],
  "reflection": "值得思考的一個問題"
}
```

成功結果保存在 SQLite，重送會回傳原結果；同一服務程序中，同一筆占卜的並行解讀會合併為一次模型請求。失敗結果不快取，可重試。模型回應逾時設定為 45 秒，並採用 LOW 思考等級降低延遲，建立連線上限 10 秒。模型端已完成但本地尚未存檔就中斷服務時，重試仍可能重新呼叫模型，不保證跨故障的計費恰好一次。

## 錯誤與範圍

問題超過 100 字回傳 400 `QUESTION_TOO_LONG` 與警告文字，不建立占卜，也不自動截斷。前端之後應顯示字數與此錯誤訊息。此限制在去除頭尾空白後計算，前端可用 `Array.from(question.trim()).length` 對齊。

解讀 prompt 獨立放在 `app/prompts/tarot.txt`。要求專業、客觀、個人化地連結問題、牌義、正逆位與牌位，綜合三張牌的關係；不以空泛安慰或捏造背景補足內容。摘要 150–250 字、每張 200–300 字、3–5 項建議是內容深度指引，不是回應成功的字數門檻。後端接受非空白且格式正確的回覆，不會因摘要未滿 80 字或逐牌解讀未滿 120 字而失敗。建議可為 1–5 項。

若模型回覆格式不完整、牌面／牌位不符、欄位空白或生成未完成，後端會用相同問題與原三張牌自動重試一次；遇到上游 500／502／503／504 時，會延遲約 2–3 秒、5–6 秒重試。格式修復最多一次，所有重試合計最多三次模型請求，共用 45 秒的總等待上限。有效的較短回覆不會觸發重試。金鑰、額度或安全拒絕不會反覆重試。重試仍失敗或服務無法連線時，前端會保留牌面並提示稍後再試，不會偽造解讀或重新抽牌。自動重試可能額外使用 API 額度。

`.gitignore` 忽略 `.env` 與其他私密環境設定（保留 `.env.example`）、資料庫、`storage/`、套件與日誌。若未來檔案已被 Git 追蹤，新增忽略規則不會自動解除追蹤；目前此資料夾尚未初始化 Git。

錯誤統一回傳 `{"error":{"code":"DRAW_REQUIRED","message":"請先依序抽完三張牌。"}}`。

- 400：輸入、牌陣、抽牌位置或 JSON 不正確。
- 404：找不到資源，或占卜憑證缺少／不正確。
- 409：抽牌順序、位置衝突，或尚未抽齊三張。
- 413／415：請求過大／不是 JSON。
- 422：模型拒絕解讀。
- 502：模型連線、格式或生成失敗。
- 503：尚未設定模型金鑰與名稱。

模型呼叫失敗時，容器日誌只記錄 Gemini 的 HTTP 狀態、標準錯誤代碼與模型名稱，不記錄金鑰、使用者問題或完整回應。可用 `docker compose -f docker-compose.server.yml logs --since 10m backend` 排查。HTTP 429 表示額度／限流；5xx 表示上游忙碌或服務故障；400／404 會回傳 `AI_CONFIG_ERROR`，需管理者確認設定。無法僅憑前端通用訊息判定是否多人同時使用。

目前為本機開發版本，預設僅監聽 127.0.0.1。前端可透過同源代理連接 `/api` 與 `/cards`，目前不開放跨來源 CORS。尚未包含會員、公開部署的流量／費用限制、資料刪除與保留期限；公開上線前需補齊。只支援單一服務程序，共用資料庫的多程序並行解讀鎖不在本版範圍內。

問題與解讀保存在本機資料庫。只有要求解讀時，問題、選項與三張牌會送往 Google Gemini；請在正式前端說明此資料處理方式。本次測試未呼叫真實付費模型，實際品質及帳戶模型相容性需填入設定後驗證。






