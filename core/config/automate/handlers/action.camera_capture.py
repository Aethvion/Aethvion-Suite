def _h_action_camera_capture(node, inputs, ctx):
    try: import cv2 as _cv2
    except ImportError: raise RuntimeError("opencv-python not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    cam_idx = int(p.get("camera_index", 0) or 0)
    w = int(p.get("width", 1280) or 1280)
    h = int(p.get("height", 720) or 720)
    import tempfile as _tf, os as _os
    if not path:
        path = _os.path.join(_tf.gettempdir(), f"capture_{_ts().replace(':','').replace('.','')}.jpg")
    cap = _cv2.VideoCapture(cam_idx)
    try:
        cap.set(_cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(_cv2.CAP_PROP_FRAME_HEIGHT, h)
        ok, frame = cap.read()
        if not ok: return {"out": "", "image": "", "width": 0, "height": 0, "error": "Could not read camera"}
        _cv2.imwrite(path, frame)
        return {"out": path, "image": path, "width": frame.shape[1], "height": frame.shape[0], "error": ""}
    except Exception as exc:
        return {"out": "", "image": "", "width": 0, "height": 0, "error": str(exc)}
    finally:
        cap.release()
