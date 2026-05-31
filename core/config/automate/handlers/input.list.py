def _h_input_list(node, inputs, ctx):
    nid = node.get("id", "")
    p = node.get("properties", {})
    raw = _INPUT_OVERRIDES.get(nid, p.get("items", ""))
    trim = bool(p.get("trim", True))
    remove_empty = bool(p.get("remove_empty", True))
    lines = str(raw).splitlines()
    if trim: lines = [ln.strip() for ln in lines]
    if remove_empty: lines = [ln for ln in lines if ln]
    return {"out": lines, "count": len(lines), "first": lines[0] if lines else ""}
