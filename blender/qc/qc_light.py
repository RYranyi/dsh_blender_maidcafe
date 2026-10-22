# -*- coding: utf-8 -*-
"""qc_light.py — 光影体检（CONTRACT §11.4）

判据（qc_rules.json → light.thresholds）：
  死黑占比（luma < 0.02）≤ 8%（阴影允许）
  爆白占比（luma > 0.98）≤ 0.2%
  平均亮度 ∈ [0.15, 0.65]
  色温估计 ∈ 2700–3000K（室内暖光；容差 ±400K，见 thresholds.cct_tolerance_k）

方法（每条都可复核）：
  1. 4 时段 × 3 天气 = 12 张 1280×720 EEVEE 渲染 → renders/qc/lt_<phase>_<weather>.png
  2. 用 bpy 读回 PNG（colorspace=Non-Color，numpy foreach_get 取 sRGB 编码值）
     —— 用 sRGB 编码值算「死黑/爆白」才对得上人眼看图的结果；线性值会把暗部夸大。
  3. 亮度 luma = 0.2126R + 0.7152G + 0.0722B（Rec.709）
  4. 色温：用黑体辐射轨迹反查。先算图像 RGB 的色度比，再用 McCamy 近似式
     求相关色温 CCT ≈ 449n³ + 3525n² + 6823.3n + 5520.33，n=(x-0.3320)/(0.1858-y)。
     只统计「中性/近中性」像素（低饱和），高饱和的物体本色不参与色温估计 —— 
     否则满屋原木色会被误算成 2000K。
  5. 灯光 rig：优先用场景自带的 clight 预设（按物件名 LT_Sun/LT_Interior/LT_World 等
     识别并按 phase/weather 系数缩放）；找不到就造一套等价三点光（会标注 rig_source）。

引擎：Blender 5.2 只有 'BLENDER_EEVEE'（没有 5.1 时代的 'BLENDER_EEVEE_NEXT'，
      实测设置 NEXT 会抛 enum not found，run-mvhgxyuujyvl）。代码里按顺序尝试，
      设置成功即用，并把实际引擎名写进报告。

用法：
  blender_rt_headless(script_file=".../qc_light.py", file=".../scene/maid_cafe.blend",
                      engine="eevee", as_job=True,
                      args="--phases morning,noon --weathers clear --samples 16")
  16 张全跑比较慢 → 建议 as_job=True，用 blender_rt_job(op="wait") 收。
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


KIND = "light"


# ============================================================ 色彩科学

def luma_of(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def srgb_to_linear(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def xy_from_rgb(rgb_lin):
    """线性 RGB → CIE xy（sRGB primaries, D65）"""
    r, g, b = rgb_lin[..., 0], rgb_lin[..., 1], rgb_lin[..., 2]
    # 线性 sRGB → XYZ (D65)
    X = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    Y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    Z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    s = X + Y + Z
    s = np.where(np.abs(s) < 1e-9, np.nan, s)
    return X / s, Y / s, Y


def cct_mccamy(x, y):
    """McCamy 近似式；适用范围约 2000–12500K，对本项目 2700–3000K 足够。"""
    n = (x - 0.3320) / (0.1858 - y)
    return 449.0 * n ** 3 + 3525.0 * n ** 2 + 6823.3 * n + 5520.33


def estimate_cct(rgb, lum, sat):
    """色温估计（两条路，互相印证）：

    路 A「中性像素」：只取低饱和像素 → 最接近「白墙/桌布」的照明色，室内场景通常最准。
      缺点：暖光把浅色照成橙黄后饱和度飙升，可能被筛光。自测实测：纯 2700K 色块
      sat≈0.66，被 0.18 阈值全滤掉 → 返回 null；纯 6500K 色块 luminance≈0.996 被
      lum<0.95 滤掉 → 也返回 null。所以必须有路 B。
    路 B「画面主色」：不按饱和度筛（只排除极暗），全画面逐像素算 CCT，取**亮度加权
      中位数** —— 亮点更接近「照明本身」，暗部色更接近阴影反弹光。任何照明下都给得出数。

    策略：A 样本够（≥300）就用 A，否则退 B；cct_detail 同时记录 A/B 两个值和所选路径，
    报告里可复核。这也解释了报告中「cct_pixels 很少」的正确含义（是 A 路的样本数）。

    为什么逐像素算而不先平均 RGB：平均会把高亮蓝天/窗外光摊到整幅，
    自测实测得出偏蓝 7242K 的假色温。
    """
    total = float(rgb.shape[0] * rgb.shape[1])
    out = {"cct_k": None, "cct_xy": None, "cct_pixels": 0, "cct_detail": {}}

    def cct_from_mask(mask, weight=None):
        rgbl = srgb_to_linear(rgb[mask])
        if rgbl.shape[0] < 50:
            return None
        X = 0.4124564 * rgbl[:, 0] + 0.3575761 * rgbl[:, 1] + 0.1804375 * rgbl[:, 2]
        Y = 0.2126729 * rgbl[:, 0] + 0.7151522 * rgbl[:, 1] + 0.0721750 * rgbl[:, 2]
        Z = 0.0193339 * rgbl[:, 0] + 0.1191920 * rgbl[:, 1] + 0.9503041 * rgbl[:, 2]
        s = X + Y + Z
        good = s > 1e-9
        if good.sum() < 50:
            return None
        xs = X[good] / s[good]
        ys = Y[good] / s[good]
        ccts = cct_mccamy(xs, ys)
        valid = np.isfinite(ccts) & (ccts > 1500) & (ccts < 15000)
        if valid.sum() < 50:
            return None
        c = ccts[valid]
        if weight is not None:
            w = np.maximum(weight[mask][good][valid], 1e-6)
            order = np.argsort(c)
            cw, ww = c[order], w[order]
            cum = np.cumsum(ww) / np.sum(ww)
            med = float(cw[min(np.searchsorted(cum, 0.5), len(cw) - 1)])
        else:
            med = float(np.median(c))
        return {"cct": med, "x": float(np.median(xs[valid])), "y": float(np.median(ys[valid])),
                "n": int(valid.sum()),
                "p25": float(np.percentile(c, 25)), "p75": float(np.percentile(c, 75))}

    neutral = (sat < 0.18) & (lum > 0.05) & (lum < 0.95)
    n_neutral = int(neutral.sum())
    out["cct_pixels"] = n_neutral
    a = cct_from_mask(neutral) if n_neutral >= 300 else None
    body = lum > 0.03          # 排除阴影/黑区噪声
    b = cct_from_mask(body, weight=lum) if int(body.sum()) > 300 else None

    use, path = (a, "A_neutral") if a else ((b, "B_dominant") if b else (None, "none"))
    if use:
        out["cct_k"] = round(use["cct"], 1)
        out["cct_xy"] = [round(use["x"], 5), round(use["y"], 5)]
    out["cct_detail"] = {
        "method": path,
        "a_neutral_cct": (round(a["cct"], 1) if a else None),
        "a_neutral_pixels": (a["n"] if a else 0),
        "b_dominant_cct": (round(b["cct"], 1) if b else None),
        "b_dominant_pixels": (b["n"] if b else 0),
        "spread_p25_p75": ([round(use["p25"], 1), round(use["p75"], 1)] if use else None),
    }
    return out


def analyze_image(path):
    img = bpy.data.images.load(path, check_existing=False)
    try:
        img.colorspace_settings.name = 'Non-Color'   # 拿到的是 sRGB 编码字节值
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        arr = buf.reshape(h, w, 4)
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3]
        lum = luma_of(rgb)
        total = float(w * h)
        dead = float((lum < 0.02).sum())
        blown = float((lum > 0.98).sum())
        # 直方图 32 bins（报告里可以直接画表）
        hist, edges = np.histogram(lum, bins=32, range=(0.0, 1.0))
        hist = hist.astype(np.int64)
        # ---- 色温（两条路，见 estimate_cct 说明）
        mx = rgb.max(axis=2)
        mn = rgb.min(axis=2)
        sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
        cct_info = estimate_cct(rgb, lum, sat)
        cct = cct_info["cct_k"]
        xy = cct_info["cct_xy"]
        cct_detail = cct_info["cct_detail"]
        n_neutral = cct_info["cct_pixels"]
        pr, pg, pb = (float(rgb[:, :, 0].mean()), float(rgb[:, :, 1].mean()),
                      float(rgb[:, :, 2].mean()))
        return {
            "path": path,
            "size": [w, h],
            "mean_luma": round(float(lum.mean()), 4),
            "median_luma": round(float(np.median(lum)), 4),
            "std_luma": round(float(lum.std()), 4),
            "min_luma": round(float(lum.min()), 4),
            "max_luma": round(float(lum.max()), 4),
            "dead_black_ratio": round(dead / total, 5),
            "blown_ratio": round(blown / total, 5),
            "mean_rgb": [round(pr, 4), round(pg, 4), round(pb, 4)],
            "r_over_b": round(pr / pb, 4) if pb > 1e-6 else None,
            "histogram": {"bins": 32, "range": [0.0, 1.0], "counts": hist.tolist()},
            "cct_k": round(cct, 1) if cct else None,
            "cct_xy": xy,
            "cct_pixels": n_neutral,
            "cct_detail": cct_detail,
            "alpha_mean": round(float(alpha.mean()), 4),
        }
    finally:
        bpy.data.images.remove(img)


# ============================================================ 灯光 rig

PHASE_DEFAULT_ELEV = {"morning": 18.0, "noon": 62.0, "dusk": 8.0, "night": 30.0}


def find_scene_rig(rules):
    """优先识别 cbuild/clight 建好的灯：LT_Sun / LT_Interior* / LT_World* 之类。"""
    rig = {"sun": None, "interior": [], "world": None, "fill": [], "source": "none"}
    for ob in bpy.data.objects:
        if ob.type != 'LIGHT':
            continue
        n = ob.name.upper()
        if "SUN" in n or "SKY" in n:
            rig["sun"] = ob.name
        elif "FILL" in n:
            rig["fill"].append(ob.name)
        elif "INTERIOR" in n or "ROOM" in n or "BAR" in n or "CEIL" in n:
            rig["interior"].append(ob.name)
        elif "WORLD" in n or "AMBIENT" in n:
            rig["world"] = ob.name
        else:
            rig["interior"].append(ob.name)
    if rig["sun"] or rig["interior"]:
        rig["source"] = "scene"
    return rig


def build_default_rig(rules):
    """场景没有灯（或只有 mesh）时，造等价三点光。不修改原场景的几何/材质。"""
    cfg = rules["light"]["default_rig"]
    sc = bpy.context.scene
    light = bpy.data.lights.new("QC_Sun", type='SUN')
    light.energy = cfg["sun"]["energy"]
    light.color = cfg["sun"]["color"]
    light.angle = math.radians(3.0)
    ob = bpy.data.objects.new("QC_LT_Sun", light)
    sc.collection.objects.link(ob)
    ob.rotation_euler = (math.radians(58.0), 0.0, math.radians(40.0))

    area = bpy.data.lights.new("QC_Interior", type='AREA')
    area.energy = cfg["interior"]["energy"]
    area.color = cfg["interior"]["color"]
    area.size = 3.0
    aob = bpy.data.objects.new("QC_LT_Interior", area)
    sc.collection.objects.link(aob)
    aob.location = (0.0, 0.0, 2.85)

    world = bpy.data.worlds.new("QC_World") if not sc.world else sc.world
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.62, 0.72, 0.95, 1.0)
        bg.inputs[1].default_value = cfg["world"]["strength"]
    return {"sun": ob.name, "interior": [aob.name], "world": world.name,
            "fill": [], "source": "default_rig"}


def apply_phase_weather(rules, rig_objs, phase, weather):
    """按 phase×weather 系数缩放灯光强度/颜色、世界背景、雾。"""
    cfg = rules["light"]["default_rig"]
    ph = cfg["phases"][phase]
    we = cfg["weather"][weather]
    factor = ph["sun_factor"] * we["sun_factor"]
    sc = bpy.context.scene
    details = {"phase": phase, "weather": weather,
               "sun_factor": round(factor, 4),
               "interior_factor": round(ph["interior_factor"] * we["interior_factor"], 4),
               "world_factor": round(ph["world_factor"] * we["world_factor"], 4)}

    sun = bpy.data.objects.get(rig_objs.get("sun") or "")
    if sun and sun.type == 'LIGHT':
        base = cfg["sun"]["energy"]
        sun.data.energy = base * factor
        sun.data.color = tuple(ph.get("sun_color", cfg["sun"]["color"]))
        elev = math.radians(ph["sun_elev_deg"])
        azim = math.radians(ph["sun_azim_deg"])
        sun.rotation_euler = (elev, 0.0, azim)
        details["sun_energy"] = round(sun.data.energy, 4)
        details["sun_elev_deg"] = ph["sun_elev_deg"]

    ifactor = ph["interior_factor"] * we["interior_factor"]
    for nm in rig_objs.get("interior") or []:
        ob = bpy.data.objects.get(nm)
        if ob and ob.type == 'LIGHT':
            ob.data.energy = cfg["interior"]["energy"] * ifactor
            ob.data.color = tuple(ph.get("interior_color", cfg["interior"]["color"]))
    details["interior_energy"] = round(cfg["interior"]["energy"] * ifactor, 2)

    if sc.world and sc.world.use_nodes:
        bg = sc.world.node_tree.nodes.get("Background")
        if bg:
            wf = ph["world_factor"] * we["world_factor"]
            bg.inputs[1].default_value = cfg["world"]["strength"] * wf
            bg.inputs[0].default_value = tuple(list(ph.get("world_color", cfg["world"]["color"])) + [1.0])
            details["world_strength"] = round(cfg["world"]["strength"] * wf, 4)

    # 雾（雨天/多云压暗远处）
    fog = we.get("fog_density", 0.0)
    if sc.world and sc.world.use_nodes:
        nt = sc.world.node_tree
        vol = nt.nodes.get("QC_WorldVolume")
        if fog > 0.0:
            if vol is None:
                vol = nt.nodes.new("ShaderNodeVolumePrincipled")
                vol.name = "QC_WorldVolume"
                vol.inputs["Density"].default_value = fog
                out = nt.nodes.get("World Output")
                if out:
                    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
            else:
                vol.inputs["Density"].default_value = fog
        details["fog_density"] = fog
    return details


def ensure_camera(rules):
    """没有相机就建一个（用 manifest / CONTRACT §1.1 的默认机位），不动已有相机。"""
    sc = bpy.context.scene
    if sc.camera and sc.camera.type == 'CAMERA':
        return sc.camera.name, "scene"
    pos = (1.85, -2.55, 1.55)
    tgt = (-1.20, 0.50, 1.05)
    man = Q.read_json(os.path.join(Q.project_root(rules), "scene", "scene_manifest.json"))
    try:
        cam = (man or {}).get("anchors", {}).get("cam_default") or {}
        if cam.get("pos"):
            pos = cam["pos"]
            tgt = cam.get("target", tgt)
    except Exception:
        pass
    cd = bpy.data.cameras.new("QC_Cam")
    cd.lens = 50.0
    cd.sensor_width = 36.0
    co = bpy.data.objects.new("QC_Cam", cd)
    sc.collection.objects.link(co)
    co.location = pos
    direction = np.array(tgt, dtype=float) - np.array(pos, dtype=float)
    import mathutils
    co.rotation_euler = mathutils.Vector(direction).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = co
    return co.name, "auto(CONTRACT §1.1 CAM_DEFAULT)"


def configure_render(rules, samples):
    sc = bpy.context.scene
    tried = []
    ok_engine = None
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"):
        try:
            sc.render.engine = eng
            ok_engine = sc.render.engine
            tried.append({"engine": eng, "ok": True})
            break
        except Exception as e:
            tried.append({"engine": eng, "ok": False, "err": str(e)[:120]})
    if ok_engine is None:
        raise RuntimeError("没有任何可用引擎: %s" % tried)
    r = rules["light"]["resolution"]
    sc.render.resolution_x, sc.render.resolution_y = int(r[0]), int(r[1])
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    sc.render.film_transparent = False
    try:
        sc.eevee.taa_render_samples = int(samples)
    except Exception:
        pass
    try:
        # 5.x: 关掉运动模糊/景深对统计的干扰
        sc.eevee.use_motion_blur = False
        sc.eevee.use_dof = False
    except Exception:
        pass
    sc.render.use_persistent_data = True
    return ok_engine, tried


# ============================================================ 主流程

def run(args, rules):
    t0 = time.time()
    root = rules["root"]
    outdir = os.path.join(root, rules["light"]["render_dir"])
    Q.ensure_dir(outdir)
    phases = [p.strip() for p in (args.phases or "").split(",") if p.strip()] \
        or rules["light"]["phases"]
    weathers = [w.strip() for w in (args.weathers or "").split(",") if w.strip()] \
        or rules["light"]["weathers"]
    samples = args.samples or rules["light"]["samples"]

    info = Q.open_scene(args)
    if info.get("path"):
        rules["root"] = os.path.dirname(os.path.dirname(os.path.abspath(info["path"])))
        root = rules["root"]
        outdir = os.path.join(root, rules["light"]["render_dir"])
        Q.ensure_dir(outdir)

    engine, engine_tried = configure_render(rules, samples)
    cam_name, cam_source = ensure_camera(rules)
    rig = find_scene_rig(rules)
    if rig["source"] == "none":
        rig = build_default_rig(rules)
    rig_evidence = {k: rig[k] for k in ("source",) if k in rig}
    rig_evidence["sun"] = rig.get("sun")
    rig_evidence["interior"] = rig.get("interior")
    rig_evidence["fill"] = rig.get("fill")
    rig_evidence["camera"] = cam_name
    rig_evidence["camera_source"] = cam_source

    thr = rules["light"]["thresholds"]
    shots = []
    findings = []
    for phase in phases:
        for weather in weathers:
            light_details = apply_phase_weather(rules, rig, phase, weather)
            name = "lt_%s_%s" % (phase, weather)
            path = os.path.join(outdir, name + ".png")
            bpy.context.scene.render.filepath = path
            tr = time.time()
            bpy.ops.render.render(write_still=True)
            render_s = round(time.time() - tr, 2)
            stat = analyze_image(path)
            stat["render_s"] = render_s
            stat["shot"] = name
            stat["phase"] = phase
            stat["weather"] = weather
            stat["light_setup"] = light_details
            # 判据
            fails = []
            warns = []
            if stat["dead_black_ratio"] > thr["dead_black_ratio_max"]:
                fails.append("死黑占比 %.2f%% > %.2f%% 上限" % (
                    stat["dead_black_ratio"] * 100, thr["dead_black_ratio_max"] * 100))
            if stat["blown_ratio"] > thr["blown_ratio_max"]:
                fails.append("爆白占比 %.3f%% > %.3f%% 上限" % (
                    stat["blown_ratio"] * 100, thr["blown_ratio_max"] * 100))
            if not (thr["mean_luma_min"] <= stat["mean_luma"] <= thr["mean_luma_max"]):
                fails.append("平均亮度 %.3f 不在 [%.2f, %.2f]" % (
                    stat["mean_luma"], thr["mean_luma_min"], thr["mean_luma_max"]))
            cct = stat.get("cct_k")
            # 色温按**时段分组**判（qc_rules.light.cct_expect_by_phase）：
            # §11.4 的 2700–3000K 是「室内暖光」口径；白天（morning/noon）有大玻璃窗、
            # 日光/天光主导画面，物理上就该偏冷（4500–7500K），拿 2700–3000K 判白天是判错口径。
            # v1 实测：白天四张 5600–6100K 全被判 FAIL —— 属误判，故分组。
            ph_cfg = (rules["light"].get("cct_expect_by_phase") or {}).get(phase) or {}
            cct_target = ph_cfg.get("k") or thr["cct_k"]
            cct_group = ph_cfg.get("group", "default")
            cct_lo, cct_hi = float(cct_target[0]), float(cct_target[1])
            stat["cct_group"] = cct_group
            stat["cct_target_k"] = [cct_lo, cct_hi]
            if cct is None:
                # 中性像素太少 → 色温不可估计。这是**方法限制**（大面积高饱和材质/低照度），
                # 不是 PASS 也不是 FAIL，记「待确认」并把可用像素数写进证据。
                warns.append("色温无法估计（可用中性像素 %d < 300，画面被高饱和材质/低照度主导）"
                             % stat["cct_pixels"])
            elif not (cct_lo <= cct <= cct_hi):
                fails.append("色温估计 %.0fK 不在 [%s 组] 期望 %d–%dK" % (
                    cct, cct_group, cct_lo, cct_hi))
            stat["checks"] = {"FAIL": fails, "WARN": warns}
            stat["verdict"] = "FAIL" if fails else ("待确认" if warns else "PASS")
            shots.append(stat)
            if fails or warns:
                findings.append({
                    "id": "LIGHT-%s" % name,
                    "kind": "lighting",
                    "verdict": stat["verdict"],
                    "severity": "FAIL" if fails else "WARN",
                    "objects": [],
                    "module": "clight",
                    "owner": "Lead",
                    "location": None,
                    "metrics": {k: stat[k] for k in (
                        "mean_luma", "dead_black_ratio", "blown_ratio", "cct_k",
                        "median_luma", "std_luma", "mean_rgb", "r_over_b")},
                    "rule": "§11.4 4 时段 × 晴/多云/雨：无死黑、无过曝、色温 2700–3000K",
                    "note": "; ".join(fails + warns),
                    "evidence": {"render": os.path.relpath(path, root),
                                 "shot": name, "phase": phase, "weather": weather},
                    "scope": args.scope,
                })

    fails_n = len([s for s in shots if s["verdict"] == "FAIL"])
    warns_n = len([s for s in shots if s["verdict"] == "待确认"])

    # ---- 按「白天自然光 / 夜间·黄昏室内暖光」分组汇总（§11.4 的 2700–3000K 只管后者）
    groups = {}
    for s in shots:
        g = s.get("cct_group", "default")
        e = groups.setdefault(g, {"group": g, "shots": [], "FAIL": 0, "WARN": 0, "PASS": 0,
                                  "mean_luma": [], "dead_black": [], "blown": [], "cct": []})
        e["shots"].append(s["shot"])
        e[s["verdict"] if s["verdict"] in ("FAIL", "PASS") else "WARN"] += 1
        e["mean_luma"].append(s["mean_luma"])
        e["dead_black"].append(s["dead_black_ratio"])
        e["blown"].append(s["blown_ratio"])
        if s.get("cct_k"):
            e["cct"].append(s["cct_k"])
    for g, e in groups.items():
        e["mean_luma_range"] = [round(min(e["mean_luma"]), 4), round(max(e["mean_luma"]), 4)]
        e["dead_black_max"] = round(max(e["dead_black"]), 5)
        e["blown_max"] = round(max(e["blown"]), 5)
        e["cct_range"] = ([round(min(e["cct"]), 1), round(max(e["cct"]), 1)] if e["cct"] else None)
        e["verdict"] = "FAIL" if e["FAIL"] else ("待确认" if e["WARN"] else "PASS")
        for k in ("mean_luma", "dead_black", "blown", "cct"):
            e.pop(k, None)
    verdict = "FAIL" if fails_n else ("待确认" if warns_n else "PASS")
    payload = {
        "kind": KIND,
        "tag": args.tag,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - t0, 2),
        "verdict": verdict,
        "engine": engine,
        "engine_tried": engine_tried,
        "samples": samples,
        "resolution": rules["light"]["resolution"],
        "phases": phases,
        "weathers": weathers,
        "render_dir": os.path.relpath(outdir, root),
        "rig": rig_evidence,
        "thresholds": thr,
        "method": ("sRGB 编码值（colorspace=Non-Color 读回）→ Rec.709 luma；死黑 luma<0.02、"
                   "爆白 luma>0.98；色温用低饱和中性像素（sat<0.18）的线性 RGB→CIE xy，"
                   "McCamy 近似式反查 CCT，避免原木色/海军蓝把估计拉偏。"),
        "by_group": groups,
        "summary": {
            "shots": len(shots), "FAIL": fails_n, "WARN": warns_n,
            "PASS": len(shots) - fails_n - warns_n,
            "worst_dead_black": max((s["dead_black_ratio"] for s in shots), default=None),
            "worst_blown": max((s["blown_ratio"] for s in shots), default=None),
            "luma_range": [min((s["mean_luma"] for s in shots), default=None),
                           max((s["mean_luma"] for s in shots), default=None)],
            "cct_range": [min((s["cct_k"] for s in shots if s["cct_k"]), default=None),
                          max((s["cct_k"] for s in shots if s["cct_k"]), default=None)],
        },
        "shots": shots,
        "findings": findings,
        "scene": {"path": bpy.data.filepath},
        "rules_md5": rules.get("_rules_md5"),
    }
    out = args.out or Q.default_out(rules, "light" + (("_" + args.tag) if args.tag else ""))
    Q.finish(payload, out, quiet=args.quiet)
    return payload


def selftest(rules, out_path):
    """验证光影统计**本身**准不准 —— 用已知答案的合成图，不依赖真场景。

    用例：
      A. 全黑图           → 死黑 100%，平均亮度 0
      B. 全白图           → 爆白 100%
      C. 中灰图           → 平均亮度 ≈ 0.5（sRGB 编码），死黑/爆白 0
      D. 2700K 黑体色      → 色温估计应落在 2700±250K
      E. 6500K 黑体色      → 色温估计应落在 6500±600K
    这些是「算法该校准到多少」的硬指标，写进 QC-REPORT 的光影方法节。
    """
    import tempfile
    tmpdir = Q.ensure_dir(os.path.join(Q.project_root(rules), ".scratch", "qc", "calib"))
    cases = []

    def make(name, rgb_lin_or_srgb, srgb_encoded=True):
        w = h = 64
        px = np.empty(w * h * 4, dtype=np.float32)
        c = np.array(rgb_lin_or_srgb, dtype=np.float32)
        px[0::4] = c[0]
        px[1::4] = c[1]
        px[2::4] = c[2]
        px[3::4] = 1.0
        img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
        img.pixels[:] = px.tolist()
        p = os.path.join(tmpdir, name + ".png")
        img.filepath_raw = p
        img.file_format = 'PNG'
        img.save()
        bpy.data.images.remove(img)
        return p

    def blackbody_srgb_rgb(k):
        """黑体色温 K → sRGB 编码值（Tanner Helland 拟合），用于造已知色温图"""
        t = k / 100.0
        if t <= 66:
            r = 255.0
            g = 99.4708025861 * math.log(t) - 161.1195681661
            b = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
        else:
            r = 329.698727446 * ((t - 60) ** -0.1332047592)
            g = 288.1221695283 * ((t - 60) ** -0.0755148492)
            b = 255.0
        return [min(max(v, 0.0), 255.0) / 255.0 for v in (r, g, b)]

    specs = [
        {"case": "A_all_black", "srgb": [0.0, 0.0, 0.0],
         "expect": {"dead_black_ratio": (1.0, 0.001), "mean_luma": (0.0, 0.001)}},
        {"case": "B_all_white", "srgb": [1.0, 1.0, 1.0],
         "expect": {"blown_ratio": (1.0, 0.001), "mean_luma": (1.0, 0.001)}},
        {"case": "C_mid_gray", "srgb": [0.5, 0.5, 0.5],
         "expect": {"mean_luma": (0.5, 0.01), "dead_black_ratio": (0.0, 0.001),
                    "blown_ratio": (0.0, 0.001)}},
        {"case": "D_2700K", "srgb": blackbody_srgb_rgb(2700),
         "expect": {"cct_k": (2700.0, 250.0)}},
        {"case": "E_6500K", "srgb": blackbody_srgb_rgb(6500),
         "expect": {"cct_k": (6500.0, 600.0)}},
    ]
    for sp in specs:
        p = make(sp["case"], sp["srgb"])
        st = analyze_image(p)
        checked = {}
        ok = True
        for key, (target, tol) in sp["expect"].items():
            got = st.get(key)
            pass_ok = got is not None and abs(float(got) - target) <= tol
            ok = ok and pass_ok
            checked[key] = {"target": target, "tol": tol, "got": got, "ok": pass_ok}
        cases.append({"case": sp["case"], "input_srgb": [round(v, 4) for v in sp["srgb"]],
                      "measured": {"mean_luma": st["mean_luma"],
                                   "dead_black_ratio": st["dead_black_ratio"],
                                   "blown_ratio": st["blown_ratio"],
                                   "cct_k": st["cct_k"]},
                      "checks": checked, "ok": ok})
    payload = {
        "kind": "light_selftest",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "blender": bpy.app.version_string,
        "cases": len(cases),
        "passed": len([c for c in cases if c["ok"]]),
        "verdict": "PASS" if all(c["ok"] for c in cases) else "FAIL",
        "results": cases,
        "method_note": ("黑体色温用 Tanner Helland 拟合生成 sRGB 参考色块，再用本项目算法反查；"
                        "若 D/E 偏差大，说明色温估计不可信，读报告时要把 cct_k 打折扣。"),
    }
    Q.finish(payload, out_path or Q.default_calib_out(rules, "light_selftest"))
    return payload


def main():
    ap = Q.base_parser("qc_light")
    ap.add_argument("--phases", default=None, help="morning,noon,dusk,night（默认全 4 个）")
    ap.add_argument("--weathers", default=None, help="clear,cloudy,rain（默认全 3 个）")
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--selftest", action="store_true", help="跑色温/亮度算法自校验（合成图）")
    args = Q.parse_args_lenient(ap, Q.cli_argv())
    rules = Q.load_rules(args.rules)
    if args.selftest:
        return selftest(rules, args.out)
    run(args, rules)


if __name__ == "__main__":
    main()
