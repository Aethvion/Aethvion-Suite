def _h_integration_slack(node, inputs, ctx):
    try: import httpx as _httpx
    except ImportError: raise RuntimeError("httpx not installed")
    p = node.get("properties", {})
    webhook_url = _to_str(inputs.get("webhook") or p.get("webhook_url", "")).strip()
    if not webhook_url: return {"out": inputs.get("in"), "error": "No webhook URL"}
    msg = _to_str(inputs.get("in", ""))
    title = _to_str(inputs.get("title") or p.get("title", "")).strip()
    blocks = []
    if title: blocks.append({"type": "header", "text": {"type": "plain_text", "text": title}})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": msg}})
    try:
        r = _httpx.post(webhook_url, json={"icon_emoji": str(p.get("icon_emoji",":robot_face:")), "blocks": blocks}, timeout=15)
        r.raise_for_status()
        return {"out": inputs.get("in"), "error": ""}
    except Exception as exc:
        return {"out": inputs.get("in"), "error": str(exc)}
