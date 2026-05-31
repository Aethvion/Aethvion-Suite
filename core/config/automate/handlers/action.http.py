def _h_action_http(node, inputs, ctx):
    try: import httpx as _httpx
    except ImportError: raise RuntimeError("httpx not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    url = _to_str(inputs.get("in") or p.get("url", "")).strip()
    method = str(p.get("method", "GET")).upper()
    try: headers = json.loads(str(p.get("headers", "{}") or "{}"))
    except Exception: headers = {}
    body = str(p.get("body", "") or "")
    if not url: return {"out": "", "error": "No URL"}
    try:
        r = _httpx.request(method, url, headers=headers, content=body.encode() if body else None, timeout=30)
        return {"out": r.text, "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
