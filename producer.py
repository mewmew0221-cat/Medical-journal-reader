"""產製端 worker：期別抓取（Pass 1）與摘要產生（Pass 2）。

用法：
    python producer.py ingest-issue --journal "N Engl J Med" --year 2026 --month 3
    python producer.py summarize            # 對 Sheet 中標記為 kept 的文章產摘要
"""
import argparse
import logging
from datetime import datetime

import llm
import pubmed_client as pm
import sheets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ingest_issue(journal: str, year: int, month: int, max_fetch: int):
    """Pass 1：建立一個期別集合，抓取、翻譯標題、寫入候選文章。"""
    sh = sheets.open_sheet()
    query = pm.build_issue_query(journal, year, month)
    cid = f"issue-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    name = f"{journal} {year}/{month:02d}"
    logger.info(f"建立集合「{name}」：{query}")
    sheets.add_collection(sh, cid, "issue", name, query, _now())

    pmids = pm.search_pubmed(query, max_results=max_fetch, sort="pub_date")
    logger.info(f"找到 {len(pmids)} 篇")
    if not pmids:
        return

    articles = pm.fetch_articles(pmids)
    titles = [a["title"] for a in articles]
    logger.info("翻譯標題中…")
    zh_titles = llm.translate_titles_bulk(titles)

    rows = []
    for a, zh in zip(articles, zh_titles):
        status = "candidate" if a["abstract"].strip() else "no_abstract"
        rows.append([
            cid, a["pmid"], a["title"], zh, a["journal"], a["pub_date"],
            a["doi"], a["url"], a["authors"], a["abstract"], "", status,
            "", "", _now(), "",
        ])
    sheets.append_articles(sh, rows)
    logger.info(f"已寫入 {len(rows)} 篇候選到 Sheet（集合 {cid}）")


def retranslate_titles(collection_id=None):
    """重新翻譯既有文章的中文標題並回寫（修正早期簡體殘留）。"""
    sh = sheets.open_sheet()
    arts = sheets.get_all_articles(sh, collection_id)
    logger.info(f"重新翻譯 {len(arts)} 篇標題")
    if not arts:
        return
    zh_titles = llm.translate_titles_bulk([a["title_en"] for a in arts])
    for a, zh in zip(arts, zh_titles):
        if zh and zh != a.get("title_zh"):
            sheets.update_article_row(sh, a["_row"], {"title_zh": zh})
    logger.info("標題已更新")


def summarize_pending(collection_id=None):
    """Pass 2：對標記為 kept 的文章產摘要並回寫。"""
    sh = sheets.open_sheet()
    kept = sheets.get_articles_by_status(sh, "kept", collection_id)
    logger.info(f"待摘要 {len(kept)} 篇")
    for r in kept:
        article = {
            "title": r["title_en"], "journal": r["journal"], "pub_date": r["pub_date"],
            "authors": r["authors"], "doi": r["doi"], "abstract": r["abstract"],
        }
        summary = llm.summarize_abstract(article)
        if summary.startswith("Error"):
            logger.warning(f"PMID {r['pmid']} 摘要失敗，略過")
            continue
        sheets.update_article_row(sh, r["_row"], {
            "summary": summary, "status": "summarized", "summarized_at": _now(),
        })
        logger.info(f"PMID {r['pmid']} 摘要完成")


def main():
    p = argparse.ArgumentParser(description="喵醫師的醫學期刊助理 — 產製端 worker")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ingest-issue", help="抓取某期刊某年月（Pass 1）")
    a.add_argument("--journal", required=True, help="PubMed 期刊縮寫，如 'N Engl J Med'")
    a.add_argument("--year", type=int, required=True)
    a.add_argument("--month", type=int, required=True)
    a.add_argument("--max", type=int, default=50)

    s = sub.add_parser("summarize", help="對已勾選 kept 的文章產摘要（Pass 2）")
    s.add_argument("--collection", default=None)

    rt = sub.add_parser("retranslate-titles", help="重新翻譯既有文章的中文標題")
    rt.add_argument("--collection", default=None)

    args = p.parse_args()
    if args.cmd == "ingest-issue":
        ingest_issue(args.journal, args.year, args.month, args.max)
    elif args.cmd == "summarize":
        summarize_pending(args.collection)
    elif args.cmd == "retranslate-titles":
        retranslate_titles(args.collection)


if __name__ == "__main__":
    main()
