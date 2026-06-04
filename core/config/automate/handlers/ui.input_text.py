def _h_ui_input_text(node, inputs, ctx):
    nid = node.get("id", "")
    p = node.get("properties", {})
    name = str(p.get("name", nid)).strip() or nid
    default = str(p.get("value", ""))
    val = _INPUT_OVERRIDES.get(nid, ctx._vars.get(name, default))
    ctx._vars[name] = val
    return {"out": str(val)}
