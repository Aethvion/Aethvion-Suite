def _h_ui_input_toggle(node, inputs, ctx):
    nid = node.get("id", "")
    p = node.get("properties", {})
    name = str(p.get("name", nid)).strip() or nid
    default = p.get("value", False)
    raw = _INPUT_OVERRIDES.get(nid, ctx._vars.get(name, default))
    if isinstance(raw, str):
        val = raw.lower() in ("true", "1", "yes")
    else:
        val = bool(raw)
    ctx._vars[name] = val
    return {"out": val}
