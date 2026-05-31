def _h_integration_discord(node, inputs, ctx):
    try: import httpx as _httpx
    except ImportError: raise RuntimeError("httpx not installed")
    p = node.get("properties", {})
    webhook_url = _to_str(inputs.get("webhook") or p.get("webhook_url", "")).strip()
    if not webhook_url: return {"out": inputs.get("in"), "error": "No webhook URL"}
    msg = _to_str(inputs.get("in", ""))
    title = _to_str(inputs.get("title") or p.get("title", "")).strip()
    username = str(p.get("username", "Aethvion"))
    payload = {"username": username}
    if title:
        payload["embeds"] = [{"title": title, "description": msg, "color": int(p.get("colour", 5793266))}]
    else:
        payload["content"] = msg
    try:
        r = _httpx.post(webhook_url, json=payload, timeout=15)
        r.raise_for_status()
        return {"out": inputs.get("in"), "error": ""}
    except Exception as exc:
        return {"out": inputs.get("in"), "error": str(exc)}
