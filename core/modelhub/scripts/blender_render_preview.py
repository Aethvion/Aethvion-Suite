"""
Blender script — render a lit three-quarter preview of a mesh to a PNG.

Run by the "blender-render-preview" Model Hub endpoint:
    blender --background --factory-startup --python blender_render_preview.py -- <input> <output.png> <resolution>
"""
import math
import sys

import bpy
from mathutils import Vector


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
    else:
        raise SystemExit(f"Unsupported input format: .{ext}")


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, dst = argv[0], argv[1]
    res = int(float(argv[2])) if len(argv) > 2 else 768

    bpy.ops.wm.read_factory_settings(use_empty=True)
    _import(src)
    scene = bpy.context.scene

    # Bounding sphere of everything imported
    points = []
    for obj in scene.objects:
        if obj.type == "MESH":
            points.extend(obj.matrix_world @ Vector(c) for c in obj.bound_box)
    if not points:
        raise SystemExit("No mesh objects found in the file")
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    centre = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 0.001)

    # Camera on a three-quarter angle, aimed at the centre
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    direction = Vector((1.0, -1.0, 0.7)).normalized()
    distance = radius / math.sin(cam_data.angle / 2) * 1.15
    cam.location = centre + direction * distance
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_data.clip_start = distance / 100
    cam_data.clip_end = distance * 10
    scene.camera = cam

    # Key + fill light
    for name, offset, energy in (("Key", Vector((1.5, -1.0, 2.0)), 4.0), ("Fill", Vector((-1.5, -1.0, 0.5)), 1.5)):
        light_data = bpy.data.lights.new(name, type="SUN")
        light_data.energy = energy
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = centre + offset * radius * 3
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()

    world = bpy.data.worlds.new("PreviewWorld")
    world.color = (0.18, 0.18, 0.2)
    scene.world = world

    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = dst
    bpy.ops.render.render(write_still=True)


main()
