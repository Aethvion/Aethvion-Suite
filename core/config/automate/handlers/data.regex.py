def _h_data_regex(node, inputs, ctx):
    import re as _re
    p = node.get("properties", {})
    pattern = _to_str(inputs.get("pattern") or p.get("pattern", ""))
    text = _to_str(inputs.get("in", ""))
    mode = str(p.get("mode", "extract"))
    replacement = str(p.get("replacement", ""))
    flags_str = str(p.get("flags", "")).lower()
    all_matches = bool(p.get("all_matches", False))
    flags = 0
    if "i" in flags_str: flags |= _re.IGNORECASE
    if "m" in flags_str: flags |= _re.MULTILINE
    if "s" in flags_str: flags |= _re.DOTALL
    try:
        if mode == "match":
            m = _re.search(pattern, text, flags)
            return {"out": m.group(0) if m else "", "matches": [], "matched": bool(m), "error": ""}
        if mode == "replace":
            return {"out": _re.sub(pattern, replacement, text, flags=flags), "matches": [], "matched": True, "error": ""}
        if all_matches:
            ms = _re.findall(pattern, text, flags)
            return {"out": ms[0] if ms else "", "matches": ms, "matched": bool(ms), "error": ""}
        m = _re.search(pattern, text, flags)
        if m:
            groups = list(m.groups()) if m.groups() else [m.group(0)]
            return {"out": groups[0], "matches": groups, "matched": True, "error": ""}
        return {"out": "", "matches": [], "matched": False, "error": ""}
    except Exception as exc:
        return {"out": "", "matches": [], "matched": False, "error": str(exc)}
