# 資料模型（Google Sheet 兩張分頁）

## `Collections`（集合 = 一個書庫單位）

| 欄位 | 說明 |
|---|---|
| `collection_id` | 主鍵，例：`issue-20260613xxxxxx` |
| `type` | `issue`（期別）或 `topic`（主題） |
| `name` | 顯示名稱，例：`N Engl J Med 2026/03`、`IgA腎炎最新治療` |
| `query` | 產生這包用的 PubMed query 字串 |
| `created_at` | 建立時間 |
| `last_synced_at` | 上次刷新時間（主題重跑/排程用） |
| `note` | 備註 |

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
