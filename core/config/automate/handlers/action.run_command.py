def _h_action_run_command(node, inputs, ctx):
    import subprocess as _sp
    p = node.get("properties", {})
    cmd = _to_str(inputs.get("cmd") or p.get("command", "")).strip()
    working_dir = str(p.get("working_dir", "")).strip() or None
    shell = bool(p.get("shell", False))
    timeout = int(p.get("timeout", 30) or 30)
    if not cmd: return {"out": "", "stderr": "", "exit_code": -1, "error": "No command"}
    try:
        res = _sp.run(cmd if shell else cmd.split(), shell=shell, capture_output=True, text=True,
                      cwd=working_dir, timeout=timeout)
        return {"out": res.stdout, "stderr": res.stderr, "exit_code": res.returncode, "error": ""}
    except Exception as exc:
        return {"out": "", "stderr": "", "exit_code": -1, "error": str(exc)}
