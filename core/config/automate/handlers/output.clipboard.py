def _h_output_clipboard(node, inputs, ctx):
    try: import pyperclip as _clip
    except ImportError: ctx._warn("[Clipboard] pyperclip not installed"); return {}
    p = node.get("properties", {})
    fmt = str(p.get("format", "auto"))
    val = inputs.get("in")
    text = json.dumps(val, indent=2, ensure_ascii=False) if (fmt == "json_pretty" and not isinstance(val, str)) else (_to_str(val).strip() if fmt == "trim" else _to_str(val))
    try:
        _clip.copy(text)
        if bool(p.get("notify", True)): ctx._info("[Clipboard] Copied to clipboard")
    except Exception as exc:
        ctx._warn(f"[Clipboard] {exc}")
    return {}
