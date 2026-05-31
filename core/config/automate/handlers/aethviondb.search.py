def _h_aethviondb_search(node, inputs, ctx):
    import time as _time
    p = node.get("properties", {})
    query = _to_str(inputs.get("in", "")).strip()
    db_name = str(p.get("database", "default")).strip() or "default"
    entity_type = str(p.get("entity_type", "")).strip()
    limit = max(1, int(p.get("limit", 10) or 10))
    min_score = float(p.get("min_score", 0.0) or 0.0)
    if not query: return {"out": "[]", "count": 0, "speed": "0ms", "error": "No query"}
    data_dir = Path(__file__).parent / "data" / "aethviondb" / db_name / "entities"
    if not data_dir.exists():
        return {"out": "[]", "count": 0, "speed": "0ms", "error": f"Database '{db_name}' not found in bundle"}
    t0 = _time.perf_counter()
    entities = []
    for fp in data_dir.glob("*.json"):
        try: entities.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception: pass
    if entity_type: entities = [e for e in entities if e.get("type") == entity_type]
    def _score(e):
        if not query: return 1.0
        q = query.lower()
        core = e.get("sections", {}).get("core", {})
        name = e.get("name","").lower(); summary = core.get("summary","").lower()
        aliases = " ".join(core.get("aliases",[])).lower(); tags = " ".join(core.get("tags",[])).lower()
        if name == q: return 1.0
        if q in name: return 0.90
        if q in summary[:400]: return 0.70
        if q in aliases: return 0.65
        if q in tags: return 0.60
        words = q.split()
        if len(words) > 1:
            hay = f"{name} {summary[:600]} {aliases} {tags}"
            matched = sum(1 for w in words if w in hay)
            if matched: return round(0.5 * matched / len(words), 3)
        return 0.0
    scored = [(e, _score(e)) for e in entities]
    scored = [(e, s) for e, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)
    results = []
    for e, s in scored[:limit]:
        core = e.get("sections", {}).get("core", {})
        results.append({"id": e.get("id",""), "name": e.get("name",""), "type": e.get("type",""),
                         "summary": core.get("summary",""), "tags": core.get("tags",[]), "_score": round(s,3)})
    elapsed = round((_time.perf_counter() - t0) * 1000, 2)
    return {"out": json.dumps(results, ensure_ascii=False), "count": len(results), "speed": f"{elapsed}ms", "error": ""}
