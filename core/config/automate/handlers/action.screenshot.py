def _h_action_screenshot(node, inputs, ctx):
    try: import mss as _mss, mss.tools as _mss_tools
    except ImportError: raise RuntimeError("mss not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    monitor_idx = int(p.get("monitor", 0) or 0)
    import tempfile as _tf, os as _os
    if not path:
        path = _os.path.join(_tf.gettempdir(), f"screenshot_{_ts().replace(':','').replace('.','')}.png")
    try:
        with _mss.mss() as sct:
            mon = sct.monitors[monitor_idx] if monitor_idx < len(sct.monitors) else sct.monitors[0]
            img = sct.grab(mon)
            _mss_tools.to_png(img.rgb, img.size, output=path)
        return {"out": path, "image": path, "width": img.width, "height": img.height, "error": ""}
    except Exception as exc:
        return {"out": "", "image": "", "width": 0, "height": 0, "error": str(exc)}
