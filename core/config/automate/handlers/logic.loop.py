def _h_logic_loop(node, inputs, ctx):
    p = node.get("properties", {})
    items = inputs.get("in", [])
    max_iter = int(p.get("max_iterations", 100) or 100)
    if isinstance(items, str):
        try: items = json.loads(items)
        except Exception: items = [items]
    if not isinstance(items, list): items = [items]
    items = items[:max_iter]
    return {"item": items[0] if items else None, "done": len(items) == 0}
