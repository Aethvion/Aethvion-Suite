def _h_memory_search_semantic(node, inputs, ctx):
    p = node.get("properties", {})
    query = _to_str(inputs.get("in", "")).lower()
    limit = int(p.get("limit", 5) or 5)
    min_score = float(p.get("min_score", 0.0) or 0.0)
    results = []
    for k, v in _MEMORY_STORE.items():
        score = 1.0 if query in k.lower() else (0.3 if any(w in k.lower() for w in query.split()) else 0.0)
        if score >= min_score: results.append({"key": k, "value": v, "_score": score})
    results.sort(key=lambda x: x["_score"], reverse=True)
    out = results[:limit]
    return {"out": json.dumps(out, ensure_ascii=False), "count": len(out), "error": ""}
