"""
Blender script — reduce a mesh's polygon count and export it as GLB.

Run by the "blender-decimate" Model Hub endpoint:
    blender --background --factory-startup --python blender_decimate.py -- <input> <output.glb> <ratio>

<ratio> is the fraction of faces to keep (0.5 = half).
"""
import sys

import bpy


def _import(path: str) -> None:
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == "obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=path)
        else:
            bpy.ops.import_scene.obj(filepath=path)
    elif ext == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == "stl":
        if hasattr(bpy.ops.wm, "stl_import"):
            bpy.ops.wm.stl_import(filepath=path)
        else:
            bpy.ops.import_mesh.stl(filepath=path)
    else:
        raise SystemExit(f"Unsupported input format: .{ext}")


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, dst = argv[0], argv[1]
    ratio = max(0.01, min(1.0, float(argv[2]) if len(argv) > 2 else 0.5))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    _import(src)

    for obj in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
        bpy.context.view_layer.objects.active = obj
        mod = obj.modifiers.new(name="Decimate", type="DECIMATE")
        mod.ratio = ratio
        bpy.ops.object.modifier_apply(modifier=mod.name)

    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB")


main()
