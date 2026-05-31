def _h_action_web_scrape(node, inputs, ctx):
    try: import httpx as _httpx
    except ImportError: raise RuntimeError("httpx not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    url = _to_str(inputs.get("url") or p.get("url", "")).strip()
    mode = str(p.get("mode", "text"))
    max_chars = int(p.get("max_chars", 0) or 0)
    ua = str(p.get("user_agent", "Mozilla/5.0 (compatible; AethvionBot/1.0)"))
    if not url: return {"out": "", "title": "", "error": "No URL"}
    try:
        r = _httpx.get(url, headers={"User-Agent": ua}, follow_redirects=True, timeout=30)
        if mode == "html":
            content, title = r.text, ""
        else:
            try:
                from bs4 import BeautifulSoup as _BS
                soup = _BS(r.text, "html.parser")
                title = soup.title.string.strip() if soup.title else ""
                if mode == "markdown":
                    content = "\n".join(t.get_text() for t in soup.find_all(["p","h1","h2","h3","li"]))
                else:
                    content = soup.get_text(separator="\n")
            except ImportError:
                import re as _re2
                content = _re2.sub(r"<[^>]+>", "", r.text)
                title = ""
        if max_chars: content = content[:max_chars]
        return {"out": content, "title": title, "error": ""}
    except Exception as exc:
        return {"out": "", "title": "", "error": str(exc)}
