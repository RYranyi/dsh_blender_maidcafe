"""Audit every downloaded PolyHaven .blend for the maid-cafe set.

Run headless:
  blender.exe -b --factory-startup -P blender_audit_models.py -- <modelsDir> <outJson>

For each <modelsDir>/<id>/<id>_1k.blend it opens the file and reports:
  objects, meshes, triangles (base mesh + depsgraph-evaluated), materials,
  images (total / with resolvable file / packed), lights, cameras, dimensions.

Never touches the GUI session; safe to re-run.
"""
import bpy
import json
import os
import sys
import traceback
import mathutils

argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

MODELS_DIR = argv[0] if len(argv) > 0 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "models")
OUT_JSON = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".scratch", "asset-scout", "models_audit.json")
BLEND_NAME_HINT = argv[2] if len(argv) > 2 else "_1k.blend"


def tri_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def audit_one(blend_path):
    bpy.ops.wm.open_mainfile(filepath=blend_path, load_ui=False)
    scn = bpy.context.scene

    meshes = [o for o in scn.objects if o.type == "MESH"]
    lights = [o for o in scn.objects if o.type == "LIGHT"]
    cameras = [o for o in scn.objects if o.type == "CAMERA"]

    base_tris = 0
    for o in meshes:
        if o.data:
            base_tris += tri_count(o.data)

    # depsgraph-evaluated triangles (modifiers / instances applied)
    eval_tris = 0
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        for o in meshes:
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            if me:
                eval_tris += tri_count(me)
                oe.to_mesh_clear()
    except Exception:
        eval_tris = base_tris

    mats = set()
    for o in scn.objects:
        for slot in getattr(o, "material_slots", []) or []:
            if slot.material:
                mats.add(slot.material.name)

    imgs = list(bpy.data.images)
    img_report = []
    for im in imgs:
        if im.name in ("Render Result", "Viewer Node"):
            continue
        fp = bpy.path.abspath(im.filepath, library=im.library) if im.filepath else ""
        img_report.append({
            "name": im.name,
            "filepath": im.filepath,
            "resolved": fp,
            "exists": bool(fp) and os.path.exists(fp),
            "packed": bool(im.packed_file),
            "size": list(im.size),
        })

    # world-space bounds of everything visible
    bbox_min = [1e9] * 3
    bbox_max = [-1e9] * 3
    for o in scn.objects:
        if o.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            continue
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            for i in range(3):
                bbox_min[i] = min(bbox_min[i], w[i])
                bbox_max[i] = max(bbox_max[i], w[i])
    if bbox_min[0] < 1e8:
        dims = [round(bbox_max[i] - bbox_min[i], 3) for i in range(3)]
        bbox = {"min": [round(v, 3) for v in bbox_min], "max": [round(v, 3) for v in bbox_max], "dims_m": dims}
    else:
        bbox = None

    return {
        "blend": blend_path,
        "blend_mb": round(os.path.getsize(blend_path) / (1024 * 1024), 2),
        "objects": len(scn.objects),
        "mesh_objects": len(meshes),
        "lights": len(lights),
        "cameras": len(cameras),
        "triangles": base_tris,
        "triangles_evaluated": eval_tris,
        "materials": len(mats),
        "material_names": sorted(mats),
        "images_total": len(img_report),
        "images_resolved": sum(1 for i in img_report if i["exists"] or i["packed"]),
        "images_missing": [i["name"] for i in img_report if not (i["exists"] or i["packed"])],
        "image_details": img_report,
        "bbox": bbox,
        "collections": [c.name for c in bpy.data.collections],
    }


def main():
    entries = []
    ids = sorted(
        d for d in os.listdir(MODELS_DIR)
        if os.path.isdir(os.path.join(MODELS_DIR, d))
    )
    for asset_id in ids:
        d = os.path.join(MODELS_DIR, asset_id)
        blends = [f for f in os.listdir(d) if f.endswith(".blend")]
        if not blends:
            entries.append({"id": asset_id, "error": "no .blend found"})
            continue
        blends.sort(key=lambda f: ("1k" not in f, f))
        p = os.path.join(d, blends[0])
        rec = {"id": asset_id, "file": blends[0]}
        try:
            rec.update(audit_one(p))
            rec.pop("blend", None)
            print("AUDIT %s objs=%d tris=%d mats=%d imgs=%d/%d" % (
                asset_id, rec["objects"], rec["triangles"], rec["materials"],
                rec["images_resolved"], rec["images_total"]))
        except Exception as e:
            rec["error"] = "%s: %s" % (type(e).__name__, e)
            rec["traceback"] = traceback.format_exc()
            print("AUDIT-ERR %s %s" % (asset_id, e))
        entries.append(rec)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)
    print("HEADLESS " + json.dumps({
        "assets": len(entries),
        "ok": sum(1 for e in entries if "error" not in e),
        "failed": [e["id"] for e in entries if "error" in e],
        "out": OUT_JSON,
    }, ensure_ascii=False))


main()
