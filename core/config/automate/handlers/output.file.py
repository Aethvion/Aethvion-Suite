def _h_output_file(node, inputs, ctx):
    import re as _re
    p = node.get("properties", {})
    path = str(p.get("path", "")).strip()
    mode = str(p.get("mode", "overwrite"))
    encoding = str(p.get("encoding", "utf-8"))
    fmt = str(p.get("format", "auto"))
    create_dirs = bool(p.get("create_dirs", True))
    val = inputs.get("in")
    if not path: return {}
    content = val if isinstance(val, str) else json.dumps(val, indent=2, ensure_ascii=False)
    if fmt == "json_pretty" and not isinstance(val, str):
        content = json.dumps(val, indent=2, ensure_ascii=False)
    elif fmt == "lines" and isinstance(val, list):
        content = "\n".join(_to_str(v) for v in val)
    try:
        path = _re.sub(r"\{\{timestamp\}\}", datetime.now().strftime("%Y%m%d_%H%M%S"), path)
        if create_dirs: os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a" if mode == "append" else "w", encoding=encoding) as f: f.write(content)
    except Exception as exc:
        ctx._error(f"[Output.File] {exc}")
    return {}
