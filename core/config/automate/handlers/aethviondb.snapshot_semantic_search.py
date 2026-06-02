def _h_aethviondb_snapshot_semantic_search(node, inputs, ctx):
    import time as _time, math as _math
    p = node.get("properties", {})
    query = _to_str(inputs.get("in", "")).strip()
    db_name = str(p.get("database", "default")).strip() or "default"
    snap_name = str(p.get("snapshot", "")).strip()
    model = str(p.get("model", "text-embedding-004")).strip() or "text-embedding-004"
    entity_type = str(p.get("entity_type", "")).strip()
    limit = max(1, int(p.get("limit", 10) or 10))
    min_score = float(p.get("min_score", 0.5) or 0.0)
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
    # Embed query
    _openai_models = {"text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"}
    try:
        if model in _openai_models:
            from openai import OpenAI as _OAI
            _api_key = os.environ.get("OPENAI_API_KEY", "")
            if not _api_key: raise RuntimeError("OPENAI_API_KEY is not set")
            _resp = _OAI(api_key=_api_key).embeddings.create(model=model, input=query)
            query_vec = _resp.data[0].embedding
        else:
            from google import genai as _genai
            _api_key = os.environ.get("GOOGLE_AI_API_KEY", "")
            if not _api_key: raise RuntimeError("GOOGLE_AI_API_KEY is not set")
            _client = _genai.Client(api_key=_api_key, http_options={"api_version": "v1"})
            _result = _client.models.embed_content(model=model, contents=query)
            if not _result or not _result.embeddings:
                raise RuntimeError("Empty embedding response")
            query_vec = list(_result.embeddings[0].values)
    except Exception as exc:
        return {"out": "[]", "count": 0, "speed": "0ms", "error": f"Embedding failed ({model}): {exc}"}
    # Load entities from snapshot
    entities = []
    for line in snap_files[0].read_text(encoding="utf-8").splitlines():
        if line.strip():
            try: entities.append(json.loads(line))
            except Exception: pass
    if entity_type: entities = [e for e in entities if e.get("type") == entity_type]
    # Cosine similarity (baked format: entity["vectors"][model]["embedding"])
    def _cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        ma = _math.sqrt(sum(x * x for x in a))
        mb = _math.sqrt(sum(x * x for x in b))
        return dot / (ma * mb) if ma and mb else 0.0
    scored = []
    no_vec = 0
    for e in entities:
        vd = (e.get("vectors") or {}).get(model)
        emb = vd.get("embedding") if isinstance(vd, dict) else None
        if not emb: no_vec += 1; continue
        sc = _cosine(query_vec, emb)
        if sc >= min_score: scored.append((e, sc))
    scored.sort(key=lambda x: x[1], reverse=True)
    results = [{**e, "_score": round(s, 4)} for e, s in scored[:limit]]
    elapsed = round((_time.perf_counter() - t0) * 1000, 2)
    warn = (f"{no_vec} entity/entities had no '{model}' embedding — bake with include_vectors=True." if no_vec else "")
    return {"out": json.dumps(results, ensure_ascii=False), "count": len(results), "speed": f"{elapsed}ms", "error": warn}
