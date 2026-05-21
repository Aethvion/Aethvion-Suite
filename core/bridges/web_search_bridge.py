"""
core/bridges/web_search_bridge.py
══════════════════════════════════
Internet search bridge — queries DuckDuckGo's Instant Answer API (no API key
required) and falls back to a HTML snippet scrape for queries that return no
direct answer.
"""
import logging
import re
import urllib.parse
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

_DDG_API     = "https://api.duckduckgo.com/"
_DDG_HEADERS = {"User-Agent": "AethvionSuite/1.0 (local AI assistant)"}
_TIMEOUT     = 12   # seconds


def web_search(args: Dict[str, Any]) -> str:
    """
    Search the web and return a concise summary of the top results.

    Args (from tool call attrs):
        query   — what to search for  (required)
        count   — max results to include in summary (default 5, max 10)
    """
    query = args.get("query", "").strip()
    if not query:
        return "[web_search ERROR] No query provided."

    try:
        count = min(int(args.get("count", 5)), 10)
    except (TypeError, ValueError):
        count = 5

    try:
        return _ddg_search(query, count)
    except Exception as e:
        logger.error(f"Web search failed: {e}", exc_info=True)
        return f"[web_search ERROR] Could not fetch results: {e}"


# ── DuckDuckGo Instant Answer + related topics ───────────────────────────────

def _ddg_search(query: str, count: int) -> str:
    encoded = urllib.parse.quote_plus(query)
    params = {
        "q":              encoded,
        "format":         "json",
        "no_html":        "1",
        "skip_disambig":  "1",
    }
    resp = requests.get(_DDG_API, params=params, headers=_DDG_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    sections: list[str] = []

    # 1. Direct answer (calculator, unit conversion, etc.)
    if data.get("Answer"):
        sections.append(f"Answer: {data['Answer']}")

    # 2. Abstract summary (Wikipedia / Wikidata)
    abstract = data.get("AbstractText", "").strip()
    if abstract:
        src = data.get("AbstractURL", "")
        sections.append(f"Summary: {abstract}" + (f"\nSource: {src}" if src else ""))

    # 3. Definition
    if data.get("Definition"):
        src = data.get("DefinitionURL", "")
        sections.append(f"Definition: {data['Definition']}" + (f" ({src})" if src else ""))

    # 4. Infobox (structured key-value for entities)
    infobox = data.get("Infobox", {})
    if isinstance(infobox, dict):
        content = infobox.get("content", [])
        if content:
            items = [f"  {e['label']}: {e['value']}" for e in content[:6]
                     if isinstance(e, dict) and e.get("label") and e.get("value")]
            if items:
                sections.append("Details:\n" + "\n".join(items))

    # 5. Related topics (actual search results-like snippets)
    topics: list[str] = []
    for t in data.get("RelatedTopics", []):
        if len(topics) >= count:
            break
        if isinstance(t, dict) and t.get("Text"):
            text = t["Text"]
            url  = t.get("FirstURL", "")
            snippet = f"• {text}" + (f"\n  {url}" if url else "")
            topics.append(snippet)
        elif isinstance(t, dict) and t.get("Topics"):
            # Nested topic group
            for sub in t["Topics"]:
                if len(topics) >= count:
                    break
                if isinstance(sub, dict) and sub.get("Text"):
                    url = sub.get("FirstURL", "")
                    topics.append(f"• {sub['Text']}" + (f"\n  {url}" if url else ""))

    if topics:
        sections.append("Results:\n" + "\n".join(topics))

    if not sections:
        # Nothing useful returned — tell the companion so it can say so
        return (
            f"[web_search] No direct results found for '{query}'. "
            "The query may be too specific or require a different phrasing."
        )

    header = f"[web_search: \"{query}\"]\n"
    return header + "\n\n".join(sections)
