# -*- coding: utf-8 -*-
"""qc_report.py — 把各体检 JSON 汇总成 docs/QC-REPORT.md + docs/qc_findings.json

设计：
  · 不自己采集数据 —— 只读 qc_collide / qc_pairs / qc_light / qc_gltf 落盘的结果 JSON，
    这样每条结论都能追溯到原始 evidence 文件（可复跑、可复核）。
  · QC-REPORT.md **追加**一节（每轮一条，按版本/时间/结论三态），不覆盖历史 ——
    契约 §12「每轮重跑后给 QC-REPORT.md 追加一节」。
  · qc_findings.json 是**当前快照**（覆盖写），供 Lead/网页工具直接消费；
    历史在 .scratch/qc/results/ 的带 tag 文件里。
  · 问题按责任模块分组，每条给：物体名 / 坐标 / 关键数字 / 规则 / 证据路径。

用法（不需要 Blender，纯 python 就能跑）：
  python blender/qc/qc_report.py --tag v1 --blend scene/maid_cafe.blend
  python blender/qc/qc_report.py --tag v1 --notes "几何第一版"
"""

import os
import sys
import json
import time
import argparse
import glob
import fnmatch
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

QC_DIR = os.path.dirname(os.path.abspath(__file__))


def root_of():
    return os.path.dirname(os.path.dirname(QC_DIR))


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_rules():
    return read_json(os.path.join(QC_DIR, "qc_rules.json"), {}) or {}


# ---------------------------------------------------------------- 结果聚合

KIND_LABEL = {
    "collide": "穿模 / 干涉 / 落地 / 贴墙",
    "pairs": "指定物体对间距 / 穿透",
    "light": "光影（4 时段 × 3 天气）",
    "gltf": "GLB 交付合规",
}
KIND_ORDER = ["collide", "pairs", "light", "gltf"]


def collect_results(results_dir, tag=None):
    """读取 results 目录下所有体检 JSON；tag 给了就优先用带 tag 的文件。

    **必须排除 calib/selftest 文件** —— 它们是「工具自身的校准」，不是场景体检结果。
    踩过的坑：collide_calib.json 能被 `collide*.json` 匹配到，于是「真场景一次没跑」
    也会得到全 PASS 的汇总结论（自测时实测到）。
    """
    excluded = ("calib", "selftest", "allow_list")
    out = {}
    for kind in KIND_ORDER:
        cands = [p for p in glob.glob(os.path.join(results_dir, kind + "*.json"))
                 if not any(x in os.path.basename(p) for x in excluded)]
        if tag:
            tagged = [p for p in cands if tag in os.path.basename(p)]
            if tagged:
                cands = tagged
            else:
                plain = [p for p in cands if tag not in os.path.basename(p)]
                if plain:
                    cands = plain
        if not cands:
            out[kind] = None
            continue
        # 取最新修改的
        p = max(cands, key=lambda x: os.stat(x).st_mtime)
        data = read_json(p)
        out[kind] = {"path": p, "data": data} if data else None
    return out


def collect_calibrations(results_dir, root=None):
    """读 4 个校准/自测结果（在独立目录，见 Q.default_calib_out），给报告「方法校准」节。"""
    cal = {}
    dirs = [os.path.join(root or root_of(), ".scratch", "qc", "calib_results"),
            results_dir]   # 兼容旧位置
    for name in ("collide_calib", "pairs_selftest", "light_selftest", "gltf_selftest"):
        found = None
        for d in dirs:
            p = os.path.join(d, name + ".json")
            if os.path.isfile(p):
                d0 = read_json(p)
                if d0:
                    found = {"path": p, "data": d0}
                    break
        if found:
            cal[name] = found
    return cal


def all_findings(bundle):
    findings = []
    for kind in KIND_ORDER:
        entry = bundle.get(kind)
        if not entry:
            continue
        data = entry["data"]
        for f in (data.get("findings") or []):
            f = dict(f)
            f.setdefault("source_kind", kind)
            f["source_file"] = os.path.basename(entry["path"])
            findings.append(f)
    return findings


def group_by_module(findings, rules):
    """按责任模块分组，同时给出负责人。

    **owner 以 qc_rules.module_owner 为准，不信 finding 里固化的旧值**：
    v6 实测教训 —— 归属被 Lead 改派后（cdecor: decor-modeler → env-decor-v2），
    旧结果 JSON 里写的 owner 已过期，若直接沿用会把活派给错的人。
    """
    owners = rules.get("module_owner", {})
    groups = {}
    for f in findings:
        mod = f.get("module") or "?"
        owner = owners.get(mod) or f.get("owner") or "?"
        f["owner"] = owner          # 就地修正，便于 qc_findings.json 也正确
        key = "%s/%s" % (mod, owner)
        groups.setdefault(key, []).append(f)
    for key in groups:
        groups[key].sort(key=lambda x: (0 if x.get("severity") == "FAIL" else 1, x.get("id", "")))
    return dict(sorted(groups.items()))


def scene_fingerprint_ok(entry, blend_md5):
    """校验结果文件记录的场景 md5 与当前 .blend 是否一致。

    返回 (ok, detail)。ok=False 时该结果不可用于本轮结论 ——
    这正是「拿探针场景/旧版本结果冒充本轮」的防线（自测时真实发生过）。
    """
    if not entry:
        return False, "无结果"
    d = entry["data"]
    rec = d.get("scene_md5")
    if not rec:
        sc = d.get("scene") or {}
        if isinstance(sc, dict):
            rec = (sc.get("scene") or {}).get("md5") or sc.get("md5")
    if not rec:
        return True, "结果未记录场景 md5（旧格式，无法核对）"
    if not blend_md5:
        return True, "当前 .blend 不存在，无法核对"
    if rec != blend_md5:
        return False, "场景 md5 不符：结果 %s… vs 当前 %s…" % (rec[:10], blend_md5[:10])
    return True, "场景 md5 一致"


def overall_verdict(bundle, scene_present=True, stale=None):
    """三态总判：任一 FAIL → FAIL；否则任一待确认/WARN → 待确认；否则 PASS。

    两条「不许放行」规则（都是为了不让空场景骗出一个 PASS）：
      · 某项体检**未运行**（缺结果文件）→ 待确认；
      · 被检对象**根本不存在**（.blend 还没生成）→ 待确认。
      · 结果记录的场景 md5 与当前 .blend 不符（stale）→ 待确认。
    """
    missing = [k for k in KIND_ORDER if not bundle.get(k)]
    stale = stale or []
    verdicts = {}
    for kind in KIND_ORDER:
        e = bundle.get(kind)
        verdicts[kind] = (e["data"].get("verdict") if e else "未运行")
    vals = [v for v in verdicts.values() if v != "未运行"]
    if "FAIL" in vals:
        v = "FAIL"
    elif any(x in ("待确认", "WARN") for x in vals) or missing or not scene_present or stale:
        v = "待确认"
    else:
        v = "PASS"
    return v, verdicts, missing


# ---------------------------------------------------------------- Markdown

def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return "\n".join(out)


def fmt_loc(loc):
    if not loc:
        return "—"
    try:
        return "(%.3f, %.3f, %.3f)" % (loc[0], loc[1], loc[2])
    except Exception:
        return str(loc)


def finding_row(f):
    m = f.get("metrics") or {}
    keys_priority = ["depth_mm", "overlap_tris", "aabb_mtv_mm", "min_z_mm", "gap_mm",
                     "min_dist_mm", "penetration_mm", "clearance_mm", "dead_black_ratio",
                     "blown_ratio", "mean_luma", "cct_k", "actual"]
    metrics = []
    for k in keys_priority:
        if k in m and m[k] is not None:
            metrics.append("%s=%s" % (k, m[k]))
    extra = [k for k in m if k not in keys_priority and m[k] is not None][:2]
    for k in extra:
        metrics.append("%s=%s" % (k, m[k]))
    ev = f.get("evidence") or {}
    evs = ev.get("render") or ev.get("glb") or ev.get("bvh") or ""
    objs = f.get("objects") or []
    return [
        f.get("severity"),
        ", ".join(objs[:3]) + ("…" if len(objs) > 3 else "") if objs else "—",
        fmt_loc(f.get("location")),
        "; ".join(metrics[:4]),
        f.get("note", ""),
        evs,
    ]


def build_markdown(tag, notes, bundle, calib, findings, groups, verdict, verdicts,
                   missing, rules, blend_info=None, extra=None, stale=None):
    md5 = hashlib.md5()
    for k in KIND_ORDER:
        e = bundle.get(k)
        if e:
            md5.update(("%s:%s;" % (k, md5_file(e["path"]))).encode())
    report_id = "QC-%s" % (md5.hexdigest()[:10] if bundle else "0000000000")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    L = []
    L.append("## QC 轮次 %s · %s · 结论 **%s**" % (tag or "(未标版本)", now, verdict))
    L.append("")
    L.append("> 本节由 `blender/qc/qc_report.py` 自动追加，**不要手改**；"
             "原始数据见 `.scratch/qc/results/`，判据见 `blender/qc/qc_rules.json`。")
    L.append("")
    L.append("### 1. 本轮结论")
    L.append("")
    rows = []
    for kind in KIND_ORDER:
        e = bundle.get(kind)
        if not e:
            rows.append([KIND_LABEL.get(kind, kind), "未运行", "—", "—"])
            continue
        d = e["data"]
        summ = d.get("summary") or {}
        if kind == "light":
            detail = "shots=%s FAIL=%s WARN=%s luma∈%s cct∈%s" % (
                summ.get("shots"), summ.get("FAIL"), summ.get("WARN"),
                summ.get("luma_range"), summ.get("cct_range"))
        elif kind == "gltf":
            detail = "checks=%s FAIL=%s tri=%s size=%sMB" % (
                summ.get("checks"), summ.get("FAIL"),
                summ.get("tri_total"), summ.get("mb"))
        elif kind == "pairs":
            detail = "pairs=%s FAIL=%s WARN=%s" % (
                summ.get("total"), summ.get("FAIL"), summ.get("WARN"))
        else:
            detail = "findings=%s FAIL=%s WARN=%s" % (
                (d.get("summary", {}).get("counts", {}) or {}).get("total"),
                (d.get("summary", {}).get("counts", {}) or {}).get("FAIL"),
                (d.get("summary", {}).get("counts", {}) or {}).get("WARN"))
        rows.append([KIND_LABEL.get(kind, kind), d.get("verdict", "?"),
                     detail, os.path.basename(e["path"])])
    L.append(md_table(["体检项", "三态结论", "关键数字", "结果文件"], rows))
    L.append("")
    if missing:
        L.append("**未运行的体检项：%s** —— 这些项不能当 PASS；"
                 "若其余项全通过，本轮结论最多只能到「待确认」。"
                 % ", ".join(KIND_LABEL.get(m, m) for m in missing))
        L.append("")
    if (blend_info or {}).get("state"):
        L.append("**场景状态：%s**（%s）—— 没有任何几何被检查过；"
                 "本轮若出现 PASS 一定是 bug（脚本已强制降级为「待确认」）。"
                 % (blend_info["state"], blend_info.get("blend")))
        L.append("")
    if stale:
        L.append("**场景指纹不符（结果不是这一版 .blend 跑出来的）：**")
        L.append("")
        for s in stale:
            L.append("- %s" % s)
        L.append("")
        L.append("这些结果不能用于本轮结论，已强制降级为「待确认」。请重跑对应体检项。")
        L.append("")

    # 汇总计数
    sev = {"FAIL": 0, "WARN": 0, "INFO": 0}
    for f in findings:
        s = f.get("severity", "INFO")
        sev[s] = sev.get(s, 0) + 1
    L.append("问题总数 **%d**：FAIL **%d** / 待确认 **%d** / INFO **%d**"
             % (len(findings), sev.get("FAIL", 0), sev.get("WARN", 0), sev.get("INFO", 0)))
    L.append("")

    # 2. 按责任模块分组
    L.append("### 2. 问题清单（按责任模块分组）")
    L.append("")
    if not groups:
        L.append("无 FAIL/WARN 级问题。")
        L.append("")
    for key, items in groups.items():
        fails = len([i for i in items if i.get("severity") == "FAIL"])
        L.append("#### %s — %d 条（FAIL %d）" % (key, len(items), fails))
        L.append("")
        L.append(md_table(
            ["级别", "物体", "坐标 (m)", "关键数字", "说明", "证据"],
            [finding_row(i) for i in items[:rules.get("report", {}).get("max_findings_inline", 120)]]))
        L.append("")
        if len(items) > 120:
            L.append("（该组共 %d 条，此处只列前 120，完整见 qc_findings.json）" % len(items))
            L.append("")

    # 3. 方法校准
    L.append("### 3. 方法校准（工具本身的捕获率，不是场景质量）")
    L.append("")
    if not calib:
        L.append("本轮未跑校准。**校准缺失时工具结论只能算「待确认」** —— 建议先跑：")
        L.append("")
        L.append("```bash")
        L.append("qc_collide.py --calib   # 11 个已知穿透/悬空/贴墙/豁免用例")
        L.append("qc_pairs.py --selftest  # 间距数值精度")
        L.append("qc_light.py --selftest  # 亮度/色温算法")
        L.append("qc_gltf.py --selftest   # GLB 解析器")
        L.append("```")
        L.append("")
    else:
        rows = []
        for name, e in calib.items():
            d = e["data"]
            if name == "collide_calib":
                rows.append(["qc_collide", d.get("verdict"),
                             "%s/%s 用例通过，捕获率 %s%%" % (
                                 d.get("caught"), d.get("cases"),
                                 round(100 * (d.get("capture_rate") or 0), 1)),
                             "漏报 %s / 误报 %s" % (
                                 ",".join(d.get("false_negative_cases") or []) or "无",
                                 ",".join(d.get("false_positive_cases") or []) or "无")])
            elif name == "pairs_selftest":
                rows.append(["qc_pairs", d.get("verdict"),
                             "%s/%s 用例，容差 %smm" % (
                                 d.get("passed"), d.get("cases"), d.get("tolerance_mm")),
                             "；".join("%s 实测 %s（期望 %s）" % (
                                 r["note"], r["measured_gap_mm"], r["expect_gap_mm"])
                                 for r in d.get("results", []))])
            elif name == "light_selftest":
                rows.append(["qc_light", d.get("verdict"),
                             "%s/%s 用例" % (d.get("passed"), d.get("cases")),
                             "；".join("%s→%sK" % (r["case"], (r["measured"] or {}).get("cct_k"))
                                       for r in d.get("results", []) if "cct" in r["case"])])
            elif name == "gltf_selftest":
                rows.append(["qc_gltf", d.get("verdict"),
                             "%s/%s 用例" % (d.get("passed"), d.get("cases")),
                             ",".join(r["case"] for r in d.get("results", []))])
        L.append(md_table(["工具", "结论", "覆盖", "明细"], rows))
        L.append("")

    # 4. 判据与口径
    L.append("### 4. 判据与口径（引用，不改契约）")
    L.append("")
    tol = rules.get("tolerances", {})
    lth = (rules.get("light") or {}).get("thresholds", {})
    L.append(md_table(["项", "判据", "来源"], [
        ["干涉", "世界 AABB 的 MTV > %smm **且** 世界空间 BVH 三角形求交命中 > 0 对 → FAIL；"
                 "仅 AABB 重叠而三角形不交 → 不计（AABB 误报）" % tol.get("min_overlap_mm"),
         "§11.1 + 实测（FromObject 不认物体变换）"],
        ["贴面接触", "AABB 重叠 ≤ %smm 视为零体积接触（杯子底面贴桌面），不判干涉" % tol.get("contact_epsilon_mm"),
         "校准 10_REST_ON_TABLE"],
        ["落地", "min_z ∈ %s mm；或被顶面齐平的物体托住（间隙 ≤ %smm）" % (
            tol.get("ground_band_mm"), tol.get("rest_on_max_gap_mm")), "§11.2"],
        ["贴墙", "挂墙物与内墙面间隙 ∈ %s mm" % tol.get("wall_gap_mm"), "§11.2"],
        ["穿墙/天花", "> %smm 报 FAIL" % tol.get("wall_penetration_min_mm"), "§11.2"],
        ["女仆脚底", "C_Maid 整组最低点 ∈ [-2, +2]mm（68 网格当一个整体）", "§11.3"],
        ["光影死黑", "luma<0.02 面积 ≤ %s%%" % (lth.get("dead_black_ratio_max") * 100 if lth.get("dead_black_ratio_max") else "?"),
         "§11.4"],
        ["光影爆白", "luma>0.98 面积 ≤ %s%%" % (lth.get("blown_ratio_max") * 100 if lth.get("blown_ratio_max") else "?"),
         "§11.4"],
        ["平均亮度", "[%s, %s]" % (lth.get("mean_luma_min"), lth.get("mean_luma_max")), "§11.4"],
        ["色温", "%sK（容差 ±%sK）" % (lth.get("cct_k"), lth.get("cct_tolerance_k")), "§11.4"],
        ["GLB 大小", "< %s MB" % round((rules.get("gltf", {}).get("max_bytes") or 0) / 1048576.0, 1), "§8"],
        ["GLB 三角面", "< %s" % rules.get("gltf", {}).get("max_tris"), "§5"],
    ]))
    L.append("")

    # 5. 已知盲区
    L.append("### 5. 已知盲区（读结论时必须知道）")
    L.append("")
    L.append("| 盲区 | 影响 | 补救 |")
    L.append("|---|---|---|")
    c = rules.get("collide", {})
    L.append("| %s 内部互穿不判干涉 | 女仆手臂穿袖、托盘穿手 **盲扫看不到** | "
             "`qc_pairs.py --pairs MD_Tray:MD_Hand_L` 点名查 |" % ", ".join(
                 c.get("allow_same_collection") or []))
    L.append("| 穿透深度是代理值 | 取重叠三角形质心到对方面片的最近距离，"
             "薄壳/共面时可能低报为 0 | 同时看 `overlap_tris`；关键件用 qc_pairs 复核 |")
    L.append("| 判定依赖物体分类启发式 | 挂墙/吊挂/落地靠 AABB 位置推断，"
             "摆错位置的好物体会被误分类 | 报告 `roles` 字段可逐条核对 |")
    L.append("| 光影色温是估计值 | 由麦凯米近似 + 中性像素统计得出，"
             "大面积单色材质下会偏 | 看 `cct_detail.a/b` 两路值与 p25–p75 分布 |")
    L.append("| GLB 合规不等于网页可用 | 未做 three.js 实跑（60 机位无穿墙） | 由 web-dev 自测 + 做交叉复核 |")
    L.append("")

    # 6. 复跑命令
    L.append("### 6. 复跑命令（幂等，按 scope 参数化）")
    L.append("")
    L.append("```bash")
    L.append("# 全量碰撞/落地/贴墙（无头独立进程，engine none）")
    L.append("blender_rt_headless(script_file=\"<项目根>/blender/qc/qc_collide.py\",")
    L.append("  file=\"<项目根>/scene/maid_cafe.blend\", engine=\"none\",")
    L.append("  args=\"--tag %s\" )" % (tag or "v1"))
    L.append("")
    L.append("# 只看某个模块")
    L.append("  args=\"--scope C_Seating --tag %s\"" % (tag or "v1"))
    L.append("")
    L.append("# 点名查物体对（女仆托盘/椅子桌/杯子桌）")
    L.append("blender_rt_headless(script_file=\".../qc_pairs.py\", file=\".../maid_cafe.blend\",")
    L.append("  engine=\"none\", args=\"--pairs MD_Tray:MD_Hand_L,MD_Cup:MD_Tray --tag %s\")" % (tag or "v1"))
    L.append("")
    L.append("# 光影 12 张（长活，as_job=True 再 wait 收）")
    L.append("blender_rt_headless(script_file=\".../qc_light.py\", file=\".../maid_cafe.blend\",")
    L.append("  engine=\"eevee\", as_job=True, args=\"--tag %s\")" % (tag or "v1"))
    L.append("")
    L.append("# GLB 校验 + 汇总成报告")
    L.append("blender_rt_headless(script_file=\".../qc_gltf.py\", engine=\"none\", args=\"--glb scene/maid_cafe.glb\")")
    L.append("python blender/qc/qc_report.py --tag %s" % (tag or "v1"))
    L.append("```")
    L.append("")
    if notes:
        L.append("### 7. 本轮备注")
        L.append("")
        L.append(notes)
        L.append("")
    if blend_info:
        L.append("### 场景证据")
        L.append("")
        L.append(md_table(["项", "值"], [[k, v] for k, v in blend_info.items()]))
        L.append("")
    return "\n".join(L)


def md5_file(path):
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                h.update(b)
    except Exception:
        return "?"
    return h.hexdigest()


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(prog="qc_report")
    ap.add_argument("--tag", default="", help="版本标签（v1/v2/...）")
    ap.add_argument("--notes", default="", help="本轮备注（写进报告末节）")
    ap.add_argument("--results-dir", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--append-only", action="store_true",
                    help="只追加，不重写（默认也是追加；此开关保留给脚本化）")
    ap.add_argument("--blend", default="scene/maid_cafe.blend")
    args = ap.parse_args()

    root = root_of()
    rules = load_rules()
    results_dir = args.results_dir or os.path.join(root, rules.get("report", {}).get(
        "results_dir", ".scratch/qc/results"))
    out_md = args.out_md or os.path.join(root, rules.get("report", {}).get(
        "doc_md", "docs/QC-REPORT.md"))
    out_json = args.out_json or os.path.join(root, rules.get("report", {}).get(
        "doc_json", "docs/qc_findings.json"))

    bundle = collect_results(results_dir, args.tag)
    calib = collect_calibrations(results_dir, root)
    findings = all_findings(bundle)
    groups = group_by_module(findings, rules)

    blend_path = args.blend if os.path.isabs(args.blend) else os.path.join(root, args.blend)
    blend_present = os.path.isfile(blend_path)
    blend_md5 = md5_file(blend_path) if blend_present else None
    # 场景指纹核对：结果必须对应当前这一版 .blend
    stale = []
    for kind in KIND_ORDER:
        e = bundle.get(kind)
        if not e:
            continue
        ok, detail = scene_fingerprint_ok(e, blend_md5)
        e["fingerprint_ok"] = ok
        e["fingerprint_detail"] = detail
        if not ok:
            stale.append("%s(%s)" % (KIND_LABEL.get(kind, kind), detail))
    verdict, verdicts, missing = overall_verdict(bundle, scene_present=blend_present,
                                                 stale=stale)

    blend_path = args.blend if os.path.isabs(args.blend) else os.path.join(root, args.blend)
    blend_info = {}
    if blend_present:
        st = os.stat(blend_path)
        blend_info = {
            "blend": os.path.relpath(blend_path, root),
            "bytes": st.st_size,
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            "md5": md5_file(blend_path),
        }
    else:
        blend_info = {"blend": os.path.relpath(blend_path, root),
                      "state": "尚未生成 —— 本轮结论不会是 PASS"}

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    payload = {
        "schema": 1,
        "generated_at": now_iso,
        "tag": args.tag,
        "verdict": verdict,
        "per_check_verdict": verdicts,
        "checks_not_run": missing,
        "scene_present": bool(blend_present),
        "counts": {
            "total": len(findings),
            "FAIL": len([f for f in findings if f.get("severity") == "FAIL"]),
            "WARN": len([f for f in findings if f.get("severity") == "WARN"]),
            "by_module": {k: len(v) for k, v in groups.items()},
        },
        "findings": findings,
        "groups": {k: [f.get("id") for f in v] for k, v in groups.items()},
        "calibration": {k: {"verdict": v["data"].get("verdict"),
                            "file": os.path.basename(v["path"])}
                        for k, v in calib.items()},
        "scene": blend_info,
        "sources": {k: (os.path.basename(v["path"]) if v else None) for k, v in bundle.items()},
        "rules": {"path": os.path.relpath(os.path.join(QC_DIR, "qc_rules.json"), root),
                  "md5": md5_file(os.path.join(QC_DIR, "qc_rules.json"))},
        "legend": {
            "verdict": {"PASS": "全部判据通过", "FAIL": "有硬判据未通过",
                        "待确认": "有 WARN，或有关键项未运行/证据不足，不能算通过"},
            "severity": {"FAIL": "硬判据违反（契约 §11 明确数值）",
                         "WARN": "超出目标但未越硬上限，或证据不足",
                         "INFO": "记录性信息"},
        },
    }
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("QC findings JSON → %s （%d 条问题，结论 %s）" % (out_json, len(findings), verdict))

    section = build_markdown(args.tag, args.notes, bundle, calib, findings, groups,
                             verdict, verdicts, missing, rules, blend_info,
                             stale=stale)
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    exists = os.path.isfile(out_md)
    header = ("# 女仆咖啡馆 · QC 体检报告\n\n"
              "> 本文件由 `blender/qc/qc_report.py` 维护：每次运行**追加**一节，"
              "不覆盖历史。判据唯一来源是 `blender/qc/qc_rules.json`（对应 CONTRACT §11）。\n"
              "> 三态口径：**PASS** = 全部判据通过；**FAIL** = 有硬判据未通过；"
              "**待确认** = 有 WARN、或关键体检项未运行/证据不足。\n"
              "> 结论一律带物体名 / 坐标 / 毫米数 / 证据路径，不接受「看起来没问题」。\n\n"
              "---\n\n")
    with open(out_md, "a" if exists else "w", encoding="utf-8") as f:
        if not exists:
            f.write(header)
        else:
            f.write("\n---\n\n")
        f.write(section)
        f.write("\n")
    print("QC 报告 → %s （追加 1 节，结论 %s）" % (out_md, verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
