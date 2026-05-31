def _h_action_file_list(node, inputs, ctx):
    from pathlib import Path as _P
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    pattern = str(p.get("pattern", "*"))
    recursive = bool(p.get("recursive", False))
    include_dirs = bool(p.get("include_dirs", False))
    sort_by = str(p.get("sort_by", "name"))
    output_as = str(p.get("output_as", "paths"))
    if not path: return {"out": [], "count": 0, "error": "No path"}
    try:
        base = _P(path)
        files = list(base.rglob(pattern) if recursive else base.glob(pattern))
        if not include_dirs: files = [f for f in files if f.is_file()]
        if sort_by == "size": files.sort(key=lambda f: f.stat().st_size)
        elif sort_by == "modified": files.sort(key=lambda f: f.stat().st_mtime)
        else: files.sort(key=lambda f: f.name)
        if output_as == "objects":
            out = [{"path": str(f), "name": f.name, "size": f.stat().st_size if f.is_file() else 0} for f in files]
        else:
            out = [str(f) for f in files]
        return {"out": out, "count": len(out), "error": ""}
    except Exception as exc:
        return {"out": [], "count": 0, "error": str(exc)}
