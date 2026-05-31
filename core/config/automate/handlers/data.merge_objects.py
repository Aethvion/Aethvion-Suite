def _h_data_merge_objects(node, inputs, ctx):
    p = node.get("properties", {})
    mode = str(p.get("merge_mode", "shallow"))
    output_as = str(p.get("output_as", "json_string"))
    result = {}
    def _deep(base, overlay):
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict): _deep(base[k], v)
            else: base[k] = v
    for key in ("a", "b", "c", "d"):
        val = inputs.get(key)
        if val is None: continue
        if isinstance(val, str):
            try: val = json.loads(val)
            except Exception: continue
        if isinstance(val, dict):
            if mode == "deep": _deep(result, val)
            else: result.update(val)
    out = result if output_as == "object" else json.dumps(result, ensure_ascii=False)
    return {"out": out, "error": ""}
