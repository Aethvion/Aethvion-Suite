def _h_action_clipboard(node, inputs, ctx):
    try: import pyperclip as _clip
    except ImportError: raise RuntimeError("pyperclip not installed")
    mode = str(node.get("properties", {}).get("mode", "write"))
    if mode in ("read", "read_then_clear"):
        content = _clip.paste()
        if mode == "read_then_clear": _clip.copy("")
        return {"out": content, "error": ""}
    text = _to_str(inputs.get("in", ""))
    _clip.copy(text)
    return {"out": text, "error": ""}
