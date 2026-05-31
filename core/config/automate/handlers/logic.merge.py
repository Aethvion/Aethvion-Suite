def _h_logic_merge(node, inputs, ctx):
    mode = str(node.get("properties", {}).get("mode", "first"))
    sources = [inputs[k] for k in ("a", "b", "c", "d") if inputs.get(k) is not None]
    if mode == "all":
        return {"out": sources, "source": "all"}
    return {"out": sources[0] if sources else None, "source": "a" if sources else ""}
