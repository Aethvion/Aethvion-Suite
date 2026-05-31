def _h_action_file_write(node, inputs, ctx):
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    mode = str(p.get("mode", "overwrite"))
    encoding = str(p.get("encoding", "utf-8"))
    newline = bool(p.get("newline", True))
    create_dirs = bool(p.get("create_dirs", True))
    content = _to_str(inputs.get("in", ""))
    if not path: return {"out": content, "path": "", "error": "No path"}
    try:
        import os.path as _op
        path = _op.expandvars(_op.expanduser(path))
        if create_dirs: os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        file_mode = "a" if mode == "append" else "w"
        if mode == "prepend":
            try: existing = open(path, encoding=encoding).read()
            except Exception: existing = ""
            content = content + ("\n" if newline else "") + existing
            file_mode = "w"
        with open(path, file_mode, encoding=encoding) as f:
            f.write(content)
            if newline and not content.endswith("\n"): f.write("\n")
        return {"out": content, "path": path, "error": ""}
    except Exception as exc:
        return {"out": content, "path": path, "error": str(exc)}
