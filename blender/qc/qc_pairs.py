# -*- coding: utf-8 -*-
"""qc_pairs.py — 指定物体对的最小间距 / 穿透深度（CONTRACT §11 专项复核）

和 qc_collide.py 的分工：
  qc_collide.py 是「全场景盲扫」——两两配对，靠容差和豁免过滤，快但粗；
  qc_pairs.py 是「点名精查」——你指定 A 对 B，它给出**双向顶点-面距离**，
  负值 = 穿透深度，正值 = 最小间隙。用于那些盲扫会因为同集合豁免而看不到的地方：
    女仆托盘 ↔ 手掌 / 杯子 ↔ 桌面 / 椅子 ↔ 桌子 / 蛋糕 ↔ 托盘
  （C_Maid 内部互相豁免，所以托盘穿手这类问题只能靠 qc_pairs 点名查。）

三种用法：
  1. 点名：--pairs MD_Tray:MD_Hand_L,MD_Cup:TB_01_Top
  2. 清单：--pair-file pairs.json     （[{a:",b:,min_mm:0,note:"..."}]）
  3. 自动：--auto --near AOI          （AOI 内所有跨集合物体对，按最小间距排序取前 N）

判据：min_mm 默认 0（不许穿透）；给了 min_mm 就判 |gap| ≥ min_mm 且不得为负。

用法：
  blender_rt_headless(script_file=".../qc_pairs.py", file=".../scene/maid_cafe.blend",
                      engine="none", args="--pairs MD_Tray:MD_Hand_L --tag v1")
"""

import os
import sys
import json
import time
import fnmatch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
import qc_common as Q


KIND = "pairs"


# ---------------------------------------------------------------- 采样精度

def exact_min_gap(chk, a, b, max_verts=12000, max_tris=12000):
    """双向「顶点到对方面片」精确最近距离 + 双向「三角形重心互相落点」复核。

    返回:
      min_dist_mm   —— 正=最小间隙，负=穿透深度（顶点落在对方面内侧的距离）
      inside_a/b    —— A 落在 B 内部的采样点数 / 反之
      via           —— 命中的采样路径（vertex->face / tri_centroid->face）
    精度说明：顶点采样是保守上界（可能略大于真实最小距离，因为最近点对面可能
    落在三角形内部而非顶点）。所以同时做三角形重心采样，两者取更小者。
    """
    ia, ib = chk.objects[a], chk.objects[b]
    ba, bb = chk.bvh(a), chk.bvh(b)
    out = {"min_dist_mm": None, "inside_a": 0, "inside_b": 0, "via": None,
           "samples": 0, "aabb_gap_mm": None}
    gap, sep, _ = Q.aabb_gap_axis(ia.aabb_min, ia.aabb_max, ib.aabb_min, ib.aabb_max)
    out["aabb_gap_mm"] = Q.r(gap * 1000.0, 3)
    best = (float("inf"), None)
    for src, dst_bvh, tag in ((ia, bb, "a"), (ib, ba, "b")):
        pts = []
        v = src.verts
        step = max(1, len(v) // max_verts)
        pts.extend(v[::step].tolist())
        t = src.tris
        tstep = max(1, len(t) // max_tris)
        pts.extend(src.verts[t[::tstep]].mean(axis=1).tolist())
        out["samples"] += len(pts)
        n_in = 0
        for p in pts:
            loc, nor, idx, dist = dst_bvh.find_nearest(p)
            if loc is None:
                continue
            s = (p[0] - loc[0]) * nor[0] + (p[1] - loc[1]) * nor[1] + (p[2] - loc[2]) * nor[2]
            if s < 0.0:
                n_in += 1
                signed = -dist          # 穿透
            else:
                signed = dist
            if abs(signed) < abs(best[0]):
                best = (signed, "%s_%s" % (tag, "vertex_or_centroid"))
        if tag == "a":
            out["inside_a"] = n_in
        else:
            out["inside_b"] = n_in
    if best[1] is not None:
        out["min_dist_mm"] = round(best[0] * 1000.0, 4)
        out["via"] = best[1]
    return out


# ---------------------------------------------------------------- 配对解析

def parse_pairs(spec):
    pairs = []
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError("--pairs 每项要写成 A:B，收到 %r" % chunk)
        a, b = chunk.split(":", 1)
        pairs.append({"a": a.strip(), "b": b.strip(), "min_mm": 0.0,
                      "note": "命令行点名"})
    return pairs


def load_pair_file(path, root):
    p = path if os.path.isabs(path) else os.path.join(root, path)
    data = Q.read_json(p)
    if not data:
        raise FileNotFoundError("pair file 不存在或非法: %s" % p)
    if isinstance(data, dict):
        data = data.get("pairs", [])
    return data


def wildcard_pairs(objects, names):
    """把带 * 的模式展开成实际存在的物体名（一个模式可以命中多个）"""
    out = []
    for n in names:
        for pat in names:
            pass
    return out


def resolve_pair(objects, a, b):
    """支持精确名与通配；返回展开后的 [(a_name, b_name)]。"""
    def expand(pat):
        if pat in objects:
            return [pat]
        hits = sorted(n for n in objects if fnmatch.fnmatchcase(n, pat))
        return hits
    la, lb = expand(a), expand(b)
    res = []
    for x in la:
        for y in lb:
            if x == y:
                continue
            res.append((x, y))
    return res


def auto_pairs(objects, aoi, limit, min_gap_mm=-1e9):
    """AOI 内跨集合的所有物体对，按 AABB 邻近度排序取前 limit 个（粗筛，精算在 check）。"""
    names = [n for n in objects if Q.scope_match(n, aoi, objects)]
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            ia, ib = objects[a], objects[b]
            if ia.coll == ib.coll and ia.coll in ("C_Maid", "C_Room"):
                continue     # 这两个集合内部豁免，自动配对没意义
            gap, sep, _ = Q.aabb_gap_axis(ia.aabb_min, ia.aabb_max, ib.aabb_min, ib.aabb_max)
            pairs.append((float(gap.max()) * 1000.0, a, b))
    pairs.sort()
    return [(a, b) for _, a, b in pairs[:limit]]


# ---------------------------------------------------------------- 主流程

def run(pairs, chk, rules, scope, tag):
    objs = chk.objects
    results = []
    t0 = time.time()
    for spec in pairs:
        a_pat, b_pat = spec["a"], spec["b"]
        min_mm = float(spec.get("min_mm", 0.0))
        expanded = resolve_pair(objs, a_pat, b_pat)
        if not expanded:
            results.append({
                "a": a_pat, "b": b_pat, "status": "MISSING_OBJECT",
                "verdict": "待确认", "severity": "WARN",
                "note": "物体名在场景里不存在（可能未构建/命名不同）；请核对 cprop 命名",
                "min_mm_required": min_mm,
            })
            continue
        for a, b in expanded:
            m = exact_min_gap(chk, a, b)
            d = m["min_dist_mm"]
            if d is None:
                results.append({"a": a, "b": b, "status": "NO_GEOMETRY", "verdict": "待确认",
                                "severity": "WARN", "note": "采样无命中（空网格？）"})
                continue
            passed = (d >= min_mm - 1e-6)
            sev = "PASS" if passed else ("WARN" if d >= min_mm - 2.0 else "FAIL")
            # 判定：要求 min_mm 间隙时，d<min_mm 即不达标；d<0 是穿透，最严重
            if d < 0:
                sev = "FAIL"
            elif not passed:
                sev = "FAIL" if d < min_mm - 2.0 else "WARN"
            results.append({
                "a": a, "b": b, "status": "CHECKED",
                "verdict": "PASS" if sev == "PASS" else ("FAIL" if sev == "FAIL" else "待确认"),
                "severity": sev,
                "min_dist_mm": d,
                "min_mm_required": min_mm,
                "penetration_mm": round(-d, 4) if d < 0 else 0.0,
                "clearance_mm": round(d, 4) if d >= 0 else 0.0,
                "inside_samples_a": m["inside_a"],
                "inside_samples_b": m["inside_b"],
                "samples": m["samples"],
                "aabb_gap_mm": m["aabb_gap_mm"],
                "via": m["via"],
                "note": spec.get("note", ""),
            })
    elapsed = round(time.time() - t0, 3)
    fails = [r for r in results if r.get("severity") == "FAIL"]
    warns = [r for r in results if r.get("severity") == "WARN"]
    verdict = "FAIL" if fails else ("待确认" if warns else "PASS")
    payload = {
        "kind": KIND,
        "scope": scope,
        "tag": tag,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": elapsed,
        "verdict": verdict,
        "summary": {"total": len(results), "FAIL": len(fails),
                    "WARN": len(warns),
                    "PASS": len([r for r in results if r.get("severity") == "PASS"])},
        "method": ("双向顶点采样 + 三角形重心采样，到对方面最近距离；负值=穿透深度。"
                   "顶点采样在最近点落在面内部时会略微高估间隙，故同时用重心采样取更小者；"
                   "报告附 samples 数以供复核。"),
        "scene": {"path": bpy.data.filepath, "objects": len(objs),
                  "md5": (Q.md5_file(bpy.data.filepath) if bpy.data.filepath else None)},
        "scene_md5": (Q.md5_file(bpy.data.filepath) if bpy.data.filepath else None),
        "results": results,
        "rules_md5": rules.get("_rules_md5"),
    }
    return payload


def main():
    ap = Q.base_parser("qc_pairs")
    ap.add_argument("--pairs", default=None, help="A:B,A:B（支持 * 通配）")
    ap.add_argument("--pair-file", default=None, help='JSON [{"a":..,"b":..,"min_mm":..}]')
    ap.add_argument("--auto", action="store_true", help="自动配对（AOI 内跨集合，按 AABB 邻近排序）")
    ap.add_argument("--near", default=None, help="--auto 的 AOI（集合名或通配）")
    ap.add_argument("--auto-limit", type=int, default=40)
    ap.add_argument("--list-allow", action="store_true", help="列出当前豁免规则（知道盲区在哪）")
    args = Q.parse_args_lenient(ap, Q.cli_argv())
    rules = Q.load_rules(args.rules)

    if args.list_allow:
        c = rules["collide"]
        payload = {
            "kind": "pairs_allow_list",
            "allow_same_collection": c.get("allow_same_collection"),
            "allow_same_collection_doc": c.get("_allow_same_collection_doc"),
            "allow_pairs": c.get("allow_pairs"),
            "allow_pairs_doc": c.get("_allow_pairs_doc"),
            "soft_fallback_patterns": c.get("soft_fallback_patterns"),
            "blind_spots": [
                "C_Maid 内部（女仆 68 网格）整体豁免 → 托盘穿手、袖口穿裙摆必须用 --pairs 点名查",
                "C_Room 内部（墙地顶窗门）整体豁免 → 窗框插墙必须用 --pairs 点名查",
                "kind:soft（椅子）与任何东西都不判干涉 → 椅子穿墙须靠 qc_collide 的墙体判据",
            ],
        }
        return Q.finish(payload, args.out or Q.default_calib_out(rules, "pairs_allow_list"))

    t0 = time.time()
    info = Q.open_scene(args)
    if info.get("path"):
        rules["root"] = os.path.dirname(os.path.dirname(os.path.abspath(info["path"])))
    objects, skipped = Q.collect_objects(rules, include_hidden=args.include_hidden)
    chk = Q.Checker(rules, objects, skipped=skipped)

    pairs = []
    if args.pairs:
        pairs.extend(parse_pairs(args.pairs))
    if args.pair_file:
        pairs.extend(load_pair_file(args.pair_file, rules["root"]))
    if args.auto:
        auto = auto_pairs(objects, args.near or args.scope, args.auto_limit)
        pairs.extend({"a": a, "b": b, "min_mm": 0.0, "note": "auto"} for a, b in auto)
    if not pairs:
        print("HEADLESS " + json.dumps({"ok": False,
                                        "error": "没有待查配对：用 --pairs / --pair-file / --auto"}))
        return

    payload = run(pairs, chk, rules, args.scope, args.tag)
    payload["elapsed_s_total"] = round(time.time() - t0, 2)
    out = args.out or Q.default_out(rules, "pairs" + (("_" + args.tag) if args.tag else ""))
    Q.finish(payload, out, quiet=args.quiet)


# ---------------------------------------------------------------- 自测

def selftest(rules, out_path):
    """3 组已知答案：10mm 间隙 / 5mm 穿透 / 0 贴合。验证数值本身对不对。"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    c = bpy.data.collections.new("C_Seating")
    bpy.context.scene.collection.children.link(c)

    def box(name, loc, size):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
        ob = bpy.context.active_object
        ob.name = name
        ob.scale = size
        for cc in list(ob.users_collection):
            cc.objects.unlink(ob)
        c.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        ob.select_set(False)
        return ob

    # 三组用例各占一条 y 车道；刻意**避免**采样顶点落在对方面平面上
    # （同尺寸同轴对齐时，穿透顶点恰好落到对方边界面上，dist=0、符号判据退化，
    #  深度会被记作 0 —— 这是顶点-面距离法的已知边界，见 exact_min_gap 说明）。
    def base(name, y, size=0.40):
        return box(name, (size / 2.0, y, size / 2.0), (size, size, size))

    # 车道 1：分离。A x∈[0,0.2]，B x∈[0.26,0.46] → 间隙 60mm
    box("PT_GapBase", (0.10, 0.0, 0.10), (0.20, 0.20, 0.20))
    box("PT_Gap", (0.36, 0.0, 0.10), (0.20, 0.20, 0.20))
    # 车道 2：穿透。A x∈[0,0.4]（大块），B 小件深埋于 A，最近面是 A 的 x=0.4 面
    #   B x∈[0.27,0.37]，y∈[0.45,0.55]、z∈[0.15,0.25] —— 各方向都严格在 A 内部
    box("PT_PenBase", (0.20, 0.50, 0.20), (0.40, 0.40, 0.40))       # x[0,0.4] y[0.3,0.7] z[0,0.4]
    box("PT_Pen", (0.32, 0.50, 0.20), (0.10, 0.10, 0.10))           # x[0.27,0.37] → 距 x=0.4 面 30mm
    # 车道 3：贴合。A x∈[0,0.2]，C x∈[0.2,0.4] → 间隙 0
    box("PT_TouchBase", (0.10, -0.50, 0.10), (0.20, 0.20, 0.20))
    box("PT_Touch", (0.30, -0.50, 0.10), (0.20, 0.20, 0.20))
    bpy.context.view_layer.update()
    objects, skipped = Q.collect_objects(rules, include_hidden=True)
    chk = Q.Checker(rules, objects, skipped=skipped)
    cases = [
        {"a": "PT_GapBase", "b": "PT_Gap", "expect_gap_mm": 60.0, "note": "分离 60mm"},
        {"a": "PT_PenBase", "b": "PT_Pen", "expect_gap_mm": -30.0, "note": "小件深埋，穿透 30mm"},
        {"a": "PT_TouchBase", "b": "PT_Touch", "expect_gap_mm": 0.0, "note": "贴合 0mm"},
    ]
    results = []
    ok_all = True
    for cs in cases:
        m = exact_min_gap(chk, cs["a"], cs["b"])
        d = m["min_dist_mm"]
        ok = d is not None and abs(d - cs["expect_gap_mm"]) <= 0.5
        ok_all = ok_all and ok
        results.append({"a": cs["a"], "b": cs["b"], "note": cs["note"],
                        "expect_gap_mm": cs["expect_gap_mm"], "measured_gap_mm": d,
                        "error_mm": (round(abs(d - cs["expect_gap_mm"]), 4) if d is not None else None),
                        "ok": ok})
    payload = {
        "kind": "pairs_selftest",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cases": len(cases), "passed": len([r for r in results if r["ok"]]),
        "verdict": "PASS" if ok_all else "FAIL",
        "tolerance_mm": 0.5,
        "results": results,
        "note": "验证「间距/穿透数值」本身准确到 0.5mm，与场景质量无关。",
    }
    Q.finish(payload, out_path or Q.default_calib_out(rules, "pairs_selftest"))
    return payload


if __name__ == "__main__":
    argv = Q.cli_argv()
    if "--selftest" in argv:
        rules = Q.load_rules()
        selftest(rules, None)
    else:
        main()
