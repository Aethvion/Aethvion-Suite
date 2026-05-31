def _h_logic_repeat(node, inputs, ctx):
    count = int(node.get("properties", {}).get("count", 3) or 3)
    val = inputs.get("in")
    return {"out": [val] * count, "count": count}
