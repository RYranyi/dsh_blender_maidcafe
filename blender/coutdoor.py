"""
coutdoor.py — C_Outdoor：街道/人行道/对面建筑/路灯/行道树/小品

只负责店外环境：人行道 + 路缘石 + 门前踏步、马路 + 标线、对面 8 栋楼、
路灯 2 盏、行道树 3 棵、垃圾桶/消防栓/长椅、10 个水洼、天空穹顶。

运行：blender -b -P coutdoor.py  → 出 4 张预览图 + 打印三角面
"""
import bpy
import math
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
                else os.getcwd())
import ccore as C
import cprop as P
import cmat as MAT
import cassets as A

MODULE = "coutdoor"
OWNER = "env-decor-v2"
TRI_BUDGET = 35000
COL = "C_Outdoor"

D2R = C.D2R
PI = C.PI
TAU = 2.0 * math.pi
STREET_X = (-24.0, 24.0)          # 街道沿 X 展开范围
SIDEWALK_TOP = 0.0                # 人行道可行走面高度（与室内地坪齐平）
ROAD_TOP = P.ROAD["z"]            # -0.14


# ══════════════════════════════════════════════════════════════════════
def build(P_=None, C_=None, M_=None, assets=None):
    Pc = P_ or P
    Cc = C_ or C
    M = M_ or MAT.palette()

    Cc.wipe_collection(COL)
    Cc.ensure_collection(COL)

    objs = []
    colliders = []
    notes = []
    lit_names = []
    rnd = random.Random(20261021)

    def add(ob):
        if ob is not None:
            objs.append(ob)
        return ob

    def bx(name, size, loc, mat, bevel=0.0, segs=2, uv=None):
        return add(Cc.box(name, size, loc=loc, mat=mat, col=COL,
                          bevel=bevel, segs=segs, uv_scale=uv))

    # ── 材质 ──────────────────────────────────────────────────────
    m_walk = M["pavers"]
    m_road = M["asphalt"]
    m_curb = MAT.M.pbr("MAT_CurbStone", base="#A8A49C", rough=0.62)
    m_paint = MAT.M.pbr("MAT_RoadPaint", base="#E2DED2", rough=0.75)
    m_soil = M["soil"]
    m_bark = MAT.M.pbr("MAT_Bark", base="#4A4038", rough=0.92)
    m_leaf = M["leaf"]
    m_leaf2 = M["leaf_dark"]
    m_bulb = M["bulb"]
    m_metal = M["black_metal"]
    m_steel = M["steel"]
    m_wood = M["wood_dark"]
    m_win_dark = MAT.M.pbr("MAT_Window_Dark", base="#20242A", rough=0.15, metal=0.3)
    m_win_lit = MAT.M.pbr("MAT_Window_Lit", base="#3A4763", rough=0.35,
                          emit="#FFD9A0", emit_strength=2.5)
    m_puddle = MAT.M.pbr("MAT_Puddle", base="#1B1E22", rough=0.42, metal=0.0,
                         specular=0.35)
    m_sky = MAT.M.pbr("MAT_SkyDome", base="#BFD8F2", emit="#BFD8F2",
                      emit_strength=0.35, rough=1.0)
    m_hydrant = MAT.M.pbr("MAT_Hydrant_Red", base="#A8271F", rough=0.45, metal=0.15)
    m_far_ground = MAT.M.pbr("MAT_FarGround", base="#8D8A84", rough=0.8)
    m_facades = [M["outer_wall"], M["brick"], M["plaster_out"]]

    # ── 1. 人行道 + 路缘石 + 门前踏步 ────────────────────────────────
    sw_y0, sw_y1 = Pc.SIDEWALK["y"]            # (-4.60, -3.00)
    sw_z0, sw_z1 = Pc.SIDEWALK["z"]            # (-0.02, 0.02)
    slab_t = 0.10
    sw_top = SIDEWALK_TOP
    walk = bx("OD_Sidewalk", (STREET_X[1] - STREET_X[0], sw_y1 - sw_y0, slab_t),
              ((STREET_X[0] + STREET_X[1]) / 2, (sw_y0 + sw_y1) / 2, sw_top - slab_t / 2),
              m_walk, bevel=0.006, segs=1, uv=2.0)

    curb_h = SIDEWALK_TOP - ROAD_TOP            # 0.14 实高（cprop 名义 0.12）
    bx("OD_Curb", (STREET_X[1] - STREET_X[0], 0.16, curb_h),
       ((STREET_X[0] + STREET_X[1]) / 2, sw_y0 - 0.08, ROAD_TOP + curb_h / 2),
       m_curb, bevel=0.014, segs=2)
    # 门前 1 级踏步：门槛石，比人行道高 12mm（室内地坪与人行道齐平，不产生高差陷阱）
    # 注意：前墙内表面 y=-3.0、墙厚 0.16 向室外伸到 y=-3.16，
    # 台阶必须整体落在 y<=-3.16 之外，否则会压进墙体（QC 报过 12mm 穿透）。
    dx0, dx1 = Pc.DOOR_X
    wall_outer_y = sw_y1 - Pc.WALL_T        # -3.16
    step_d = 0.26
    bx("OD_DoorStep", (dx1 - dx0 + 0.24, step_d, 0.012),
       ((dx0 + dx1) / 2, wall_outer_y - step_d / 2, SIDEWALK_TOP + 0.006),
       m_curb, bevel=0.005, segs=1)
    notes.append("sidewalk top z=0.0 (flush with indoor floor); curb riser 0.14 to road -0.14; "
                 "door threshold slab +12mm")

    # ── 2. 马路面 + 标线 ────────────────────────────────────────────
    r_y0, r_y1 = Pc.ROAD["y"]
    # 沥青铺到路缘石外沿（-4.76），避免马路与人行道之间留缝
    road_y_far = -4.76
    road = bx("OD_Road", (STREET_X[1] - STREET_X[0], road_y_far - r_y0, 0.10),
              ((STREET_X[0] + STREET_X[1]) / 2, (r_y0 + road_y_far) / 2, ROAD_TOP - 0.05),
              m_road)
    Cc.uv_world(road, 3.0)
    cy = (r_y0 + r_y1) / 2
    n_dash = 8
    span = 8.0
    step = span / n_dash
    for i in range(n_dash):
        x = -span / 2 + step * (i + 0.5)
        bx(f"OD_RoadDash_{i}", (step * 0.58, 0.14, 0.006),
           (x, cy, ROAD_TOP + 0.003), m_paint)
    for nm, yy in (("OD_RoadEdge_S", r_y1 - 0.24), ("OD_RoadEdge_N", r_y0 + 0.24)):
        bx(nm, (STREET_X[1] - STREET_X[0], 0.10, 0.006),
           ((STREET_X[0] + STREET_X[1]) / 2, yy, ROAD_TOP + 0.003), m_paint)
    notes.append("road paint: 8 dashes + 2 edge lines, 3mm above asphalt")

    # ── 3. 对面 8 栋楼 ─────────────────────────────────────────────
    bf = Pc.BLDG_FAR
    by0, by1 = bf["y"]                        # (-15.0, -9.60)
    front_y = by1                             # 面向街道的立面
    span_x = Pc.BLDG_SPAN_X                    # 6.0
    n_bldg = 8
    # 8 栋 × 6.0m = 48m，正好铺满 STREET_X；P.BLDG_FAR["x"](-18,18) 只有 6 跨，
    # 这里按任务要求扩到 8 栋，左右各外延 6m 以覆盖相机视野。
    bx0 = -span_x * n_bldg / 2                 # -24.0
    bx1 = span_x * n_bldg / 2                  # 24.0
    # 对面地块地面（承接建筑底部，从马路对面延伸到建筑后方）
    bx("OD_FarGround", (bx1 - bx0 + 4.0, 16.60 - 9.20, 0.30),
       ((bx0 + bx1) / 2, (-9.20 + -16.60) / 2, -0.15), m_far_ground)
    bx("OD_FarCurb", (bx1 - bx0 + 4.0, 0.14, 0.14),
       ((bx0 + bx1) / 2, -9.20 + 0.07, ROAD_TOP + 0.07), m_curb, bevel=0.01, segs=1)

    depth = front_y - by0                      # 5.4
    heights = [8.6, 12.4, 10.2, 14.6, 9.4, 11.8, 13.4, 8.9]
    for i in range(n_bldg):
        cx = bx0 + span_x * (i + 0.5)
        h = heights[i]
        mat = m_facades[i % 3]
        body = add(Cc.box(f"OD_Bldg_{i}", (span_x - 0.28, depth, h),
                          loc=(cx, (by0 + by1) / 2, h / 2), mat=mat, col=COL,
                          bevel=0.03, segs=1, uv_scale=0.25))
        # 屋顶女儿墙（4 段）
        for tag, sz, lc in [
                ("F", (span_x - 0.28, 0.22, 0.55), (cx, front_y - 0.11, h + 0.275)),
                ("B", (span_x - 0.28, 0.22, 0.55), (cx, by0 + 0.11, h + 0.275)),
                ("L", (0.22, depth - 0.44, 0.55), (cx - span_x / 2 + 0.14 + 0.11, (by0 + by1) / 2, h + 0.275)),
                ("R", (0.22, depth - 0.44, 0.55), (cx + span_x / 2 - 0.14 - 0.11, (by0 + by1) / 2, h + 0.275))]:
            add(Cc.box(f"OD_BldgParapet_{i}{tag}", sz, loc=lc, mat=mat, col=COL,
                       bevel=0.01, segs=1, uv_scale=0.25))
        # 底层深色基座带（商铺感）
        bx(f"OD_BldgBase_{i}", (span_x - 0.28, 0.06, 1.15),
           (cx, front_y + 0.02, 0.575), m_steel if i % 2 else m_metal)
        # 窗格阵列：3~4 列 × 4~6 行（每栋 ≤30 个）
        ncol = 3 + (i % 2)
        nrow = 4 + (i % 3)
        if ncol * nrow > 30:
            nrow = 30 // ncol
        win_w = 0.82 if ncol >= 4 else 1.02
        win_h = 1.10
        z_lo = 2.05
        z_hi = h - 1.95                     # 顶部留出空调外机带
        cols = []
        for c in range(ncol):
            cols.append(cx - span_x * 0.34 + (span_x * 0.68) * (c / max(1, ncol - 1)))
        rows = []
        for r in range(nrow):
            rows.append(z_lo + (z_hi - z_lo) * (r / max(1, nrow - 1)))
        k = 0
        for r in range(nrow):
            for c in range(ncol):
                lit = rnd.random() < 0.38
                mw = m_win_lit if lit else m_win_dark
                nm = f"OD_WindowLit_{i}_{k}" if lit else f"OD_Window_{i}_{k}"
                ob = Cc.box(nm, (win_w, 0.10, win_h),
                            loc=(cols[c], front_y + 0.025, rows[r]), mat=mw, col=COL)
                objs.append(ob)
                if lit:
                    lit_names.append(nm)
                # 窗台薄片（每 3 个窗挑 1 个，省面）
                if (r + c) % 3 == 0:
                    add(Cc.box(f"OD_WindowSill_{i}_{k}", (win_w + 0.10, 0.14, 0.06),
                               loc=(cols[c], front_y + 0.04, rows[r] - win_h / 2 - 0.03),
                               mat=m_curb, col=COL))
                k += 1
        # 2~3 个空调外机（顶层窗带上方，不压窗）
        ac_z = h - 1.05
        for a in range(2 + (i % 2)):
            ax = cx + span_x * (-0.24 + 0.30 * a)
            add(Cc.box(f"OD_BldgAC_{i}_{a}", (0.72, 0.36, 0.50),
                       loc=(ax, front_y + 0.20, ac_z), mat=m_steel, col=COL,
                       bevel=0.012, segs=1))
            add(Cc.box(f"OD_BldgACgrill_{i}_{a}", (0.60, 0.03, 0.38),
                       loc=(ax, front_y + 0.39, ac_z), mat=M["grille"], col=COL))
        colliders.append({"name": f"OD_Bldg_{i}", "kind": "solid",
                          "aabb": [[cx - span_x / 2, by0, 0.0],
                                   [cx + span_x / 2, by1, h]]})
    notes.append(f"{n_bldg} far buildings, window boxes <=30/bldg, lit windows named OD_WindowLit_*")

    # ── 4. 路灯 ×2 ────────────────────────────────────────────────
    for i, sl in enumerate(Pc.STREET_LAMPS):
        lx, ly = sl["x"], sl["y"]
        add(Cc.cyl(f"OD_Lamp_{i}_Base", r=0.16, h=0.16, segs=16,
                   loc=(lx, ly, 0.08), mat=m_curb, col=COL))
        add(Cc.cyl(f"OD_Lamp_{i}_Pole", r=0.06, h=3.55, segs=14,
                   loc=(lx, ly, 0.16 + 3.55 / 2), mat=m_metal, col=COL, bevel=0.004))
        arm_pts = [(lx, ly, 3.62), (lx, ly - 0.16, 3.86),
                   (lx, ly - 0.44, 3.94), (lx, ly - 0.66, 3.90)]
        add(Cc.tube_along(f"OD_Lamp_{i}_Arm", arm_pts, radius=0.045, segs=7,
                          mat=m_metal, col=COL))
        shade_prof = [(0.34, 0.0), (0.31, 0.05), (0.24, 0.11),
                      (0.12, 0.17), (0.06, 0.20)]
        add(Cc.lathe(f"OD_Lamp_{i}_Head", shade_prof, segs=16,
                     loc=(lx, ly - 0.66, 3.70), mat=m_metal, col=COL,
                     close_bottom=False, close_top=True))
        add(Cc.sphere(f"OD_Lamp_{i}_Bulb", r=0.085, segs=12, rings=8,
                      loc=(lx, ly - 0.66, 3.74), mat=m_bulb, col=COL))
        notes.append(f"OD_Lamp_{i} at ({lx},{ly}), head emissive bulb z~3.74")
    notes.append("street lamps are procedural (not street_lamp_01 asset, too heavy)")

    # ── 5. 行道树 ×3（避开橱窗视线，落在街道两端）──────────────────
    tree_spec = [(-5.35, -4.06, 2.30, 0.88), (5.10, -4.06, 2.55, 0.95),
                 (8.55, -4.02, 2.15, 0.82)]
    for i, (tx, ty, th, cr) in enumerate(tree_spec):
        add(Cc.cyl(f"OD_Tree_{i}_Pit", r=0.46, h=0.03, segs=14,
                   loc=(tx, ty, 0.015), mat=m_soil, col=COL))
        add(Cc.cyl(f"OD_Tree_{i}_Trunk", r=0.105, h=th, segs=10, r2=0.072,
                   loc=(tx, ty, th / 2), mat=m_bark, col=COL, shade="smooth"))
        blob = [(0.0, 0.0, th * 0.92, cr), (0.16, -0.10, th * 1.16, cr * 0.80),
                (-0.15, 0.09, th * 0.72, cr * 0.68)]
        for j, (ox, oy, oz, r) in enumerate(blob):
            add(Cc.sphere(f"OD_Tree_{i}_Crown{j}", r=r, segs=10, rings=6,
                          loc=(tx + ox, ty + oy, oz), mat=m_leaf if j % 2 == 0 else m_leaf2,
                          col=COL, scale=(1.12, 1.12, 0.86)))
        colliders.append({"name": f"OD_Tree_{i}", "kind": "solid",
                          "aabb": [[tx - 0.16, ty - 0.16, 0.0], [tx + 0.16, ty + 0.16, th]]})

    # ── 6. 垃圾桶 ×2 / 消防栓 / 长椅 ────────────────────────────────
    for i, (bx_, by_) in enumerate([(4.55, -3.55), (-4.85, -3.60)]):
        add(Cc.cyl(f"OD_Bin_{i}_Body", r=0.24, h=0.62, segs=16,
                   loc=(bx_, by_, 0.31), mat=m_metal, col=COL, bevel=0.006, bsegs=1))
        add(Cc.ring_tube(f"OD_Bin_{i}_Rim", R=0.245, r=0.022, segs=20, rsegs=6,
                         loc=(bx_, by_, 0.62), mat=m_steel, col=COL))
        add(Cc.cyl(f"OD_Bin_{i}_Lid", r=0.255, h=0.035, segs=16,
                   loc=(bx_, by_, 0.655), mat=m_steel, col=COL))
        colliders.append({"name": f"OD_Bin_{i}", "kind": "solid",
                          "aabb": [[bx_ - 0.26, by_ - 0.26, 0.0], [bx_ + 0.26, by_ + 0.26, 0.66]]})

    hx, hy = -4.30, -4.34
    add(Cc.cyl("OD_Hydrant_Body", r=0.10, h=0.56, segs=14,
               loc=(hx, hy, 0.28), mat=m_hydrant, col=COL))
    add(Cc.sphere("OD_Hydrant_Dome", r=0.105, segs=14, rings=8,
                  loc=(hx, hy, 0.575), mat=m_hydrant, col=COL, scale=(1, 1, 0.72)))
    for j, (ox, oy, rot) in enumerate([(0.11, 0.0, (0, PI / 2, 0)), (-0.11, 0.0, (0, PI / 2, 0))]):
        add(Cc.cyl(f"OD_Hydrant_Nozzle{j}", r=0.05, h=0.10, segs=10,
                   loc=(hx + ox, hy + oy, 0.40), rot=rot, mat=m_hydrant, col=COL))
    add(Cc.cyl("OD_Hydrant_Cap", r=0.075, h=0.05, segs=12,
               loc=(hx, hy, 0.665), mat=m_hydrant, col=COL))
    colliders.append({"name": "OD_Hydrant", "kind": "solid",
                      "aabb": [[hx - 0.13, hy - 0.13, 0.0], [hx + 0.13, hy + 0.13, 0.70]]})

    # 长椅（靠人行道内侧，背朝马路；避开橱窗视线与灯柱）
    # 注意：Cc.box 的位置参数顺序是 (name, size, loc, rot, mat, col)，
    # 只传 (name, size, loc, 材质) 会把材质塞进 rot、col 落成默认 "C_Default"
    # （QC 报过 9 个 OD_Bench_* 跑到 C_Default）—— 这里必须 mat=/col= 具名传参。
    bnx, bny = 6.90, -4.16
    for j, ox in enumerate([-0.62, 0.62]):
        add(Cc.box(f"OD_Bench_Leg{j}", (0.07, 0.46, 0.40),
                   loc=(bnx + ox, bny - 0.04, 0.20), mat=m_metal, col=COL,
                   bevel=0.008, segs=1))
    for j in range(3):
        add(Cc.box(f"OD_Bench_Seat{j}", (1.52, 0.125, 0.042),
                   loc=(bnx, bny - 0.16 + 0.145 * j, 0.42), mat=m_wood, col=COL,
                   bevel=0.007, segs=1))
    for j, ox in enumerate([-0.62, 0.62]):
        add(Cc.box(f"OD_Bench_Post{j}", (0.06, 0.06, 0.46),
                   loc=(bnx + ox, bny - 0.30, 0.63), mat=m_metal, col=COL,
                   bevel=0.006, segs=1))
    for j in range(2):
        add(Cc.box(f"OD_Bench_Back{j}", (1.52, 0.045, 0.115),
                   loc=(bnx, bny - 0.285 - 0.035 * j, 0.60 + 0.175 * j),
                   rot=(9 * D2R, 0, 0), mat=m_wood, col=COL,
                   bevel=0.007, segs=1))
    colliders.append({"name": "OD_Bench", "kind": "solid",
                      "aabb": [[bnx - 0.78, bny - 0.36, 0.0], [bnx + 0.78, bny + 0.14, 0.80]]})

    # ── 7. 水洼 ×10（拒绝采样：落在人行道内，避开小品与环境物）───────
    # 用 poly_prism 直接生成椭圆盘（世界坐标顶点），避免改 mesh 后 matrix_world 不刷新
    obstacles = [(4.55, -3.55, 0.45), (-4.85, -3.60, 0.45), (-4.30, -4.34, 0.42),
                 (6.90, -4.16, 0.95), (-3.00, -4.35, 0.35), (2.40, -4.35, 0.35)]
    obstacles += [(tx, ty, 0.62) for (tx, ty, _h, _r) in tree_spec]
    y_lo, y_hi = -4.46, -3.16          # 水洼中心可用带
    made = 0
    tries = 0
    while made < 10 and tries < 400:
        tries += 1
        rx = rnd.uniform(0.26, 0.62)
        ry = rx * rnd.uniform(0.55, 0.95)
        px = rnd.uniform(-7.5, 7.5)     # 集中在店门前一段，远景可不铺
        py = rnd.uniform(y_lo + ry, y_hi - ry)
        if py + ry > -3.05 or py - ry < -4.55:
            continue
        if any((px - ox) ** 2 + (py - oy) ** 2 < (rx + orad) ** 2
               for (ox, oy, orad) in obstacles):
            continue
        nseg = 20
        poly = [(rx * math.cos(TAU * i / nseg), ry * math.sin(TAU * i / nseg))
                for i in range(nseg)]
        add(Cc.poly_prism(f"OD_Puddle_{made}", poly, thickness=0.003, axis="Z",
                          loc=(px, py, SIDEWALK_TOP + 0.003), mat=m_puddle,
                          col=COL, shade="smooth"))
        made += 1
    notes.append(f"puddles: {made} elliptical discs 3mm above sidewalk, "
                 "rejection-sampled off obstacles")

    # ── 8. 天空穹顶（法线朝内）────────────────────────────────────
    sky = Cc.sphere("OD_SkyDome", r=40.0, segs=20, rings=12,
                    loc=(0.0, -6.0, 0.0), mat=m_sky, col=COL)
    sky.data.flip_normals()
    objs.append(sky)
    notes.append("OD_SkyDome r=40, normals flipped inward, excluded from selfcheck framing")

    # ── 统计 ──────────────────────────────────────────────────────
    # 关键：depsgraph 不更新时 matrix_world 仍是单位阵（新建物体只设了 location），
    # 会让 world_aabb / colliders 拿到局部坐标。统一刷新一次。
    bpy.context.view_layer.update()
    tris = Cc.tri_count(objs)
    Cc.log(f"{MODULE}: {len(objs)} objects, {tris} tris (budget {TRI_BUDGET})")
    return {
        "objects": objs,
        "collections": [COL],
        "colliders": colliders,
        "anchors": {
            "sky_dome_name": "OD_SkyDome",
            "sky_dome_radius": 40.0,
            "window_lit_names": lit_names,
            "window_lit_count": len(lit_names),
            "sidewalk_top_z": SIDEWALK_TOP,
            "road_top_z": ROAD_TOP,
            "curb_h": curb_h,
            "bldg_front_y": front_y,
            "street_lamps": [dict(name=f"OD_Lamp_{i}", x=s["x"], y=s["y"],
                                  head_z=3.74) for i, s in enumerate(Pc.STREET_LAMPS)],
            "street_x": list(STREET_X),
        },
        "notes": "; ".join(notes),
        "tris": tris,
    }


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    M = MAT.palette()
    r = build(P, C, M, {})
    keep = [o for o in r["objects"] if o.name != "OD_SkyDome"]
    C.selfcheck(MODULE, keep, res=(960, 720), samples=24,
                views=[
                    {"name": "street", "from": (-11.0, -5.2, 2.6), "look": (10.0, -7.2, 2.6), "lens": 30},
                    {"name": "facade", "from": (-1.6, -6.2, 2.1), "look": (3.0, -12.5, 6.5), "lens": 24},
                    {"name": "walk", "from": (-3.4, -3.35, 1.55), "look": (7.5, -4.30, 0.85), "lens": 26},
                    {"name": "cross", "from": (3.15, -5.35, 1.62), "look": (-3.2, -4.05, 1.55), "lens": 32},
                    {"name": "top", "from": (0.0, -4.2, 14.0), "look": (0.0, -4.4, 0.0), "lens": 32},
                ])
