"""
core/modelhub/glb.py
Dependency-free helpers for binary glTF (.glb) and Wavefront OBJ files.

Used by:
    • the mesh.inspect node  — deterministic facts about a mesh (triangles, UVs, textures…)
    • the demo endpoints     — build a placeholder mesh / apply a texture without a GPU

Only the container format is handled here (JSON chunk + BIN chunk).  No geometry
processing is done; for that, plug Blender or another tool in as a `command` endpoint.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any, Optional

_GLB_MAGIC  = 0x46546C67   # "glTF"
_CHUNK_JSON = 0x4E4F534A   # "JSON"
_CHUNK_BIN  = 0x004E4942   # "BIN\0"


class MeshFormatError(ValueError):
    pass


# GLB container

def parse_glb(data: bytes) -> tuple[dict, bytes]:
    """Split a .glb into (gltf_json, binary_chunk)."""
    if len(data) < 20:
        raise MeshFormatError("File too small to be a GLB")
    magic, version, _length = struct.unpack_from("<III", data, 0)
    if magic != _GLB_MAGIC:
        raise MeshFormatError("Not a GLB file (bad magic)")
    if version != 2:
        raise MeshFormatError(f"Unsupported glTF version {version}")

    gltf: Optional[dict] = None
    bin_chunk = b""
    offset = 12
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset: offset + chunk_len]
        offset += chunk_len
        if chunk_type == _CHUNK_JSON:
            gltf = json.loads(chunk.decode("utf-8"))
        elif chunk_type == _CHUNK_BIN and not bin_chunk:
            bin_chunk = bytes(chunk)
    if gltf is None:
        raise MeshFormatError("GLB has no JSON chunk")
    return gltf, bin_chunk


def build_glb(gltf: dict, bin_chunk: bytes) -> bytes:
    """Assemble a .glb from a glTF JSON dict and its binary buffer."""
    bin_chunk = bin_chunk + b"\x00" * ((4 - len(bin_chunk) % 4) % 4)
    if gltf.get("buffers"):
        gltf["buffers"][0]["byteLength"] = len(bin_chunk)
    elif bin_chunk:
        gltf["buffers"] = [{"byteLength": len(bin_chunk)}]

    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)

    total = 12 + 8 + len(js) + (8 + len(bin_chunk) if bin_chunk else 0)
    out = bytearray(struct.pack("<III", _GLB_MAGIC, 2, total))
    out += struct.pack("<II", len(js), _CHUNK_JSON) + js
    if bin_chunk:
        out += struct.pack("<II", len(bin_chunk), _CHUNK_BIN) + bin_chunk
    return bytes(out)


# Inspection

def _glb_stats(data: bytes) -> dict:
    gltf, bin_chunk = parse_glb(data)
    accessors = gltf.get("accessors", [])
    views     = gltf.get("bufferViews", [])

    vertices = triangles = primitives = 0
    has_uv = has_normals = has_colors = has_tangents = False
    untextured_prims = 0
    bb_min: list[float] | None = None
    bb_max: list[float] | None = None
    materials = gltf.get("materials", [])

    def _mat_has_texture(idx: Any) -> bool:
        if not isinstance(idx, int) or idx >= len(materials):
            return False
        pbr = materials[idx].get("pbrMetallicRoughness", {})
        return "baseColorTexture" in pbr

    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            primitives += 1
            attrs = prim.get("attributes", {})
            pos = attrs.get("POSITION")
            pos_count = 0
            if isinstance(pos, int) and pos < len(accessors):
                acc = accessors[pos]
                pos_count = int(acc.get("count", 0))
                vertices += pos_count
                mn, mx = acc.get("min"), acc.get("max")
                if isinstance(mn, list) and isinstance(mx, list) and len(mn) == 3 and len(mx) == 3:
                    bb_min = mn[:] if bb_min is None else [min(a, b) for a, b in zip(bb_min, mn)]
                    bb_max = mx[:] if bb_max is None else [max(a, b) for a, b in zip(bb_max, mx)]
            has_uv       |= "TEXCOORD_0" in attrs
            has_normals  |= "NORMAL" in attrs
            has_colors   |= "COLOR_0" in attrs
            has_tangents |= "TANGENT" in attrs
            if not _mat_has_texture(prim.get("material")):
                untextured_prims += 1

            mode = prim.get("mode", 4)
            idx = prim.get("indices")
            n = int(accessors[idx].get("count", 0)) if isinstance(idx, int) and idx < len(accessors) else pos_count
            if mode == 4:
                triangles += n // 3
            elif mode in (5, 6):
                triangles += max(0, n - 2)

    images = []
    for i, img in enumerate(gltf.get("images", [])):
        entry = {"index": i, "name": img.get("name", f"image_{i}"),
                 "mime": img.get("mimeType", ""), "embedded": False, "size_bytes": 0}
        bv = img.get("bufferView")
        if isinstance(bv, int) and bv < len(views):
            entry["embedded"]   = True
            entry["size_bytes"] = int(views[bv].get("byteLength", 0))
        images.append(entry)

    size = [round(b - a, 5) for a, b in zip(bb_min, bb_max)] if bb_min and bb_max else None
    return {
        "format":        "glb",
        "vertices":      vertices,
        "triangles":     triangles,
        "meshes":        len(gltf.get("meshes", [])),
        "primitives":    primitives,
        "nodes":         len(gltf.get("nodes", [])),
        "materials":     len(materials),
        "textures":      len(gltf.get("textures", [])),
        "images":        images,
        "animations":    len(gltf.get("animations", [])),
        "skins":         len(gltf.get("skins", [])),
        "has_uvs":       has_uv,
        "has_normals":   has_normals,
        "has_vertex_colors": has_colors,
        "has_tangents":  has_tangents,
        "is_textured":   primitives > 0 and untextured_prims == 0,
        "bounds_min":    bb_min,
        "bounds_max":    bb_max,
        "size":          size,
        "generator":     gltf.get("asset", {}).get("generator", ""),
    }


def _obj_stats(text: str) -> dict:
    v = vt = vn = faces = tris = 0
    mats: set[str] = set()
    for line in text.splitlines():
        if line.startswith("v "):
            v += 1
        elif line.startswith("vt "):
            vt += 1
        elif line.startswith("vn "):
            vn += 1
        elif line.startswith("f "):
            faces += 1
            tris += max(1, len(line.split()) - 3)
        elif line.startswith("usemtl "):
            mats.add(line[7:].strip())
    return {
        "format": "obj", "vertices": v, "triangles": tris, "faces": faces,
        "materials": len(mats), "textures": 0, "images": [],
        "has_uvs": vt > 0, "has_normals": vn > 0, "is_textured": False,
        "animations": 0, "skins": 0,
    }


def inspect_mesh(path: str | Path) -> dict:
    """Return deterministic facts about a mesh file.  Never raises for unknown formats."""
    p = Path(path)
    ext = p.suffix.lower().lstrip(".")
    base = {"file": p.name, "format": ext, "size_bytes": p.stat().st_size}
    try:
        if ext == "glb":
            base.update(_glb_stats(p.read_bytes()))
        elif ext == "obj":
            base.update(_obj_stats(p.read_text(encoding="utf-8", errors="replace")))
        else:
            base["note"] = (f"Detailed inspection supports .glb and .obj; '.{ext}' files report "
                            "size only. Convert with a mesh.process endpoint (e.g. Blender).")
    except MeshFormatError as exc:
        base["error"] = str(exc)
    return base


def extract_images(path: str | Path) -> list[tuple[str, str, bytes]]:
    """Return [(name, mime, bytes)] for every texture image embedded in a .glb."""
    p = Path(path)
    if p.suffix.lower() != ".glb":
        return []
    gltf, bin_chunk = parse_glb(p.read_bytes())
    views = gltf.get("bufferViews", [])
    out = []
    for i, img in enumerate(gltf.get("images", [])):
        bv = img.get("bufferView")
        if not isinstance(bv, int) or bv >= len(views):
            continue
        view  = views[bv]
        start = int(view.get("byteOffset", 0))
        blob  = bin_chunk[start: start + int(view.get("byteLength", 0))]
        if blob:
            out.append((img.get("name", f"texture_{i}"), img.get("mimeType", "image/png"), blob))
    return out


# Building — used by the demo endpoints

def make_box_glb(size: tuple[float, float, float] = (1.0, 1.0, 1.0), name: str = "Box") -> bytes:
    """A unit-style box with normals and UVs (24 vertices, 12 triangles), untextured."""
    hx, hy, hz = (s / 2 for s in size)
    # face: (normal, 4 corners counter-clockwise seen from outside)
    faces = [
        (( 0,  0,  1), [(-hx, -hy,  hz), ( hx, -hy,  hz), ( hx,  hy,  hz), (-hx,  hy,  hz)]),
        (( 0,  0, -1), [( hx, -hy, -hz), (-hx, -hy, -hz), (-hx,  hy, -hz), ( hx,  hy, -hz)]),
        (( 1,  0,  0), [( hx, -hy,  hz), ( hx, -hy, -hz), ( hx,  hy, -hz), ( hx,  hy,  hz)]),
        ((-1,  0,  0), [(-hx, -hy, -hz), (-hx, -hy,  hz), (-hx,  hy,  hz), (-hx,  hy, -hz)]),
        (( 0,  1,  0), [(-hx,  hy,  hz), ( hx,  hy,  hz), ( hx,  hy, -hz), (-hx,  hy, -hz)]),
        (( 0, -1,  0), [(-hx, -hy, -hz), ( hx, -hy, -hz), ( hx, -hy,  hz), (-hx, -hy,  hz)]),
    ]
    uv_quad = [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]
    pos, nrm, uvs, idx = [], [], [], []
    for f, (n, corners) in enumerate(faces):
        for c, uv in zip(corners, uv_quad):
            pos.extend(c); nrm.extend(n); uvs.extend(uv)
        b = f * 4
        idx.extend([b, b + 1, b + 2, b, b + 2, b + 3])

    pos_b = struct.pack(f"<{len(pos)}f", *pos)
    nrm_b = struct.pack(f"<{len(nrm)}f", *nrm)
    uv_b  = struct.pack(f"<{len(uvs)}f", *uvs)
    idx_b = struct.pack(f"<{len(idx)}H", *idx)
    blob  = pos_b + nrm_b + uv_b + idx_b

    o1, o2, o3 = len(pos_b), len(pos_b) + len(nrm_b), len(pos_b) + len(nrm_b) + len(uv_b)
    gltf = {
        "asset": {"version": "2.0", "generator": "Aethvion Suite demo endpoint"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
            "indices": 3, "material": 0, "mode": 4,
        }]}],
        "materials": [{"name": "Default", "pbrMetallicRoughness": {
            "baseColorFactor": [0.8, 0.8, 0.8, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.8}}],
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0,  "byteLength": len(pos_b), "target": 34962},
            {"buffer": 0, "byteOffset": o1, "byteLength": len(nrm_b), "target": 34962},
            {"buffer": 0, "byteOffset": o2, "byteLength": len(uv_b),  "target": 34962},
            {"buffer": 0, "byteOffset": o3, "byteLength": len(idx_b), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 24, "type": "VEC3",
             "min": [-hx, -hy, -hz], "max": [hx, hy, hz]},
            {"bufferView": 1, "componentType": 5126, "count": 24, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 24, "type": "VEC2"},
            {"bufferView": 3, "componentType": 5123, "count": 36, "type": "SCALAR"},
        ],
    }
    return build_glb(gltf, blob)


def apply_base_color_texture(glb_data: bytes, image_bytes: bytes, mime: str = "image/png",
                             name: str = "BaseColor") -> bytes:
    """Embed *image_bytes* in a GLB and use it as the base-colour texture of every primitive."""
    gltf, bin_chunk = parse_glb(glb_data)
    bin_chunk = bin_chunk + b"\x00" * ((4 - len(bin_chunk) % 4) % 4)

    views = gltf.setdefault("bufferViews", [])
    views.append({"buffer": 0, "byteOffset": len(bin_chunk), "byteLength": len(image_bytes)})
    bin_chunk += image_bytes

    images = gltf.setdefault("images", [])
    images.append({"name": name, "mimeType": mime, "bufferView": len(views) - 1})
    samplers = gltf.setdefault("samplers", [])
    samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
    textures = gltf.setdefault("textures", [])
    textures.append({"source": len(images) - 1, "sampler": len(samplers) - 1})

    materials = gltf.setdefault("materials", [])
    materials.append({"name": f"{name}Material", "pbrMetallicRoughness": {
        "baseColorTexture": {"index": len(textures) - 1},
        "baseColorFactor": [1.0, 1.0, 1.0, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.7}})
    mat_idx = len(materials) - 1
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            prim["material"] = mat_idx
    return build_glb(gltf, bin_chunk)


def normalize_glb(
    data: bytes,
    *,
    center_xz: bool = True,
    ground_y: bool = True,
    target_size: float = 1.0,
    rotate_y_deg: float = 0.0,
) -> tuple[bytes, dict]:
    """Center X/Z, snap Y-min to 0, uniformly scale to *target_size*, and rotate around Y.

    Pure-Python binary glTF transform that preserves UVs, PBR textures, materials,
    indices, and animations.  Deduplicates accessor indices so shared buffers are
    never transformed twice.
    """
    gltf, bin_chunk = parse_glb(data)
    buf = bytearray(bin_chunk)
    accessors = gltf.get("accessors", [])
    views = gltf.get("bufferViews", [])

    pos_ids: set[int] = set()
    nrm_ids: set[int] = set()
    tan_ids: set[int] = set()
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            attrs = prim.get("attributes", {})
            for key, bucket in (("POSITION", pos_ids), ("NORMAL", nrm_ids), ("TANGENT", tan_ids)):
                idx = attrs.get(key)
                if isinstance(idx, int) and 0 <= idx < len(accessors):
                    bucket.add(idx)

    if not pos_ids:
        return data, _glb_stats(data)

    rad = math.radians(float(rotate_y_deg or 0.0))
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    do_rot = abs(rad) > 1e-7

    def _rot_y(x: float, y: float, z: float) -> tuple[float, float, float]:
        if not do_rot:
            return x, y, z
        return (x * cos_a + z * sin_a, y, -x * sin_a + z * cos_a)

    def _acc_layout(acc_idx: int, expected_comps: int):
        acc = accessors[acc_idx]
        if acc.get("componentType") != 5126:
            return None
        bv_idx = acc.get("bufferView")
        if not isinstance(bv_idx, int) or not (0 <= bv_idx < len(views)):
            return None
        bv = views[bv_idx]
        stride = int(bv.get("byteStride") or (expected_comps * 4))
        base = int(bv.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
        count = int(acc.get("count", 0))
        return acc, base, stride, count

    # Pass 1: compute global bounding box after optional Y rotation
    bb_min = [math.inf, math.inf, math.inf]
    bb_max = [-math.inf, -math.inf, -math.inf]
    any_vert = False

    for idx in pos_ids:
        info = _acc_layout(idx, 3)
        if not info:
            continue
        _acc, base, stride, count = info
        for i in range(count):
            off = base + i * stride
            if off + 12 > len(buf):
                break
            x, y, z = struct.unpack_from("<fff", buf, off)
            rx, ry, rz = _rot_y(x, y, z)
            any_vert = True
            if rx < bb_min[0]: bb_min[0] = rx
            if ry < bb_min[1]: bb_min[1] = ry
            if rz < bb_min[2]: bb_min[2] = rz
            if rx > bb_max[0]: bb_max[0] = rx
            if ry > bb_max[1]: bb_max[1] = ry
            if rz > bb_max[2]: bb_max[2] = rz

    if not any_vert:
        return data, _glb_stats(data)

    extents = [bb_max[0] - bb_min[0], bb_max[1] - bb_min[1], bb_max[2] - bb_min[2]]
    max_extent = max(extents)
    scale = (float(target_size) / max_extent) if (target_size and target_size > 0 and max_extent > 1e-8) else 1.0
    tx = -0.5 * (bb_min[0] + bb_max[0]) * scale if center_xz else 0.0
    ty = -bb_min[1] * scale if ground_y else 0.0
    tz = -0.5 * (bb_min[2] + bb_max[2]) * scale if center_xz else 0.0

    # Pass 2: write transformed positions and update per-accessor min/max
    for idx in pos_ids:
        info = _acc_layout(idx, 3)
        if not info:
            continue
        acc, base, stride, count = info
        a_min = [math.inf, math.inf, math.inf]
        a_max = [-math.inf, -math.inf, -math.inf]
        for i in range(count):
            off = base + i * stride
            if off + 12 > len(buf):
                break
            x, y, z = struct.unpack_from("<fff", buf, off)
            rx, ry, rz = _rot_y(x, y, z)
            nx, ny, nz = rx * scale + tx, ry * scale + ty, rz * scale + tz
            struct.pack_into("<fff", buf, off, nx, ny, nz)
            if nx < a_min[0]: a_min[0] = nx
            if ny < a_min[1]: a_min[1] = ny
            if nz < a_min[2]: a_min[2] = nz
            if nx > a_max[0]: a_max[0] = nx
            if ny > a_max[1]: a_max[1] = ny
            if nz > a_max[2]: a_max[2] = nz
        if count > 0 and all(math.isfinite(v) for v in a_min + a_max):
            acc["min"] = [round(v, 6) for v in a_min]
            acc["max"] = [round(v, 6) for v in a_max]

    if do_rot:
        for idx in nrm_ids:
            info = _acc_layout(idx, 3)
            if not info:
                continue
            _acc, base, stride, count = info
            for i in range(count):
                off = base + i * stride
                if off + 12 > len(buf):
                    break
                nx, ny, nz = struct.unpack_from("<fff", buf, off)
                rx, ry, rz = _rot_y(nx, ny, nz)
                struct.pack_into("<fff", buf, off, rx, ry, rz)
        for idx in tan_ids:
            info = _acc_layout(idx, 4)
            if not info:
                continue
            _acc, base, stride, count = info
            for i in range(count):
                off = base + i * stride
                if off + 16 > len(buf):
                    break
                txv, tyv, tzv, twv = struct.unpack_from("<ffff", buf, off)
                rx, ry, rz = _rot_y(txv, tyv, tzv)
                struct.pack_into("<ffff", buf, off, rx, ry, rz, twv)

    out_bytes = build_glb(gltf, bytes(buf))
    return out_bytes, _glb_stats(out_bytes)
