"""
ccore.py — 女仆咖啡馆项目 · 几何/集合/材质/UV/预览 基础库（唯一底座）

设计原则
--------
1. 纯 bpy/bmesh，不联网、不依赖 numpy；所有随机数由调用方 seed。
2. 所有物体创建都显式指定集合（绝不依赖“当前激活集合”这种隐式状态）。
3. 每个几何都有可预测的原点：box/cyl 原点在几何中心（loc 指中心）；
   plane 原点在中心；lathe 原点在底面中心（z=0 为底）。
4. 提供自检渲染工具 selfcheck()，各模块 `python module.py` 即可出预览图。

用法
----
    import ccore as C
    ob = C.box("TB_01_top", (0.76,0.76,0.04), loc=(0,0,0.74),
                mat=M.get("MAT_Wood_Oak"), col="C_Seating", bevel=0.006)
"""
import bpy
import bmesh
import math
import os
import sys
import json
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else r"E:\dsh\maid_cafe\blender"
if HERE not in sys.path:
    sys.path.append(HERE)

TAU = math.tau
PI = math.pi
D2R = math.pi / 180.0
R2D = 180.0 / math.pi


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexc(h, alpha=1.0):
    """'#RRGGBB' → 线性 RGBA（Blender 输入期望线性值）。"""
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), alpha)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp3(a, b, t):
    return tuple(lerp(a[i], b[i], t) for i in range(3))


def clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def smoothstep(a, b, x):
    if b == a:
        return 0.0
    t = clamp01((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


# ══════════════════════════════════════════════════════════════════════
# 场景 / 集合
# ══════════════════════════════════════════════════════════════════════
def scene():
    return bpy.context.scene


def log(*a):
    print("[CCORE]", *a)


def deselect_all():
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    bpy.context.view_layer.objects.active = None


def ensure_collection(name, parent=None):
    """取或建集合；parent 为 None 时挂到场景根。"""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def wipe_collection(name):
    """删除集合内所有物体并移除集合（幂等）。"""
    col = bpy.data.collections.get(name)
    if col is None:
        return 0
    n = 0
    for ob in list(col.objects):
        try:
            bpy.data.objects.remove(ob, do_unlink=True)
            n += 1
        except Exception as e:  # pragma: no cover
            log("wipe failed", ob.name, e)
    for child in list(col.children):
        wipe_collection(child.name)
    for c in list(bpy.data.collections):
        if c.name == name:
            try:
                bpy.data.collections.remove(c)
            except Exception:
                pass
    return n


def link_to(ob, col):
    """把物体移入指定集合（从其它集合摘除，保留场景根）。"""
    col = ensure_collection(col) if isinstance(col, str) else col
    for c in list(ob.users_collection):
        if c != col:
            c.objects.unlink(ob)
    if ob.name not in col.objects:
        col.objects.link(ob)
    return ob


# ══════════════════════════════════════════════════════════════════════
# 通用辅助
# ══════════════════════════════════════════════════════════════════════
def _new_mesh_obj(name, bm, col, mat, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    # 容错：部分调用把材质当第 4 个位置参数传 box(name, size, loc, mat)，
    # 这里把「非旋转序列」的 rot 认成材质，避免 mathutils.Euler() 报错。
    if rot is not None and not isinstance(rot, (tuple, list, Vector, Euler, Matrix)):
        if mat is None:
            mat = rot
        rot = (0, 0, 0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.validate(verbose=False)
    ob = bpy.data.objects.new(name, me)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler(rot)
    ob.scale = Vector(scale)
    (ensure_collection(col) if isinstance(col, str) else col).objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    deselect_all()
    return ob


def _apply_scale(ob):
    """把 scale 烘进网格（避免导出时非均匀缩放导致法线问题）。"""
    s = tuple(ob.scale)
    if s == (1.0, 1.0, 1.0):
        return ob
    me = ob.data
    M = Matrix.Diagonal(Vector(s)).to_4x4()
    me.transform(M)
    ob.scale = (1.0, 1.0, 1.0)
    return ob


def _finish(ob, bevel=0.0, segs=2, shade=None, smooth_angle=None, uv_scale=None):
    if bevel and bevel > 0:
        bevel_mod(ob, bevel, segs)
        apply_mods(ob)
    if uv_scale:
        uv_world(ob, uv_scale)
    if shade == "smooth":
        shade_smooth(ob)
    elif shade == "auto":
        shade_auto(ob, smooth_angle if smooth_angle is not None else 40 * D2R)
    elif shade == "flat":
        shade_flat(ob)
    return ob


# ══════════════════════════════════════════════════════════════════════
# 基元
# ══════════════════════════════════════════════════════════════════════
def _split_extra(args, mat, rot):
    """兼容 box(name,size,loc,mat) 与 box(name,size,loc,rot) 两种位置参数写法。"""
    for a in args:
        if a is None:
            continue
        if isinstance(a, bpy.types.Material):
            if mat is None:
                mat = a
        elif isinstance(a, (tuple, list, Vector)) and len(a) == 3 and all(
                isinstance(v, (int, float)) for v in a):
            rot = tuple(a)
    return mat, rot


def box(name, size, loc=(0, 0, 0), *args, rot=(0, 0, 0), mat=None, col="C_Default",
        bevel=0.0, segs=2, shade="flat", uv_scale=None, **kw):
    """轴对齐盒；loc = 几何中心。第 4 个位置参数可以是材质或旋转（自动识别）。"""
    mat, rot = _split_extra(args, mat, rot)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    ob = _new_mesh_obj(name, bm, col, mat, loc, rot, (1, 1, 1))
    return _finish(ob, bevel, segs, shade, uv_scale=uv_scale)


def box_mm(name, size_mm, loc=(0, 0, 0), **kw):
    return box(name, tuple(v / 1000.0 for v in size_mm), loc, **kw)


def cyl(name, r=0.5, h=1.0, segs=24, r2=None, loc=(0, 0, 0), rot=(0, 0, 0),
        mat=None, col="C_Default", cap=True, bevel=0.0, bsegs=2,
        shade="auto", uv_scale=None, *args, **kw):
    """圆柱/圆台；原点在几何中心（z 方向居中）。r2 为顶半径。"""
    mat, rot = _split_extra(args, mat, rot)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=segs,
                          radius1=r, radius2=(r if r2 is None else r2), depth=h)
    ob = _new_mesh_obj(name, bm, col, mat, loc, rot, (1, 1, 1))
    return _finish(ob, bevel, bsegs, shade, uv_scale=uv_scale)


def cyl_base(name, r=0.5, h=1.0, **kw):
    """圆柱，原点在底面中心（很多家具腿用这个更顺手）。"""
    loc = kw.pop("loc", (0, 0, 0))
    ob = cyl(name, r=r, h=h, loc=(loc[0], loc[1], loc[2] + h / 2.0), **kw)
    return ob


def sphere(name, r=0.5, segs=24, rings=16, loc=(0, 0, 0), rot=(0, 0, 0),
           mat=None, col="C_Default", shade="smooth", scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r)
    ob = _new_mesh_obj(name, bm, col, mat, loc, rot, scale)
    _apply_scale(ob)
    if shade == "smooth":
        shade_smooth(ob)
    return ob


def plane(name, sx=1.0, sy=1.0, loc=(0, 0, 0), rot=(0, 0, 0), mat=None,
          col="C_Default", uv_scale=None, toward="+Z"):
    """矩形平面。toward 指定法线朝向（'+Z' 地板, '-Y' 朝街, '+Y' 朝后墙, '±X' 侧墙）。"""
    base_rot = {"+Z": (0, 0, 0), "-Z": (PI, 0, 0),
                "-Y": (PI / 2, 0, 0), "+Y": (PI / 2, 0, PI),
                "+X": (PI / 2, 0, -PI / 2), "-X": (PI / 2, 0, PI / 2)}[toward]
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bmesh.ops.scale(bm, vec=Vector((sx, sy, 1.0)), verts=bm.verts)
    ob = _new_mesh_obj(name, bm, col, mat, loc,
                       tuple(a + b for a, b in zip(rot, base_rot)), (1, 1, 1))
    if uv_scale:
        uv_world(ob, uv_scale)
    return ob


def quads(name, verts, faces, mat=None, col="C_Default", uv_scale=None,
          shade="auto", bevel=0.0):
    """任意 4 边面网格（verts 为世界/局部坐标列表）。"""
    bm = bmesh.new()
    bv = [bm.verts.new(Vector(v)) for v in verts]
    bm.verts.ensure_lookup_table()
    for f in faces:
        try:
            bm.faces.new([bv[i] for i in f])
        except ValueError:
            pass
    bm.normal_update()
    ob = _new_mesh_obj(name, bm, col, mat, (0, 0, 0), (0, 0, 0), (1, 1, 1))
    return _finish(ob, bevel, 2, shade, uv_scale=uv_scale)


def lathe(name, profile, segs=32, loc=(0, 0, 0), rot=(0, 0, 0), mat=None,
          col="C_Default", close_bottom=True, close_top=True, uv_scale=None,
          shade="auto"):
    """旋转体：profile = [(r, z), ...] 从底到顶（r=0 表示轴心点）。"""
    bm = bmesh.new()
    rings = []
    for (r, z) in profile:
        if r <= 1e-6:
            rings.append([bm.verts.new(Vector((0, 0, z)))])
        else:
            ring = []
            for i in range(segs):
                a = TAU * i / segs
                ring.append(bm.verts.new(Vector((r * math.cos(a), r * math.sin(a), z))))
            rings.append(ring)
    bm.verts.ensure_lookup_table()
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for i in range(segs):
                bm.faces.new((a[0], b[i], b[(i + 1) % segs]))
        elif len(b) == 1:
            for i in range(segs):
                bm.faces.new((a[i], b[0], a[(i + 1) % segs]))
        else:
            for i in range(segs):
                j = (i + 1) % segs
                bm.faces.new((a[i], a[j], b[j], b[i]))
    if close_bottom and len(rings[0]) > 1:
        bm.faces.new(list(reversed(rings[0])))
    if close_top and len(rings[-1]) > 1:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _new_mesh_obj(name, bm, col, mat, loc, rot, (1, 1, 1))
    return _finish(ob, 0, 2, shade, uv_scale=uv_scale)


def loft(name, sections, closed_ring=True, cap=True, mat=None, col="C_Default",
         shade="auto", uv_scale=None, bevel=0.0):
    """放样：sections = [[(x,y,z), ...], ...] 每节顶点数相同。"""
    bm = bmesh.new()
    rings = []
    for sec in sections:
        rings.append([bm.verts.new(Vector(p)) for p in sec])
    bm.verts.ensure_lookup_table()
    n = len(rings[0])
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        lim = n if closed_ring else n - 1
        for i in range(lim):
            j = (i + 1) % n
            try:
                bm.faces.new((a[i], a[j], b[j], b[i]))
            except ValueError:
                pass
    if cap and closed_ring:
        try:
            bm.faces.new(list(reversed(rings[0])))
            bm.faces.new(rings[-1])
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _new_mesh_obj(name, bm, col, mat, (0, 0, 0), (0, 0, 0), (1, 1, 1))
    return _finish(ob, bevel, 2, shade, uv_scale=uv_scale)


def poly_prism(name, poly, thickness, axis="Z", loc=(0, 0, 0), rot=(0, 0, 0),
               mat=None, col="C_Default", bevel=0.0, segs=2, shade="flat",
               uv_scale=None):
    """2D 多边形沿 axis 拉伸 thickness。poly 在 XY 平面（axis=Z 时）。"""
    bm = bmesh.new()
    vs = [bm.verts.new(Vector((p[0], p[1], 0))) for p in poly]
    f = bm.faces.new(vs)
    bmesh.ops.recalc_face_normals(bm, faces=[f])
    bmesh.ops.solidify(bm, geom=[f], thickness=thickness)
    if axis == "Z":
        pass
    elif axis == "Y":
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                         matrix=Matrix.Rotation(-PI / 2, 3, "X"))
    elif axis == "X":
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                         matrix=Matrix.Rotation(PI / 2, 3, "Y"))
    ob = _new_mesh_obj(name, bm, col, mat, loc, rot, (1, 1, 1))
    return _finish(ob, bevel, segs, shade, uv_scale=uv_scale)


def tube_along(name, pts, radius=0.01, segs=10, mat=None, col="C_Default",
               shade="smooth", caps=True):
    """沿折线扫圆截面（管子/线缆/扶手）。用曲线 + 转网格实现圆角平滑。"""
    cu = bpy.data.curves.new(name + "_cu", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]
        bp.co = Vector(p)
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    cu.bevel_depth = radius
    cu.bevel_resolution = max(1, segs // 4)
    cu.resolution_u = 6
    cu.use_fill_caps = caps
    ob = bpy.data.objects.new(name, cu)
    (ensure_collection(col) if isinstance(col, str) else col).objects.link(ob)
    join_convert_mesh(ob)
    if mat:
        ob.data.materials.append(mat)
    return ob


def ring_tube(name, R=1.0, r=0.02, segs=48, rsegs=10, loc=(0, 0, 0),
              rot=(0, 0, 0), mat=None, col="C_Default"):
    """圆环（环面）。"""
    bm = bmesh.new()
    rings = []
    for i in range(segs):
        a = TAU * i / segs
        cx, cy = R * math.cos(a), R * math.sin(a)
        ring = []
        for j in range(rsegs):
            b = TAU * j / rsegs
            ring.append(bm.verts.new(Vector((cx + r * math.cos(b) * math.cos(a),
                                             cy + r * math.cos(b) * math.sin(a),
                                             r * math.sin(b)))))
        rings.append(ring)
    for i in range(segs):
        a, b = rings[i], rings[(i + 1) % segs]
        for j in range(rsegs):
            k = (j + 1) % rsegs
            bm.faces.new((a[j], b[j], b[k], a[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _new_mesh_obj(name, bm, col, mat, loc, rot, (1, 1, 1))
    shade_smooth(ob)
    return ob


# ══════════════════════════════════════════════════════════════════════
# 修改器 / 着色 / UV
# ══════════════════════════════════════════════════════════════════════
def bevel_mod(ob, width=0.005, segments=2, limit="ANGLE", angle=30 * D2R, harden=True):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = limit
    if limit == "ANGLE":
        try:
            m.angle_limit = angle
        except Exception:
            pass
    m.harden_normals = harden
    return m


def apply_mods(ob):
    if not ob.modifiers:
        return ob
    deselect_all()
    bpy.context.view_layer.objects.active = ob
    for m in list(ob.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except Exception as e:
            log("modifier_apply failed", ob.name, m.name, e)
            ob.modifiers.remove(m)
    return ob


def join_convert_mesh(ob):
    """曲线等非网格 → 网格（不 join 别的）。"""
    if ob.type == "MESH":
        return ob
    deselect_all()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.convert(target="MESH")
    return bpy.context.view_layer.objects.active


def shade_smooth(ob):
    me = ob.data
    for p in me.polygons:
        p.use_smooth = True
    return ob


def shade_flat(ob):
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


def shade_auto(ob, angle=40 * D2R):
    """自动平滑（Blender 4.1+ 用 Smooth by Angle 修改器 / 5.x 运算符）。"""
    me = ob.data
    try:
        bpy.ops.object.shade_auto_smooth(angle=angle)
        return ob
    except Exception:
        pass
    try:
        m = ob.modifiers.new("SmoothByAngle", "NODES")
        ng = bpy.data.node_groups.get("Smooth by Angle")
        if ng:
            m.node_group = ng
        return ob
    except Exception:
        return shade_smooth(ob)


def remesh_voxel(ob, voxel=0.01, adaptivity=0.0):
    m = ob.modifiers.new("Remesh", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = voxel
    m.adaptivity = adaptivity
    apply_mods(ob)
    return ob


def boolean(ob, cutter, op="DIFFERENCE", solver="EXACT", apply=True, keep_cutter=False):
    m = ob.modifiers.new("Bool", "BOOLEAN")
    m.operation = op
    m.object = cutter
    try:
        m.solver = solver
    except Exception:
        pass
    if apply:
        apply_mods(ob)
        if not keep_cutter:
            bpy.data.objects.remove(cutter, do_unlink=True)
    return ob


def decimate(ob, ratio=0.5, use_collapse=True):
    """减面。带安全回滚：若减完反而变多（退化/非流形网格常见），恢复原网格。"""
    t0 = tri_count(ob)
    backup = ob.data.copy()
    m = ob.modifiers.new("Decimate", "DECIMATE")
    if use_collapse:
        m.decimate_type = "COLLAPSE"
        m.ratio = ratio
    else:
        m.decimate_type = "DISSOLVE"
        m.angle_limit = 5 * D2R
    apply_mods(ob)
    t1 = tri_count(ob)
    if t1 >= t0:
        old = ob.data
        ob.data = backup
        bpy.data.meshes.remove(old)
        log("decimate made it worse (%d -> %d), reverted %s" % (t0, t1, ob.name))
    else:
        bpy.data.meshes.remove(backup)
    return ob


def uv_world(ob, scale=1.0, use_world=True):
    """按世界坐标 + 面法线主轴生成平铺 UV（贴图不会拉伸，跨物体连续）。"""
    me = ob.data
    if not getattr(me, "polygons", None):
        return ob
    if not me.uv_layers:
        try:
            me.uv_layers.new(name="UVMap")
        except Exception:
            return ob
    uvl = me.uv_layers.active
    if uvl is None:
        return ob
    M = ob.matrix_world if use_world else Matrix.Identity(4)
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            v = M @ me.vertices[me.loops[li].vertex_index].co
            if ax == 2:      # 顶/底：XY
                u, w = v.x, v.y
            elif ax == 1:    # 前后：XZ
                u, w = v.x, v.z
            else:            # 左右：YZ
                u, w = v.y, v.z
            uvl.data[li].uv = (u / scale, w / scale)
    return ob


def uv_planar(ob, scale=1.0, axis="Y"):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            if axis == "Y":
                uvl.data[li].uv = (v.x / scale, v.z / scale)
            elif axis == "Z":
                uvl.data[li].uv = (v.x / scale, v.y / scale)
            else:
                uvl.data[li].uv = (v.y / scale, v.z / scale)
    return ob


# ══════════════════════════════════════════════════════════════════════
# 材质
# ══════════════════════════════════════════════════════════════════════
def mat_assign(ob, mat, slot=0):
    me = ob.data
    if mat is None:
        return ob
    if len(me.materials) == 0:
        me.materials.append(mat)
    else:
        me.materials[slot] = mat
    return ob


def mat_add(ob, mat):
    ob.data.materials.append(mat)
    return len(ob.data.materials) - 1


def set_face_material(ob, mat_index, pred):
    """按面中心谓词设置材质索引。"""
    for p in ob.data.polygons:
        c = p.center
        if pred(c):
            p.material_index = mat_index
    return ob


# ══════════════════════════════════════════════════════════════════════
# 变换 / 度量
# ══════════════════════════════════════════════════════════════════════
def join(obs, name, col=None):
    obs = [o for o in obs if o is not None]
    if not obs:
        return None
    deselect_all()
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name + "_mesh"
    if col:
        link_to(ob, col)
    return ob


def duplicate(ob, name=None, offset=(0, 0, 0), rot=None):
    nb = ob.copy()
    nb.data = ob.data.copy()
    nb.name = name or (ob.name + "_dup")
    for c in ob.users_collection:
        c.objects.link(nb)
    nb.location = ob.location + Vector(offset)
    if rot is not None:
        nb.rotation_euler = Euler(rot)
    return nb


def mirrored_x(ob, name=None):
    """X 镜像副本（几何镜像，法线已修）。"""
    nb = ob.copy()
    nb.data = ob.data.copy()
    nb.name = name or (ob.name + "_mir")
    for c in ob.users_collection:
        c.objects.link(nb)
    me = nb.data
    for v in me.vertices:
        v.co.x = -v.co.x
    me.flip_normals()
    nb.location = Vector((-ob.location.x, ob.location.y, ob.location.z))
    nb.rotation_euler = Euler((ob.rotation_euler.x, -ob.rotation_euler.y, -ob.rotation_euler.z))
    return nb


def apply_transforms(obs, loc=True, rot=True, scale=True):
    deselect_all()
    obs = [o for o in obs if o and o.type == "MESH"]
    for o in obs:
        o.select_set(True)
    if obs:
        bpy.context.view_layer.objects.active = obs[0]
        bpy.ops.object.transform_apply(location=loc, rotation=rot, scale=scale)
        deselect_all()
    return obs


def apply_all_transforms_recursive(root_collections):
    n = 0
    for cn in root_collections:
        col = bpy.data.collections.get(cn)
        if not col:
            continue
        for ob in list(col.all_objects):
            if ob.type == "MESH":
                ob.select_set(True)
                n += 1
    if n:
        bpy.context.view_layer.objects.active = [o for o in bpy.context.selected_objects if o.type == "MESH"][0]
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        deselect_all()
    return n


def world_aabb(obs):
    """世界包围盒：[min, max]；obs 可为单个物体或列表。"""
    if not isinstance(obs, (list, tuple)):
        obs = [obs]
    mn = [1e9, 1e9, 1e9]
    mx = [-1e9, -1e9, -1e9]
    for ob in obs:
        if ob is None or ob.type != "MESH":
            continue
        for corner in ob.bound_box:
            p = ob.matrix_world @ Vector(corner)
            for i in range(3):
                mn[i] = min(mn[i], p[i])
                mx[i] = max(mx[i], p[i])
    return [round(v, 5) for v in mn], [round(v, 5) for v in mx]


def tri_count(obs):
    if not isinstance(obs, (list, tuple)):
        obs = [obs]
    t = 0
    for ob in obs:
        if ob is None or ob.type != "MESH":
            continue
        me = ob.data
        me.calc_loop_triangles()
        t += len(me.loop_triangles)
    return t


def snap_floor(ob, floor_z=0.0):
    """把物体最低点对齐到 floor_z（不改 X/Y）。"""
    mn, mx = world_aabb(ob)
    dz = floor_z - mn[2]
    ob.location.z += dz
    return ob


def set_origin(ob, point=(0, 0, 0)):
    """把原点移到世界点 point（保持几何位置）。"""
    p = Vector(point)
    delta = ob.matrix_world.translation - p
    me = ob.data
    me.transform(Matrix.Translation(delta))
    ob.location = p
    return ob


def scale_about(ob, s, pivot=(0, 0, 0)):
    p = Vector(pivot)
    me = ob.data
    me.transform(Matrix.Translation(-p) @ Matrix.Diagonal(Vector((s, s, s))).to_4x4() @ Matrix.Translation(p))
    return ob


def rotate_about(ob, pivot, axis="Z", angle_deg=0.0):
    """绕世界空间 pivot 旋转（轴为 'X'/'Y'/'Z'），保持几何/变换一致。"""
    R = Matrix.Rotation(angle_deg * D2R, 3, axis)
    piv = Vector(pivot)
    ob.data.transform(R.to_4x4())
    ob.location = piv + R @ (Vector(ob.location) - piv)
    return ob


# ══════════════════════════════════════════════════════════════════════
# 预览渲染（模块自检用）
# ══════════════════════════════════════════════════════════════════════
def _ensure_world(strength=1.0, color=(0.55, 0.55, 0.58)):
    w = bpy.data.worlds.get("QC_World") or bpy.data.worlds.new("QC_World")
    scene().world = w
    try:
        w.use_nodes = True
        bg = w.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[0].default_value = (*color, 1.0)
            bg.inputs[1].default_value = strength
    except Exception:
        pass
    return w


def _add_area(name, loc, look_at, power=200.0, size=2.0, color=(1, 0.95, 0.88)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    ob.location = Vector(loc)
    d = Vector(look_at) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scene().collection.objects.link(ob)
    return ob


def render_camera(name, loc, look_at, lens=50, ortho=None):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    ob = bpy.data.objects.new(name, cd)
    ob.location = Vector(loc)
    d = Vector(look_at) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scene().collection.objects.link(ob)
    return ob


def setup_engine(engine="eevee", samples=32, res=(800, 600)):
    r = scene().render
    r.resolution_x, r.resolution_y = res
    r.resolution_percentage = 100
    r.image_settings.file_format = "PNG"
    try:
        r.film_transparent = False
    except Exception:
        pass
    sc = scene()
    eng = engine.lower()
    if eng == "eevee":
        for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                sc.render.engine = name
                break
            except Exception:
                continue
        try:
            sc.eevee.taa_render_samples = samples
        except Exception:
            pass
        try:
            sc.eevee.use_raytracing = True
        except Exception:
            pass
    elif eng == "cycles":
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples
        sc.cycles.device = "GPU"
        try:
            sc.cycles.use_denoising = True
        except Exception:
            pass
    else:
        sc.render.engine = "BLENDER_WORKBENCH"
    try:
        sc.view_settings.view_transform = "AgX"
        try:
            sc.view_settings.look = "AgX - Medium High Contrast"
        except Exception:
            pass
    except Exception:
        try:
            sc.view_settings.view_transform = "Filmic"
        except Exception:
            pass
    return sc


def selfcheck(module_name, objects, outdir=r"E:\dsh\maid_cafe\renders\modules",
              views=None, res=(880, 660), samples=24, engine="eevee",
              ground=True, extra_setup=None):
    """模块自检：三点光 + 相机 + 渲染多视角，返回图片路径列表。

    views: [{"name":"persp","from":(x,y,z),"look":(x,y,z),"lens":50}, ...]
           缺省自动取 3/4 视角。
    """
    os.makedirs(outdir, exist_ok=True)
    mn, mx = world_aabb(objects)
    if mn[0] > 1e8:
        log("selfcheck: no objects")
        return []
    ctr = [(mn[i] + mx[i]) / 2 for i in range(3)]
    size = max(mx[i] - mn[i] for i in range(3)) or 1.0
    _ensure_world(0.55)
    # 三点光：功率按场景尺度自适应，并做上限钳制的“摄影棚”强度
    def _pw(base, k):
        return min(4000.0, max(60.0, base * k))
    _add_area("QC_Key", (ctr[0] + size * 1.2, ctr[1] - size * 1.4, ctr[2] + size * 1.6),
              ctr, power=_pw(size * size, 55), size=size * 1.2, color=(1.0, 0.94, 0.86))
    _add_area("QC_Fill", (ctr[0] - size * 1.6, ctr[1] - size * 0.9, ctr[2] + size * 0.8),
              ctr, power=_pw(size * size, 16), size=size * 1.8, color=(0.85, 0.9, 1.0))
    _add_area("QC_Rim", (ctr[0] - size * 0.4, ctr[1] + size * 1.8, ctr[2] + size * 1.4),
              ctr, power=_pw(size * size, 30), size=size * 1.0, color=(1.0, 0.9, 0.8))
    if ground:
        plane("QC_Ground", sx=size * 6, sy=size * 6,
              loc=(ctr[0], ctr[1], mn[2] - 0.001), mat=None, col="C_QC")
    setup_engine(engine, samples, res)
    if views is None:
        d = size * 1.85
        views = [
            {"name": "persp", "from": (ctr[0] + d * 0.9, ctr[1] - d * 1.15, ctr[2] + d * 0.65),
             "look": ctr},
            {"name": "front", "from": (ctr[0], ctr[1] - d * 1.55, ctr[2] + size * 0.25),
             "look": ctr},
            {"name": "side", "from": (ctr[0] + d * 1.5, ctr[1], ctr[2] + size * 0.3), "look": ctr},
            {"name": "top", "from": (ctr[0] + d * 0.35, ctr[1] - d * 0.45, ctr[2] + d * 1.3),
             "look": ctr},
        ]
    if extra_setup:
        extra_setup()
    paths = []
    cam = bpy.data.objects.get("QC_Cam")
    for v in views:
        c = cam or render_camera("QC_Cam", v.get("from"), v.get("look", ctr),
                                 v.get("lens", 50), v.get("ortho"))
        c.location = Vector(v["from"])
        c.rotation_euler = (Vector(v.get("look", ctr)) - Vector(v["from"])).to_track_quat("-Z", "Y").to_euler()
        if v.get("lens"):
            c.data.lens = v["lens"]
        scene().camera = c
        p = os.path.join(outdir, f"{module_name}_{v['name']}.png")
        scene().render.filepath = p
        try:
            bpy.ops.render.render(write_still=True)
            paths.append(p)
            log("rendered", p)
        except Exception as e:
            log("render failed", p, e)
    return paths


# ══════════════════════════════════════════════════════════════════════
# 文件
# ══════════════════════════════════════════════════════════════════════
def save_blend(path, compress=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=path, compress=compress)
        log("saved", path, os.path.getsize(path))
    except Exception as e:
        log("save failed", path, e)
    return path


def load_blend(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    return bpy.context.scene


def purge_orphans():
    for _ in range(3):
        try:
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        except Exception:
            break


def stats(collections=None):
    """集合三角面统计。"""
    out = {}
    for cn in (collections or [c.name for c in bpy.data.collections]):
        col = bpy.data.collections.get(cn)
        if not col:
            continue
        t, n = 0, 0
        for ob in col.all_objects:
            if ob.type == "MESH":
                t += tri_count(ob)
                n += 1
        out[cn] = {"tris": t, "objects": n}
    return out
