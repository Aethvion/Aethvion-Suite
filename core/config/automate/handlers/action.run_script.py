def _h_action_run_script(node, inputs, ctx):
    script = str(node.get("properties", {}).get("script", ""))
    ns = {"input_data": inputs.get("in"), "inputs": inputs, "ctx": ctx, "json": json, "result": None}
    try:
        exec(script, ns)
        return {"out": ns.get("result", inputs.get("in")), "error": ""}
    except Exception as exc:
        return {"out": None, "error": str(exc)}
