# 喵醫師的醫學期刊助理 · Medical Journal Reader

把 PubMed 文獻整理成繁體中文書庫的個人工具：依**期別**或自訂**主題**收集文章 →
翻譯標題 → 篩選 → 自適應摘要 → 保留原文連結與個人註記，回頭慢慢讀。

## 架構

```
Google Sheet（資料：Collections 集合 / Articles 文章）
      ↕
GAS Web App（讀寫 API，前端用）           ← M2 之後
      ↕
靜態前端（書庫 → 勾選 → 閱讀＋註記）       ← M2 之後
      ↑
Python producer（抓 PubMed + Gemini 摘要，寫進 Sheet）  ← 本檔，M1
GitHub Actions 排程刷新                    ← M5 之後
```

設計理念：**Sheet 當佇列、Python 當推進狀態的 worker、前端只讀＋改狀態＋寫註記**。
詳見 [docs/schema.md](docs/schema.md)。

## Roadmap

- **M1（現在）**：Sheet schema + Python producer（期別模式：抓取→翻標題→寫候選；摘要 Pass）
- **M2**：GAS 讀寫 API + 最小前端（看集合→讀摘要→寫註記）
- **M3**：摘要 Pass 串接 + 前端勾選 kept/dropped
- **M4**：主題模式（LLM 起草 query + 篩選器 UI + 語意排序漏斗）
- **M5**：GitHub Actions 排程自動刷新

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

> 第一次執行會自動在你的 Sheet 建立 `Collections` 與 `Articles` 兩張分頁與表頭。
