"""
cbar.py — C_Bar：L 形吧台、后操作台/层架、设备（咖啡机/磨豆机/手冲/糖浆/收银/水槽）

全部程序化 + 复用 PolyHaven 材质；对外暴露 BAR_* 尺寸取自 cprop。
"""
import bpy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
                else r"E:\dsh\maid_cafe\blender")
import ccore as C
import cprop as P
import cmat as MAT

MODULE = "cbar"
OWNER = "lead"
TRI_BUDGET = 70000
COL = "C_Bar"
D2R = C.D2R
PI = C.PI


# ══════════════════════════════════════════════════════════════════════
def _cabinet_body(name, x, y, z0, z1, mat, col, inset=0.03, kick=0.10,
                  front="-Y", door_split=2):
    """橱柜体：主体 + 踢脚凹槽 + 分缝柜门（薄板凸出 8mm）。"""
    objs = []
    w = x[1] - x[0]
    d = y[1] - y[0]
    body_z0 = z0 + kick
    objs.append(C.box(name + "_Body", (w, d, z1 - body_z0),
                      loc=((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, (body_z0 + z1) / 2),
                      mat=mat, col=col, bevel=0.006, segs=1))
    # 踢脚（内缩）
    objs.append(C.box(name + "_Kick", (w - 0.06, d - 0.06, kick),
                      loc=((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, z0 + kick / 2),
                      mat=M_black(), col=col))
    # 柜门（面朝 front）
    yy = y[0] + 0.008 if front == "-Y" else y[1] - 0.008
    gap = 0.012
    for i in range(door_split):
        dw = (w - gap * (door_split + 1)) / door_split
        dx0 = x[0] + gap + i * (dw + gap)
        objs.append(C.box(f"{name}_Door{i}", (dw, 0.018, (z1 - body_z0) - 0.06),
                          loc=(dx0 + dw / 2, yy, (body_z0 + z1) / 2 - 0.02),
                          mat=mat, col=col, bevel=0.004, segs=1))
        # 拉手
        hx = dx0 + dw - 0.035 if front == "-Y" else dx0 + 0.035
        objs.append(C.box(f"{name}_DHandle{i}", (0.012, 0.02, 0.10),
                          loc=(hx, yy + (-0.022 if front == "-Y" else 0.022), z1 - 0.16),
                          mat=M_brass_(), col=col))
    return objs


_M = None


def M_black():
    return _M["black_metal"]


def M_brass_():
    return _M["brass"]


# ══════════════════════════════════════════════════════════════════════
def build(P_, C_, M_, assets):
    global _M
    _M = M_
    C.wipe_collection(COL)
    C.ensure_collection(COL)
    objs = []
    colliders = []

    m_counter = M_["wood_counter"]
    m_oak = M_["wood_oak"]
    m_dark = M_["wood_dark"]
    m_marble = M_["marble"]
    m_brass = M_["brass"]
    m_steel = M_["steel"]
    m_black = M_["black_metal"]
    m_glass = M_["glass"]
    m_porcelain = M_["porcelain"]
    m_ceramic = M_["ceramic_mat"]

    BT = P.BAR_TOP_Z
    slab = P.BAR_SLAB_T
    over = P.BAR_OVERHANG

    # ── 1. L 形主吧台 ──────────────────────────────────────────────
    main = P.BAR_MAIN
    ret = P.BAR_RETURN
    # 柜体（主段 + 回折段）
    objs += _cabinet_body("BA_BarMain", main["x"], main["y"], 0.0, BT - slab,
                          m_counter, COL, kick=0.10, front="-Y", door_split=4)
    objs += _cabinet_body("BA_BarRet", ret["x"], ret["y"], 0.0, BT - slab,
                          m_counter, COL, kick=0.10, front="-X", door_split=2)

    # 台面板（大理石，出檐）
    sx = (main["x"][1] - main["x"][0]) + over * 2
    sy = (main["y"][1] - main["y"][0]) + over * 2
    top = C.box("BA_BarTop", (sx, sy, slab),
                loc=((main["x"][0] + main["x"][1]) / 2, (main["y"][0] + main["y"][1]) / 2,
                     BT - slab / 2),
                mat=m_marble, col=COL, bevel=0.008, segs=2)
    C.uv_world(top, 1.2)
    objs.append(top)
    # 回折段台面
    # 回折段台面：y 只从 main.y[1] 起，与主段在转角处「不重叠、只接缝」
    # （原来 y 从 ret.y[0]-over 起，与主段在 x[2.94,3.74]×y[1.11,1.91] 完全同高重叠，
    #   bevel 造成顶点穿透 7.43mm —— qc 唯一的 FAIL）
    # 主段含出檐的最外沿 = main.y[1] + over；回折段从此处 +2mm 起，彻底不重叠
    # （原来 -0.004 仍与主段重叠，bevel 8mm 让边缘外扩 → 顶点穿透 8mm）
    ret_y0 = main["y"][1] + over + 0.002
    ret_w = (ret["y"][1] + over) - ret_y0
    top2 = C.box("BA_BarTopRet",
                 ((ret["x"][1] - ret["x"][0]) + over * 2, ret_w, slab),
                 loc=((ret["x"][0] + ret["x"][1]) / 2, ret_y0 + ret_w / 2, BT - slab / 2),
                 mat=m_marble, col=COL, bevel=0.008, segs=2)
    C.uv_world(top2, 1.2)
    objs.append(top2)

    # 台沿压边（黄铜细条，嵌在台面前缘 8mm）
    objs.append(C.box("BA_BarEdge",
                      (main["x"][1] - main["x"][0], 0.014, 0.012),
                      loc=((main["x"][0] + main["x"][1]) / 2, main["y"][0] - over - 0.004, BT - 0.014),
                      mat=m_brass, col=COL))

    # 吧台前侧的下横杆（脚踏）
    objs.append(C.cyl("BA_BarFootRail", r=0.016, h=main["x"][1] - main["x"][0] - 0.3,
                      segs=12, rot=(0, PI / 2, 0),
                      loc=((main["x"][0] + main["x"][1]) / 2, main["y"][0] - 0.10, 0.16),
                      mat=m_brass, col=COL))
    for xx in (main["x"][0] + 0.22, main["x"][1] - 0.22):
        objs.append(C.cyl("BA_FootBracket", r=0.012, h=0.16, segs=8,
                          loc=(xx, main["y"][0] - 0.10, 0.08), mat=m_brass, col=COL))

    # ── 2. 后操作台 + 水槽 + 防溅板 ────────────────────────────────
    bb = P.BAR_BACK
    objs += _cabinet_body("BA_BackBar", bb["x"], bb["y"], 0.0, P.BAR_BACK_TOP_Z - 0.04,
                          m_counter, COL, kick=0.08, front="-Y", door_split=5)
    btop = C.box("BA_BackTop", (bb["x"][1] - bb["x"][0], bb["y"][1] - bb["y"][0] + 0.03, 0.04),
                 loc=((bb["x"][0] + bb["x"][1]) / 2, (bb["y"][0] + bb["y"][1]) / 2,
                      P.BAR_BACK_TOP_Z - 0.02),
                 mat=M_["steel_brushed"], col=COL, bevel=0.004, segs=1)
    objs.append(btop)
    # 防溅板（后墙上，钢/马赛克）
    objs.append(C.box("BA_Backsplash",
                      (bb["x"][1] - bb["x"][0], 0.018, P.BACKSPLASH["h"]),   # 0.018 薄板，避开腰线
                      loc=((bb["x"][0] + bb["x"][1]) / 2,
                           P.ROOM_Y[1] - 0.040,   # 后移到墙裙内侧，前表面 2.969 < 腰线 2.972
                           P.BAR_BACK_TOP_Z + P.BACKSPLASH["h"] / 2),
                      mat=M_["ceramic_tile"], col=COL))
    # 水槽（凹槽 + 龙头）
    sk = P.SINK
    objs.append(C.box("BA_SinkBasin", (sk["x"][1] - sk["x"][0], sk["y"][1] - sk["y"][0], P.SINK_RECESS),
                      # 盆体：上沿对齐台面**顶面**(BAR_BACK_TOP_Z=0.90)，
                      # 这样凹槽才看得见（原来 -0.022 让盆顶 0.878 被 0.86-0.90 的台面盖住，
                      # 视觉上"水龙头下面没有凹槽"）。台面已开孔(24顶点/26面)，不会穿模。
                      loc=((sk["x"][0] + sk["x"][1]) / 2, (sk["y"][0] + sk["y"][1]) / 2,
                           P.BAR_BACK_TOP_Z - P.SINK_RECESS / 2 + 0.001),
                      mat=M_["steel"], col=COL))
    # 龙头
    fx = (sk["x"][0] + sk["x"][1]) / 2
    objs.append(C.cyl("BA_FaucetBase", r=0.022, h=0.04, segs=16,
                      loc=(fx, P.ROOM_Y[1] - 0.10, P.BAR_BACK_TOP_Z + 0.02), mat=m_brass, col=COL))
    objs.append(C.tube_along("BA_Faucet",
                             [(fx, P.ROOM_Y[1] - 0.10, P.BAR_BACK_TOP_Z + 0.03),
                              (fx, P.ROOM_Y[1] - 0.10, P.BAR_BACK_TOP_Z + 0.30),
                              (fx, P.ROOM_Y[1] - 0.24, P.BAR_BACK_TOP_Z + 0.34),
                              (fx, P.ROOM_Y[1] - 0.26, P.BAR_BACK_TOP_Z + 0.22)],
                             radius=0.012, segs=10, mat=m_brass, col=COL))
    # 沥水架 + 洗杯器
    objs.append(C.box("BA_Drainer", (0.36, 0.22, 0.012),
                      loc=(sk["x"][1] + 0.28, (sk["y"][0] + sk["y"][1]) / 2, P.BAR_BACK_TOP_Z + 0.006),
                      mat=M_["grille"], col=COL))

    # ── 3. 后吧层架（3 层 + 立柱）──────────────────────────────────
    sh = P.BAR_SHELF
    for i, z in enumerate(P.BAR_SHELF_Z):
        objs.append(C.box(f"BA_Shelf_{i}", (sh["x"][1] - sh["x"][0], sh["y"][1] - sh["y"][0], 0.025),
                          loc=((sh["x"][0] + sh["x"][1]) / 2, (sh["y"][0] + sh["y"][1]) / 2, z),
                          mat=m_oak, col=COL, bevel=0.003, segs=1))
    for xx in (sh["x"][0] + 0.03, sh["x"][1] - 0.03):
        objs.append(C.box("BA_ShelfUpright", (0.03, sh["y"][1] - sh["y"][0], P.BAR_SHELF_Z[2] - 1.20),
                          loc=(xx, (sh["y"][0] + sh["y"][1]) / 2, (1.20 + P.BAR_SHELF_Z[2]) / 2),
                          mat=m_dark, col=COL))
    # 层架下沿灯带
    objs.append(C.box("BA_ShelfLED", (sh["x"][1] - sh["x"][0] - 0.1, 0.02, 0.012),
                      loc=((sh["x"][0] + sh["x"][1]) / 2, sh["y"][0] + 0.02, P.BAR_SHELF_Z[1] - 0.022),
                      mat=M_["led"], col=COL))

    # ── 4. 倒挂杯架（横杆 + 挂钩 + 倒挂马克杯）─────────────────────
    cr = P.CUP_RAIL
    objs.append(C.cyl("BA_CupRailRod", r=0.012, h=cr["x"][1] - cr["x"][0], segs=10,
                      rot=(0, PI / 2, 0),
                      loc=((cr["x"][0] + cr["x"][1]) / 2, cr["y"], cr["z"]),
                      mat=m_brass, col=COL))
    for xx in (cr["x"][0], cr["x"][1]):
        objs.append(C.box("BA_CupRailBracket", (0.02, 0.30, 0.02),
                          loc=(xx, cr["y"] - 0.14, cr["z"] + 0.02), mat=m_brass, col=COL))
        objs.append(C.cyl("BA_CupRailPost", r=0.012, h=cr["z"] - (P.BAR_SHELF_Z[0]),
                          loc=(xx, cr["y"] - 0.28, (cr["z"] + P.BAR_SHELF_Z[0]) / 2),
                          mat=m_brass, col=COL))
    # 挂钩 + 杯子（每 0.16m 一个，倒挂）
    n_cup = 12
    for i in range(n_cup):
        cx = cr["x"][0] + 0.12 + i * ((cr["x"][1] - cr["x"][0] - 0.24) / (n_cup - 1))
        objs.append(C.cyl(f"BA_Hook_{i}", r=0.004, h=0.05, segs=6,
                          loc=(cx, cr["y"], cr["z"] - 0.026), mat=m_steel, col=COL))
        # 倒挂杯：杯口朝下（lathe 反过来）
        cup = C.lathe(f"BA_Mug_{i}",
                      [(0.0, 0.0), (0.035, 0.0), (0.040, 0.012), (0.038, 0.075), (0.037, 0.078)],
                      segs=16, loc=(cx, cr["y"], cr["z"] - 0.14),
                      mat=m_porcelain, col=COL)
        cup.rotation_euler = (PI, 0, 0)   # 倒扣
        # 把手
        objs.append(cup)
        # 把手：杯体翻转后占 z∈[cr.z-0.218, cr.z-0.14]，把手要对准杯身中部
        # （原 cr.z-0.10 让把手悬在杯口上方 90mm+，老兄指出的"马克杯和握把错位"）
        objs.append(C.ring_tube(f"BA_MugHandle_{i}", R=0.026, r=0.005, segs=16, rsegs=6,
                                loc=(cx + 0.042, cr["y"], cr["z"] - 0.179),
                                rot=(0, PI / 2, 0), mat=m_porcelain, col=COL))

    # 4.5 杯碟叠（台上）
    objs.append(_stack_dishes("BA_PlateStack", 0.22, 8, P.BAR_BACK_TOP_Z + 0.006,
                              -1.35, 2.70, m_porcelain, COL))

    # ── 5. 意式咖啡机（组：机身/冲煮头/蒸汽棒/温杯盘/滴水盘/表盘）──
    objs += _espresso_machine(M_, COL, objs)
    # ── 6. 磨豆机 ─────────────────────────────────────────────────
    objs += _grinder(M_, COL, objs)
    # ── 7. 手冲台（壶 + 滤杯 + 秤 + 温控壶）───────────────────────
    objs += _pourover(M_, COL, objs)
    # ── 8. 糖浆瓶组（6 瓶不同色）──────────────────────────────────
    objs += _syrups(M_, COL, objs)
    # ── 9. 收银机（外部模型）───────────────────────────────────────
    objs += _register(M_, COL, assets)

    # 小物：吧台上纸巾盒、菜单夹、笔筒、小费罐
    objs.append(C.box("BA_NapkinBox", (0.11, 0.13, 0.10),
                      loc=(0.62, 1.62, BT + 0.05), mat=M_["porcelain"],
                      col=COL, bevel=0.006, segs=2))
    objs.append(C.cyl("BA_TipJar", r=0.045, h=0.13, segs=20,
                      loc=(0.04, 1.55, BT + 0.065), mat=m_glass, col=COL))
    objs.append(C.cyl("BA_TipJarCap", r=0.046, h=0.02, segs=20,
                      loc=(0.04, 1.55, BT + 0.13), mat=m_brass, col=COL))

    # ── 10. 后吧瓶罐 ───────────────────────────────────────────────
    objs += _bottles_row(M_, COL)

    # 碰撞体
    for ob in objs:
        if ob is None:
            continue
        if ob.name.startswith(("BA_BarMain", "BA_BarRet", "BA_BackBar", "BA_Shelf_", "BA_Espresso")):
            mn, mx = C.world_aabb(ob)
            colliders.append({"name": ob.name, "aabb": [mn, mx], "kind": "solid"})

    tris = C.tri_count(objs)
    C.log(f"{MODULE}: {len(objs)} objects, {tris} tris (budget {TRI_BUDGET})")
    return {"objects": [o for o in objs if o], "collections": [COL],
            "colliders": colliders,
            "anchors": {"bar_top_z": BT,
                        "espresso": [P.ESPRESSO["x"], P.ESPRESSO["y"]],
                        "register": [P.REGISTER["x"], P.REGISTER["y"]]},
            "notes": "L-shaped marble bar, back bar shelving, espresso/grinder/pourover/syrup stations",
            "tris": tris}


def _stack_dishes(name, r, n, z0, x, y, mat, col):
    """一叠盘子（8 个，微错位）。"""
    objs = []
    grp = []
    for i in range(n):
        p = C.cyl(f"{name}_{i}", r=r, h=0.012, segs=24,
                  loc=(x + (i % 2) * 0.002, y, z0 + i * 0.011),
                  mat=mat, col=col, bevel=0.002, bsegs=1)
        grp.append(p)
    return C.join(grp, name, col)


def _espresso_machine(M_, COL, existing):
    e = P.ESPRESSO
    cx = (e["x"][0] + e["x"][1]) / 2
    cy = (e["y"][0] + e["y"][1]) / 2
    z0 = e["z"][0]
    objs = []
    m_steel = M_["steel"]
    m_black = M_["black_metal"]
    m_brass = M_["brass"]
    m_glass = M_["glass"]
    # 机身（不锈钢箱体，带圆角）
    body = C.box("BA_Espresso_Body", (e["x"][1] - e["x"][0], e["y"][1] - e["y"][0], 0.42),
                 loc=(cx, cy, z0 + 0.21), mat=M_["steel_brushed"], col=COL, bevel=0.02, segs=3)
    objs.append(body)
    # 顶部温杯盘（托盘 + 围栏）
    objs.append(C.box("BA_Espresso_CupWarm", (e["x"][1] - e["x"][0] - 0.06, e["y"][1] - e["y"][0] - 0.06, 0.02),
                      loc=(cx, cy, z0 + 0.43), mat=m_steel, col=COL))
    for i, (dx, dy, sx, sy) in enumerate([(0, -0.20, 0.68, 0.014), (0, 0.20, 0.68, 0.014),
                                          (-0.34, 0, 0.014, 0.42), (0.34, 0, 0.014, 0.42)]):
        objs.append(C.box(f"BA_Espresso_Rail{i}", (sx, sy, 0.035),
                          loc=(cx + dx, cy + dy, z0 + 0.455), mat=m_steel, col=COL))
    # 正立面装饰：压力表 + 旋钮 + 冲煮头群
    objs.append(C.cyl("BA_Espresso_GaugeRim", r=0.045, h=0.012, segs=24, rot=(PI / 2, 0, 0),
                      loc=(cx - 0.22, e["y"][0] + 0.004, z0 + 0.32), mat=m_brass, col=COL))
    objs.append(C.cyl("BA_Espresso_Gauge", r=0.036, h=0.004, segs=24, rot=(PI / 2, 0, 0),
                      loc=(cx - 0.22, e["y"][0] - 0.002, z0 + 0.32), mat=M_["porcelain"], col=COL))
    for i in range(2):   # 双冲煮头
        gx = cx - 0.13 + i * 0.26
        objs.append(C.cyl(f"BA_Espresso_Group{i}", r=0.042, h=0.09, segs=20,
                          loc=(gx, e["y"][0] + 0.02, z0 + 0.26), mat=m_brass, col=COL))
        objs.append(C.cyl(f"BA_Espresso_Portaf{i}", r=0.055, h=0.022, segs=20,
                          loc=(gx, e["y"][0] - 0.03, z0 + 0.205), mat=m_black, col=COL))
        # 手柄
        objs.append(C.cyl(f"BA_Espresso_Handle{i}", r=0.013, h=0.15, segs=10,
                          rot=(PI / 2, 0, 0),
                          loc=(gx, e["y"][0] - 0.11, z0 + 0.205), mat=m_black, col=COL))
        # 粉碗
        objs.append(C.cyl(f"BA_Espresso_Basket{i}", r=0.032, h=0.03, segs=16,
                          loc=(gx, e["y"][0] - 0.055, z0 + 0.208), mat=m_steel, col=COL))
    # 蒸汽棒（右侧，弯管 + 头）
    sx = e["x"][1] - 0.05
    objs.append(C.cyl("BA_Espresso_SteamBase", r=0.016, h=0.05, segs=12,
                      loc=(sx, e["y"][0] + 0.03, z0 + 0.22), mat=m_steel, col=COL))
    objs.append(C.tube_along("BA_Espresso_SteamWand",
                             [(sx, e["y"][0] + 0.03, z0 + 0.22),
                              (sx + 0.02, e["y"][0] - 0.03, z0 + 0.14),
                              (sx + 0.03, e["y"][0] - 0.10, z0 + 0.08)],
                             radius=0.008, segs=8, mat=m_steel, col=COL))
    # 滴水盘（前伸，栅格）
    objs.append(C.box("BA_Espresso_Drip", (0.44, 0.18, 0.016),
                      loc=(cx, e["y"][0] - 0.05, z0 + 0.008), mat=m_black, col=COL, bevel=0.003, segs=1))
    for i in range(9):
        objs.append(C.box(f"BA_Espresso_DripSlat{i}", (0.40, 0.008, 0.004),
                          loc=(cx, e["y"][0] - 0.135 + i * 0.019, z0 + 0.018), mat=m_steel, col=COL))
    # 底部支脚
    for dx in (-0.32, 0.32):
        for dy in (-0.16, 0.16):
            objs.append(C.cyl("BA_Espresso_Foot", r=0.018, h=0.03, segs=10,
                              loc=(cx + dx, cy + dy, z0 + 0.015), mat=m_black, col=COL))
    return objs


def _grinder(M_, COL, existing):
    g = P.GRINDER
    cx = (g["x"][0] + g["x"][1]) / 2
    cy = (g["y"][0] + g["y"][1]) / 2
    z0 = g["z"][0]
    m_black = M_["black_metal"]
    m_steel = M_["steel"]
    m_glass = M_["glass"]
    m_brass = M_["brass"]
    objs = []
    objs.append(C.box("BA_Grinder_Base", (0.20, 0.22, 0.06),
                      loc=(cx, cy, z0 + 0.03), mat=m_black, col=COL, bevel=0.008, segs=2))
    # 机箱（斜背）
    objs.append(C.cyl("BA_Grinder_Tower", r=0.075, h=0.26, segs=24,
                      loc=(cx, cy + 0.02, z0 + 0.19), mat=m_black, col=COL))
    # 豆仓（玻璃漏斗）
    objs.append(C.lathe("BA_Grinder_Hopper",
                        [(0.0, 0.0), (0.055, 0.0), (0.088, 0.14), (0.092, 0.16),
                         (0.090, 0.165)],
                        segs=28, loc=(cx, cy + 0.02, z0 + 0.32), mat=m_glass, col=COL,
                        close_top=False))
    objs.append(C.cyl("BA_Grinder_HopperLid", r=0.095, h=0.018, segs=28,
                      loc=(cx, cy + 0.02, z0 + 0.49), mat=m_black, col=COL, bevel=0.004, bsegs=2))
    objs.append(C.cyl("BA_Grinder_HopperCollar", r=0.062, h=0.02, segs=24,
                      loc=(cx, cy + 0.02, z0 + 0.315), mat=m_brass, col=COL))
    # 咖啡粉出口 + 接粉杯
    objs.append(C.box("BA_Grinder_Spout", (0.05, 0.09, 0.03),
                      loc=(cx, cy - 0.11, z0 + 0.10), mat=m_steel, col=COL))
    objs.append(C.box("BA_Grinder_Fork", (0.10, 0.02, 0.008),
                      loc=(cx, cy - 0.13, z0 + 0.055), mat=m_brass, col=COL))
    # 研磨粗细旋钮
    objs.append(C.cyl("BA_Grinder_Dial", r=0.022, h=0.016, segs=16,
                      loc=(cx + 0.07, cy + 0.05, z0 + 0.22), mat=m_brass, col=COL))
    return objs


def _pourover(M_, COL, existing):
    p = P.POUR_OVER
    cx = (p["x"][0] + p["x"][1]) / 2
    cy = (p["y"][0] + p["y"][1]) / 2
    z0 = p["z"][0]
    m_porcelain = M_["porcelain"]
    m_steel = M_["steel"]
    m_glass = M_["glass"]
    m_brass = M_["brass"]
    m_coffee = M_["coffee"]
    objs = []
    # 木质托盘
    objs.append(C.box("BA_Pour_Tray", (0.44, 0.30, 0.02),
                      loc=(cx, cy, z0 + 0.01), mat=M_["wood_table"], col=COL, bevel=0.004))
    # 电子秤
    objs.append(C.box("BA_Pour_Scale", (0.20, 0.22, 0.02),
                      loc=(cx - 0.10, cy + 0.02, z0 + 0.03), mat=M_["black_metal"], col=COL,
                      bevel=0.004, segs=1))
    # 细嘴壶（不锈钢，带把手）
    objs.append(C.lathe("BA_Pour_KettleBody",
                        [(0.0, 0.0), (0.048, 0.0), (0.052, 0.006), (0.050, 0.10),
                         (0.042, 0.125), (0.040, 0.128)],
                        segs=28, loc=(cx - 0.10, cy + 0.02, z0 + 0.043), mat=m_steel, col=COL))
    objs.append(C.tube_along("BA_Pour_KettleSpout",
                             [(cx - 0.10 + 0.048, cy + 0.02, z0 + 0.10),
                              (cx - 0.10 + 0.11, cy + 0.02, z0 + 0.135),
                              (cx - 0.10 + 0.15, cy + 0.02, z0 + 0.125)],
                             radius=0.008, segs=8, mat=m_steel, col=COL))
    objs.append(C.ring_tube("BA_Pour_KettleHandle", R=0.045, r=0.008, segs=20, rsegs=6,
                            loc=(cx - 0.10 - 0.055, cy + 0.02, z0 + 0.10),
                            rot=(0, PI / 2, 0), mat=M_["black_metal"], col=COL))
    # 玻璃分享壶 + 滤杯
    objs.append(C.lathe("BA_Pour_Server",
                        [(0.0, 0.0), (0.045, 0.0), (0.048, 0.004), (0.052, 0.10),
                         (0.046, 0.13), (0.044, 0.132)],
                        segs=24, # 右移 17mm：原 cx+0.13 与 BA_Pour_CupCoffee 液面 x 重叠 11.5mm，
                        # 实测顶点级穿透 8.58mm（手冲壶壁扫过杯内液面）
                        loc=(cx + 0.147, cy + 0.01, z0 + 0.043), mat=m_glass, col=COL))
    objs.append(C.lathe("BA_Pour_Dripper",
                        [(0.0, 0.0), (0.016, 0.0), (0.050, 0.052), (0.056, 0.058)],
                        segs=24, loc=(cx + 0.13, cy + 0.01, z0 + 0.175),
                        mat=m_porcelain, col=COL))
    # 滤纸
    objs.append(C.lathe("BA_Pour_FilterPaper",
                        [(0.0, 0.0), (0.048, 0.045), (0.052, 0.05)],
                        segs=20, loc=(cx + 0.13, cy + 0.01, z0 + 0.182),
                        mat=M_["paper"], col=COL))
    # 小杯
    objs.append(C.lathe("BA_Pour_Cup",
                        [(0.0, 0.0), (0.032, 0.0), (0.035, 0.008), (0.033, 0.055), (0.032, 0.058)],
                        segs=20, loc=(cx - 0.10 + 0.16, cy + 0.02, z0 + 0.043),
                        mat=m_porcelain, col=COL))
    # 咖啡液面
    objs.append(C.cyl("BA_Pour_CupCoffee", r=0.030, h=0.002, segs=18,
                      loc=(cx - 0.10 + 0.16, cy + 0.02, z0 + 0.088), mat=m_coffee, col=COL))
    return objs


def _syrups(M_, COL, existing):
    s = P.SYRUP
    z0 = P.BAR_TOP_Z
    cols = ["#7A2B2B", "#C8792D", "#D8C08A", "#5B7F4A", "#3E5E83", "#8E5A86"]
    mats = []
    for i, hx in enumerate(cols):
        mats.append(M_.__class__ and MAT.M.pbr(f"MAT_Syrup_{i}", base=hx, rough=0.12,
                                               transmission=0.35, coat=0.6))
    objs = []
    # 木托盘
    objs.append(C.box("BA_Syrup_Tray", (s["x"][1] - s["x"][0], 0.18, 0.016),
                      loc=((s["x"][0] + s["x"][1]) / 2, 1.51, z0 + 0.008),
                      mat=M_["wood_table"], col=COL, bevel=0.004))
    for i in range(6):
        x = s["x"][0] + 0.055 + i * 0.088
        # 瓶身
        objs.append(C.cyl(f"BA_Syrup_Bottle{i}", r=0.028, h=0.17, segs=16,
                          loc=(x, 1.51, z0 + 0.105), mat=mats[i], col=COL, bevel=0.008, bsegs=2))
        # 瓶颈 + 泵头
        objs.append(C.cyl(f"BA_Syrup_Neck{i}", r=0.012, h=0.05, segs=12,
                          loc=(x, 1.51, z0 + 0.215), mat=mats[i], col=COL))
        objs.append(C.cyl(f"BA_Syrup_Pump{i}", r=0.016, h=0.045, segs=12,
                          loc=(x, 1.51, z0 + 0.262), mat=M_["steel"], col=COL))
        objs.append(C.box(f"BA_Syrup_PumpTop{i}", (0.04, 0.02, 0.014),
                          loc=(x, 1.51, z0 + 0.288), mat=M_["steel"], col=COL))
        # 标签圈
        objs.append(C.cyl(f"BA_Syrup_Label{i}", r=0.0295, h=0.055, segs=16,
                          loc=(x, 1.51, z0 + 0.09), mat=M_["paper"], col=COL))
    return objs


def _bottles_row(M_, COL):
    """后架上的罐/瓶/茶壶排列（用外部 wine_bottles/tea_set 会太重，这里程序化）。"""
    objs = []
    sh = P.BAR_SHELF
    y = (sh["y"][0] + sh["y"][1]) / 2
    x0, x1 = sh["x"][0] + 0.18, sh["x"][1] - 0.18
    n = 9
    heights = [0.19, 0.24, 0.16, 0.28, 0.21, 0.17, 0.25, 0.19, 0.22]
    rads = [0.042, 0.038, 0.05, 0.035, 0.045, 0.048, 0.036, 0.043, 0.040]
    for i in range(n):
        x = x0 + i * (x1 - x0) / (n - 1)
        z = P.BAR_SHELF_Z[2] + 0.0125
        h = heights[i]
        r = rads[i]
        # 罐体
        mat = M_["ceramic_mat"] if i % 2 == 0 else M_["wood_dark"]
        objs.append(C.lathe(f"BA_Jar_{i}",
                            [(0.0, 0.0), (r * 0.9, 0.0), (r, h * 0.08), (r * 0.97, h * 0.8),
                             (r * 0.80, h * 0.9), (r * 0.78, h * 0.92)],
                            segs=18, loc=(x, y, z), mat=mat, col=COL))
        # 盖
        objs.append(C.cyl(f"BA_JarLid_{i}", r=r * 0.80, h=0.018, segs=18,
                          loc=(x, y, z + h * 0.92 + 0.009), mat=M_["brass"], col=COL,
                          bevel=0.003, bsegs=2))
    # 中间层：茶壶 2 个 + 杯
    for i, (xx, rr) in enumerate([(sh["x"][0] + 0.55, 0.085), (sh["x"][0] + 1.55, 0.075)]):
        z = P.BAR_SHELF_Z[1] + 0.0125
        objs.append(C.lathe(f"BA_Teapot_{i}",
                            [(0.0, 0.0), (rr * 0.85, 0.0), (rr, rr * 0.35), (rr * 0.92, rr * 0.9),
                             (rr * 0.55, rr * 1.05), (rr * 0.50, rr * 1.08)],
                            segs=24, loc=(xx, y, z), mat=M_["porcelain"], col=COL))
        objs.append(C.box(f"BA_TeapotLid_{i}", (rr * 0.9, rr * 0.9, 0.012),
                          loc=(xx, y, z + rr * 1.10), mat=M_["porcelain"], col=COL))
        objs.append(C.ring_tube(f"BA_TeapotHandle_{i}", R=rr * 0.52, r=0.007, segs=20, rsegs=6,
                                loc=(xx + rr * 0.86, y, z + rr * 0.55),
                                rot=(PI / 2, 0, 0), mat=M_["porcelain"], col=COL))
        # 壶嘴
        objs.append(C.tube_along(f"BA_TeapotSpout_{i}",
                                 [(xx - rr * 0.9, y, z + rr * 0.35),
                                  (xx - rr * 1.35, y, z + rr * 0.70),
                                  (xx - rr * 1.55, y, z + rr * 0.92)],
                                 radius=0.010, segs=8, mat=M_["porcelain"], col=COL))
    # 下层：咖啡豆罐 4 个
    for i in range(4):
        xx = sh["x"][0] + 0.35 + i * 0.55
        z = P.BAR_SHELF_Z[0] + 0.0125
        objs.append(C.cyl(f"BA_BeanJar_{i}", r=0.075, h=0.20, segs=18,
                          loc=(xx, y, z + 0.10), mat=M_["glass"], col=COL, bevel=0.01, bsegs=2))
        objs.append(C.cyl(f"BA_BeanJarLid_{i}", r=0.078, h=0.022, segs=18,
                          loc=(xx, y, z + 0.21), mat=M_["wood_dark"], col=COL))
        # 豆子（堆在罐底）
        objs.append(C.cyl(f"BA_Beans_{i}", r=0.068, h=0.09, segs=16,
                          loc=(xx, y, z + 0.05), mat=M_["coffee"], col=COL))
    return objs


def _register(M_, COL, assets):
    """收银机：优先外部模型 CashRegister_01。"""
    try:
        import cassets as A
    except Exception:
        import sys
        sys.path.insert(0, r"E:\dsh\maid_cafe\blender")
        import cassets as A
    reg = P.REGISTER
    cx = (reg["x"][0] + reg["x"][1]) / 2
    cy = (reg["y"][0] + reg["y"][1]) / 2
    objs = []
    if A.model_blend("CashRegister_01"):
        got = A.import_model("CashRegister_01", col=COL, name_prefix="BA_Register")
        for ob in got:
            ob.location = (cx, cy, P.BAR_TOP_Z)
            ob.rotation_euler = (0, 0, 180 * D2R)
        objs += got
        if got:
            mn, mx = C.world_aabb(got[0])
            h = mx[2] - mn[2]
            # 目标高度 0.35 m
            if h > 1e-6:
                s = 0.35 / h
                C.scale_about(got[0], s)
                got[0].location = (cx, cy, P.BAR_TOP_Z)
                objs = got
    else:
        objs.append(C.box("BA_Register_Body", (0.42, 0.34, 0.20),
                          loc=(cx, cy, P.BAR_TOP_Z + 0.10), mat=M_["steel"], col=COL,
                          bevel=0.01, segs=2))
        objs.append(C.box("BA_Register_Screen", (0.30, 0.02, 0.18),
                          loc=(cx, cy - 0.17, P.BAR_TOP_Z + 0.26), mat=M_["black_metal"],
                          col=COL, rot=(-20 * D2R, 0, 0)))
        objs.append(C.box("BA_Register_Drawer", (0.40, 0.30, 0.10),
                          loc=(cx, cy, P.BAR_TOP_Z + 0.05), mat=M_["black_metal"], col=COL))
    return objs


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M = MAT.palette()
    res = build(P, C, M, {})
    C.selfcheck(MODULE, res["objects"], res=(960, 720), samples=24,
                views=[
                    {"name": "persp", "from": (2.6, -1.6, 1.9), "look": (1.0, 1.6, 0.9), "lens": 32},
                    {"name": "front", "from": (1.2, -1.4, 1.35), "look": (1.2, 1.7, 0.9), "lens": 30},
                    {"name": "detail", "from": (2.4, 0.7, 1.35), "look": (2.5, 1.5, 1.05), "lens": 45},
                    {"name": "top", "from": (1.2, 0.2, 4.2), "look": (1.2, 1.6, 0.8), "ortho": 4.2},
                ])
