def _h_data_parse_json(node, inputs, ctx):
    try:
        return {"out": json.loads(_to_str(inputs.get("in", ""))), "error": ""}
    except Exception as exc:
        return {"out": None, "error": str(exc)}
