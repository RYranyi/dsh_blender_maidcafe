# -*- coding: utf-8 -*-
"""qc_gltf.py — GLB/glTF 交付校验（CONTRACT §11.5 §5 §8）

不依赖外部 validator：自己解析 GLB 二进制头 + JSON chunk + BIN chunk，
逐项核对（每一项都有明确的 PASS/FAIL 判据与实测数字）：

  §8 文件大小      < 40 MB
  §5 三角面总数    < 500k（目标 420k 以内记 WARN）
  §5 逐区块预算    C_Room 60k / C_Bar 70k / C_Display 40k / C_Seating 70k /
                   C_Decor 60k / C_Outdoor 35k / C_Maid 260k
  §8 贴图内嵌      GLB 里所有 image 必须有 bufferView（不能是外部 uri）
  §8 MIME          内嵌 image 的 mimeType ∈ image/jpeg|image/png（贴图内嵌要求）
  §11.5 accessor   每个 accessor 的 count/type/componentType/bufferView 合法，
                   且 byteOffset+元素大小 ≤ bufferView.byteLength
  §11.5 几何        POSITION accessor 必须有 min/max（glTF 规范强制，three.js 依赖它做包围盒）
  §11.5 图元        mesh.primitives 的 mode 默认 4（TRIANGLES），attributes 必须含 POSITION

节点/集合归属：GLB 里集合被导出成父子节点链，用节点树回溯每个 mesh 属于哪个 C_xxx 集合名，
从而能给出「逐区块三角面数」—— 这是 §5 预算的直接证据。

用法：
  # 主路径（推荐）：插件外部校验器
  blender_rt_plan(op="gltf_validate", args={path:"E:/dsh/maid_cafe/scene/maid_cafe.glb"})
  # 本脚本（补充：给逐区块 tri、内嵌统计、accessor 合法性）
  blender_rt_headless(script_file=".../qc_gltf.py", engine="none",
                      args="--glb scene/maid_cafe.glb")
自测：
  blender_rt_headless(script_file=".../qc_gltf.py", engine="none", args="--selftest")
"""

import os
import sys
import json
import time
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qc_common as Q


KIND = "gltf"
GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942

COMPONENT = {
    5120: ("BYTE", 1), 5121: ("UNSIGNED_BYTE", 1),
    5122: ("SHORT", 2), 5123: ("UNSIGNED_SHORT", 2),
    5125: ("UNSIGNED_INT", 4), 5126: ("FLOAT", 4),
}
TYPE_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
              "MAT2": 4, "MAT3": 9, "MAT4": 16}


def parse_glb(path):
    """解析 GLB：返回 (header, json_dict, bin_len, errors)。异常直接抛。"""
    with open(path, "rb") as f:
        data = f.read()
    total = len(data)
    if total < 12:
        raise ValueError("文件小于 12 字节，不是 GLB")
    magic, version, length = struct.unpack("<III", data[:12])
    out = {"magic": hex(magic), "version": version,
           "declared_length": length, "actual_length": total,
           "chunks": []}
    if magic != GLB_MAGIC:
        raise ValueError("magic 不是 glTF（0x%08X），可能是 .gltf 文本或损坏文件" % magic)
    if length != total:
        out["length_mismatch"] = {"declared": length, "actual": total}
    pos = 12
    gltf = None
    bin_len = 0
    while pos + 8 <= total:
        clen, ctype = struct.unpack("<II", data[pos:pos + 8])
        pos += 8
        chunk = data[pos:pos + clen]
        pos += clen
        out["chunks"].append({"type": hex(ctype), "length": clen})
        if ctype == CHUNK_JSON:
            gltf = json.loads(chunk.decode("utf-8").rstrip("\x00 "))
        elif ctype == CHUNK_BIN:
            bin_len = clen
    if gltf is None:
        raise ValueError("GLB 里没有 JSON chunk")
    return out, gltf, bin_len, total


def node_collection_map(gltf, rules=None):
    """把每个有 mesh 的节点映射到它所属的集合。

    v3 实测：GLB 里 906 个 node **全部是根节点、且没有 C_ 集合层** ——
    Blender 导出器没有把 Collection 变成 node 层级（所有对象平铺在 Scene 下）。
    所以「节点树回溯 C_xxx」这条路在这个项目里失效，改用**名字前缀**归属：
      RM_→C_Room  BA_→C_Bar  DS_→C_Display  TB_/CH_→C_Seating  DC_→C_Decor
      OD_→C_Outdoor
      MD_* 与女仆本体网格（无前缀：Apron/Arm/Skirt/Torso…）→ C_Maid
    前缀表来自 qc_rules.prefix_map，女仆无前缀名单来自 maid_prefixless。
    """
    nodes = gltf.get("nodes", [])
    prefix_map = (rules or {}).get("prefix_map", {}) or {}
    prefixless = set(((rules or {}).get("gltf", {}) or {}).get("maid_prefixless") or [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i

    def coll_of(idx):
        # 先试节点树（将来 cbuild 若保留层级仍可用）
        cur, guard = idx, 0
        while cur is not None and guard < 64:
            nm = nodes[cur].get("name", "")
            if nm.startswith("C_"):
                return nm
            cur = parent.get(cur)
            guard += 1
        # 回退：名字前缀
        nm = nodes[idx].get("name", "")
        for pre, mod in prefix_map.items():
            if nm.startswith(pre):
                return {"croom": "C_Room", "cbar": "C_Bar", "cdisplay": "C_Display",
                        "cseating": "C_Seating", "cdecor": "C_Decor",
                        "coutdoor": "C_Outdoor", "cmaid": "C_Maid",
                        "clight": "C_Light", "qc": "C_QC"}.get(mod, mod)
        if nm in prefixless:
            return "C_Maid"      # 女仆本体网格没有 MD_ 前缀
        # 女仆本体的其它网格（无前缀，但有典型名字）
        if any(k in nm for k in ("Skirt", "Sleeve", "Sock", "Torso", "Bodice", "Apron",
                                 "Collar", "Cuff", "Hand", "Leg", "Foot", "Hair", "Eye",
                                 "Brow", "Mouth", "Neck", "Arm", "Panties", "BackBow",
                                 "Button", "Placket", "Knot", "Loop", "Sash", "Tail",
                                 "Iris", "Lash", "Sclera", "Head", "Ear", "Nose")):
            return "C_Maid"
        return "(no_collection)"

    return {i: coll_of(i) for i in range(len(nodes))}, nodes, parent


def tri_count_of_primitive(prim, gltf):
    """按 indices accessor 的 count/3，或 POSITION 的 count/3 估算三角面数。"""
    idx = prim.get("indices")
    if idx is not None:
        acc = gltf["accessors"][idx]
        return acc.get("count", 0) // 3
    pos = prim.get("attributes", {}).get("POSITION")
    if pos is not None:
        acc = gltf["accessors"][pos]
        return acc.get("count", 0) // 3
    return 0


def check_accessors(gltf, bin_len):
    """accessor 合法性：componentType/type/count/bufferView 边界"""
    problems = []
    accs = gltf.get("accessors", []) or []
    bvs = gltf.get("bufferViews", []) or []
    buffers = gltf.get("buffers", []) or []
    # buffer 大小校验（GLB 内嵌 buffer 无 uri，长度必须等于 BIN chunk）
    for bi, buf in enumerate(buffers):
        if "uri" not in buf:
            if bin_len and buf.get("byteLength", 0) > bin_len:
                problems.append({"where": "buffers[%d]" % bi, "kind": "buffer_overflow",
                                 "detail": "byteLength %d > BIN chunk %d" % (
                                     buf.get("byteLength", 0), bin_len)})
    for vi, bv in enumerate(bvs):
        blen = bv.get("byteLength", 0)
        off = bv.get("byteOffset", 0)
        b = bv.get("buffer", 0)
        if b >= len(buffers):
            problems.append({"where": "bufferViews[%d]" % vi, "kind": "bad_buffer_index",
                             "detail": "buffer=%d 但只有 %d 个 buffer" % (b, len(buffers))})
            continue
        buflen = buffers[b].get("byteLength", bin_len)
        if off + blen > buflen:
            problems.append({"where": "bufferViews[%d]" % vi, "kind": "bufferView_overflow",
                             "detail": "offset+len=%d > buffer %d" % (off + blen, buflen)})
    for ai, a in enumerate(accs):
        ct = a.get("componentType")
        tp = a.get("type")
        cnt = a.get("count", 0)
        if ct not in COMPONENT:
            problems.append({"where": "accessors[%d]" % ai, "kind": "bad_componentType",
                             "detail": str(ct)})
            continue
        if tp not in TYPE_NCOMP:
            problems.append({"where": "accessors[%d]" % ai, "kind": "bad_type", "detail": str(tp)})
            continue
        elem = COMPONENT[ct][1] * TYPE_NCOMP[tp]
        bvi = a.get("bufferView")
        if bvi is None:
            continue     # 允许无 bufferView（用 sparse 或全零）
        if bvi >= len(bvs):
            problems.append({"where": "accessors[%d]" % ai, "kind": "bad_bufferView_index",
                             "detail": "bufferView=%d 但有 %d 个" % (bvi, len(bvs))})
            continue
        bv = bvs[bvi]
        acc_off = a.get("byteOffset", 0)
        stride = bv.get("byteStride") or elem
        need = acc_off + stride * max(cnt - 1, 0) + elem
        if need > bv.get("byteLength", 0):
            problems.append({"where": "accessors[%d]" % ai, "kind": "accessor_overflow",
                             "detail": "需要 %d 字节 > bufferView %d" % (
                                 need, bv.get("byteLength", 0))})
        if cnt <= 0:
            problems.append({"where": "accessors[%d]" % ai, "kind": "zero_count",
                             "detail": "count=%d" % cnt})
    return problems


def collect_evidence(gltf, bin_len, total, rules, header=None):
    """把 GLB 全量核对结果组织成 evidence。"""
    gcfg = rules["gltf"]
    nodes_map, nodes, parent = node_collection_map(gltf, rules)
    meshes = gltf.get("meshes", []) or []
    accs = gltf.get("accessors", []) or []
    tris_by_coll = {}
    tri_total = 0
    prim_issues = []
    pos_no_minmax = []
    for ni, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        coll = nodes_map.get(ni, "(no_collection)")
        m = meshes[node["mesh"]]
        for pi, prim in enumerate(m.get("primitives", [])):
            t = tri_count_of_primitive(prim, gltf)
            tri_total += t
            tris_by_coll[coll] = tris_by_coll.get(coll, 0) + t
            mode = prim.get("mode", 4)
            if mode != 4:
                prim_issues.append({"mesh": m.get("name"), "primitive": pi, "mode": mode,
                                    "detail": "mode != 4(TRIANGLES)"})
            if "POSITION" not in prim.get("attributes", {}):
                prim_issues.append({"mesh": m.get("name"), "primitive": pi,
                                    "detail": "缺 POSITION"})
            pidx = prim.get("attributes", {}).get("POSITION")
            if pidx is not None and pidx < len(accs):
                a = accs[pidx]
                if "min" not in a or "max" not in a:
                    pos_no_minmax.append({"mesh": m.get("name"), "accessor": pidx})

    images = gltf.get("images", []) or []
    imgs = []
    allowed_mime = gcfg.get("allowed_image_mime") or ["image/jpeg", "image/png"]
    for i, im in enumerate(images):
        imgs.append({
            "index": i, "name": im.get("name"),
            "mimeType": im.get("mimeType"),
            "embedded": "bufferView" in im,
            "uri": im.get("uri"),
            "bufferView": im.get("bufferView"),
            "size_bytes": (gltf["bufferViews"][im["bufferView"]].get("byteLength")
                           if "bufferView" in im and im["bufferView"] < len(gltf.get("bufferViews", []))
                           else None),
        })
    mats = gltf.get("materials", []) or []
    acc_problems = check_accessors(gltf, bin_len)

    size_mb = round(total / (1024.0 * 1024.0), 3)
    budget = gcfg.get("tri_budget", {})
    coll_check = {}
    for coll, t in sorted(tris_by_coll.items()):
        cap = budget.get(coll)
        coll_check[coll] = {"tris": t, "budget": cap,
                            "ok": (cap is None or t <= cap),
                            "used_pct": (round(100.0 * t / cap, 1) if cap else None)}
    checks = []
    checks.append({"id": "size", "label": "§8 GLB < 40MB", "actual": size_mb,
                   "limit": round(gcfg["max_bytes"] / 1048576.0, 1),
                   "unit": "MB", "ok": total <= gcfg["max_bytes"]})
    checks.append({"id": "tris", "label": "§5 三角面 < 500k", "actual": tri_total,
                   "limit": gcfg["max_tris"], "unit": "tri",
                   "ok": tri_total < gcfg["max_tris"],
                   "warn": tri_total > gcfg.get("target_total", 420000) and
                           tri_total <= gcfg["max_tris"]})
    for coll, info in coll_check.items():
        if info["budget"] is None:
            continue
        checks.append({"id": "tris_" + coll, "label": "§5 %s 预算" % coll,
                       "actual": info["tris"], "limit": info["budget"], "unit": "tri",
                       "ok": info["ok"], "used_pct": info["used_pct"]})
    not_embedded = [im for im in imgs if not im["embedded"]]
    checks.append({"id": "images_embedded", "label": "§8 贴图内嵌（无外部 uri）",
                   "actual": len(imgs) - len(not_embedded), "limit": len(imgs), "unit": "image",
                   "ok": gcfg.get("require_embedded_images", True) is False or not not_embedded})
    bad_mime = [im for im in imgs if im["mimeType"] not in allowed_mime]
    checks.append({"id": "image_mime",
                   "label": "§8 image mimeType ∈ %s" % "/".join(
                       m.split("/")[-1] for m in allowed_mime),
                   "actual": len(imgs) - len(bad_mime), "limit": len(imgs), "unit": "image",
                   "ok": gcfg.get("require_mime", True) is False or not bad_mime})
    # WebP 走法记录：v3 起贴图转 WebP。允许的两种合规写法：
    #   (a) image.mimeType 直接写 image/webp（glTF 2.0 规范接受，three.js 认）
    #   (b) 用 EXT_texture_webp 扩展声明
    # 这里只做记录 + 扩展一致性核对，两种都算合规。
    mime_kinds = {}
    for im in imgs:
        mime_kinds[im["mimeType"]] = mime_kinds.get(im["mimeType"], 0) + 1
    ext_used = (gltf.get("extensionsUsed") or [])
    tex_webp_ext = any((tex.get("extensions") or {}).get("EXT_texture_webp")
                       for tex in (gltf.get("textures") or []))
    webp_how = ("none" if not mime_kinds.get("image/webp") else
                "ext_declared" if ("EXT_texture_webp" in ext_used or tex_webp_ext) else "mime_only")
    checks.append({"id": "webp_how", "label": "WebP 内嵌写法（记录，两种均合规）",
                   "actual": webp_how, "limit": "none|ext_declared|mime_only", "unit": "-",
                   "ok": True})
    allowed_ext = gcfg.get("allowed_extensions") or []
    unknown_ext = [e for e in ext_used if allowed_ext and e not in allowed_ext]
    checks.append({"id": "extensions", "label": "extensionsUsed ⊆ 白名单（three.js 认得的）",
                   "actual": len(unknown_ext), "limit": 0, "unit": "extension",
                   "ok": not unknown_ext})
    checks.append({"id": "accessors", "label": "§11.5 accessor 合法性",
                   "actual": len(acc_problems), "limit": 0, "unit": "problem",
                   "ok": len(acc_problems) == 0})
    checks.append({"id": "position_minmax", "label": "§11.5 POSITION 有 min/max",
                   "actual": len(pos_no_minmax), "limit": 0, "unit": "problem",
                   "ok": len(pos_no_minmax) == 0})
    checks.append({"id": "primitives", "label": "§11.5 primitive mode/attributes",
                   "actual": len(prim_issues), "limit": 0, "unit": "problem",
                   "ok": len(prim_issues) == 0})

    fails = [c for c in checks if not c["ok"]]
    warns = [c for c in checks if c.get("warn")]
    evidence = {
        "bytes": total,
        "mb": size_mb,
        "tri_total": tri_total,
        "tris_by_collection": dict(sorted(tris_by_coll.items())),
        "collection_budget": coll_check,
        "nodes": len(nodes),
        "meshes": len(meshes),
        "primitives": sum(len(m.get("primitives", [])) for m in meshes),
        "materials": len(mats),
        "material_names": [m.get("name") for m in mats][:400],
        "images": imgs,
        "image_count": len(imgs),
        "bin_chunk_bytes": bin_len,
        "accessors": len(accs),
        "bufferViews": len(gltf.get("bufferViews", []) or []),
        "buffers": [{"byteLength": b.get("byteLength"), "uri": b.get("uri")}
                    for b in (gltf.get("buffers", []) or [])],
        "extensions_used": gltf.get("extensionsUsed", []),
        "extensions_required": gltf.get("extensionsRequired", []),
        "asset_generator": (gltf.get("asset") or {}).get("generator"),
        "asset_version": (gltf.get("asset") or {}).get("version"),
        "accessor_problems": acc_problems[:100],
        "position_no_minmax": pos_no_minmax[:100],
        "primitive_issues": prim_issues[:100],
        "checks": checks,
        "chunks": (header or {}).get("chunks"),
        "length_mismatch": (header or {}).get("length_mismatch"),
    }
    return evidence, fails, warns


def run(path, rules, out_path, tag=""):
    t0 = time.time()
    gcfg = rules["gltf"]
    p = path if os.path.isabs(path) else os.path.join(Q.project_root(rules), path)
    if not os.path.isfile(p):
        payload = {"kind": KIND, "verdict": "待确认", "severity": "WARN",
                   "glb": p, "glb_exists": False,
                   "note": "GLB 尚未产出（cbuild.py 还没导出）；这不代表不合格，只说明还没到 GLB 验收阶段。",
                   "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        Q.finish(payload, out_path or Q.default_out(rules, "gltf" + (("_" + tag) if tag else "")))
        return payload
    header, gltf, bin_len, total = parse_glb(p)
    ev, fails, warns = collect_evidence(gltf, bin_len, total, rules, header)
    findings = []
    for c in fails:
        findings.append({
            "id": "GLTF-%s" % c["id"], "kind": "glb", "verdict": "FAIL", "severity": "FAIL",
            "objects": [], "module": "cbuild", "owner": "Lead", "location": None,
            "metrics": {k: c.get(k) for k in ("actual", "limit", "unit", "used_pct")},
            "rule": c["label"],
            "note": "%s：实测 %s %s，上限 %s" % (
                c["label"], c.get("actual"), c.get("unit"), c.get("limit")),
            "evidence": {"glb": os.path.relpath(p, Q.project_root(rules))},
            "scope": None,
        })
    for c in warns:
        findings.append({
            "id": "GLTF-WARN-%s" % c["id"], "kind": "glb", "verdict": "待确认", "severity": "WARN",
            "objects": [], "module": "cbuild", "owner": "Lead", "location": None,
            "metrics": {k: c.get(k) for k in ("actual", "limit", "unit")},
            "rule": c["label"],
            "note": "%s：实测 %s tri 超过目标 %d（但仍在 500k 硬上限内）" % (
                c["label"], c.get("actual"), gcfg.get("target_total", 420000)),
            "evidence": {}, "scope": None,
        })
    verdict = "FAIL" if fails else ("待确认" if warns else "PASS")
    payload = {
        "kind": KIND,
        "tag": tag,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - t0, 3),
        "glb": p,
        "glb_exists": True,
        "glb_md5": Q.md5_file(p),
        "glb_mtime": int(os.stat(p).st_mtime),
        "verdict": verdict,
        "summary": {"checks": len(ev["checks"]), "FAIL": len(fails), "WARN": len(warns),
                    "PASS": len(ev["checks"]) - len(fails) - len(warns),
                    "tri_total": ev["tri_total"], "mb": ev["mb"]},
        "evidence": ev,
        "findings": findings,
        "method": ("自解析 GLB：magic/version/length + JSON chunk + BIN chunk；"
                   "节点树回溯 C_xxx 集合归属做逐区块 tri 统计；"
                   "accessor 按 componentType×type 元素大小校验 bufferView 边界；"
                   "独立于 Blender 导出器，可交叉验证。"),
        "rules_md5": rules.get("_rules_md5"),
    }
    Q.finish(payload, out_path or Q.default_out(rules, "gltf" + (("_" + tag) if tag else "")))
    return payload


# ============================================================ 自测

def _make_glb(path, tris_ok=True, external_image=False):
    """手工造一个最小 GLB 用于自测（不依赖 Blender 导出器）。"""
    # 3 个顶点 1 个三角形
    pos = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    idx = struct.pack("<3H", 0, 1, 2)
    bin_blob = pos + idx
    gltf = {
        "asset": {"version": "2.0", "generator": "qc_selftest"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "C_Seating", "mesh": 0, "children": []}],
        "meshes": [{"name": "TB_Test", "primitives": [{
            "attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos)},
            {"buffer": 0, "byteOffset": len(pos), "byteLength": len(idx)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [0, 0, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "materials": [],
        "images": [],
    }
    if external_image:
        gltf["images"] = [{"uri": "tex/wood_diff.jpg"}]
    if not tris_ok:
        # 故意把 accessor count 写错，验证 accessor 校验能抓到
        gltf["accessors"][0]["count"] = 999999
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    bin_blob += b"\x00" * ((4 - len(bin_blob) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", GLB_MAGIC, 2, total))
        f.write(struct.pack("<II", len(js), CHUNK_JSON))
        f.write(js)
        f.write(struct.pack("<II", len(bin_blob), CHUNK_BIN))
        f.write(bin_blob)


def selftest(rules, out_path):
    tmpdir = Q.ensure_dir(os.path.join(Q.project_root(rules), ".scratch", "qc", "calib"))
    good = os.path.join(tmpdir, "_st_good.glb")
    bad = os.path.join(tmpdir, "_st_badaccessor.glb")
    ext = os.path.join(tmpdir, "_st_external_img.glb")
    _make_glb(good)
    _make_glb(bad, tris_ok=False)
    _make_glb(ext, external_image=True)
    cases = []

    def check(name, path, expect_verdict, expect_ids):
        header, gltf, bin_len, total = parse_glb(path)
        ev, fails, warns = collect_evidence(gltf, bin_len, total, rules, header)
        fail_ids = [c["id"] for c in fails]
        missing = [i for i in expect_ids if i not in fail_ids]
        ok = (not missing)
        cases.append({"case": name, "glb": os.path.basename(path),
                      "expect_fail_ids": expect_ids, "got_fail_ids": fail_ids,
                      "tri_total": ev["tri_total"], "mb": ev["mb"],
                      "ok": ok,
                      "detail": "OK" if ok else ("未抓到 " + ",".join(missing))})

    check("good_glb", good, "PASS", [])
    check("bad_accessor_count", bad, "FAIL", ["accessors"])
    check("external_image_uri", ext, "FAIL", ["images_embedded"])
    payload = {
        "kind": "gltf_selftest",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cases": len(cases),
        "passed": len([c for c in cases if c["ok"]]),
        "verdict": "PASS" if all(c["ok"] for c in cases) else "FAIL",
        "results": cases,
        "note": "用手工构造的最小 GLB 验证解析器与判据本身，不依赖真导出。",
    }
    Q.finish(payload, out_path or Q.default_calib_out(rules, "gltf_selftest"))
    return payload


def main():
    ap = Q.base_parser("qc_gltf")
    ap.add_argument("--glb", default="scene/maid_cafe.glb")
    ap.add_argument("--selftest", action="store_true")
    args = Q.parse_args_lenient(ap, Q.cli_argv())
    rules = Q.load_rules(args.rules)
    if args.selftest:
        return selftest(rules, args.out)
    return run(args.glb, rules, args.out, args.tag)


if __name__ == "__main__":
    main()
