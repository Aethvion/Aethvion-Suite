def _h_aethviondb_snapshot_search(node, inputs, ctx):
    import time as _time
    p = node.get("properties", {})
    query = _to_str(inputs.get("in", "")).strip()
    db_name = str(p.get("database", "default")).strip() or "default"
    snap_name = str(p.get("snapshot", "")).strip()
    entity_type = str(p.get("entity_type", "")).strip()
    limit = max(1, int(p.get("limit", 10) or 10))
    min_score = float(p.get("min_score", 0.0) or 0.0)
    if not query: return {"out": "[]", "count": 0, "speed": "0ms", "error": "No query"}
    baked_dir = Path(__file__).parent / "data" / "aethviondb" / db_name / "baked"
    if not baked_dir.exists():
        return {"out": "[]", "count": 0, "speed": "0ms", "error": f"No snapshots for '{db_name}' in bundle"}
    snap_files = sorted(baked_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if snap_name:
        snap_files = [f for f in snap_files if f.stem == snap_name] or snap_files
    if not snap_files:
        return {"out": "[]", "count": 0, "speed": "0ms", "error": "No snapshot found"}
    t0 = _time.perf_counter()
    entities = []
    for line in snap_files[0].read_text(encoding="utf-8").splitlines():
        if line.strip():
            try: entities.append(json.loads(line))
            except Exception: pass
    if entity_type: entities = [e for e in entities if e.get("type") == entity_type]
    def _score(e):
        if not query: return 1.0
        q = query.lower()
        name = e.get("name","").lower(); summary = e.get("summary","").lower()
        tags = " ".join(e.get("tags",[])).lower(); aliases = " ".join(e.get("aliases",[])).lower()
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
    results = [{**e, "_score": round(s,3)} for e, s in scored[:limit]]
    elapsed = round((_time.perf_counter() - t0) * 1000, 2)
    return {"out": json.dumps(results, ensure_ascii=False), "count": len(results), "speed": f"{elapsed}ms", "error": ""}
