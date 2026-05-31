def _h_data_list_item(node, inputs, ctx):
    p = node.get("properties", {})
    idx = int(inputs["index"] if inputs.get("index") is not None else p.get("index", 0))
    slice_end = int(p.get("slice_end", 0) or 0)
    items = inputs.get("in", [])
    if isinstance(items, str):
        try: items = json.loads(items)
        except Exception: items = [items]
    if not isinstance(items, list): items = [items]
    count = len(items)
    if slice_end > 0: return {"out": items[idx:slice_end], "count": count, "error": ""}
    if -count <= idx < count: return {"out": items[idx], "count": count, "error": ""}
    return {"out": None, "count": count, "error": f"Index {idx} out of range ({count} items)"}
