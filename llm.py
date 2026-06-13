"""LLM 處理：標題批次翻譯、自適應摘要。（query 起草／語意排序留待 M4）"""
import json
import logging

import google.generativeai as genai

import config

logger = logging.getLogger(__name__)


def _model(name: str):
    genai.configure(api_key=config.GEMINI_API_KEY)
    return genai.GenerativeModel(name)


def translate_titles_bulk(titles: list, model: str = None) -> list:
    """一次打包翻譯多筆標題（省 API 額度）。回傳與輸入等長的中文標題清單。"""
    if not titles:
        return []
    model = model or config.LITE_MODEL
    listed = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    prompt = (
        "你是台灣的醫學翻譯專家。將以下英文期刊標題依序翻成流暢的醫學術語。\n"
        "務必使用【台灣慣用的繁體中文（正體中文）】，嚴禁出現任何簡體字。\n"
        '嚴格輸出 JSON，包含一個名為 "translations" 的陣列，依序放每篇的中文翻譯，'
        "不要輸出其他任何文字。\n\n"
        f"{listed}"
    )
    try:
        resp = _model(model).generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json"
            ),
        )
        data = json.loads(resp.text.strip())
        out = data.get("translations", [])
        if len(out) == len(titles):
            return out
        logger.warning(f"翻譯數量不符：預期 {len(titles)} 實得 {len(out)}")
        return out[: len(titles)] + titles[len(out):]
    except Exception as e:
        logger.error(f"translate_titles_bulk 失敗: {e}")
        return [f"[翻譯失敗] {t}" for t in titles]


SUMMARY_PROMPT = """你是一位台灣的資深醫學主治醫師。請閱讀以下文獻，整理成排版分明的繁體中文。
務必使用【台灣慣用的繁體中文（正體中文）】，嚴禁出現任何簡體字。

論文標題: {title}
期刊: {journal} ({date})
作者: {authors}
DOI: {doi}
原始摘要:
{abstract}

輸出要求：
第一行： # [繁體中文標題] (英文標題)
1. **文獻資訊**（期刊、出版年月、第一作者、DOI）
2. **背景與目的**（一句話）
3. **重點整理**：依文章性質自動選擇呈現方式——
   - 研究型（RCT/世代等）→ 用 PICO（P 族群與人數 / I 介入 / C 對照 / O 核心結論與數據）
   - 綜述/沒有 PICO 結構 → 改用 3-5 點重點條列
   - letter/editorial/評論 → 用 2-3 句話講核心觀點
4. **臨床應用價值**（一句話）

直接輸出結果，不要多餘引言。"""


def summarize_abstract(article: dict, model: str = None) -> str:
    """產生自適應格式的繁中摘要（依文章性質在 PICO / 條列 / 短評間切換）。"""
    model = model or config.SUMMARY_MODEL
    prompt = SUMMARY_PROMPT.format(
        title=article.get("title", ""),
        journal=article.get("journal", ""),
        date=article.get("pub_date", ""),
        authors=article.get("authors", ""),
        doi=article.get("doi", ""),
        abstract=article.get("abstract", ""),
    )
    try:
        return _model(model).generate_content(prompt).text.strip()
    except Exception as e:
        logger.error(f"summarize 失敗: {e}")
        return f"Error: 產生摘要失敗 ({e})"
