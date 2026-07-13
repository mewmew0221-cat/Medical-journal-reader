"""產製端 worker：期別/主題抓取（Pass 1）與摘要產生（Pass 2）。

用法：
    python producer.py ingest-issue --journal "N Engl J Med" --year 2026 --month 3
    python producer.py summarize            # 對 Sheet 中標記為 kept 的文章產摘要
    python producer.py run-jobs             # 撿 Sheet 的 Jobs 佇列（網頁發起的工作）跑掉
"""
import argparse
import json
import logging
from datetime import datetime

import llm
import pubmed_client as pm
import sheets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _article_row(cid, a, zh, relevance=""):
    """組一列 Articles（欄位順序須對齊 sheets.ARTICLES_HEADERS）。"""
    status = "candidate" if a["abstract"].strip() else "no_abstract"
    return [
        cid, a["pmid"], a["title"], zh, a["journal"], a["pub_date"],
        a["doi"], a["url"], a["authors"], a["abstract"], relevance, status,
        "", "", _now(), "",
    ]


def ingest_issue(journal: str, year: int, month: int, max_fetch: int):
    """Pass 1（期別）：建立集合，抓取、翻譯標題、寫入候選文章。"""
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

    rows = [_article_row(cid, a, zh) for a, zh in zip(articles, zh_titles)]
    sheets.append_articles(sh, rows)
    logger.info(f"已寫入 {len(rows)} 篇候選到 Sheet（集合 {cid}）")


def draft_topic(collection_id: str):
    """主題模式 Stage 0：依集合的主題描述（存在 note）起草 PubMed query 寫回。"""
    sh = sheets.open_sheet()
    col = sheets.get_collection(sh, collection_id)
    if not col:
        logger.warning(f"集合 {collection_id} 不存在，略過 draft")
        return
    topic = col.get("note") or col.get("name") or ""
    logger.info(f"為主題「{topic}」起草 query…")
    query = llm.draft_pubmed_query(topic)
    sheets.update_collection(sh, collection_id, {"query": query})
    logger.info(f"已起草 query：{query}")


def ingest_topic(collection_id: str, max_fetch: int):
    """主題模式 Stage 1+2：用集合已確認的 query 搜尋、翻譯標題、LLM 語意排序、寫候選。"""
    sh = sheets.open_sheet()
    col = sheets.get_collection(sh, collection_id)
    if not col:
        logger.warning(f"集合 {collection_id} 不存在，略過 ingest")
        return
    query = col.get("query", "")
    topic = col.get("note") or col.get("name") or ""
    if not query:
        logger.warning(f"集合 {collection_id} 尚無 query，略過")
        return

    pmids = pm.search_pubmed(query, max_results=max_fetch, sort="relevance")
    logger.info(f"主題粗篩找到 {len(pmids)} 篇")
    existing = sheets.existing_pmids(sh, collection_id)
    pmids = [p for p in pmids if p not in existing]
    if not pmids:
        sheets.update_collection(sh, collection_id, {"last_synced_at": _now()})
        logger.info("沒有新文章")
        return

    articles = pm.fetch_articles(pmids)
    titles = [a["title"] for a in articles]
    logger.info("翻譯標題＋語意排序中…")
    zh_titles = llm.translate_titles_bulk(titles)
    scores = llm.rank_titles_by_relevance(topic, titles)

    rows = [
        _article_row(collection_id, a, zh, relevance=score)
        for a, zh, score in zip(articles, zh_titles, scores)
    ]
    sheets.append_articles(sh, rows)
    sheets.update_collection(sh, collection_id, {"last_synced_at": _now()})
    logger.info(f"已寫入 {len(rows)} 篇候選到主題集合 {collection_id}")


def rescan_watched(max_fetch: int = 50):
    """排程重掃：把每個有訂閱（watch=on）的主題集合排成一件 ingest_topic 工作。

    同 query 重跑，靠 ingest_topic 內既有的 pmid 去重，只會補進新文章。
    排成 Jobs 而非直接抓，是為了讓網頁的「工作狀態」面板看得到這次重掃。
    之後 run-jobs 會把這些 pending 工作撿起來推進。
    """
    sh = sheets.open_sheet()
    watched = sheets.get_watched_collections(sh)
    if not watched:
        logger.info("沒有訂閱自動更新的主題集合")
        return
    logger.info(f"重掃 {len(watched)} 個訂閱中的主題集合")
    for col in watched:
        cid = col["collection_id"]
        jid = sheets.enqueue_job(
            sh, "ingest_topic", {"collection_id": cid, "max": max_fetch}, _now()
        )
        logger.info(f"已排入重掃工作 {jid}（集合 {cid}：{col.get('name')}）")


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
    """Pass 2：對標記為 kept 的文章產摘要並回寫。回傳失敗的 pmid 清單（供 run_jobs 寫進 Jobs.message）。"""
    sh = sheets.open_sheet()
    kept = sheets.get_articles_by_status(sh, "kept", collection_id)
    logger.info(f"待摘要 {len(kept)} 篇")
    failed = []
    for r in kept:
        article = {
            "title": r["title_en"], "journal": r["journal"], "pub_date": r["pub_date"],
            "authors": r["authors"], "doi": r["doi"], "abstract": r["abstract"],
        }
        summary = llm.summarize_abstract(article)
        if summary.startswith("Error"):
            logger.warning(f"PMID {r['pmid']} 摘要失敗，略過")
            failed.append(r["pmid"])
            continue
        sheets.update_article_row(sh, r["_row"], {
            "summary": summary, "status": "summarized", "summarized_at": _now(),
        })
        logger.info(f"PMID {r['pmid']} 摘要完成")
    return failed


def run_jobs():
    """撿 Jobs 佇列裡 pending 的工作（網頁發起的）依序跑掉，回寫狀態。"""
    sh = sheets.open_sheet()
    jobs = sheets.get_pending_jobs(sh)
    if not jobs:
        logger.info("沒有待處理的工作")
        return
    logger.info(f"撿到 {len(jobs)} 件待處理工作")
    for job in jobs:
        jid, jtype = job.get("job_id"), job.get("type")
        try:
            params = json.loads(job.get("params") or "{}")
        except json.JSONDecodeError:
            params = {}
        logger.info(f"▶ 執行 {jid}（{jtype}）params={params}")
        sheets.update_job(sh, job["_row"], {"status": "running"})
        try:
            failed = _dispatch_job(jtype, params)
            message = ""
            if failed:
                message = f"完成，但 {len(failed)} 篇摘要失敗（PMID: {', '.join(failed)}）"[:500]
            sheets.update_job(sh, job["_row"], {
                "status": "done", "finished_at": _now(), "message": message,
            })
            logger.info(f"✔ {jid} 完成" + (f"（{len(failed)} 篇失敗）" if failed else ""))
        except Exception as e:
            logger.exception(f"✘ {jid} 失敗")
            sheets.update_job(sh, job["_row"], {
                "status": "error", "finished_at": _now(), "message": str(e)[:500],
            })


def _dispatch_job(jtype: str, params: dict):
    """執行工作，回傳值目前只有 summarize 有意義（失敗的 pmid 清單），其餘回 None。"""
    if jtype == "ingest_issue":
        ingest_issue(
            params["journal"], int(params["year"]), int(params["month"]),
            int(params.get("max", 50)),
        )
    elif jtype == "summarize":
        return summarize_pending(params.get("collection") or None)
    elif jtype == "draft_topic":
        draft_topic(params["collection_id"])
    elif jtype == "ingest_topic":
        ingest_topic(params["collection_id"], int(params.get("max", 50)))
    else:
        raise ValueError(f"未知的工作類型：{jtype}")


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

    it = sub.add_parser("ingest-topic", help="用已確認 query 抓主題集合（Stage 1+2）")
    it.add_argument("--collection", required=True, help="主題集合 collection_id")
    it.add_argument("--max", type=int, default=50)

    dt = sub.add_parser("draft-topic", help="為主題集合起草 PubMed query（Stage 0）")
    dt.add_argument("--collection", required=True, help="主題集合 collection_id")

    sub.add_parser("run-jobs", help="撿 Jobs 佇列（網頁發起的工作）依序執行")

    rw = sub.add_parser("rescan-watched", help="把訂閱中的主題集合排成重掃工作（排程用）")
    rw.add_argument("--max", type=int, default=50)

    args = p.parse_args()
    if args.cmd == "ingest-issue":
        ingest_issue(args.journal, args.year, args.month, args.max)
    elif args.cmd == "summarize":
        summarize_pending(args.collection)
    elif args.cmd == "retranslate-titles":
        retranslate_titles(args.collection)
    elif args.cmd == "ingest-topic":
        ingest_topic(args.collection, args.max)
    elif args.cmd == "draft-topic":
        draft_topic(args.collection)
    elif args.cmd == "run-jobs":
        run_jobs()
    elif args.cmd == "rescan-watched":
        rescan_watched(args.max)


if __name__ == "__main__":
    main()
