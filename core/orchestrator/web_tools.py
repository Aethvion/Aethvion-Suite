"""
core/orchestrator/web_tools.py
══════════════════════════════
Web fetch and search utilities for the Code agent runner.
Pure functions — no AgentRunner state required.
"""
from __future__ import annotations

import re


def fetch_url(url: str) -> str:
    """Fetch a URL with smart HTML extraction (trafilatura → html.parser → raw)."""
    import urllib.request
    import urllib.error
    _CAP = 12_000
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AethvionAgent/1.0)",
            "Accept": "application/json, text/html, text/plain, */*",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw_bytes = resp.read()

        body = raw_bytes.decode("utf-8", errors="replace")

        # JSON / plain text — return raw, no extraction needed
        if "application/json" in content_type or "text/plain" in content_type:
            if len(body) > _CAP:
                body = body[:_CAP] + "\n...(truncated)"
            return f"HTTP {status}\n{body}"

        # HTML — try smart extraction strategies
        is_html = "text/html" in content_type or body.lstrip()[:15].lower().startswith("<!doctype")
        if is_html:
            # Strategy 1: trafilatura — best for articles, docs, blog posts
            try:
                import trafilatura  # type: ignore
                extracted = trafilatura.extract(
                    body, include_comments=False, include_tables=True,
                    no_fallback=False,
                )
                if extracted and len(extracted) > 150:
                    if len(extracted) > _CAP:
                        extracted = extracted[:_CAP] + "\n...(truncated)"
                    return f"HTTP {status} [extracted]\n{extracted}"
            except ImportError:
                pass
            except Exception:
                pass

            # Strategy 2: html.parser semantic extraction
            try:
                from html.parser import HTMLParser

                class _SE(HTMLParser):
                    _SKIP = {"script", "style", "nav", "footer", "header",
                             "aside", "noscript", "svg", "form"}
                    _BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "li",
                              "pre", "code", "blockquote", "td", "th", "dt", "dd"}

                    def __init__(self):
                        super().__init__()
                        self._depth = 0
                        self.parts: list[str] = []

                    def handle_starttag(self, tag, attrs):
                        if tag in self._SKIP:
                            self._depth += 1

                    def handle_endtag(self, tag):
                        if tag in self._SKIP and self._depth:
                            self._depth -= 1
                        if tag in self._BLOCK and self.parts and self.parts[-1] != "\n":
                            self.parts.append("\n")

                    def handle_data(self, data):
                        if self._depth:
                            return
                        t = data.strip()
                        if t:
                            self.parts.append(t + " ")

                p = _SE()
                p.feed(body)
                text = "".join(p.parts).strip()
                # Collapse noisy whitespace
                text = re.sub(r" {3,}", "  ", text)
                text = re.sub(r"\n{3,}", "\n\n", text)
                if text and len(text) > 100:
                    if len(text) > _CAP:
                        text = text[:_CAP] + "\n...(truncated)"
                    return f"HTTP {status} [html]\n{text}"
            except Exception:
                pass

        # Fallback: raw with increased cap
        if len(body) > _CAP:
            body = body[:_CAP] + "\n...(truncated)"
        return f"HTTP {status}\n{body}"

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        return f"HTTP {e.code} {e.reason}: {body}"
    except Exception as e:
        return f"Fetch error: {e}"

# ── file backup / restore ──────────────────────────────────────


def search_web(query: str, max_results: int = 6) -> str:
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                title = r.get("title", "")
                href  = r.get("href", "")
                body  = r.get("body", "")
                results.append(f"[{title}]\n{href}\n{body}")
        if not results:
            return "No results found."
        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Search error: {e}"

# Patterns that are unconditionally blocked regardless of workspace isolation.
# These represent irreversible destructive operations that no legitimate agent
# task should ever need to perform.
_BLOCKED_COMMAND_PATTERNS = [
    # Windows: wipe entire drive / system directories
    r"(?i)\bformat\s+[a-z]:",
    r"(?i)del\s+/[sq].*\s+[a-z]:\\",
    r"(?i)rmdir\s+/[sq].*\s+[a-z]:\\",
    r"(?i)rd\s+/[sq].*\s+[a-z]:\\",
    # POSIX: recursive delete from root or home
    r"rm\s+-[^\s]*r[^\s]*\s+/\s*$",
    r"rm\s+-[^\s]*r[^\s]*\s+~/",
    # Registry destruction
    r"(?i)reg\s+delete\s+hk[lcmu]",
    # Shutdown / reboot
    r"(?i)\bshutdown\b",
    r"(?i)\breboot\b",
]

