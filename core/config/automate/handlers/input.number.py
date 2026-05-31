def _h_input_number(node, inputs, ctx):
    nid = node.get("id", "")
    raw = _INPUT_OVERRIDES.get(nid, node.get("properties", {}).get("value", 0))
    try: return {"out": float(raw)}
    except Exception: return {"out": 0}
