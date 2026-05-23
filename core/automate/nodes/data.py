"""
core/automate/nodes/data.py
════════════════════════════
Handler functions for all data.* and transform.* node types.
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from ._utils import _to_str, _safe_eval


def data_format_text(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p        = node.get("properties", {})
    template = str(p.get("template", "{{input}}"))
    in_val   = _to_str(inputs.get("in", ""))
    out      = template.replace("{{input}}", in_val)
    # Also substitute any workflow variables set by data.set_variable nodes
    for k, v in ctx._vars.items():
        out = out.replace("{{" + k + "}}", _to_str(v))
    return {"out": out}


def data_parse_json(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    raw = _to_str(inputs.get("in", ""))
    try:
        return {"out": json.loads(raw), "error": ""}
    except json.JSONDecodeError as exc:
        return {"out": None, "error": str(exc)}


def data_set_variable(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p     = node.get("properties", {})
    name  = str(p.get("name", "var")).strip() or "var"
    value = inputs.get("in", "")
    ctx._vars[name] = value   # persists for the duration of this workflow run
    return {"out": value}


def data_filter(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p     = node.get("properties", {})
    items = inputs.get("in", [])
    if not isinstance(items, list):
        try:
            items = json.loads(_to_str(items))
        except Exception:
            items = [items]

    expr = str(p.get("expression", "")).strip()
    if not expr:
        return {"match": items, "rest": []}

    match, rest = [], []
    for item in items:
        try:
            ok = bool(_safe_eval(expr, {"item": item}))
        except Exception:
            ok = False
        (match if ok else rest).append(item)

    return {"match": match, "rest": rest}


def transform_combine(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p   = node.get("properties", {})
    a   = _to_str(inputs.get("a", ""))
    b   = _to_str(inputs.get("b", ""))
    sep = str(p.get("separator", "\\n")).replace("\\n", "\n").replace("\\t", "\t")
    return {"out": a + sep + b}


def data_template(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p        = node.get("properties", {})
    template = str(p.get("template", ""))
    in_val   = inputs.get("in", "")

    variables: dict[str, str] = {}

    # Expand JSON input object into template variables
    if isinstance(in_val, dict):
        variables.update({str(k): _to_str(v) for k, v in in_val.items()})
    else:
        raw_in = _to_str(in_val)
        try:
            obj = json.loads(raw_in)
            if isinstance(obj, dict):
                variables.update({str(k): _to_str(v) for k, v in obj.items()})
        except Exception:
            pass
        variables["input"] = raw_in

    # Named port overrides (var_a, var_b, var_c)
    for port in ("var_a", "var_b", "var_c"):
        val = inputs.get(port)
        if val is not None:
            variables[port] = _to_str(val)

    def _replacer(m: re.Match) -> str:
        parts   = m.group(1).split("|", 1)
        key     = parts[0].strip()
        default = parts[1] if len(parts) > 1 else ""
        return variables.get(key, default)

    result     = re.sub(r"\{\{([^}]+)\}\}", _replacer, template)
    unresolved = re.findall(r"\{\{[^}]+\}\}", result)
    error      = f"Unresolved: {unresolved}" if unresolved else ""
    return {"out": result, "error": error}


def data_extract_json(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p      = node.get("properties", {})
    in_val = inputs.get("in", "")

    if isinstance(in_val, str):
        try:
            obj = json.loads(in_val)
        except Exception as exc:
            return {"out": p.get("default", ""), "error": f"JSON parse error: {exc}"}
    else:
        obj = in_val

    key_path = str(p.get("key", "")).strip()
    if not key_path:
        return {"out": obj, "error": ""}

    try:
        current = obj
        for part in key_path.split("."):
            if isinstance(current, list):
                current = current[int(part)]
            elif isinstance(current, dict):
                current = current[part]
            else:
                raise KeyError(part)

        mode = str(p.get("output_as", "auto"))
        if mode == "string":
            out = _to_str(current)
        elif mode == "json":
            out = json.dumps(current, ensure_ascii=False)
        else:
            out = current
        return {"out": out, "error": ""}

    except (KeyError, IndexError, TypeError) as exc:
        default = p.get("default", "")
        if default != "":
            return {"out": default, "error": ""}
        return {"out": "", "error": f"Key not found: {key_path} ({exc})"}


def data_type_convert(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p   = node.get("properties", {})
    val = inputs.get("in", "")
    to  = str(p.get("to", "string"))

    try:
        if to == "string":
            out = json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)
        elif to == "integer":
            out = int(float(str(val).strip()))
        elif to == "float":
            out = float(str(val).strip())
        elif to == "boolean":
            s          = str(val).strip().lower()
            true_vals  = [v.strip().lower() for v in str(p.get("true_values",  "true,yes,1,on")).split(",")]
            false_vals = [v.strip().lower() for v in str(p.get("false_values", "false,no,0,off")).split(",")]
            if s in true_vals:
                out = True
            elif s in false_vals:
                out = False
            else:
                out = bool(val)
        elif to == "json":
            out = json.loads(val) if isinstance(val, str) else val
        else:
            out = val
        return {"out": out, "error": ""}
    except Exception as exc:
        return {"out": val, "error": f"Conversion to {to} failed: {exc}"}


def data_split_text(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p            = node.get("properties", {})
    text         = _to_str(inputs.get("in", ""))
    mode         = str(p.get("mode", "delimiter"))
    trim         = bool(p.get("trim", True))
    remove_empty = bool(p.get("remove_empty", True))

    if mode == "lines":
        parts = text.splitlines()
    elif mode == "words":
        parts = text.split()
    elif mode == "chunks":
        size  = max(1, int(p.get("chunk_size", 500) or 500))
        parts = [text[i:i + size] for i in range(0, max(len(text), 1), size)]
    else:  # delimiter
        parts = text.split(str(p.get("delimiter", ",")))

    if trim and mode != "chunks":
        parts = [s.strip() for s in parts]
    if remove_empty:
        parts = [s for s in parts if s]

    first = parts[0]  if parts else ""
    last  = parts[-1] if parts else ""
    return {
        "out":   json.dumps(parts, ensure_ascii=False),
        "first": first,
        "last":  last,
        "count": len(parts),
    }


def data_merge_objects(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p    = node.get("properties", {})
    mode = str(p.get("merge_mode", "shallow"))

    def _parse(val: Any) -> dict:
        if isinstance(val, dict):
            return val
        if val is None:
            return {}
        try:
            result = json.loads(_to_str(val))
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def _deep_merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    merged: dict = {}
    for port in ("a", "b", "c", "d"):
        val = inputs.get(port)
        if val is None:
            continue
        obj = _parse(val)
        if mode == "deep":
            merged = _deep_merge(merged, obj)
        else:
            merged.update(obj)

    out_mode = str(p.get("output_as", "json_string"))
    out = json.dumps(merged, ensure_ascii=False) if out_mode == "json_string" else merged
    return {"out": out, "error": ""}


def data_list_item(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p      = node.get("properties", {})
    in_val = inputs.get("in", "[]")

    if isinstance(in_val, str):
        try:
            lst = json.loads(in_val)
        except Exception as exc:
            return {"out": "", "count": 0, "error": f"Not a valid list: {exc}"}
    else:
        lst = in_val

    if not isinstance(lst, list):
        return {"out": "", "count": 0, "error": "Input is not a list"}

    try:
        idx = int(inputs.get("index") or p.get("index", 0))
    except (ValueError, TypeError):
        idx = 0

    slice_end = int(p.get("slice_end", 0) or 0)

    try:
        if slice_end != 0:
            out = json.dumps(lst[idx:slice_end], ensure_ascii=False)
        else:
            out = lst[idx]
        return {"out": out, "count": len(lst), "error": ""}
    except IndexError:
        return {"out": "", "count": len(lst),
                "error": f"Index {idx} out of range (list has {len(lst)} items)"}


def data_regex(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p        = node.get("properties", {})
    text     = _to_str(inputs.get("in", ""))
    pattern  = _to_str(inputs.get("pattern") or p.get("pattern", ""))
    mode     = str(p.get("mode", "extract"))
    repl     = str(p.get("replacement", ""))
    flag_str = str(p.get("flags", ""))

    flags = 0
    if "i" in flag_str: flags |= re.IGNORECASE
    if "m" in flag_str: flags |= re.MULTILINE
    if "s" in flag_str: flags |= re.DOTALL

    try:
        compiled = re.compile(pattern, flags)
    except re.error as exc:
        return {"out": "", "matches": "[]", "matched": "false", "error": str(exc)}

    if mode == "match":
        found = bool(compiled.search(text))
        return {"out": str(found).lower(), "matches": "[]",
                "matched": str(found).lower(), "error": ""}

    if mode == "replace":
        result  = compiled.sub(repl, text)
        matched = str(bool(compiled.search(text))).lower()
        return {"out": result, "matches": "[]", "matched": matched, "error": ""}

    # extract — findall returns tuples when there are multiple capture groups;
    # flatten each tuple to a single space-joined string for consistent output.
    raw_matches = compiled.findall(text)
    all_m = [(" ".join(m) if isinstance(m, tuple) else str(m)) for m in raw_matches]
    matched = bool(all_m)

    if p.get("all_matches", False):
        out = json.dumps(all_m, ensure_ascii=False)
    else:
        out = all_m[0] if all_m else ""

    return {
        "out":     out,
        "matches": json.dumps(all_m, ensure_ascii=False),
        "matched": str(matched).lower(),
        "error":   "",
    }


def data_csv_parse(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p         = node.get("properties", {})
    raw       = _to_str(inputs.get("in", ""))
    delimiter = str(p.get("delimiter", ","))
    has_hdr   = bool(p.get("has_header", True))
    output_as = str(p.get("output_as", "objects"))   # "objects" or "arrays"
    skip_empty = bool(p.get("skip_empty_rows", True))

    # Un-escape common escape sequences entered in a UI text field
    delimiter = delimiter.replace("\\t", "\t")

    try:
        reader_args = {
            "delimiter": delimiter,
            "skipinitialspace": True,
        }
        reader_obj = csv.reader(io.StringIO(raw), **reader_args)
        all_rows   = list(reader_obj)
    except Exception as exc:
        return {"out": "[]", "rows": 0, "headers": "[]", "error": str(exc)}

    if skip_empty:
        all_rows = [r for r in all_rows if any(cell.strip() for cell in r)]

    if not all_rows:
        return {"out": "[]", "rows": 0, "headers": "[]", "error": ""}

    if has_hdr:
        headers  = all_rows[0]
        data_rows = all_rows[1:]
    else:
        headers   = []
        data_rows = all_rows

    if output_as == "objects" and has_hdr:
        result = [dict(zip(headers, row)) for row in data_rows]
    else:
        result = data_rows

    return {
        "out":     json.dumps(result, ensure_ascii=False),
        "rows":    len(data_rows),
        "headers": json.dumps(headers, ensure_ascii=False),
        "error":   "",
    }
