"""Google Sheet 存取層：建立 schema、寫入/更新文章、依狀態讀取。"""
import logging

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COLLECTIONS = "Collections"
ARTICLES = "Articles"

COLLECTIONS_HEADERS = [
    "collection_id", "type", "name", "query", "created_at", "last_synced_at", "note",
]
ARTICLES_HEADERS = [
    "collection_id", "pmid", "title_en", "title_zh", "journal", "pub_date",
    "doi", "url", "authors", "abstract", "relevance_score", "status",
    "summary", "note", "added_at", "summarized_at",
]


def open_sheet():
    """連線並確保兩張分頁與表頭都就緒，回傳 Spreadsheet 物件。"""
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(config.SHEET_ID)
    _ensure_tab(sh, COLLECTIONS, COLLECTIONS_HEADERS)
    _ensure_tab(sh, ARTICLES, ARTICLES_HEADERS)
    return sh


def _ensure_tab(sh, title, headers):
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(headers))
    if ws.row_values(1) != headers:
        ws.update(values=[headers], range_name="A1")
    return ws


def add_collection(sh, collection_id, ctype, name, query, created_at):
    ws = sh.worksheet(COLLECTIONS)
    ws.append_row(
        [collection_id, ctype, name, query, created_at, "", ""],
        value_input_option="USER_ENTERED",
    )


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
