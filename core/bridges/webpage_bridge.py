"""
core/bridges/webpage_bridge.py
Live Web Page & Documentation Reader Connector.
Fetches any URL, strips HTML/script/style boilerplate, and returns clean readable text
so users and companions (/read_url https://...) can read documentation and articles together.
"""

import html
import re
import urllib.request
from urllib.parse import urlparse


def _clean_html_to_text(raw_html: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else "Untitled Page"

    # Strip scripts, styles, svg, noscript, nav, footer
    cleaned = re.sub(
        r"<(script|style|svg|noscript|iframe|header|footer|nav)[^>]*>.*?</\1>",
        " ",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Preserve line breaks for block elements and headings
    cleaned = re.sub(r"<(h[1-6])[^>]*>(.*?)</\1>", r"\n\n### \2\n", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<(p|div|li|br|tr|pre|blockquote)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)

    lines = []
    for line in cleaned.splitlines():
        s = re.sub(r"[ \t]+", " ", line).strip()
        if s:
            lines.append(s)
    return title, "\n".join(lines)


def read_page(args: dict = None) -> str:
    """Fetch a web page URL and return its clean readable text content."""
    if args is None:
        args = {}
    url = str(args.get("url") or args.get("query") or "").strip()
    if not url:
        return "Web Reader Error: Provide a 'url' argument (e.g. https://docs.python.org/3/)."

    # Extract URL if embedded in a longer sentence
    url_match = re.search(r"https?://\S+", url)
    if url_match:
        url = url_match.group(0).rstrip(".,;)")
    elif not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return f"Web Reader Error: Invalid URL '{url}'."

    max_chars = min(20000, max(1000, int(args.get("max_chars", 10000) or 10000)))

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,text/plain,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_bytes = resp.read(500_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            raw_text = raw_bytes.decode(charset, errors="replace")

        title, body = _clean_html_to_text(raw_text)
        if len(body) > max_chars:
            body = body[:max_chars] + f"\n...[truncated at {max_chars} chars]"
        return f"Web Page: {title}\nURL: {url}\n\n{body}"
    except Exception as e:
        return f"Web Reader Error ({url}): {e}"
