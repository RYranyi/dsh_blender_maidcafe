"""
fix_shelf_v7.py —— 最终版：只改二层 + 三层植物 + 底部书排 + 水槽加深

严格保持用户已做的内容：
  · Board_3 茶具 DC_Shf_tea_set_01   —— 不碰
  · Board_4 酒瓶 DC_Shf_wine_bottles_01 —— 不碰
  · Board_2 五个位置（用户摆好的 X）—— 位置保留，只换新资源
  · 柜顶留空 —— 不碰

改动：
  ① Board_0：两排 93 本 → 单排铺满（用户要求「只要一排」）
  ② Board_1：空的 → 可爱咖啡馆装饰（小黄鸭/猫雕像/铜鲸鱼/蜡烛台/装饰书/水壶）
  ③ Board_2：换 5 个首次使用的植物（不重复）
  ④ 水槽：0.171 m → 0.40 m

碰撞检测：所有新摆放物件之间、与层板/侧板/背板，全部做真实 AABB 相交检查。
"""
import bpy
import sys
import os
import random
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


def scale_xyz(ob, sx, sy, sz, pivot="base"):
    a = ab(ob)
    if pivot == "base":
        c = Vector(((a[0] + a[1]) / 2, (a[2] + a[3]) / 2, a[4]))
    else:
        c = Vector(((a[0] + a[1]) / 2, (a[2] + a[3]) / 2, (a[4] + a[5]) / 2))
    T = (Matrix.Translation(c) @ Matrix.Diagonal(Vector((sx, sy, sz)).to_4d())
         @ Matrix.Translation(-c))
    ob.matrix_world = T @ ob.matrix_world
    upd()


def to_aabb_center_bottom(ob, cx, y_back, z_base):
    a = ab(ob)
    ob.location.x += cx - (a[0] + a[1]) / 2
    ob.location.y += y_back - a[3]
    ob.location.z += z_base - a[4]
    upd()
    return ab(ob)


def hits(a, b, eps=0.002):
    """严格 AABB 相交（eps 容差内不算相交）。"""
    return (a[0] < b[1] - eps and a[1] > b[0] + eps and
            a[2] < b[3] - eps and a[3] > b[2] + eps and
            a[4] < b[5] - eps and a[5] > b[4] + eps)


# ══════════════════════════════════════════════════════════
# 柜体参数
# ══════════════════════════════════════════════════════════
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
SIDE_L_IN = BX0
SIDE_R_IN = BX1
log.append("柜内 X[%.3f,%.3f] W=%.3f  Y[%.3f,%.3f] D=%.3f"
           % (BX0, BX1, BX1 - BX0, Y_FRONT, BACK_FRONT, BACK_FRONT - Y_FRONT))
log.append("层板顶面: " + ", ".join("%.3f" % z for z in BOARD_TOP))


# ══════════════════════════════════════════════════════════
# ① Board_0：两排 → 单排铺满
# ══════════════════════════════════════════════════════════
books = [o for o in bpy.data.objects
         if (o.name or "").startswith("DC_BookFill_") or
            (o.name or "").startswith("DC_Book_")]
log.append("")
log.append("Board_0 原有书 %d 本" % len(books))

protos = []
for o in books:
    a = ab(o)
    protos.append((o, a[1] - a[0], a[3] - a[2], a[5] - a[4]))
# 只留 3 个原对象做样板，其余删掉
keep = protos[:3]
del_list = [p[0] for p in protos[3:]]
for o in del_list:
    try:
        bpy.data.objects.remove(o, do_unlink=True)
    except Exception:
        pass
log.append("  保留 3 本做样板，删除 %d 本，改为单排排布" % len(del_list))

random.seed(20261022)
ZB = BOARD_TOP[0]
ZBOT = ZB
BOOK_GAP_FROM_BACK = 0.070          # 书背与书架背板的间隙
ROW_Y_BACK = BACK_FRONT - BOOK_GAP_FROM_BACK   # 单排，后侧离背板留空
GAP = 0.0035
xcur = BX0 + 0.008
made = 0
idx = 0
while xcur < BX1 - 0.020 and made < 200:
    src, wt, dt, ht = keep[idx % len(keep)]
    # 复制（linked data 省内存）
    dup = src.copy()
    dup.data = src.data
    dup.name = "DC_BookRow_%03d" % made
    for col in list(src.users_collection):
        col.objects.link(dup)
    w = max(0.020, min(0.040, wt * random.uniform(0.92, 1.18)))
    d = random.uniform(0.150, 0.185)
    h = random.uniform(0.150, 0.230)
    a = ab(dup)
    scale_xyz(dup, w / max(a[1] - a[0], 1e-6),
              d / max(a[3] - a[2], 1e-6),
              h / max(a[5] - a[4], 1e-6))
    a = ab(dup)
    dup.location.x += xcur - a[0]
    dup.location.y += ROW_Y_BACK - a[3]
    dup.location.z += ZBOT - a[4]
    upd()
    xcur += w + GAP
    made += 1
    idx += 1
# 删掉那 3 个样板
for p in keep:
    try:
        bpy.data.objects.remove(p[0], do_unlink=True)
    except Exception:
        pass
log.append("  单排 %d 本，占用 x[%.3f,%.3f]"
           % (made, BX0 + 0.008, xcur - GAP))
log.append("  书背 y=%.3f，背板前 y=%.3f → 间隙 %.3f m"
           % (ROW_Y_BACK, BACK_FRONT, BOOK_GAP_FROM_BACK))


# ══════════════════════════════════════════════════════════
# ② Board_1：可爱咖啡馆装饰（顺序排布 + 碰撞检测）
# ══════════════════════════════════════════════════════════
L1 = 1
L1_Z = BOARD_TOP[L1]
CAP1 = (BOARD_TOP[L1 + 1] - 0.022) - L1_Z - 0.010

# 可爱 + 咖啡馆氛围，全部首次使用，互不重复
L1_ORDER = [
    ("rubber_duck_toy",       0.105, 200),   # 小黄鸭（可爱）
    ("concrete_cat_statue",   0.165, 180),   # 猫雕像（可爱）
    ("decorative_book_set_01", 0.195, 180),  # 装饰书
    ("brass_candleholders",   0.130, 175),   # 黄铜烛台
    ("bronze_whale_statue",   0.115, 190),   # 铜鲸鱼（可爱）
    ("vintage_electric_kettle", 0.175, 160), # 复古电水壶（咖啡馆）
    ("pot_enamel_01",         0.140, 185),   # 搪瓷壶
    ("jug_01",                0.155, 170),   # 陶壶
]
GAP1 = 0.026
log.append("")
log.append("Board_1 z=%.3f 净高上限 %.3f" % (L1_Z, CAP1))
x = BX0 + 0.012
l1 = []
placed_bounds = []
for pid, hgt, rz in L1_ORDER:
    nm = "DC_L1_" + pid
    objs = A.import_model(pid, col="C_Decor", target_height=hgt,
                          face="-Y", name_prefix=nm)
    if not objs:
        log.append("  WARN 导入失败 " + pid)
        continue
    ob = objs[0]
    a = ab(ob)
    w = a[1] - a[0]
    if a[5] - a[4] > CAP1:
        s = CAP1 / (a[5] - a[4])
        scale_xyz(ob, s, s, s)
        a = ab(ob)
        w = a[1] - a[0]
    # 太宽（如书立、烛台组）就横向压缩
    MAXW = 0.30
    if w > MAXW:
        scale_xyz(ob, MAXW / w, 1.0, 1.0)
        a = ab(ob)
        w = a[1] - a[0]
    if x + w > BX1 - 0.010:
        log.append("  %-28s 放不下（x=%.3f w=%.3f），跳过" % (pid, x, w))
        for o in objs:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
        continue
    cx = x + w / 2
    a = to_aabb_center_bottom(ob, cx, BACK_FRONT - 0.014, L1_Z)
    # Y 前后夹紧（不能超出柜前）
    if a[2] < Y_FRONT + 0.016:
        ob.location.y += (Y_FRONT + 0.016) - a[2]
        upd()
        a = ab(ob)
    # 碰撞检测：与已放的比
    conflict = False
    for pb in placed_bounds:
        if hits(a, pb):
            conflict = True
            break
    if conflict:
        log.append("  %-28s 与已放物件重叠，跳过" % pid)
        for o in objs:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
        continue
    placed_bounds.append(a)
    l1.append((nm, a))
    log.append("  %-28s x[%.3f,%.3f] y[%.3f,%.3f] z[%.3f,%.3f] W%.3f H%.3f"
               % (nm, a[0], a[1], a[2], a[3], a[4], a[5],
                  a[1] - a[0], a[5] - a[4]))
    x = a[1] + GAP1
log.append("  Board_1 共 %d 件，占用 x[%.3f,%.3f] / 上限 %.3f"
           % (len(l1), l1[0][1][0] if l1 else 0, x - GAP1, BX1))


# ══════════════════════════════════════════════════════════
# ③ Board_2：换 5 个新植物（位置用用户摆好的 X）
# ══════════════════════════════════════════════════════════
L2 = 2
L2_Z = BOARD_TOP[L2]
CAP2 = (BOARD_TOP[L2 + 1] - 0.022) - L2_Z - 0.010
USER_X = [-3.7465, -3.4695, -3.2380, -2.8680, -2.5405]

# 删除旧的 5 盆（pot_a/b/c/d + potted_plant_01）——这些是用户已摆好的位置
OLD_PLANTS = ["DC_Shf_pot_a", "DC_Shf_pot_b", "DC_Shf_pot_c",
              "DC_Shf_pot_d", "DC_Shf_potted_plant_01"]
for nm in OLD_PLANTS:
    o = bpy.data.objects.get(nm)
    if o:
        bpy.data.objects.remove(o, do_unlink=True)
log.append("")
log.append("Board_2 z=%.3f 净高上限 %.3f，5 个位置换新植物" % (L2_Z, CAP2))

# 5 个首次使用的植物（都不与 Board_1、Board_3、Board_4 重复）
L2_ITEMS = [
    ("potted_plant_02",        0.235),
    ("calathea_orbifolia_01",  0.225),
    ("fern_02",                0.195),
    ("searsia_lucida",         0.215),
    ("planter_pot_clay",       0.180),
]
SLOT = 0.245
l2 = []
for i, (pid, hgt) in enumerate(L2_ITEMS):
    cx = USER_X[i]
    nm = "DC_L2_" + pid
    objs = A.import_model(pid, col="C_Decor", target_height=hgt,
                          face="-Y", name_prefix=nm)
    if not objs:
        log.append("  WARN 导入失败 " + pid)
        continue
    ob = objs[0]
    a = ab(ob)
    w, d, h = a[1] - a[0], a[3] - a[2], a[5] - a[4]
    # 宽高比大（贴地植物）→ 横向压缩，保留高度
    sx = min(1.0, SLOT / max(w, 1e-6))
    sy = min(1.0, 0.30 / max(d, 1e-6))
    if sx < 0.999 or sy < 0.999:
        scale_xyz(ob, sx, sy, 1.0)
        a = ab(ob)
    # 高度超限就整体压
    if a[5] - a[4] > CAP2:
        s = CAP2 / (a[5] - a[4])
        scale_xyz(ob, 1.0, 1.0, s)
        a = ab(ob)
    a = to_aabb_center_bottom(ob, cx, BACK_FRONT - 0.014, L2_Z)
    if a[2] < Y_FRONT + 0.016:
        ob.location.y += (Y_FRONT + 0.016) - a[2]
        upd()
        a = ab(ob)
    l2.append((nm, a))
    log.append("  %-30s x[%.3f,%.3f] y[%.3f,%.3f] z[%.3f,%.3f] W%.3f D%.3f H%.3f"
               % (nm, a[0], a[1], a[2], a[3], a[4], a[5],
                  a[1] - a[0], a[3] - a[2], a[5] - a[4]))

# ══════════════════════════════════════════════════════════
# ④ 水槽加深
# ══════════════════════════════════════════════════════════
log.append("")
bpy.context.view_layer.update()


def make_box(name, x0v, x1v, y0v, y1v, z0v, z1v, col="C_Bar"):
    me = bpy.data.meshes.new(name + "_m")
    vs = [(x0v, y0v, z0v), (x1v, y0v, z0v), (x1v, y1v, z0v), (x0v, y1v, z0v),
          (x0v, y0v, z1v), (x1v, y0v, z1v), (x1v, y1v, z1v), (x0v, y1v, z1v)]
    fs = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
          (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me.from_pydata(vs, [], fs)
    me.update()
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.data.collections.get(col, bpy.context.scene.collection).objects.link(ob)
    return ob


def apply_bool(target, cutter):
    C.deselect_all()
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    m = target.modifiers.new("BOOL", "BOOLEAN")
    m.operation = "DIFFERENCE"
    m.object = cutter
    m.solver = "EXACT"
    deps = bpy.context.evaluated_depsgraph_get()
    ev = target.evaluated_get(deps)
    nme = bpy.data.meshes.new_from_object(ev)
    target.modifiers.remove(m)
    target.data = nme
    upd()
    return target


sink = bpy.data.objects.get("BA_SinkBasin.001") or bpy.data.objects.get("BA_SinkBasin")
top = bpy.data.objects.get("BA_BackTop")
body = bpy.data.objects.get("BA_BackBar_Body")
if sink and top:
    sa = ab(sink)
    ta = ab(top)
    ba = ab(body) if body else None
    RIM_Z = ta[5]
    WALL = 0.022
    FLOOR = 0.020
    MAX_D = RIM_Z - ((ba[4] if ba else 0.08) + 0.020)
    TARGET_D = min(0.400, MAX_D)
    BOT_Z = RIM_Z - TARGET_D
    ox0, ox1 = sa[0], sa[1]
    oy0, oy1 = sa[2], sa[3]
    ix0, ix1 = ox0 + WALL, ox1 - WALL
    iy0, iy1 = oy0 + WALL, oy1 - WALL
    iz0 = BOT_Z + FLOOR
    log.append("水槽原深 %.3f m → 新深 %.3f m（盆底 z=%.3f，柜体底 z=%.3f）"
               % (sa[5] - sa[4], TARGET_D, BOT_Z, ba[4] if ba else 0.08))

    # 台面开孔（确认）
    mw = top.matrix_world
    cov_area = 0.0
    for poly in top.data.polygons:
        n = (mw.to_3x3() @ poly.normal).normalized()
        c = mw @ poly.center
        if (n.z > 0.5 and abs(c.z - RIM_Z) < 0.004 and
                ox0 - 0.005 <= c.x <= ox1 + 0.005 and
                oy0 - 0.005 <= c.y <= oy1 + 0.005):
            cov_area += poly.area
    if cov_area > 0.02:
        cut = make_box("_cut", ox0 + 0.004, ox1 - 0.004,
                       oy0 + 0.004, oy1 - 0.004, ta[4] - 0.03, ta[5] + 0.03)
        apply_bool(top, cut)
        bpy.data.objects.remove(cut, do_unlink=True)
        log.append("  台面已重新开孔")
    else:
        log.append("  台面已有孔，跳过")

    mats = [s.material for s in sink.material_slots if s.material]
    outer = make_box("_newbasin", ox0, ox1, oy0, oy1, BOT_Z, RIM_Z + 0.0005)
    inner = make_box("_newin", ix0, ix1, iy0, iy1, iz0, RIM_Z + 0.06)
    apply_bool(outer, inner)
    bpy.data.objects.remove(inner, do_unlink=True)
    for mm in mats:
        outer.data.materials.append(mm)
    if not mats and sink.data.materials:
        for mm in sink.data.materials:
            if mm:
                outer.data.materials.append(mm)
    for poly in outer.data.polygons:
        poly.use_smooth = False
    sink.name = "_OLD_SINK"
    outer.name = "BA_SinkBasin"
    outer.data.name = "BA_SinkBasin_mesh"
    bpy.data.objects.remove(sink, do_unlink=True)
    upd()
    na = ab(outer)
    log.append("  新水槽: x[%.3f,%.3f] y[%.3f,%.3f] z[%.3f,%.3f] 内腔深 %.3f m"
               % (na[0], na[1], na[2], na[3], na[4], na[5], RIM_Z - iz0))


# ══════════════════════════════════════════════════════════
# 全局自检
# ══════════════════════════════════════════════════════════
log.append("")
log.append("══ 全局自检 ══")

# 收集书架区所有物件，做两两相交检查（排除「层板本身」和上下层）
SHELF_AREA = (X0 - 0.02, X1 + 0.02, Y_FRONT - 0.02, YB_BACK + 0.02,
              -0.02, 2.06)
items = []
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    n = o.name or ""
    if not (n.startswith("DC_L1_") or n.startswith("DC_L2_") or
            n.startswith("DC_BookRow_") or n.startswith("DC_BookFill_") or
            n.startswith("DC_Book_") or n.startswith("DC_Shf_")):
        continue
    a = ab(o)
    if a[1] < SHELF_AREA[0] or a[0] > SHELF_AREA[1]:
        continue
    if a[3] < SHELF_AREA[2] or a[2] > SHELF_AREA[3]:
        continue
    items.append((n, a))

log.append("书架区物件 %d 个" % len(items))

bad = 0
for i in range(len(items)):
    for j in range(i + 1, len(items)):
        if hits(items[i][1], items[j][1], 0.0015):
            log.append("  ⚠ 相交: %s ↔ %s" % (items[i][0], items[j][0]))
            bad += 1
log.append("两两相交: %s" % ("无 ✓" if bad == 0 else "%d 处" % bad))

# 越界检查
oob = 0
for n, a in items:
    if a[0] < X0 - 0.001 or a[1] > X1 + 0.001:
        log.append("  ⚠ %s X越界" % n)
        oob += 1
    if a[2] < Y_FRONT - 0.001 or a[3] > YB_BACK + 0.001:
        log.append("  ⚠ %s Y越界 (y0=%.3f, y1=%.3f, 柜前%.3f)"
                   % (n, a[2], a[3], Y_FRONT))
        oob += 1
    if a[5] > 2.05 + 0.001:
        log.append("  ⚠ %s 超柜顶" % n)
        oob += 1
log.append("越界: %s" % ("无 ✓" if oob == 0 else "%d 处" % oob))

# 与层板/侧板/背板相交
plates = [bpy.data.objects.get("DC_ShelfBoard_%d" % i) for i in range(6)]
plates += [bpy.data.objects.get("DC_ShelfSide_L"),
           bpy.data.objects.get("DC_ShelfSide_R"),
           bpy.data.objects.get("DC_ShelfBack")]
plates = [p for p in plates if p]
plate_bounds = [(p.name, ab(p)) for p in plates]
pl_bad = 0
for n, a in items:
    for pn, pa in plate_bounds:
        if hits(a, pa, 0.0025):
            log.append("  ⚠ %s 与 %s 相交" % (n, pn))
            pl_bad += 1
log.append("与层板/侧板/背板相交: %s" % ("无 ✓" if pl_bad == 0 else "%d 处" % pl_bad))

# 用户原有内容仍在
log.append("")
for nm in ("DC_Shf_tea_set_01", "DC_Shf_wine_bottles_01"):
    o = bpy.data.objects.get(nm)
    log.append("  %s : %s" % (nm, "存在 ✓" if o else "⚠ 丢失"))

upd()
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
log.append("")
log.append("已保存 " + BLEND)
print("\n".join(log))
print("FIX_SHELF_V7_DONE")
