def _h_data_csv_parse(node, inputs, ctx):
    import csv as _csv, io as _io
    p = node.get("properties", {})
    text = _to_str(inputs.get("in", ""))
    delim = str(p.get("delimiter", ","))
    if delim == "\\t": delim = "\t"
    has_header = bool(p.get("has_header", True))
    output_as = str(p.get("output_as", "objects"))
    skip_empty = bool(p.get("skip_empty_rows", True))
    rows = list(_csv.reader(_io.StringIO(text), delimiter=delim))
    if skip_empty: rows = [r for r in rows if any(c.strip() for c in r)]
    if has_header and rows:
        headers = rows[0]; data_rows = rows[1:]
    else:
        headers = []; data_rows = rows
    out = [dict(zip(headers, r)) for r in data_rows] if (output_as == "objects" and has_header) else data_rows
    return {"out": out, "rows": len(data_rows), "headers": headers, "error": ""}
