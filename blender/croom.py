"""
croom.py — C_Room：建筑本体（地面/墙/墙裙/天花/窗/门/踢脚/灯槽）

只负责“壳”：地面、四面墙（含窗洞与门洞）、墙裙、腰线、踢脚、天花、吊顶跌级、
窗框与玻璃、门框与玻璃门、窗帘轨。所有装饰性小物在 cdecor.py。

运行：blender -b -P croom.py     → 出 4 张预览图 + 打印三角面
"""
import bpy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
                else os.getcwd())
import ccore as C
import cprop as P
import cmat as MAT

MODULE = "croom"
OWNER = "lead"
TRI_BUDGET = 60000
COL = "C_Room"

D2R = C.D2R
PI = C.PI


# ══════════════════════════════════════════════════════════════════════
def _wall_panel(name, span, height, thickness, axis, fixed, mat, col):
    """建一块墙板。axis='X' 表示墙沿 X 展开（前后墙），fixed 为其 y 坐标。"""
    if axis == "X":
        size = (span, thickness, height)
        loc = ((fixed[0] + fixed[1]) / 2 if isinstance(fixed, tuple) else fixed, 0, 0)
    else:
        size = (thickness, span, height)
        loc = (fixed, 0, 0)
    return size, loc


def build(P_, C_, M_, assets):
    C.wipe_collection(COL)
    C.ensure_collection(COL)
    objs = []
    colliders = []
    notes = []

    x0, x1 = P.ROOM_X
    y0, y1 = P.ROOM_Y
    H = P.CEIL_Z
    T = P.WALL_T
    W = x1 - x0
    D = y1 - y0

    m_floor = M_["floor"]
    m_wall = M_["wall"]
    m_accent = M_["wall_accent"]
    m_wood = M_["wood_oak"]
    m_dark = M_["wood_dark"]
    m_marble = M_["marble"]
    m_glass = M_["glass"]
    m_frame = M_["wood_dark"]
    m_brass = M_["brass"]

    # ── 1. 地面（人字拼）：用厚板，顶面 z=0 ──────────────────────────
    fl = C.box("RM_Floor", (W, D, P.FLOOR_T), loc=(0, 0, -P.FLOOR_T / 2),
               mat=m_floor, col=COL, uv_scale=None)
    C.uv_world(fl, 2.4)
    objs.append(fl)

    # 地面收边（踢脚下方压条，视觉上区分墙/地）
    objs.append(C.box("RM_FloorTrim", (W, 0.02, 0.012), loc=(0, y0 + 0.01, 0.006),
                      mat=m_dark, col=COL))

    # ── 2. 天花 + 跌级（局部吊顶，中间抬高）────────────────────────
    # 外圈跌级：贴墙一圈宽 0.55 的吊顶，下沿 z = CEIL_RECESS_Z 内凹
    rec = 0.55
    rim_h = H - P.CEIL_RECESS_Z
    for nm, sz, lc in [
        ("RM_CeilRimS", (W, rec, rim_h), (0, y0 + rec / 2, P.CEIL_RECESS_Z + rim_h / 2)),
        ("RM_CeilRimN", (W, rec, rim_h), (0, y1 - rec / 2, P.CEIL_RECESS_Z + rim_h / 2)),
        ("RM_CeilRimW", (rec, D - rec * 2, rim_h), (x0 + rec / 2, (y0 + y1) / 2, P.CEIL_RECESS_Z + rim_h / 2)),
        ("RM_CeilRimE", (rec, D - rec * 2, rim_h), (x1 - rec / 2, (y0 + y1) / 2, P.CEIL_RECESS_Z + rim_h / 2)),
    ]:
        objs.append(C.box(nm, sz, loc=lc, mat=m_accent, col=COL, bevel=0.008))
    # 中央平顶
    objs.append(C.box("RM_CeilCenter", (W - rec * 2, D - rec * 2, 0.04),
                      loc=(0, 0, P.CEIL_RECESS_Z - 0.02), mat=m_wall, col=COL))
    # 跌级侧面（灯带槽内侧竖面）
    for nm, sz, lc in [
        ("RM_CoveS", (W - rec * 2, 0.02, rim_h), (0, y0 + rec, P.CEIL_RECESS_Z + rim_h / 2)),
        ("RM_CoveN", (W - rec * 2, 0.02, rim_h), (0, y1 - rec, P.CEIL_RECESS_Z + rim_h / 2)),
        ("RM_CoveW", (0.02, D - rec * 2, rim_h), (x0 + rec, 0, P.CEIL_RECESS_Z + rim_h / 2)),
        ("RM_CoveE", (0.02, D - rec * 2, rim_h), (x1 - rec, 0, P.CEIL_RECESS_Z + rim_h / 2)),
    ]:
        objs.append(C.box(nm, sz, loc=lc, mat=M_["led"], col=COL))
    notes.append("ceiling: recessed cove with emissive strip")

    # ── 3. 墙：四面（前后墙带洞口，用多边形+洞 = 分段拼）────────────
    wain = P.WAINSCOT_Z

    def wall_face(name, axis, fixed_coord, out_sign, spans):
        """spans = [(a0,a1,z0,z1)] 用 4 边面生成墙板（单面朝内 + 背面挤出）。"""
        for i, (a0, a1, z0, z1) in enumerate(spans):
            if a1 - a0 < 1e-4 or z1 - z0 < 1e-4:
                continue
            nm = f"{name}_{i}"
            w = a1 - a0
            h = z1 - z0
            if axis == "X":
                sz = (w, T, h)
                lc = ((a0 + a1) / 2, fixed_coord + out_sign * T / 2, (z0 + z1) / 2)
            else:
                sz = (T, w, h)
                lc = (fixed_coord + out_sign * T / 2, (a0 + a1) / 2, (z0 + z1) / 2)
            ob = C.box(nm, sz, loc=lc, mat=m_wall, col=COL)
            C.uv_world(ob, 3.0)
            objs.append(ob)
            return ob  # 只为兼容；实际循环内 append

    # 前墙（y=y0，朝室外 −Y）：洞口 WIN_X/WIN_Z + DOOR_X/DOOR_Z
    wx0, wx1 = P.WIN_X
    wz0, wz1 = P.WIN_Z
    dx0, dx1 = P.DOOR_X
    dz0, dz1 = P.DOOR_Z
    front_spans = [
        (x0, wx0, 0, H),                 # 窗左
        (wx0, wx1, 0, wz0),              # 窗下（矮墙）
        (wx0, wx1, wz1, H),              # 窗上
        (wx1, dx0, wz0, wz1),            # 窗与门之间（窗台高到窗顶）
        (wx1, dx0, wz1, H),              # ★ 窗与门之间「窗顶以上到天花」——原来漏了这段，
                                         #    导致 x[0.35,1.15] z[2.58,3.0] 没有墙体，
                                         #    从室内能看穿到外皮背面（老兄截图里的"缺一块"）
        (wx1, dx0, 0, wz0) if wx1 < dx0 else None,   # 窗与门之间窗台以下
        (dx0, dx1, dz1, H),              # 门上
        (dx1, x1, 0, H),                 # 门右
    ]
    front_spans = [s for s in front_spans if s]
    for i, (a0, a1, z0, z1) in enumerate(front_spans):
        if a1 - a0 < 1e-4 or z1 - z0 < 1e-4:
            continue
        ob = C.box(f"RM_WallFront_{i}", (a1 - a0, T, z1 - z0),
                   loc=((a0 + a1) / 2, y0 - T / 2, (z0 + z1) / 2), mat=m_wall, col=COL)
        C.uv_world(ob, 3.0)
        objs.append(ob)

    # 后墙（y=y1，朝室内 +Y 面）
    ob = C.box("RM_WallBack", (W, T, H), loc=(0, y1 + T / 2, H / 2), mat=m_wall, col=COL)
    C.uv_world(ob, 3.0)
    objs.append(ob)
    # 左墙 / 右墙
    for nm, xc in (("RM_WallLeft", x0 - T / 2), ("RM_WallRight", x1 + T / 2)):
        ob = C.box(nm, (T, D, H), loc=(xc, 0, H / 2), mat=m_wall, col=COL)
        C.uv_world(ob, 3.0)
        objs.append(ob)

    # 外墙皮：只在洞口以外区域补一层薄板（不能整面覆盖，否则挡死门窗）
    # 前墙外侧：窗左 / 窗右（门左、门右）/ 窗上下 / 门上
    def _skin(nm, axis, a0, a1, z0, z1, y_coord, out_sign):
        if a1 - a0 < 1e-4 or z1 - z0 < 1e-4:
            return
        if axis == "X":
            objs.append(C.box(nm, (a1 - a0, 0.02, z1 - z0),
                             loc=((a0 + a1) / 2, y_coord + out_sign * 0.01, (z0 + z1) / 2),
                             mat=M_["outer_wall"], col=COL))
        else:
            objs.append(C.box(nm, (0.02, a1 - a0, z1 - z0),
                             loc=(y_coord + out_sign * 0.01, (a0 + a1) / 2, (z0 + z1) / 2),
                             mat=M_["outer_wall"], col=COL))
    fy_out = y0 - T
    _skin("RM_SkinF_L", "X", x0, wx0, 0, H, fy_out, -1)
    _skin("RM_SkinF_M", "X", wx1, dx0, 0, H, fy_out, -1)
    _skin("RM_SkinF_R", "X", dx1, x1, 0, H, fy_out, -1)
    _skin("RM_SkinF_UnderWin", "X", wx0, wx1, 0, wz0, fy_out, -1)
    _skin("RM_SkinF_AboveWin", "X", wx0, wx1, wz1, H, fy_out, -1)
    _skin("RM_SkinF_AboveDoor", "X", dx0, dx1, dz1, H, fy_out, -1)
    _skin("RM_SkinB", "X", x0, x1, 0, H, y1 + T, 1)

    # ── 4. 墙裙（四面，凸出墙面 18mm）+ 腰线压边 + 踢脚 ────────────
    wain_t = P.WAINSCOT_T
    # 前墙墙裙（避开窗洞下沿以下部分窗洞 z0=0.72 > 墙裙 0.95，需要避开）
    for nm, sz, lc in [
        ("RM_WainFront_L", (wx0 - x0, D * 0 + wain_t, wain), (x0 and (x0 + wx0) / 2, y0 + wain_t / 2, wain / 2)),
        ("RM_WainFront_R", (x1 - dx1, wain_t, wain), ((dx1 + x1) / 2, y0 + wain_t / 2, wain / 2)),
        ("RM_WainFront_M", (dx0 - wx1, wain_t, wain), ((wx1 + dx0) / 2, y0 + wain_t / 2, wain / 2)),
        ("RM_WainBack", (W, wain_t, wain), (0, y1 - wain_t / 2, wain / 2)),
        ("RM_WainLeft", (wain_t, D, wain), (x0 + wain_t / 2, 0, wain / 2)),
        ("RM_WainRight", (wain_t, D, wain), (x1 - wain_t / 2, 0, wain / 2)),
    ]:
        if sz[0] <= 0.001:
            continue
        ob = C.box(nm, sz, loc=lc, mat=m_wood, col=COL)
        C.uv_world(ob, 1.6)
        objs.append(ob)
    # 腰线（顶部压条 + 踢脚）
    for nm, z, hgt, dep in (("RM_ChairRail", wain, 0.045, 0.028), ("RM_Skirting", 0.07, 0.10, 0.022)):
        # 四面各一条
        for tag, sz, lc in [
            ("S", (W, dep, hgt), (0, y0 + dep / 2, z + (hgt / 2 if nm == "RM_Skirting" else 0))),
            ("N", (W, dep, hgt), (0, y1 - dep / 2, z + (hgt / 2 if nm == "RM_Skirting" else 0))),
            ("W", (dep, D, hgt), (x0 + dep / 2, 0, z + (hgt / 2 if nm == "RM_Skirting" else 0))),
            ("E", (dep, D, hgt), (x1 - dep / 2, 0, z + (hgt / 2 if nm == "RM_Skirting" else 0))),
        ]:
            ob = C.box(f"{nm}_{tag}", sz, loc=lc, mat=m_dark if nm == "RM_Skirting" else m_wood,
                       col=COL, bevel=0.004, segs=1)
            objs.append(ob)

    # ── 5. 窗：窗框 + 竖梃 + 玻璃 + 窗台板 ─────────────────────────
    frame_w = 0.055
    fz0, fz1 = wz0, wz1
    fx0, fx1 = wx0, wx1
    # 窗框四边（贴着洞口内壁，厚 0.07）
    fy = y0 - T / 2
    for nm, sz, lc in [
        ("RM_WinFrame_T", (fx1 - fx0, 0.07, frame_w), ((fx0 + fx1) / 2, fy, fz1 - frame_w / 2)),
        ("RM_WinFrame_B", (fx1 - fx0, 0.07, frame_w), ((fx0 + fx1) / 2, fy, fz0 + frame_w / 2)),
        ("RM_WinFrame_L", (frame_w, 0.07, fz1 - fz0), (fx0 + frame_w / 2, fy, (fz0 + fz1) / 2)),
        ("RM_WinFrame_R", (frame_w, 0.07, fz1 - fz0), (fx1 - frame_w / 2, fy, (fz0 + fz1) / 2)),
    ]:
        objs.append(C.box(nm, sz, loc=lc, mat=m_frame, col=COL, bevel=0.004, segs=1))
    # 竖梃（3 根 → 4 块玻璃）
    n_mull = P.WIN_MULLIONS
    for i in range(1, n_mull):
        mx = fx0 + (fx1 - fx0) * i / n_mull
        objs.append(C.box(f"RM_WinMullion_{i}", (0.045, 0.075, fz1 - fz0 - frame_w * 2),
                          loc=(mx, fy, (fz0 + fz1) / 2), mat=m_frame, col=COL, bevel=0.004, segs=1))
    # 横梃（上部开窗分隔，z = 2.30）
    cross_z = 2.28
    objs.append(C.box("RM_WinCross", (fx1 - fx0 - frame_w * 2, 0.075, 0.04),
                      loc=((fx0 + fx1) / 2, fy, cross_z), mat=m_frame, col=COL))
    # 玻璃（4 块，略微内缩）
    for i in range(n_mull):
        gx0 = fx0 + (fx1 - fx0) * i / n_mull + (frame_w if i == 0 else 0.022)
        gx1 = fx0 + (fx1 - fx0) * (i + 1) / n_mull - (frame_w if i == n_mull - 1 else 0.022)
        for j, (gz0, gz1) in enumerate([(fz0 + frame_w, cross_z - 0.02), (cross_z + 0.02, fz1 - frame_w)]):
            ob = C.box(f"RM_WinGlass_{i}_{j}", (gx1 - gx0, 0.012, gz1 - gz0),
                       loc=((gx0 + gx1) / 2, fy + 0.005, (gz0 + gz1) / 2), mat=m_glass, col=COL)
            objs.append(ob)
    # 窗台板（室内侧，出墙 0.12）
    ob = C.box("RM_WinSill", (fx1 - fx0 + 0.16, 0.14, 0.045),
               loc=((fx0 + fx1) / 2, y0 + 0.07, fz0 - 0.02), mat=m_marble, col=COL, bevel=0.006)
    objs.append(ob)

    # ── 6. 门：门框 + 双开玻璃门（固定微开）────────────────────────
    dy = y0 - T / 2
    for nm, sz, lc in [
        ("RM_DoorFrame_T", (dx1 - dx0 + 0.12, 0.10, 0.06), ((dx0 + dx1) / 2, dy, dz1 + 0.03)),
        ("RM_DoorFrame_L", (0.06, 0.10, dz1), (dx0 - 0.03, dy, dz1 / 2)),
        ("RM_DoorFrame_R", (0.06, 0.10, dz1), (dx1 + 0.03, dy, dz1 / 2)),
    ]:
        objs.append(C.box(nm, sz, loc=lc, mat=m_frame, col=COL, bevel=0.004, segs=1))
    # 门扇（每扇 ~0.64 宽，玻璃 + 边框），以门洞边缘为合页向室内微开 10°
    leaf_w = (dx1 - dx0) / 2 - 0.012
    open_deg = 5.0
    hinge_y = y0 + 0.02
    door_h = dz1 - 0.02
    for i, (hinge_x, dirn) in enumerate([(dx0 + 0.008, 1), (dx1 - 0.008, -1)]):
        # 先以「关闭状态」建在门洞平面：局部 x 从 0 到 dirn*leaf_w
        cx = dirn * leaf_w / 2
        parts = []
        parts.append(C.box(f"RM_DoorGlass_{i}", (leaf_w - 0.10, 0.012, door_h - 0.16),
                           loc=(cx, 0.0, door_h / 2 + 0.02), mat=m_glass, col=COL))
        for nm2, sz2, lc2 in [
            ("T", (leaf_w, 0.032, 0.055), (cx, 0.0, door_h / 2 + 0.02 + (door_h - 0.16) / 2 + 0.027)),
            ("B", (leaf_w, 0.032, 0.13), (cx, 0.0, door_h / 2 + 0.02 - (door_h - 0.16) / 2 - 0.065)),
            ("Hinge", (0.045, 0.032, door_h - 0.16), (dirn * 0.0225, 0.0, door_h / 2 + 0.02)),
            ("Edge", (0.045, 0.032, door_h - 0.16), (dirn * (leaf_w - 0.0225), 0.0, door_h / 2 + 0.02)),
        ]:
            parts.append(C.box(f"RM_DoorStile_{i}{nm2}", sz2, loc=lc2, mat=m_frame, col=COL,
                               bevel=0.003, segs=1))
        # 把手（横向拉手，靠门缝一侧）
        parts.append(C.cyl(f"RM_DoorHandle_{i}", r=0.013, h=0.16, segs=12, rot=(0, PI / 2, 0),
                           loc=(dirn * (leaf_w - 0.085), -0.045, 1.02), mat=m_brass, col=COL))
        parts.append(C.cyl(f"RM_DoorHandleBase_{i}", r=0.016, h=0.02, segs=12, rot=(PI / 2, 0, 0),
                           loc=(dirn * (leaf_w - 0.085), -0.02, 1.02), mat=m_brass, col=COL))
        leaf = C.join(parts, f"RM_DoorLeaf_{i}", COL)
        # 把原点移到世界原点（几何不动），再平移到合页位置
        C.set_origin(leaf, (0.0, 0.0, 0.0))
        leaf.location = C.Vector((hinge_x, hinge_y, 0.0))
        # 绕合页转开（两扇都向室内 +Y 打开）
        C.rotate_about(leaf, (hinge_x, hinge_y, 0.0), "Z", open_deg * dirn)
        objs.append(leaf)
        # 门上玻璃横楣（固定扇，门洞上方 0.20m 高）
        objs.append(C.box(f"RM_DoorTransom_{i}", (leaf_w, 0.012, 0.16),
                          loc=(hinge_x + dirn * leaf_w / 2, hinge_y, door_h - 0.08),
                          mat=m_glass, col=COL))

    # ── 7. 窗帘轨（窗前上方，装饰用）──────────────────────────────
    objs.append(C.cyl("RM_CurtainRod", r=0.014, h=fx1 - fx0 + 0.3, segs=12, rot=(0, PI / 2, 0),
                      loc=((fx0 + fx1) / 2, y0 + 0.16, fz1 + 0.14), mat=m_brass, col=COL))
    for i, (sx, sy) in enumerate([(fx0 - 0.12, 1), (fx1 + 0.12, -1)]):
        objs.append(C.box(f"RM_CurtainBracket_{i}", (0.03, 0.20, 0.03),
                          loc=(sx, y0 + 0.10, fz1 + 0.14), mat=m_brass, col=COL))

    # ── 8. 门内脚垫 ────────────────────────────────────────────────
    mat_ob = C.box("RM_Doormat", (1.0, 0.6, 0.012), loc=((dx0 + dx1) / 2, y0 + 0.42, 0.006),
                   mat=M_["cotton"], col=COL, bevel=0.004, segs=1)
    C.uv_world(mat_ob, 0.6)
    objs.append(mat_ob)

    # ── 统计 & 碰撞 ────────────────────────────────────────────────
    for ob in objs:
        if ob is None:
            continue
        mn, mx = C.world_aabb(ob)
        if ob.name.startswith("RM_Wall") or ob.name.startswith("RM_Wain") or ob.name.startswith("RM_Skin"):
            colliders.append({"name": ob.name, "aabb": [mn, mx], "kind": "solid"})
    colliders.append({"name": "ROOM_BOUNDS",
                      "aabb": [[x0, y0, 0.0], [x1, y1, H]], "kind": "room"})

    tris = C.tri_count(objs)
    C.log(f"{MODULE}: {len(objs)} objects, {tris} tris (budget {TRI_BUDGET})")
    return {"objects": objs, "collections": [COL], "colliders": colliders,
            "anchors": {"win": [[fx0, fz0], [fx1, fz1]],
                        "door": [[dx0, dz0], [dx1, dz1]],
                        "ceiling_recess_z": P.CEIL_RECESS_Z},
            "notes": "; ".join(notes), "tris": tris}


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    M = MAT.palette()
    res = build(P, C, M, {})
    C.selfcheck(MODULE, res["objects"], res=(900, 700), samples=24,
                views=[
                    {"name": "inside", "from": (1.9, -2.4, 1.62), "look": (-1.2, 1.2, 1.0), "lens": 24},
                    {"name": "window", "from": (-1.0, 1.8, 1.55), "look": (-2.0, -3.0, 1.4), "lens": 28},
                    {"name": "topf", "from": (0.0, -1.0, 7.5), "look": (0, 0, 0), "ortho": 9.5},
                ])
