def _h_input_file(node, inputs, ctx):
    p = node.get("properties", {})
    path = str(p.get("path", "")).strip()
    encoding = str(p.get("encoding", "utf-8"))
    strip = bool(p.get("strip", False))
    if not path: return {"out": "", "path": "", "name": "", "size": 0}
    try:
        import os.path as _op
        path = _op.expandvars(_op.expanduser(path))
        if encoding == "binary":
            data = open(path, "rb").read()
            return {"out": data.hex(), "path": path, "name": _op.basename(path), "size": len(data)}
        content = open(path, encoding=encoding).read()
        if strip: content = content.strip()
        return {"out": content, "path": path, "name": _op.basename(path), "size": len(content)}
    except Exception as exc:
        return {"out": "", "path": path, "name": "", "size": 0, "error": str(exc)}
