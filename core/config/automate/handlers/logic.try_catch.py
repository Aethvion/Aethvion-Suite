def _h_logic_try_catch(node, inputs, ctx):
    p = node.get("properties", {})
    in_val = inputs.get("in")
    error_in = inputs.get("error_in")
    filter_str = str(p.get("error_contains", "")).strip()
    if error_in is not None:
        if filter_str and filter_str not in str(error_in):
            return {"try": None, "catch": None, "always": error_in}
        return {"try": None, "catch": error_in, "always": error_in}
    return {"try": in_val, "catch": None, "always": in_val}
