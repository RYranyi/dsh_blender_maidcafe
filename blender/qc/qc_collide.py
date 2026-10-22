# -*- coding: utf-8 -*-
"""qc_collide.py — 穿模 / 干涉 / 落地 / 贴墙 / 吊挂 / 天花 体检（CONTRACT §11.1 §11.2 §11.3）

判据口径（全部来自 qc_rules.json，脚本内不硬编码阈值）
------------------------------------------------------------------
§11.1 干涉（双门，避免 AABB 独用的漏报与误报）：
  门 1 —— 世界 AABB 的 MTV（最小平移量 = 各轴重叠量的最小值）> 5mm，才进候选；
  门 2 —— 世界空间 BVH 三角形精确求交，overlap() 条数 > 0 才算真干涉。
  两门都过 → FAIL（附：重叠三角形数、穿透深度代理值、AABB 逐轴重叠量）
  门 1 过、门 2 不过 → 记 `pairs_aabb_false_positive`（「只用 AABB 会误报」的直接证据）
  门 1 不过、门 2 过（薄件深嵌 / MTV 小但穿透深）→ 用 BVH 深度再判，> 5mm 仍 FAIL
  排除：kind:"soft"（§11.1 椅子插桌下）、同集合连续模型（C_Room 构件、C_Maid 整体）、
        qc_rules.json 的 allow_pairs（默认空，见文件内说明为什么必须空）

  为什么不用 BVHTree.FromObject(ob, depsgraph)：**它不应用物体世界变换**。
  实测两个相距 100m 的立方体仍报 overlap=2（run-mvhgvlz2xl1t）。故一律
  BVHTree.FromPolygons(世界坐标顶点, 三角形, all_triangles=True)。

§11.2 落地：非 soft 物体 min_z ∈ [-2mm, +2mm]。
  二级判据：不贴地但被别的物体顶面托住（间隙 ≤2mm）→ 合法，记 rest_on，不报。
§11.2 贴墙：挂墙物与内墙面间隙 ∈ [0, 6mm]；插进墙 > 5mm → FAIL。
§11.2 天花：顶面超 z=3.0 且 > 5mm → FAIL（吊灯/纱帘）。
§11.3 女仆：C_Maid 整组（68 网格）最低点 z ∈ [-2mm, +2mm]。

用法
------------------------------------------------------------------
  真场景：blender_rt_headless(script_file="E:/dsh/maid_cafe/blender/qc/qc_collide.py",
                 file="E:/dsh/maid_cafe/scene/maid_cafe.blend", engine="none",
                 args="--scope C_Seating --tag v1")
  自测校准：args="--calib"（自建 11 个已知用例，不需要真场景）
"""

import os
import sys
import json
import time
import math
import fnmatch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
import qc_common as Q


KIND = "collide"


# ============================================================ 干涉（双门）

def check_interference(chk, names, findings, stats, rules, scope, min_overlap_mm=None):
    tol = rules["tolerances"]
    min_ov = (min_overlap_mm if min_overlap_mm is not None else tol["min_overlap_mm"]) / 1000.0
    eps = tol.get("contact_epsilon_mm", 1.5) / 1000.0
    objs = chk.objects
    for i in range(len(names)):
        a = names[i]
        ia = objs[a]
        for j in range(i + 1, len(names)):
            b = names[j]
            ib = objs[b]
            stats["pairs_total"] += 1
            gap, sep, _ = Q.aabb_gap_axis(ia.aabb_min, ia.aabb_max, ib.aabb_min, ib.aabb_max)
            mtv = -float(gap.max())            # >0 = AABB 各轴均相交；值 = 各轴重叠最小值
            if mtv <= 0.0:
                continue                       # 包围盒分离 → 几何必不相交
            if mtv <= eps:
                # 贴面接触（杯子放在桌面上）：亚毫米级/零体积重叠，不是干涉
                stats["pairs_contact_only"] = stats.get("pairs_contact_only", 0) + 1
                continue
            stats["pairs_aabb_touch"] += 1
            above_ta = mtv > min_ov
            if not above_ta:
                stats["pairs_aabb_within_tolerance"] += 1
            why = (chk.allow_pair(a, b) or chk.same_coll_exempt(ia, ib) or chk.soft_exempt(ia, ib)
                   or chk.component_exempt(a, b))
            if why:
                stats["pairs_exempted"] += 1
                key = a + "|" + b
                stats["exemptions"] = (stats.get("exemptions") or [])
                stats["exemptions"].append({"a": a, "b": b, "aabb_mtv_mm": round(mtv * 1000.0, 2),
                                            "why": why})
                continue
            pen = chk.penetration(a, b)
            stats["bvh_pair_checks"] += 1
            if pen["overlap_tris"] <= 0:
                if above_ta:
                    stats["pairs_aabb_false_positive"] += 1
                    ex = (stats.get("false_positive_examples") or [])[-9:]
                    ex.append({"a": a, "b": b, "aabb_mtv_mm": round(mtv * 1000.0, 2)})
                    stats["false_positive_examples"] = ex
                continue
            stats["pairs_bvh_overlap"] += 1
            stats["tri_overlap_total"] += pen["overlap_tris"]
            depth = pen["depth_mm"] / 1000.0        # 顶点法，且已被 AABB MTV 封顶
            dv = (pen.get("depth_vertex_mm") or 0.0) / 1000.0
            mtv_m = (pen.get("aabb_mtv_mm") or 0.0) / 1000.0
            # 判定：三角形相交说明两物体确实互相穿过，但**深度只看顶点法**（精确、且被 MTV 封顶）。
            # 若顶点法测不到（同尺寸同轴对齐时顶点恰好落在对方表面 → 退化为 0），标 WARN，
            # 提示用 qc_pairs 复核。绝不使用质心法的值判 FAIL —— 实测它会给出 3518mm 的荒谬深度。
            if depth >= min_ov:
                sev = "FAIL"
                rule_txt = "§11.1 干涉：顶点级穿透 %.2fmm ≥ 5mm 容差" % (depth * 1000)
            elif mtv_m >= min_ov and dv < 1e-4:
                sev = "WARN"
                rule_txt = ("§11.1 干涉：三角形相交 %d 对、AABB 重叠 %.2fmm，但顶点级穿透 %.3fmm"
                            "（顶点退化到共面）→ 深度不确定，请 qc_pairs 点名复核"
                            % (pen["overlap_tris"], mtv_m * 1000, dv * 1000))
            else:
                stats["pairs_touch_only"] = stats.get("pairs_touch_only", 0) + 1
                continue
            focus = ib if ia.coll == "C_Room" else ia
            coll, mod, owner = Q.attribute([a, b], objs, rules)
            findings.append(Q.finding(
                "INT-%s-%s" % (a, b), "interference", sev, [a, b], mod, owner,
                focus.center,
                {"aabb_mtv_mm": round(mtv * 1000.0, 3),
                 "overlap_tris": pen["overlap_tris"],
                 "depth_mm": pen["depth_mm"],
                 "depth_vertex_mm": pen.get("depth_vertex_mm"),
                 "depth_centroid_mm": pen.get("depth_centroid_mm"),
                 "depth_uncertain": pen.get("depth_uncertain"),
                 "overlap_axes_mm": pen["overlap_aabb_mm"],
                 "tris_a": ia.tri_count, "tris_b": ib.tri_count},
                rule_txt,
                "BVH 世界空间求交命中 %d 对三角形；顶点级穿透深度 %.3fmm"
                "（取两物体顶点落在对方内部的最近距离最大值，非质心代理值）"
                % (pen["overlap_tris"], pen["depth_mm"]),
                {"bvh": "world_space_frompolygons",
                 "depth_method": pen.get("depth_method"),
                 "aabb_only_would_report": bool(above_ta)},
                scope=scope))


# ============================================================ 墙体 / 天花 / 贴墙

def check_walls(chk, names, findings, rules, scope):
    tol = rules["tolerances"]
    room = rules["room"]
    wall_cfg = rules.get("wall_mounted_expect", {})
    x0, x1 = room["x"]
    y0, y1 = room["y"]
    z1 = room["z"][1]
    pen_min = tol["wall_penetration_min_mm"] / 1000.0
    gap_lo, gap_hi = [v / 1000.0 for v in tol["wall_gap_mm"]]
    ceil_min = tol["ceil_penetration_min_mm"] / 1000.0
    objs = chk.objects
    for n in names:
        io = objs[n]
        role, reason = chk.classify(n)
        if role in ("ignore", "component"):
            # component：装配子件跟随父件，不单独判「贴墙/穿墙」——
            # 否则柜门把手、抽屉拉手会被报成"挂墙物间隙超标"（v3 实测会多出几十条噪声）。
            continue
        # 穿墙
        pens = []
        if io.aabb_min[0] < x0 - 1e-9:
            pens.append(("-x", x0 - float(io.aabb_min[0])))
        if io.aabb_max[0] > x1 + 1e-9:
            pens.append(("+x", float(io.aabb_max[0]) - x1))
        if io.aabb_min[1] < y0 - 1e-9:
            pens.append(("-y", y0 - float(io.aabb_min[1])))
        if io.aabb_max[1] > y1 + 1e-9:
            pens.append(("+y", float(io.aabb_max[1]) - y1))
        if pens:
            pens.sort(key=lambda t: -t[1])
            axis, depth = pens[0]
            if depth > pen_min:
                coll, mod, owner = Q.attribute([n], objs, rules)
                findings.append(Q.finding(
                    "WALL-%s" % n, "wall_penetration", "FAIL", [n], mod, owner, io.center,
                    {"wall": axis, "depth_mm": round(depth * 1000.0, 2),
                     "aabb": [Q.r(io.aabb_min), Q.r(io.aabb_max)], "role": role},
                    "§11.2 静态物体不得插进墙体（内墙面 x=±4.0 / y=±3.0，>5mm 报 FAIL）",
                    "AABB 沿 %s 越过内墙面 %.2fmm" % (axis, depth * 1000.0),
                    {"wall_t": room["wall_t"]}, scope=scope))
        # 挂墙间隙
        if role == "wall":
            cands = Q.wall_proximity(io, room)
            want = None
            for pat, sides in wall_cfg.items():
                if fnmatch.fnmatchcase(n, pat):
                    want = [s.strip() for s in sides.split(",")]
                    break
            if want:
                cands = [c for c in cands if c[0] in want] + [c for c in cands if c[0] not in want]
            axis, gap = cands[0]
            # 贴墙容差可按物体类型分级（qc_rules.tolerances.wall_gap_mm_by_pattern）：
            # 画框/黑板框的「框料深度」天然产生 ~10mm 安装留缝，与 §11.2 的 0–6mm
            # 不冲突 —— 那是「挂画留缝」而非「悬空缺陷」。基准面取自实测墙内表面。
            gap_fail = gap_hi
            gap_rule_txt = "§11.2 挂墙物与墙间隙 ∈ [0, 6mm]"
            for pat, pat_mm, why in (tol.get("wall_gap_mm_by_pattern") or []):
                if fnmatch.fnmatchcase(n, pat):
                    gap_fail = pat_mm / 1000.0
                    gap_rule_txt = "§11.2 挂墙物与墙间隙（%s：容差放宽到 0–%.0fmm）" % (
                        pat, pat_mm)
                    break
            if gap >= -1e-9 and gap > gap_fail:
                coll, mod, owner = Q.attribute([n], objs, rules)
                # 「超出量在 warn_band 内」降级为 WARN（Lead 裁决：画框 10mm 是挂画安装间隙，
                # 保留判据但记 WARN 不阻塞交付；放宽容差会掩盖真问题，降级严重度更诚实）
                warn_band = tol.get("wall_gap_warn_band_mm", 0.0) / 1000.0
                over = gap - gap_fail
                sev = "WARN" if over <= warn_band + 1e-9 else "FAIL"
                findings.append(Q.finding(
                    "WGAP-%s" % n, "wall_gap", sev, [n], mod, owner, io.center,
                    {"wall": axis, "gap_mm": round(gap * 1000.0, 2),
                     "expect_mm": [tol["wall_gap_mm"][0], round(gap_fail * 1000.0, 1)],
                     "excess_mm": round(over * 1000.0, 2),
                     "role": role, "role_reason": reason},
                    gap_rule_txt,
                    "挂墙物 %s 距 %s 内墙面 %.2fmm（应 0–%.0fmm，超出 %.2fmm）%s" % (
                        n, axis, gap * 1000.0, gap_fail * 1000.0, over * 1000.0,
                        " —— 属挂画安装间隙，记 WARN" if sev == "WARN" else ""),
                    {}, scope=scope))
        # 天花
        top = float(io.aabb_max[2])
        if top > z1 + 1e-9:
            depth = top - z1
            if depth > ceil_min:
                coll, mod, owner = Q.attribute([n], objs, rules)
                findings.append(Q.finding(
                    "CEIL-%s" % n, "ceiling_penetration", "FAIL", [n], mod, owner, io.center,
                    {"depth_mm": round(depth * 1000.0, 2), "role": role,
                     "top_z": round(top, 4), "ceil_z": z1},
                    "§11.2 吊灯/纱帘不得穿天花（顶面 z ≤ 3.0）",
                    "顶面 z=%.4f 穿出天花 %.2fmm" % (top, depth * 1000.0),
                    {}, scope=scope))


# ============================================================ 落地 / 支撑 / 悬空

def aggregate_members(chk, rules):
    """返回 {物体名: 它所属的 aggregate 组定义}，供个体落地判据跳过。

    **只收 group 里带 tolerance_mm 的组（有整组落地判据的）**；
    道具归属组（maid_props）不参与跳过，否则托盘道具会漏掉落地检查。
    """
    objs = chk.objects
    out = {}
    for agg in rules.get("aggregate_ground", []):
        if agg.get("tolerance_mm") is None:
            continue
        for n in objs:
            if n in chk.components:
                continue        # 子件已由 component 角色处理
            if objs[n].coll == agg["group"] and any(
                    fnmatch.fnmatchcase(n, p) for p in agg["patterns"]):
                out[n] = agg
    return out


def check_ground(chk, names, findings, rules, scope, agg_set=None):
    """落地 / 支撑 / 悬空。

    agg_set：由 aggregate_ground 接管的物体（女仆 68 网格）。
    **这些物体必须跳个体落地判据** —— §11.3 要按「整组最低点」判脚底；
    逐个判会把「女仆躯干从 z=0.06 起」这种正常连接件报成 floating
    （桩场景实测到：MD_Body 被误报，而整组脚底 z=0 其实是合格的）。
    """
    tol = rules["tolerances"]
    g_lo, g_hi = [v / 1000.0 for v in tol["ground_band_mm"]]
    rest_max = tol["rest_on_max_gap_mm"] / 1000.0
    search_m = tol["support_search_mm"] / 1000.0
    objs = chk.objects
    agg_set = agg_set or set()
    pool = [objs[c] for c in objs if not chk.ignored(c)]
    supports = {}
    for n in names:
        if n in agg_set:
            supports[n] = {"type": "aggregate_group",
                           "handled_by": "aggregate_ground（按整组最低点判定，§11.3）"}
            continue
        io = objs[n]
        role, reason = chk.classify(n)
        if role in ("ignore", "wall", "hang"):
            continue
        if role == "component":
            # 装配子件（抽屉把手/柜门/杯架钩）靠父件支撑，不各自贴地。
            # v1 实测：不跳过会产出 138 条 floating 误报（把正常柜门当悬空物）。
            supports[n] = {"type": "component_of",
                           "object": (chk.components.get(n) or {}).get("component_of"),
                           "by": (chk.components.get(n) or {}).get("by")}
            continue
        if role == "attached":
            # 附件（把手/旋钮/贴纸/支架/门/导轨/拉手）：附着于最近的主体，**不参与落地判据**。
            # v5 实测：不豁免会产出 28 条 cbar handle 悬空（BA_MugHandle_* 报 1189mm 等），
            # 而门把手本来就不该贴地 —— Lead 已明确裁决这类按「附着」处理。
            supports[n] = {"type": "attached", "reason": reason}
            continue
        zmin = float(io.aabb_min[2])
        if g_lo <= zmin <= g_hi:
            supports[n] = {"type": "floor", "gap_mm": round(zmin * 1000.0, 2)}
            continue
        if zmin < g_lo:
            coll, mod, owner = Q.attribute([n], objs, rules)
            findings.append(Q.finding(
                "SINK-%s" % n, "floor_penetration", "FAIL", [n], mod, owner, io.center,
                {"min_z_mm": round(zmin * 1000.0, 2), "expect_mm": tol["ground_band_mm"],
                 "role": role, "role_reason": reason},
                "§11.2 落地物 min_z ∈ [-2mm, +2mm]",
                "最低点 z=%.2fmm，陷进地面 %.2fmm" % (zmin * 1000.0, -zmin * 1000.0),
                {}, scope=scope))
            continue
        sink_max = tol.get("rest_on_sink_mm", 20.0) / 1000.0
        hit = Q.find_supports(io, pool, max(rest_max, sink_max))
        if hit:
            # 底面陷进支撑物（dz<0）也算被托住：这种缺陷已由「干涉」判据覆盖，
            # 这里再报一次 floating 会让同一个问题出现两条 finding（校准发现的重复计数）。
            name0, dz0 = hit[0]
            if dz0 >= 0.0 and dz0 > rest_max:
                hit = []   # 间隙超过允许值 → 不算被支撑，继续走 floating 分支
            else:
                supports[n] = {"type": "rest_on", "object": name0,
                               "gap_mm": round(dz0 * 1000.0, 2)}
                continue
        below = Q.nearest_below(io, pool, search_m)
        coll, mod, owner = Q.attribute([n], objs, rules)
        # 报告口径（qc_rules.tolerances._floating_report_semantics）：
        #   min_z_mm 只作定位参考；真正表示「悬空多少」的是 support_gap_mm。
        #   v5 实测教训：DC_WinPot 坐窗台上，底 0.770 / 窗台顶 0.722，实际差 48mm，
        #   但只写 min_z=770mm 会被误读成"飘在 0.77m 高空"。
        if below:
            sup_obj = objs.get(below[0])
            gap_mm = round(below[1] * 1000.0, 2)
            sup_top_z = round(float(sup_obj.aabb_max[2]), 4) if sup_obj else None
            note = ("最低点 z=%.2fmm；正下方最近 %s 顶面 z=%.3f，**实际悬空间隙 %.2fmm**"
                    "（>%.1fmm 允许间隙）"
                    % (zmin * 1000.0, below[0], (sup_top_z or 0), gap_mm, rest_max * 1000.0))
        else:
            gap_mm = None
            sup_top_z = None
            note = ("最低点 z=%.2fmm 离地，且 %.0fmm 内找不到可支撑面"
                    "（真实悬空量 = %.2fmm）"
                    % (zmin * 1000.0, search_m * 1000, zmin * 1000.0))
        metrics = {"min_z_mm": round(zmin * 1000.0, 2),
                   "expect_mm": tol["ground_band_mm"],
                   "role": role, "role_reason": reason,
                   "nearest_support": (below[0] if below else None),
                   "support_top_z": sup_top_z,
                   "support_gap_mm": gap_mm,
                   "floating_amount_mm": (gap_mm if gap_mm is not None else round(zmin * 1000.0, 2)),
                   "support_search_mm": tol["support_search_mm"]}
        # 多实体合并体（如 DC_PlantLeaves 6849 顶点跨 5m）：附簇数提示，
        # 让负责人知道"越界的是其中部分实体"，而不是整件都在飘。
        span_m = float(max(io.aabb_max - io.aabb_min))
        if (span_m >= tol.get("merged_obj_span_m", 2.0)
                and io.tri_count >= tol.get("merged_obj_verts", 1000)):
            metrics["merged_object"] = True
            metrics["aabb_span_m"] = round(span_m, 3)
            note += "  ⚠ 该物体是多实体合并体（AABB 跨 %.2fm、%d 三角面），越界可能只涉及其中部分实体。" % (
                span_m, io.tri_count)
        findings.append(Q.finding(
            "FLOAT-%s" % n, "floating", "FAIL", [n], mod, owner, io.center,
            metrics,
            "§11.2 落地物 min_z ∈ [-2mm, +2mm]（或明确被支撑）；"
            "『悬空量』以 support_gap_mm / floating_amount_mm 为准", note, {}, scope=scope))
    return supports


# ============================================================ 女仆整组脚底

def check_aggregate_ground(chk, findings, rules, scope):
    """整组落地判据（§11.3 女仆脚底）+ 托盘道具归属（§7）。

    注意 patterns 语义：['*'] 表示「整个集合」，用于 C_Maid —— 女仆 106 个网格的
    实际名字是 Apron/Arm/Skirt 等，**没有 MD_ 前缀**（v1 实测），靠前缀匹配会漏掉全部。
    """
    objs = chk.objects
    tol = rules["tolerances"]
    for agg in rules.get("aggregate_ground", []):
        members = [n for n in objs
                   if objs[n].coll == agg["group"]
                   and any(fnmatch.fnmatchcase(n, p) for p in agg["patterns"])
                   and not chk.ignored(n)]
        if not members:
            continue
        # ---- (a) 整组最低点（只对定义了 tolerance 的组）
        tol_mm = agg.get("tolerance_mm")
        if tol_mm is not None:
            zmin = min(float(objs[n].aabb_min[2]) for n in members)
            lo, hi = [v / 1000.0 for v in tol_mm]
            if not (lo <= zmin <= hi):
                worst = min(members, key=lambda n: objs[n].aabb_min[2])
                coll, mod, owner = Q.attribute(members, objs, rules)
                findings.append(Q.finding(
                    "AGG-%s" % agg["id"], "ground_contact", "FAIL", [worst], mod, owner,
                    objs[worst].center,
                    {"group_min_z_mm": round(zmin * 1000.0, 2), "group_size": len(members),
                     "expect_mm": tol_mm, "lowest_object": worst},
                    agg["rule"],
                    "%s 组最低点 z=%.2fmm（%d 个网格参与）" % (
                        agg["group"], zmin * 1000.0, len(members)),
                    {}, scope=scope))
        # ---- (b) 道具必须落在容器 AABB 内（托盘上的杯子/蛋糕/咖啡）
        containers = [n for n in members if n in (agg.get("container") or [])]
        props = [n for n in members if n in (agg.get("props") or [])]
        if containers and props:
            cmin = np.min([objs[c].aabb_min for c in containers], axis=0)
            cmax = np.max([objs[c].aabb_max for c in containers], axis=0)
            for p in props:
                po = objs[p]
                # **只判水平越界**：托盘上的东西是多层叠放的（蛋糕底→奶油→顶→草莓；
                # 杯→咖啡），纵向天然高于托盘顶面，按纵向判会把正常叠放全报成越界（v3 实测 10 条）。
                out = np.maximum(cmin - po.aabb_min, po.aabb_max - cmax)
                worst_out = float(max(out[0], out[1])) * 1000.0
                if worst_out > tol.get("prop_overflow_tolerance_mm", 5.0):
                    coll, mod, owner = Q.attribute([p], objs, rules)
                    findings.append(Q.finding(
                        "PROP-%s" % p, "prop_outside_container", "FAIL", [p], mod, owner,
                        po.center,
                        {"horizontal_overflow_mm": round(worst_out, 2),
                         "container": containers,
                         "container_aabb": [Q.r(cmin), Q.r(cmax)],
                         "prop_aabb": [Q.r(po.aabb_min), Q.r(po.aabb_max)]},
                        agg["rule"],
                        "道具 %s 水平超出托盘范围 %.2fmm（杯子/蛋糕必须落在托盘内）"
                        % (p, worst_out),
                        {}, scope=scope))


# ============================================================ 关键配对（点名复核）

def critical_pairs(chk, findings, rules, scope, spec="MD_Tray:Hand,MD_Tray:Hand.001,"
                                                  "MD_Cup:MD_Tray,MD_CakeBase:MD_Plate,"
                                                  "MD_Tray:Apron,MD_Tray:Bodice,"
                                                  "MD_Body:BA_BarMain"):
    """点名复核必须判的配对 —— 这些对里很多落在 C_Maid 的同集合豁免内
    （女仆 106 网格互相豁免），盲扫看不到，必须显式点名。

    输出 dir="interior"（嵌在里面对该配对是正常的，如杯在托盘内）或
    "must_not_overlap"（跨模块互穿必须查）。
    """
    objs = chk.objects
    names = list(objs.keys())
    arts = []
    for item in spec.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        a, b = item.split(":", 1)
        la = [a] if a in objs else sorted(n for n in names if fnmatch.fnmatchcase(n, a))
        lb = [b] if b in objs else sorted(n for n in names if fnmatch.fnmatchcase(n, b))
        for x in la:
            for y in lb:
                if x == y:
                    continue
                pen = chk.penetration(x, y)
                arts.append({
                    "pair": "%s : %s" % (x, y),
                    "digest": {"overlap_tris": pen["overlap_tris"],
                               "aabb_mtv_mm": pen["overlap_aabb_mm"],
                               "depth_mm": pen["depth_mm"]},
                    "module_x": objs[x].coll, "module_y": objs[y].coll,
                    "same_collection": objs[x].coll == objs[y].coll,
                })
        if not la or not lb:
            arts.append({"pair": item, "digest": None,
                         "missing": ([a] if not la else []) + ([b] if not lb else []),
                         "note": "物体名在场景里不存在"})
    return arts


# ============================================================ 主流程

def run_checks(chk, scope=None, limit=200, min_overlap_mm=None, rules=None):
    rules = rules or chk.rules
    objs = chk.objects
    findings = []
    stats = {
        "pairs_total": 0, "pairs_aabb_touch": 0, "pairs_aabb_within_tolerance": 0,
        "pairs_exempted": 0, "pairs_aabb_false_positive": 0, "pairs_bvh_overlap": 0,
        "pairs_touch_only": 0, "pairs_grazing": 0, "bvh_pair_checks": 0, "tri_overlap_total": 0,
    }
    names = [n for n in objs if Q.scope_match(n, scope, objs) and not chk.ignored(n)]
    # 装配子件识别（必须早于任何 role 判定）
    t0 = time.time()
    chk.components = Q.annotate_components(objs, rules)
    stats["components"] = len(chk.components)
    stats["time_components_s"] = round(time.time() - t0, 2)
    t0 = time.time()
    check_interference(chk, names, findings, stats, rules, scope, min_overlap_mm)
    stats["time_interference_s"] = round(time.time() - t0, 2)
    t0 = time.time()
    check_walls(chk, names, findings, rules, scope)
    check_aggregate_ground(chk, findings, rules, scope)
    agg = set(aggregate_members(chk, rules).keys())
    supports = check_ground(chk, names, findings, rules, scope, agg_set=agg)
    stats["critical_pairs"] = critical_pairs(chk, findings, rules, scope)
    stats["aggregate_group_size"] = len(agg)
    stats["time_ground_s"] = round(time.time() - t0, 2)
    stats["supported_count"] = len([v for v in supports.values() if v.get("type") != "aggregate_group"])
    findings.sort(key=lambda f: (Q.SEV_ORDER.get(f["severity"], 9), f["kind"], f["id"]))
    return findings, stats, supports


# ============================================================ 校准场景（自测工具本身）

def build_calib_scene():
    """11 个已知用例，每个都有明确期望：
       require = 必须出现的 finding kind；forbid = 不允许出现（出现即误报）。
       expected_exempt = 期望被豁免的配对（验证豁免机制真的生效，而不是碰巧没报）。

    这条校准验证的是**工具本身**，与真场景质量无关；结果写进 QC-REPORT「方法校准」节。
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    colls = {}
    for name in ("C_Room", "C_Maid", "C_Seating", "C_Decor", "C_Light"):
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        colls[name] = c

    def box(name, loc, size, coll, rot_z_deg=0.0):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
        ob = bpy.context.active_object
        ob.name = name
        ob.scale = size
        if rot_z_deg:
            ob.rotation_euler = (0.0, 0.0, math.radians(rot_z_deg))
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        colls[coll].objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        ob.select_set(False)
        return ob

    # CASE 01 PEN —— 20mm 互穿（两者都落地，排除落地噪声）
    box("TB_PenA", (1.00, 0.00, 0.10), (0.20, 0.20, 0.20), "C_Seating")   # x∈[0.90,1.10]
    box("TB_PenB", (1.18, 0.00, 0.10), (0.20, 0.20, 0.20), "C_Seating")   # x∈[1.08,1.28] 重叠 20mm
    # CASE 02 FLOAT —— 底面 z=0.05，离地 50mm
    box("TB_Float", (2.00, 0.00, 0.15), (0.20, 0.20, 0.20), "C_Seating")
    # CASE 03 SINK —— 陷地 20mm
    box("TB_Sink", (2.50, 0.00, 0.08), (0.20, 0.20, 0.20), "C_Seating")
    # CASE 04 WALLPEN —— 越过 x=+4.0 内墙面 20mm（x∈[3.92,4.02]）
    box("DC_WallPen", (3.97, 0.00, 1.50), (0.10, 0.10, 0.10), "C_Decor")
    # CASE 05 WALLGAP —— 距墙 20mm（应 0–6mm；x∈[3.88,3.98]）
    box("DC_WallGap", (3.93, 0.30, 1.50), (0.10, 0.10, 0.10), "C_Decor")
    # CASE 06 NEST_LEGAL —— 杯子在托盘内（C_Maid 同集合豁免），托盘放在手上（rest_on）
    box("MD_Hands", (-1.70, 0.30, 0.60), (0.26, 0.20, 0.52), "C_Maid")     # 顶面 z=0.86
    box("MD_Tray", (-1.70, 0.30, 0.865), (0.30, 0.30, 0.01), "C_Maid")     # 底面 0.86，垫在手上
    box("MD_Cup", (-1.70, 0.30, 0.885), (0.08, 0.08, 0.06), "C_Maid")      # 与托盘重叠 10mm
    # CASE 07 AABB_FALSE_POSITIVE —— 两根 45° 平行细杆：AABB 大量相交，几何间隔 50mm
    box("TB_RodA", (0.00, 0.00, 0.15), (0.80, 0.03, 0.30), "C_Seating", rot_z_deg=45)
    box("TB_RodB", (0.0566, -0.0566, 0.15), (0.80, 0.03, 0.30), "C_Seating", rot_z_deg=45)
    # CASE 08 SOFT_CHAIR —— 椅子插桌下（kind:soft 豁免，不自报 interference）
    box("TB_Table", (-2.50, -2.00, 0.37), (0.80, 0.80, 0.74), "C_Seating")  # 桌面 z=0.74
    box("CH_Chair", (-2.50, -2.45, 0.40), (0.30, 0.30, 0.80), "C_Seating")  # 顶到 0.80 穿桌 60mm
    # CASE 09 SAME_COLL_NOT_EXEMPT —— 同集合（C_Seating）两件家具互穿：必须报（反例）
    box("TB_TwinA", (2.00, 2.00, 0.10), (0.20, 0.20, 0.20), "C_Seating")
    box("TB_TwinB", (2.15, 2.00, 0.10), (0.20, 0.20, 0.20), "C_Seating")   # 重叠 50mm
    # CASE 10 REST_ON_TABLE —— 杯子落在桌面（合法支撑，不许报 floating）
    box("TB_Table2", (0.50, -1.50, 0.37), (0.60, 0.60, 0.74), "C_Seating")
    box("TB_CupOnTable", (0.50, -1.50, 0.77), (0.08, 0.08, 0.06), "C_Seating")
    # CASE 11 MAID_FEET —— 女仆整组最低点离地 20mm
    box("MD_Body", (-1.70, 0.30, 0.62), (0.40, 0.30, 1.20), "C_Maid")       # z∈[0.02,1.22]
    # 干扰项：灯光对象不该进入 mesh 体检
    light = bpy.data.lights.new("L1", type='POINT')
    lob = bpy.data.objects.new("LT_Test", light)
    lob.location = (1, 1, 2)
    colls["C_Light"].objects.link(lob)

    expected = [
        {"case": "01_PEN", "objects": ["TB_PenA", "TB_PenB"],
         "require": ["interference"], "forbid": []},
        {"case": "02_FLOAT", "objects": ["TB_Float"],
         "require": ["floating"], "forbid": []},
        {"case": "03_SINK", "objects": ["TB_Sink"],
         "require": ["floor_penetration"], "forbid": []},
        {"case": "04_WALLPEN", "objects": ["DC_WallPen"],
         "require": ["wall_penetration"], "forbid": []},
        {"case": "05_WALLGAP", "objects": ["DC_WallGap"],
         "require": ["wall_gap"], "forbid": []},
        {"case": "06_NEST_LEGAL", "objects": ["MD_Cup", "MD_Tray"],
         "require": [], "forbid": ["interference", "floating"],
         "expect_exempt": [["MD_Cup", "MD_Tray"]]},
        {"case": "07_AABB_FALSE_POSITIVE", "objects": ["TB_RodA", "TB_RodB"],
         "require": [], "forbid": ["interference"]},
        {"case": "08_SOFT_CHAIR", "objects": ["CH_Chair", "TB_Table"],
         "require": [], "forbid": ["interference"],
         "expect_exempt": [["CH_Chair", "TB_Table"]]},
        {"case": "09_SAME_COLL_NOT_EXEMPT", "objects": ["TB_TwinA", "TB_TwinB"],
         "require": ["interference"], "forbid": []},
        {"case": "10_REST_ON_TABLE", "objects": ["TB_CupOnTable", "TB_Table2"],
         "require": [], "forbid": ["interference", "floating"]},
        {"case": "11_MAID_FEET", "objects": ["MD_Body"],
         "require": ["ground_contact"], "forbid": []},
    ]
    return expected


def run_calib(rules, out_path):
    t0 = time.time()
    expected = build_calib_scene()
    bpy.context.view_layer.update()
    objects, skipped = Q.collect_objects(rules, include_hidden=True)
    # 校准场景无 scene_manifest.json → 走 soft_fallback_patterns（CH_*），并显式记录来源
    chk = Q.Checker(rules, objects, kinds={}, skipped=skipped)
    findings, stats, supports = run_checks(chk, scope=None, rules=rules)

    by_obj = {}
    for f in findings:
        for o in f["objects"]:
            by_obj.setdefault(o, []).append(f)
    exempted = {(e["a"], e["b"]): e["why"] for e in (stats.get("exemptions") or [])}

    results = []
    caught = 0
    for exp in expected:
        hits = []
        for o in exp["objects"]:
            for h in by_obj.get(o, []):
                if h not in hits:
                    hits.append(h)
        kinds = sorted({h["kind"] for h in hits})
        missing = [k for k in exp["require"] if k not in kinds]
        forbidden = [k for k in exp["forbid"] if k in kinds]
        exempt_ok, exempt_detail = True, []
        for pair in exp.get("expect_exempt", []):
            a, b = pair
            got = exempted.get((a, b)) or exempted.get((b, a))
            if not got:
                exempt_ok = False
                exempt_detail.append("豁免未生效 %s|%s" % (a, b))
            else:
                exempt_detail.append("%s|%s → %s" % (a, b, got))
        ok = not missing and not forbidden and exempt_ok
        if ok:
            caught += 1
        detail = "OK" if ok else "; ".join(
            ([("漏报 " + ",".join(missing))] if missing else []) +
            ([("误报 " + ",".join(forbidden))] if forbidden else []) + exempt_detail)
        results.append({
            "case": exp["case"], "require": exp["require"], "forbid": exp["forbid"],
            "objects": exp["objects"], "ok": ok, "detail": detail,
            "finding_kinds": kinds, "exemptions": exempt_detail,
            "findings": [{"id": h["id"], "kind": h["kind"], "severity": h["severity"]} for h in hits],
        })

    fn = [r["case"] for r in results if ("漏报" in r["detail"])]
    fp = [r["case"] for r in results if ("误报" in r["detail"])]
    ex_fail = [r["case"] for r in results if ("豁免未生效" in r["detail"])]
    tags = sorted({o.coll for o in objects.values()})
    coll_obj = {k: 0 for k in tags}
    for o in objects.values():
        coll_obj[o.coll] = coll_obj.get(o.coll, 0) + 1
    payload = {
        "kind": "collide_calib",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "blender": bpy.app.version_string,
        "rules_md5": rules.get("_rules_md5"),
        "elapsed_s": round(time.time() - t0, 2),
        "cases": len(expected),
        "caught": caught,
        "capture_rate": round(caught / float(len(expected)), 4),
        "false_negative_cases": fn,
        "false_positive_cases": fp,
        "exemption_miss_cases": ex_fail,
        "verdict": "PASS" if (not fn and not fp and not ex_fail) else "FAIL",
        "test_scene": {"objects": len(objects), "by_collection": coll_obj,
                       "skipped": skipped, "tri_total": sum(o.tri_count for o in objects.values())},
        "stats": stats,
        "details": results,
        "note": "校准只验证工具本身的捕获率/误报率/豁免生效，与真场景质量无关。",
    }
    Q.finish(payload, out_path or Q.default_calib_out(rules, "collide_calib"))
    return payload


# ============================================================ 入口

def main():
    ap = Q.base_parser("qc_collide")
    ap.add_argument("--calib", action="store_true", help="跑自测校准（自建 11 个已知用例）")
    ap.add_argument("--min-overlap-mm", type=float, default=None, help="覆盖 §11.1 的 5mm 阈值")
    args = Q.parse_args_lenient(ap, Q.cli_argv())
    rules = Q.load_rules(args.rules)

    if args.calib:
        return run_calib(rules, args.out)

    t0 = time.time()
    info = Q.open_scene(args)
    if info.get("path"):
        rules["root"] = os.path.dirname(os.path.dirname(os.path.abspath(info["path"])))
    objects, skipped = Q.collect_objects(rules, include_hidden=args.include_hidden)
    manifest, kinds, coll_detail = Q.load_manifest_colliders(rules["root"], rules)
    chk = Q.Checker(rules, objects, manifest=manifest, kinds=kinds, skipped=skipped,
                            colliders_detail=coll_detail)
    findings, stats, supports = run_checks(chk, scope=args.scope, limit=args.limit,
                                           min_overlap_mm=args.min_overlap_mm, rules=rules)
    snap = Q.scene_snapshot(rules, objects, skipped, info)
    payload = {
        "kind": KIND,
        "scope": args.scope,
        "tag": args.tag,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - t0, 2),
        "verdict": Q.verdict_of(findings),
        "summary": Q.summarize(findings),
        "stats": stats,
        "scene": snap,
        "manifest_present": bool(manifest),
        "supports": supports,
        "critical_pairs": stats.get("critical_pairs"),
        "roles": {n: {"role": chk.classify(n)[0], "reason": chk.classify(n)[1]}
                  for n in objects if Q.scope_match(n, args.scope, objects)},
        "findings": findings[:args.limit],
        "findings_total": len(findings),
        "findings_truncated": max(0, len(findings) - args.limit),
        "rules_md5": rules.get("_rules_md5"),
    }
    out = args.out or Q.default_out(rules, "collide" + (("_" + args.tag) if args.tag else ""))
    Q.finish(payload, out, quiet=args.quiet)


if __name__ == "__main__":
    main()
