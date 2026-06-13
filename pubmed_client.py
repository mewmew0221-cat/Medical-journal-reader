"""PubMed E-utilities 用戶端：搜尋 PMID、批次抓取並解析文章。"""
import logging
import xml.etree.ElementTree as ET

import requests

import config

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _common_params() -> dict:
    """帶上 API key 與 tool/email（有 key 速率較高）。"""
    p = {}
    if config.NCBI_API_KEY:
        p["api_key"] = config.NCBI_API_KEY
    if config.NCBI_EMAIL:
        p["email"] = config.NCBI_EMAIL
        p["tool"] = "meow-journal-reader"
    return p


def search_pubmed(query: str, max_results: int = 50, sort: str = "pub_date") -> list:
    """回傳符合 query 的 PMID 清單。sort: 'pub_date'（最新）或 'relevance'（Best Match）。"""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": sort,
        **_common_params(),
    }
    try:
        r = requests.get(ESEARCH_URL, params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        logger.error(f"esearch 失敗 query='{query}': {e}")
        return []


def fetch_articles(pmids: list) -> list:
    """一次 efetch 多筆 PMID（逗號串接），回傳文章 dict 清單。"""
    if not pmids:
        return []
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        **_common_params(),
    }
    try:
        r = requests.get(EFETCH_URL, params=params, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        return [_parse_article(a) for a in root.findall(".//PubmedArticle")]
    except Exception as e:
        logger.error(f"efetch 失敗: {e}")
        return []


def _parse_article(article: ET.Element) -> dict:
    """把單一 PubmedArticle XML 節點轉成 dict。"""
    data = {
        "pmid": "", "title": "", "abstract": "", "journal": "",
        "pub_date": "", "doi": "", "authors": "", "url": "",
    }

    pmid_elem = article.find(".//PMID")
    if pmid_elem is not None:
        data["pmid"] = pmid_elem.text or ""

    title_elem = article.find(".//ArticleTitle")
    if title_elem is not None:
        # itertext 把標題內的 <i>/<sup> 等內嵌標籤一併取出
        data["title"] = "".join(title_elem.itertext()).strip()

    # 摘要可能分段（BACKGROUND / METHODS / RESULTS / CONCLUSIONS）
    parts = []
    for ab in article.findall(".//AbstractText"):
        label = ab.get("Label", "")
        text = "".join(ab.itertext()).strip()
        if text:
            parts.append(f"{label}: {text}" if label else text)
    data["abstract"] = "\n".join(parts)

    iso = article.find(".//Journal/ISOAbbreviation")
    jtitle = article.find(".//Journal/Title")
    if iso is not None and iso.text:
        data["journal"] = iso.text
    elif jtitle is not None and jtitle.text:
        data["journal"] = jtitle.text

    y = article.find(".//PubDate/Year")
    m = article.find(".//PubDate/Month")
    year = y.text if y is not None else ""
    month = m.text if m is not None else "01"
    data["pub_date"] = f"{year}-{month}" if year else ""

    for eid in article.findall(".//ELocationID"):
        if eid.get("EIdType") == "doi":
            data["doi"] = eid.text or ""
            break

    authors = article.findall(".//AuthorList/Author")
    if authors:
        last = authors[0].find("LastName")
        last_txt = last.text if last is not None else ""
        data["authors"] = f"{last_txt} et al." if len(authors) > 1 else last_txt

    data["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{data['pmid']}/"
    return data


def build_issue_query(journal: str, year: int, month: int) -> str:
    """組期別 query：指定期刊 + 出版年月 + 原著/綜述。"""
    return (
        f'"{journal}"[Journal] '
        f'AND ("Journal Article"[Publication Type] OR "Review"[Publication Type]) '
        f'AND ("{year}/{month:02d}"[dp])'
    )
