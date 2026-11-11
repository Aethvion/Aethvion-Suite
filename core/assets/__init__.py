"""
core/assets — the Asset Library.

    from core.assets import store, values
    rec = store.create_from_bytes(png_bytes, ext="png", name="sword concept")
    ref = store.asset_ref(rec)          # the value that flows along workflow wires
"""
from . import store, values  # noqa: F401
