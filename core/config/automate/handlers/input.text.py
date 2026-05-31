def _h_input_text(node, inputs, ctx):
    nid = node.get("id", "")
    val = _INPUT_OVERRIDES.get(nid, node.get("properties", {}).get("value", ""))
    return {"out": str(val)}
