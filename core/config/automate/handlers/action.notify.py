def _h_action_notify(node, inputs, ctx):
    p = node.get("properties", {})
    title = _to_str(inputs.get("title") or p.get("title", "Workflow"))
    msg = _to_str(inputs.get("message") or p.get("message", ""))
    msg = msg.replace("{{input}}", _to_str(inputs.get("in", "")))
    try:
        from plyer import notification
        notification.notify(title=title, message=msg, timeout=5)
    except Exception as exc:
        ctx._warn(f"[Notify] {exc}")
    return {"out": inputs.get("in"), "error": ""}
