# 資料模型（Google Sheet 三張分頁）

## `Collections`（集合 = 一個書庫單位）

| 欄位 | 說明 |
|---|---|
| `collection_id` | 主鍵，例：`issue-20260613xxxxxx`、`topic-20260613xxxxxx` |
| `type` | `issue`（期別）或 `topic`（主題） |
| `name` | 顯示名稱，例：`N Engl J Med 2026/03`、`IgA腎炎最新治療` |
| `query` | 產生這包用的 PubMed query 字串（主題模式由 LLM 起草、人工確認） |
| `created_at` | 建立時間 |
| `last_synced_at` | 上次刷新時間（主題重跑/排程用） |
| `note` | 備註；**主題模式**這裡存使用者輸入的自然語言主題描述（供起草 query 與語意排序用） |
| `status` | `active`（一般）或 `draft`（主題已建、query 起草中／待使用者確認）。空白＝視為 active |

## `Articles`（文章 = 屬於某集合的一篇）

| 欄位 | 說明 |
|---|---|
| `collection_id` | 外鍵，屬於哪個集合 |
| `pmid` | 去重用的自然鍵 |
| `title_en` / `title_zh` | 原文 / 中譯標題 |
| `journal` / `pub_date` / `doi` / `url` / `authors` | 基本資訊 |
| `abstract` | 原始英文摘要 |
| `relevance_score` | 主題模式 Stage 2 語意排序分數（期別模式留空） |
| `status` | 狀態機，見下 |
| `summary` | 產出的繁中摘要 |
| `note` | 你的註記（已讀、重點…） |
| `added_at` / `summarized_at` | 時間戳 |

## 文章狀態機

```
candidate ──你勾選──▶ kept ──產摘要──▶ summarized ──你讀──▶ read
    └─────────────▶ dropped（不想看）
no_abstract：原廠無摘要的 review/letter，仍可保留只寫註記
```

- **Pass 1（producer）**：寫入 `candidate` / `no_abstract`
- **你在前端**：改成 `kept` / `dropped`、寫 `note`
- **Pass 2（producer）**：把 `kept` → `summarized`，填 `summary`

## `Jobs`（工作佇列 = 網頁發起、Python worker 推進）

網頁不直接呼叫 LLM/PubMed，而是把要做的事寫成一列 `Jobs`；本機（未來 M5 改 GitHub Actions）
跑 `python producer.py run-jobs` 撿起來執行。

| 欄位 | 說明 |
|---|---|
| `job_id` | 主鍵，例：`job-20260613xxxxxx-123` |
| `type` | `ingest_issue` / `summarize` / `draft_topic` / `ingest_topic` |
| `params` | JSON 字串，依 type 不同（見下） |
| `status` | `pending` → `running` → `done` / `error` |
| `created_at` / `finished_at` | 時間戳 |
| `message` | 失敗時的錯誤訊息 |

`params` 內容：
- `ingest_issue`：`{journal, year, month, max}`（worker 會自建 issue 集合）
- `summarize`：`{collection}`（可省＝對全部 kept 產摘要）
- `draft_topic`：`{collection_id}`（worker 讀該集合 note 當主題，起草 query 寫回 `query`）
- `ingest_topic`：`{collection_id, max}`（worker 用已確認的 query 做粗篩＋語意排序）

## 主題模式漏斗（痛點④）

```
[網頁] 輸入主題描述 ─▶ new_topic：建 draft 集合 + 排 draft_topic
[worker] draft_topic ─▶ LLM 起草 query 寫回集合（status 仍 draft）
[網頁] 檢視/微調 query ─▶ confirm_topic：status=active + 排 ingest_topic
[worker] ingest_topic ─▶ PubMed 粗篩 → 翻譯標題 → LLM 語意排序（relevance_score）→ 寫 candidate
[網頁] 依分數高低勾選 kept ─▶ 排 summarize ─▶ [worker] 只對 kept 產摘要
```
