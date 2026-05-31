def _h_data_filter(node, inputs, ctx):
    expr = str(node.get("properties", {}).get("expression", "")).strip()
    items = inputs.get("in", [])
    if isinstance(items, str):
        try: items = json.loads(items)
        except Exception: items = [items]
    if not isinstance(items, list): items = [items]
    match, rest = [], []
    for item in items:
        try:
            ok = bool(_safe_eval(expr, {"item": item, "value": item})) if expr else bool(item)
        except Exception: ok = False
        (match if ok else rest).append(item)
    return {"match": match, "rest": rest}
