"""Google Sheet 存取層：建立 schema、寫入/更新文章、依狀態讀取。"""
import logging

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COLLECTIONS = "Collections"
ARTICLES = "Articles"
JOBS = "Jobs"

# 注意：新欄位一律「附加在尾端」，不要插中間，否則既有資料列會跟表頭錯位。
COLLECTIONS_HEADERS = [
    "collection_id", "type", "name", "query", "created_at", "last_synced_at", "note",
    "status",  # active | draft（主題模式起草中、等使用者確認 query）
]
ARTICLES_HEADERS = [
    "collection_id", "pmid", "title_en", "title_zh", "journal", "pub_date",
    "doi", "url", "authors", "abstract", "relevance_score", "status",
    "summary", "note", "added_at", "summarized_at",
]
JOBS_HEADERS = [
    "job_id", "type", "params", "status", "created_at", "finished_at", "message",
]


def open_sheet():
    """連線並確保各分頁與表頭都就緒，回傳 Spreadsheet 物件。"""
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(config.SHEET_ID)
    _ensure_tab(sh, COLLECTIONS, COLLECTIONS_HEADERS)
    _ensure_tab(sh, ARTICLES, ARTICLES_HEADERS)
    _ensure_tab(sh, JOBS, JOBS_HEADERS)
    return sh


def _ensure_tab(sh, title, headers):
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(headers))
    if ws.row_values(1) != headers:
        ws.update(values=[headers], range_name="A1")
    return ws


def add_collection(sh, collection_id, ctype, name, query, created_at,
                   note="", status="active"):
    ws = sh.worksheet(COLLECTIONS)
    ws.append_row(
        [collection_id, ctype, name, query, created_at, "", note, status],
        value_input_option="USER_ENTERED",
    )


def get_collection(sh, collection_id) -> dict | None:
    """取單一集合（附 _row 真實列號供回寫）。找不到回 None。"""
    ws = sh.worksheet(COLLECTIONS)
    for i, r in enumerate(ws.get_all_records(), start=2):
        if str(r["collection_id"]) == str(collection_id):
            r["_row"] = i
            return r
    return None


def update_collection(sh, collection_id, fields: dict):
    """更新某集合的指定欄位（依 collection_id 找列）。"""
    ws = sh.worksheet(COLLECTIONS)
    row = get_collection(sh, collection_id)
    if not row:
        return
    for key, val in fields.items():
        col = COLLECTIONS_HEADERS.index(key) + 1
        ws.update_cell(row["_row"], col, val)


def existing_pmids(sh, collection_id) -> set:
    """該集合內已存在的 PMID（去重用）。"""
    ws = sh.worksheet(ARTICLES)
    return {
        str(r["pmid"])
        for r in ws.get_all_records()
        if str(r["collection_id"]) == str(collection_id)
    }


def append_articles(sh, rows):
    if not rows:
        return
    ws = sh.worksheet(ARTICLES)
    ws.append_rows(rows, value_input_option="USER_ENTERED")


def get_all_articles(sh, collection_id=None) -> list:
    """取出文章（可指定集合），附 _row 真實列號供回寫。"""
    ws = sh.worksheet(ARTICLES)
    out = []
    for i, r in enumerate(ws.get_all_records(), start=2):  # 第 1 列是表頭
        if collection_id and str(r["collection_id"]) != str(collection_id):
            continue
        r["_row"] = i
        out.append(r)
    return out


def get_articles_by_status(sh, status, collection_id=None) -> list:
    """取出指定狀態的文章列（附 _row 真實列號供回寫）。"""
    ws = sh.worksheet(ARTICLES)
    out = []
    for i, r in enumerate(ws.get_all_records(), start=2):  # 第 1 列是表頭
        if r.get("status") != status:
            continue
        if collection_id and str(r["collection_id"]) != str(collection_id):
            continue
        r["_row"] = i
        out.append(r)
    return out


def update_article_row(sh, row_index, fields: dict):
    """更新某一列的指定欄位。"""
    ws = sh.worksheet(ARTICLES)
    for key, val in fields.items():
        col = ARTICLES_HEADERS.index(key) + 1
        ws.update_cell(row_index, col, val)


# --- Jobs 佇列（網頁發起、Python worker 推進）---

def get_pending_jobs(sh) -> list:
    """取出狀態為 pending 的工作（附 _row 真實列號供回寫）。"""
    ws = sh.worksheet(JOBS)
    out = []
    for i, r in enumerate(ws.get_all_records(), start=2):
        if r.get("status") == "pending":
            r["_row"] = i
            out.append(r)
    return out


def update_job(sh, row_index, fields: dict):
    ws = sh.worksheet(JOBS)
    for key, val in fields.items():
        col = JOBS_HEADERS.index(key) + 1
        ws.update_cell(row_index, col, val)
