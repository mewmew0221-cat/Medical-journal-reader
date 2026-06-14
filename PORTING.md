# 搬移 / 全新部署清單（PORTING）

把這個專案架到「**另一組帳號**」上（換電腦、或給別人用）的完整步驟。

核心觀念：**程式碼可以照抄，但所有「身分」和「鑰匙」都要換成自己的**——
Sheet、服務帳戶、Gemini 金鑰、GAS、PAT、通關碼，沒有一個能共用。

> 角色提醒：**GitHub Actions** 是真正跑 Python 的「工人」（代替本機）；
> **服務帳戶**只是工人用來刷進 Sheet 的「識別證」，它本身不執行任何東西。

---

## 0. 會用到的帳號／金鑰一覽

| 項目 | 哪裡拿 | 放哪裡 |
|---|---|---|
| Google Sheet（建一張空的） | https://sheets.google.com | 記下 **Sheet ID**（網址中間那段） |
| 服務帳戶 JSON | Google Cloud Console | 本機 `service_account.json` ＋ GitHub secret `GOOGLE_SERVICE_ACCOUNT` |
| Gemini API key | https://aistudio.google.com/apikey | 本機 `.env` ＋ GitHub secret `GEMINI_API_KEY` |
| NCBI API key（可選） | https://account.ncbi.nlm.nih.gov/ | 本機 `.env` ＋ GitHub secret `NCBI_API_KEY` |
| GitHub PAT（fine-grained） | GitHub 帳號設定 | **GAS 指令碼屬性 `GH_PAT`** |
| 通關碼（自訂一組） | 自己想 | **GAS 指令碼屬性 `API_TOKEN`** ＋ 網頁第一次輸入 |

---

## A. Google 端（Sheet ＋ 服務帳戶）

1. 建一張新的 Google Sheet，從網址複製 **Sheet ID**
   （`https://docs.google.com/spreadsheets/d/<這段就是 ID>/edit`）
2. 到 https://console.cloud.google.com/ 建立專案 → 啟用 **Google Sheets API**
3. 建立 **Service Account** → 產生 **JSON 金鑰** → 存成專案根目錄的 `service_account.json`
4. 打開那份 JSON，複製裡面的 `client_email`（長得像 `xxx@xxx.iam.gserviceaccount.com`）
5. 回到你的 Sheet → 右上「共用」→ 把上面那個 email 加進去、權限設「**編輯者**」

> 第一次跑 producer 時會自動在 Sheet 建好 `Collections` / `Articles` / `Jobs` 三張分頁。

---

## B. GitHub 端（repo ＋ secrets ＋ Pages ＋ PAT）

1. 把這個 repo clone / fork 到**自己的 GitHub 帳號**
2. **Settings → Secrets and variables → Actions**，新增 5 個 repository secrets：
   | Secret | 內容 |
   |---|---|
   | `GEMINI_API_KEY` | Gemini 金鑰 |
   | `NCBI_API_KEY` | NCBI 金鑰（可留空字串） |
   | `NCBI_EMAIL` | E-utilities 禮貌性 email（可留空） |
   | `SHEET_ID` | 你的 Sheet ID |
   | `GOOGLE_SERVICE_ACCOUNT` | **整份 `service_account.json` 的內容**（貼 JSON 全文，不是只貼 email） |
3. **Settings → Pages**：來源（Source）設成 **GitHub Actions**（不要選 Deploy from branch）
4. 建 **fine-grained PAT**：https://github.com/settings/personal-access-tokens/new
   - Repository access → Only select repositories → 勾**這個 repo**
   - Permissions → Repository → **Actions：Read and write**（其他都 No access）
   - Generate → **複製 token**（只顯示一次）→ 等下貼進 GAS（見 C-4）

---

## C. GAS 端（貼碼 ＋ 改常數 ＋ 屬性 ＋ 部署 ＋ 外部授權）

1. 到 https://script.google.com 建新專案，把 `gas/Code.gs` 內容整個貼進去
2. **改檔案開頭寫死的常數**（不改會指到別人的資源！）：
   ```js
   const SHEET_ID = '你自己的 Sheet ID';
   const GH_OWNER = '你的 GitHub 帳號';
   const GH_REPO  = '你的 repo 名';
   // GH_WORKFLOW 維持 'run-jobs.yml' 即可
   ```
3. **專案設定 → 指令碼屬性**，新增兩個：
   - `API_TOKEN` = 自訂的通關碼
   - `GH_PAT` = B-4 複製的 PAT
4. **部署 → 新增部署作業 → 類型「網頁應用程式」**
   - 執行身分：**我**；存取權：**任何人**
   - 取得 **/exec 網址**（等下貼進前端，見 D）
5. **跑一次外部授權**（很重要，否則 `run_now` 會拋例外）：
   - 函式下拉選 **`authorizeExternal`** → ▶ 運行
   - 跳授權 → 進階 → 前往專案(不安全) → **允許**（會要「連線至外部服務」權限）
   - 執行日誌印 `{ok=true}` 即成功

> 之後每次「改 GAS 程式碼」要生效，都得 **部署 → 管理部署 → 編輯 → 新版本**（光存檔不算）。

---

## D. 前端

1. 改 `web/app.js` 開頭：
   ```js
   const API = '你 GAS 的 /exec 網址';
   ```
2. `git push` → GitHub Actions 自動把 `web/` 部署到 Pages
3. 你的網址：`https://<你的帳號>.github.io/<repo 名>/`

---

## E. 本機（要在本機手動跑 producer 時才需要）

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
複製 `.env.example` 成 `.env`，填 `GEMINI_API_KEY` / `NCBI_API_KEY` / `NCBI_EMAIL` /
`SHEET_ID` / `GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json`。

---

## ✅ 驗收清單

- [ ] Sheet 已分享給服務帳戶 email（編輯者）
- [ ] GitHub 5 個 secrets 都設了
- [ ] Pages 來源＝GitHub Actions，網址打得開
- [ ] `Code.gs` 的 `SHEET_ID` / `GH_OWNER` / `GH_REPO` 已改成自己的
- [ ] GAS 指令碼屬性 `API_TOKEN` / `GH_PAT` 都設了
- [ ] GAS 已部署成網頁應用程式、拿到 /exec
- [ ] `app.js` 的 `API` 已換成自己的 /exec
- [ ] 跑過 `authorizeExternal` 並看到 `{ok=true}`
- [ ] 在 Actions 手動 Run workflow 一次 → 綠燈（驗證 5 個 secrets）
- [ ] 網頁按「⚡ 立即執行」→ Actions 冒出新 run

全部打勾就完成了。卡關時：去 GitHub **Actions** 看紅燈 log，
或用本機 PowerShell `Invoke-RestMethod` 直接 POST 到 GAS /exec（無瀏覽器 CORS）看真正回應。
