# 喵醫師的醫學期刊助理 · Medical Journal Reader

把 PubMed 文獻整理成繁體中文書庫的個人工具：依**期別**或自訂**主題**收集文章 →
翻譯標題 → 篩選 → 自適應摘要 → 保留原文連結與個人註記，回頭慢慢讀。

## 架構

```
Google Sheet（Collections 集合 / Articles 文章 / Jobs 佇列）
      ↕
GAS Web App（讀寫 API，前端用）                 ← M2
      ↕
靜態前端（書庫 → 勾選 → 閱讀＋註記；發起工作寫進 Jobs）  ← M2 / M3
      ↑
Python producer（撿 Jobs → 抓 PubMed + Gemini 摘要/排序，寫回 Sheet）  ← M1 / M3 / M4
GitHub Actions 跑 run-jobs（網頁立即執行／每週排程重掃訂閱）  ← M5
```

設計理念：**Sheet 當佇列、Python 當推進狀態的 worker、前端只讀＋改狀態＋寫註記**。
詳見 [docs/schema.md](docs/schema.md)。

## Roadmap

- ✅ **M1**：Sheet schema + Python producer（期別模式：抓取→翻標題→寫候選；摘要 Pass）
- ✅ **M2**：GAS 讀寫 API + 最小前端（看集合→讀摘要→寫註記→前端勾選 kept/dropped）
- ✅ **M3**：網頁發起工作（`Jobs` 佇列：新增一期、按鈕產摘要，免開 CLI）
- ✅ **M4**：主題模式漏斗（LLM 起草 query → 人工確認 → 粗篩 → 語意排序 → 勾選 → 摘要）
- ✅ **M5（第一段）**：雲端 on-demand 觸發（網頁「⚡ 立即執行」）+ 主題訂閱排程重掃（`watch=on`）
  - 待做：期刊出刊偵測（偵測新一期自動建集合）

## 安裝與設定（M1）

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
pip install -r requirements.txt
```

需要三組憑證，填進 `.env`（複製 `.env.example`）：

1. **Gemini API key** → https://aistudio.google.com/apikey
2. **NCBI API key**（建議）→ 登入 https://account.ncbi.nlm.nih.gov/ →
   Account Settings → API Key Management → 建立。
3. **Google 服務帳戶**（讓程式能寫 Sheet）：
   - 到 https://console.cloud.google.com/ 建立專案，啟用 **Google Sheets API**
   - 建立 Service Account → 產生 JSON 金鑰，存成專案根目錄的 `service_account.json`
   - 建立一份 Google Sheet，從網址複製 **Sheet ID** 填入 `.env` 的 `SHEET_ID`
   - 把該 Sheet **分享給服務帳戶的 email**（JSON 裡的 `client_email`），權限「編輯者」

## 使用（M1）

```bash
# Pass 1：抓某期刊某年月，翻譯標題，寫入候選
python producer.py ingest-issue --journal "N Engl J Med" --year 2026 --month 3

# 到 Google Sheet 的 Articles 分頁，把想看的文章 status 改成 kept

# Pass 2：對 kept 的文章產摘要並回寫
python producer.py summarize
```

> 第一次執行會自動在你的 Sheet 建立 `Collections`、`Articles`、`Jobs` 分頁與表頭。

## 使用（M3：網頁發起、本機 worker 推進）

網頁（GitHub Pages）只把工作排進 Sheet 的 `Jobs` 佇列，真正抓取/摘要由本機 worker 執行：

```bash
# 在網頁按「＋ 新增一期」「＋ 新增主題」「✨ 為此集合產摘要」「確認並抓取」後，
# 回本機跑這行把佇列裡 pending 的工作做掉，再回網頁按「重新整理」：
python producer.py run-jobs
```

主題模式也可純 CLI 操作：

```bash
python producer.py draft-topic   --collection topic-xxxx   # Stage 0：起草 query
python producer.py ingest-topic  --collection topic-xxxx   # Stage 1+2：粗篩＋語意排序
```

## 使用（M5：雲端執行，免開電腦）

設定好後（見下），本機那行 `run-jobs` 就不再是必要：

- **⚡ 立即執行（雲端）**：網頁按一下 → GAS 用 PAT 觸發 GitHub Actions 跑 `run-jobs`，把佇列裡的工作做掉。約一兩分鐘後按「重新整理」看結果。
- **🔔 訂閱自動更新**：在某個**主題**集合勾這個開關（`Collections.watch=on`），每週排程會同 query 重掃、自動補進新文章（靠 PMID 去重）。期別集合不重掃。

### M5 一次性設定

**1. GitHub repo secrets**（repo → Settings → Secrets and variables → Actions → New repository secret）：

| Secret | 內容 |
|---|---|
| `GEMINI_API_KEY` | Gemini 金鑰 |
| `NCBI_API_KEY` | NCBI 金鑰（可留空） |
| `NCBI_EMAIL` | E-utilities 禮貌性 email（可留空） |
| `SHEET_ID` | 你的 Google Sheet ID |
| `GOOGLE_SERVICE_ACCOUNT` | **整份 `service_account.json` 的內容**（直接貼 JSON 全文） |

**2. GitHub fine-grained PAT**（給 GAS 觸發用）：
- https://github.com/settings/tokens → Fine-grained tokens → Generate new token
- Repository access：只選 `Medical-journal-reader`
- Permissions → Repository → **Actions: Read and write**
- 產生後複製 token

**3. 把 PAT 存進 GAS**：Apps Script 編輯器 → 專案設定 → 指令碼屬性 → 新增 `GH_PAT` = 剛剛的 token。
（`gas/Code.gs` 頂端的 `GH_OWNER`/`GH_REPO`/`GH_WORKFLOW` 已對應本 repo，換 repo 才需改。）

> 排程在 `.github/workflows/run-jobs.yml`，預設每週一台北 08:00。改 cron 即可調整頻率。

## 部署更新（改了 GAS / 前端後）

- **GAS**：Apps Script 編輯器貼上 `gas/Code.gs` → 部署 → 管理部署 → 編輯 → **新版本**（光存檔不生效）。
- **前端**：`git push` 後 GitHub Actions 自動部署 `web/` 到 Pages。
