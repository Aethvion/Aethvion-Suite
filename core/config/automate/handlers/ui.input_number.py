def _h_ui_input_number(node, inputs, ctx):
    nid = node.get("id", "")
    p = node.get("properties", {})
    name = str(p.get("name", nid)).strip() or nid
    default = p.get("value", 0)
    raw = _INPUT_OVERRIDES.get(nid, ctx._vars.get(name, default))
    try:
        val = float(raw)
    except (ValueError, TypeError):
        val = 0.0
    ctx._vars[name] = val
    return {"out": val}
