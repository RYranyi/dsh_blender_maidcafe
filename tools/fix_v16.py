"""
fix_v16.py —— 基于用户最新版（16:08）

严格只改两层：
  Board_1 (z=0.481)  空的 → 4 个小玩偶（小黄鸭 / 猫 / 鲨鱼 / 魔鬼鱼）
  Board_2 (z=0.871)  5 个旧盆栽 → 4 件现成盆栽
                      potted_plant_01 / 02 / 04 + 1 个花箱（箱内种 3 株蕨）
                      为什么要花箱：PolyHaven 自带的成品盆栽只有 3 个，
                      花箱属于同一「盆栽」属性，且是箱内长植物（不是空箱）

不动：
  Board_0 单排书 / Board_3 茶具 / Board_4 酒瓶 / 柜顶 / 水槽 / 房间其他所有内容
"""
import bpy
import sys
import os
import re
from mathutils import Vector, Matrix

ROOT = None
for start in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
    p = start
    for _ in range(6):
        if os.path.isfile(os.path.join(p, "scene", "maid_cafe.blend")):
            ROOT = p
            break
        p = os.path.dirname(p)
    if ROOT:
        break
sys.path.insert(0, os.path.join(ROOT, "blender"))
import ccore as C
import cassets as A

BLEND = os.path.join(ROOT, "scene", "maid_cafe.blend")
bpy.ops.wm.open_mainfile(filepath=BLEND)
bpy.context.view_layer.update()
log = []


def upd():
    bpy.context.view_layer.update()


def ab(ob):
    upd()
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return (min(p.x for p in pts), max(p.x for p in pts),
            min(p.y for p in pts), max(p.y for p in pts),
            min(p.z for p in pts), max(p.z for p in pts))


def gbox(objs):
    bs = [ab(o) for o in objs]
    return (min(b[0] for b in bs), max(b[1] for b in bs),
            min(b[2] for b in bs), max(b[3] for b in bs),
            min(b[4] for b in bs), max(b[5] for b in bs))


def sxy(ob, sx, sy, sz=1.0, ax=None, ay=None, az=None):
    a = ab(ob)
    ax = (a[0] + a[1]) / 2 if ax is None else ax
    ay = (a[2] + a[3]) / 2 if ay is None else ay
    az = a[4] if az is None else az
    T = (Matrix.Translation(Vector((ax, ay, az)))
         @ Matrix.Diagonal(Vector((sx, sy, sz)).to_4d())
         @ Matrix.Translation(Vector((-ax, -ay, -az))))
    ob.matrix_world = T @ ob.matrix_world
    upd()


def shift(ob, dx, dy, dz):
    ob.location.x += dx
    ob.location.y += dy
    ob.location.z += dz
    upd()


def to_pos(ob, cx, y_back, z_base):
    a = ab(ob)
    shift(ob, cx - (a[0] + a[1]) / 2, y_back - a[3], z_base - a[4])
    return ab(ob)


def hits(a, b, eps=0.002):
    return (a[0] < b[1] - eps and a[1] > b[0] + eps and
            a[2] < b[3] - eps and a[3] > b[2] + eps and
            a[4] < b[5] - eps and a[5] > b[4] + eps)


def decimate(ob, cap):
    C.deselect_all()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    now = C.tri_count([ob])
    if now <= cap * 1.06:
        return now
    m = ob.modifiers.new("D", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = max(0.01, min(1.0, float(cap) / max(now, 1)))
    m.use_collapse_triangulate = True
    C.deselect_all()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.object.modifier_apply(modifier=m.name)
    except Exception:
        ob.modifiers.remove(m)
    upd()
    return C.tri_count([ob])


# ═══════════════════════════════════════════════════
SB = bpy.data.objects["DC_ShelfBack"]
YB_BACK = ab(SB)[3]
l_ = ab(bpy.data.objects["DC_ShelfSide_L"])
r_ = ab(bpy.data.objects["DC_ShelfSide_R"])
TH = l_[1] - l_[0]
X0, X1 = l_[0], r_[1]
BX0, BX1 = X0 + TH + 0.006, X1 - TH - 0.006
b0 = ab(bpy.data.objects["DC_ShelfBoard_0"])
Y_FRONT = b0[2]
BACK_FRONT = YB_BACK - 0.020
BOARD_TOP = [ab(bpy.data.objects["DC_ShelfBoard_%d" % i])[5] for i in range(6)]
IW = BX1 - BX0
Y_MIN = Y_FRONT + 0.018
Y_MAX = BACK_FRONT - 0.004
log.append("柜内 X[%.3f,%.3f] W=%.3f  Y[%.3f,%.3f]"
           % (BX0, BX1, IW, Y_FRONT, BACK_FRONT))

# 只清 Board_2 上的旧盆栽（pot_a~d、potted_plant_01）
OLD = ["DC_Shf_pot_a", "DC_Shf_pot_b", "DC_Shf_pot_c", "DC_Shf_pot_d",
       "DC_Shf_potted_plant_01"]
removed = []
for nm in OLD:
    o = bpy.data.objects.get(nm)
    if o:
        a = ab(o)
        removed.append("%s z[%.2f,%.2f]" % (nm, a[4], a[5]))
        bpy.data.objects.remove(o, do_unlink=True)
# 顺便清掉我之前可能留下的
for o in list(bpy.data.objects):
    n = o.name or ""
    if n.startswith(("DC_L1g", "DC_L2g", "DC_L1_", "DC_L2_")):
        bpy.data.objects.remove(o, do_unlink=True)
log.append("已删除 Board_2 旧盆栽 %d 个: %s" % (len(removed), ", ".join(removed)))


def place(lvl, z_level, cx, pid, target_h, tri_cap, tag, max_w=0.32):
    objs = A.import_model(pid, col="C_Decor", target_height=target_h,
                          face="-Y", name_prefix="DC_%s_%s" % (tag, pid))
    if not objs:
        log.append("  ! 导入失败 %s" % pid)
        return None, None
    ob = objs[0]
    if tri_cap and C.tri_count([ob]) > tri_cap * 1.06:
        decimate(ob, tri_cap)
    a = ab(ob)
    w = a[1] - a[0]
    if w > max_w:
        sxy(ob, max_w / w, max_w / w)
        a = ab(ob)
    to_pos(ob, cx, Y_MAX, z_level)
    a = ab(ob)
    if a[2] < Y_MIN:
        shift(ob, 0, Y_MIN - a[2], 0)
        a = ab(ob)
    cap_top = (BOARD_TOP[lvl + 1] - 0.022) - 0.008
    if a[5] > cap_top:
        sxy(ob, 1.0, 1.0, (cap_top - a[4]) / max(a[5] - a[4], 1e-6))
        a = ab(ob)
        shift(ob, 0, 0, z_level - a[4])
        a = ab(ob)
    return ob, a


# ═══════════════════════════════════════════════════
# Board_1：4 个小玩偶
# ═══════════════════════════════════════════════════
L1, Z1 = 1, BOARD_TOP[1]
H1 = (BOARD_TOP[2] - 0.022) - Z1
log.append("")
log.append("Board_1 z=%.3f 净高 %.3f → 4 个小玩偶" % (Z1, H1))

TOYS = [
    ("rubber_duck_toy",      0.120, 4300, 0.22),
    ("concrete_cat_statue",  0.150, 12000, 0.18),
    ("bronze_shark_statue",  0.140, 7400, 0.32),
    ("bronze_ray_statue",    0.125, 1900, 0.32),
]
SL1 = [BX0 + IW * (i + 0.5) / 4 for i in range(4)]
b1 = []
for i, (pid, h, tc, mw) in enumerate(TOYS):
    ob, a = place(L1, Z1, SL1[i], pid, h, tc, "L1g%d" % i, max_w=mw)
    if a:
        b1.append(a)
        log.append("  位%d %-22s x[%.3f,%.3f] z[%.3f,%.3f] W%.3f H%.3f  面%d"
                   % (i + 1, pid, a[0], a[1], a[4], a[5],
                      a[1] - a[0], a[5] - a[4], C.tri_count([ob])))

# ═══════════════════════════════════════════════════
# Board_2：3 个成品盆栽 + 1 花箱（箱内种 3 株蕨）
# ═══════════════════════════════════════════════════
L2, Z2 = 2, BOARD_TOP[2]
H2 = (BOARD_TOP[3] - 0.022) - Z2
log.append("")
log.append("Board_2 z=%.3f 净高 %.3f → 3 现成盆栽 + 1 花箱" % (Z2, H2))

POTS = [
    ("potted_plant_01", 0.300, 16500, 0.34),
    ("potted_plant_02", 0.300, 16500, 0.34),
    ("potted_plant_04", 0.290, 6100, 0.30),
]
SL2 = [BX0 + IW * (i + 0.5) / 4 for i in range(4)]
b2 = []
for i, (pid, h, tc, mw) in enumerate(POTS):
    ob, a = place(L2, Z2, SL2[i], pid, h, tc, "L2g%d" % i, max_w=mw)
    if a:
        b2.append(a)
        log.append("  位%d %-18s x[%.3f,%.3f] z[%.3f,%.3f] W%.3f H%.3f  面%d"
                   % (i + 1, pid, a[0], a[1], a[4], a[5],
                      a[1] - a[0], a[5] - a[4], C.tri_count([ob])))

# 位4：花箱 + 3 株蕨（箱内长植物，不是空箱）
boxns = "DC_L2g3_box"
bos = A.import_model("planter_box_02", col="C_Decor", target_height=0.110,
                     face="-Y", name_prefix=boxns)
if bos:
    box = bos[0]
    if C.tri_count([box]) > 11500:
        decimate(box, 11500)
    a = ab(box)
    if a[1] - a[0] > 0.38:
        sxy(box, 0.38 / (a[1] - a[0]), 0.38 / (a[1] - a[0]))
    to_pos(box, SL2[3], Y_MAX, Z2)
    bx = ab(box)
    if bx[2] < Y_MIN:
        shift(box, 0, Y_MIN - bx[2], 0)
        bx = ab(box)
    box_w = bx[1] - bx[0]
    box_h = bx[5] - bx[4]
    soil = bx[5] - box_h * 0.20          # 箱内土面
    ferns = []
    for fi, frac in enumerate((-0.30, 0.0, 0.30)):
        fn = A.import_model("fern_02", col="C_Decor", target_height=0.130,
                            face="-Y", name_prefix=boxns + "_fern%d" % fi)
        if not fn:
            continue
        fe = fn[0]
        if C.tri_count([fe]) > 6300:
            decimate(fe, 6300)
        fa = ab(fe)
        fw = fa[1] - fa[0]
        lim = box_w * 0.40
        if fw > lim:
            sxy(fe, lim / fw, lim / fw)
            fa = ab(fe)
        cx = SL2[3] + frac * box_w * 0.5
        shift(fe, cx - (fa[0] + fa[1]) / 2,
              ((bx[2] + bx[3]) / 2) - ((fa[2] + fa[3]) / 2),
              soil - fa[4])
        ferns.append(fe)
    g = gbox([box] + ferns)
    b2.append(g)
    log.append("  位4 %-18s + 3株蕨 x[%.3f,%.3f] z[%.3f,%.3f] W%.3f H%.3f"
               % ("planter_box_02", g[0], g[1], g[4], g[5],
                  g[1] - g[0], g[5] - g[4]))

# ═══════════════════════════════════════════════════
log.append("")
log.append("══ 自检 ══")
items = []
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    n = o.name or ""
    if not n.startswith(("DC_L1g", "DC_L2g", "DC_BookRow_", "DC_Shf_")):
        continue
    a = ab(o)
    if a[1] < X0 - 0.02 or a[0] > X1 + 0.02:
        continue
    if a[3] < Y_FRONT - 0.02 or a[2] > YB_BACK + 0.02:
        continue
    items.append((n, a))


def grp(name):
    m = re.search(r"(L[12]g[0-3])", name)
    return m.group(1) if m else name


bad = 0
for i in range(len(items)):
    for j in range(i + 1, len(items)):
        gi, gj = grp(items[i][0]), grp(items[j][0])
        if gi == gj and gi.startswith("L"):
            continue
        if hits(items[i][1], items[j][1], 0.0015):
            log.append("  ! 相交 %s ↔ %s" % (items[i][0], items[j][0]))
            bad += 1
log.append("书架区 %d 件  相交 %d 处 %s"
           % (len(items), bad, "OK" if bad == 0 else "FAIL"))

plates = [bpy.data.objects.get("DC_ShelfBoard_%d" % i) for i in range(6)]
plates += [bpy.data.objects.get("DC_ShelfSide_L"),
           bpy.data.objects.get("DC_ShelfSide_R"),
           bpy.data.objects.get("DC_ShelfBack")]
pb = [(p.name, ab(p)) for p in plates if p]
plb = 0
for n, a in items:
    for pn, pa in pb:
        if hits(a, pa, 0.0025):
            log.append("  ! %s ↔ %s" % (n, pn))
            plb += 1
log.append("与柜体相交 %d 处 %s" % (plb, "OK" if plb == 0 else "FAIL"))

oob = 0
for n, a in items:
    if (a[0] < X0 - 0.001 or a[1] > X1 + 0.001 or
            a[2] < Y_FRONT - 0.001 or a[3] > YB_BACK + 0.001 or a[5] > 2.051):
        log.append("  ! %s 越界" % n)
        oob += 1
log.append("越界 %d 处 %s" % (oob, "OK" if oob == 0 else "FAIL"))

log.append("")
log.append("  Board_1: %d 件  宽度 %s" % (len(b1), ", ".join("%.3f" % (g[1] - g[0]) for g in b1)))
log.append("  Board_2: %d 件  宽度 %s" % (len(b2), ", ".join("%.3f" % (g[1] - g[0]) for g in b2)))

# 用户原有内容
log.append("")
for nm in ("DC_Shf_tea_set_01", "DC_Shf_wine_bottles_01"):
    o = bpy.data.objects.get(nm)
    if o:
        a = ab(o)
        log.append("  %-24s 保留 OK  z[%.3f,%.3f]" % (nm, a[4], a[5]))
    else:
        log.append("  %-24s !! 丢失" % nm)

# 书
nb = len([o for o in bpy.data.objects if (o.name or "").startswith(("DC_BookRow_", "DC_Book_", "DC_BookFill_"))])
log.append("  Board_0 书本: %d 本" % nb)

# 水槽
snk = [o.name for o in bpy.data.objects if o.type == "MESH" and "sink" in (o.name or "").lower()]
log.append("  水槽对象: %s" % (snk if snk else "!! 未找到"))

COLS = ("C_Room", "C_Bar", "C_Display", "C_Seating", "C_Decor", "C_Outdoor", "C_Maid")
seen = set()
tot = 0
for cn in COLS:
    col = bpy.data.collections.get(cn)
    if not col:
        continue
    for o in col.all_objects:
        if o.type != "MESH" or o.name in seen:
            continue
        seen.add(o.name)
        o.data.calc_loop_triangles()
        tot += len(o.data.loop_triangles)
log.append("  全场景三角面 %d" % tot)

upd()
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
log.append("")
log.append("已保存 " + BLEND)
print("\n".join(log))
print("FIX_V16_DONE")
