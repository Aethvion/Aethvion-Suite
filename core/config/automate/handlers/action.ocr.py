def _h_action_ocr(node, inputs, ctx):
    try: import pytesseract as _tess; from PIL import Image as _Image
    except ImportError: raise RuntimeError("pytesseract/Pillow not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    image_path = _to_str(inputs.get("image") or p.get("image_path", "")).strip()
    lang = str(p.get("language", "eng"))
    config = str(p.get("config", "")).strip()
    if not image_path: return {"out": "", "error": "No image path"}
    try:
        img = _Image.open(image_path)
        text = _tess.image_to_string(img, lang=lang, config=config)
        return {"out": text.strip(), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
