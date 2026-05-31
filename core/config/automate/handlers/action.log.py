def _h_action_log(node, inputs, ctx):
    p = node.get("properties", {})
    msg = str(p.get("message", "{{input}}")).replace("{{input}}", _to_str(inputs.get("in", "")))
    level = str(p.get("level", "info")).lower()
    if level == "error": ctx._error(f"[Log] {msg}")
    elif level == "warning": ctx._warn(f"[Log] {msg}")
    else: ctx._info(f"[Log] {msg}")
    return {"out": inputs.get("in")}
