# -*- coding: utf-8 -*-
"""qc_common.py — QC 体检公共内核（qc-inspector 专用，只读场景，不改几何/材质）

设计要点（踩过的坑，别改回去）：
1. **BVHTree.FromObject(ob, depsgraph) 不应用物体世界变换** —— 两个相隔 100m 的立方体
   仍然报 overlap=2。所以一律用 `BVHTree.FromPolygons(世界坐标顶点, 三角形, all_triangles=True)`
   自建世界空间 BVH。见 _probe 记录：run-mvhgvlz2xl1t。
2. 穿透深度是**代理指标**：取重叠三角形质心到对方面片的最近距离，用对方面法线判内外侧，
   取「落在对方内部的最大深度」。对薄壳/开放网格要结合 overlap_tris 一起看，报告里已注明。
3. 落地判据不是「min_z==0」这么简单：杯子放在桌上也是「被支撑」。所以分两级：
   floor_contact（贴地）/ support_contact（坐在别的物体顶面上）。两者都不可得 → FLOATING。
4. 所有判据数字来自 qc_rules.json，脚本内不硬编码阈值。

用法：
    blender -b --factory-startup -P qc_collide.py -- --blend scene/maid_cafe.blend --scope C_Seating
无头通道：
    blender_rt_headless(script_file=..., file=..., args="--scope C_Seating", engine="none")
"""

import bpy
import os
import sys
import json
import time
import math
import fnmatch
import hashlib
import argparse

import numpy as np
from mathutils.bvhtree import BVHTree


# ---------------------------------------------------------------- 基础路径 / 配置

def qc_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return r"E:\dsh\maid_cafe\blender\qc"


def project_root(rules=None):
    if rules and rules.get("root"):
        return rules["root"]
    return os.path.dirname(os.path.dirname(qc_dir()))


def load_rules(path=None):
    p = path or os.path.join(qc_dir(), "qc_rules.json")
    with open(p, "r", encoding="utf-8") as f:
        rules = json.load(f)
    rules["_rules_path"] = p
    rules["_rules_md5"] = md5_file(p)
    return rules


def md5_file(path, chunk=1 << 20):
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def ensure_dir(p):
    if p and not os.path.isdir(p):
        os.makedirs(p, exist_ok=True)
    return p


def _np_default(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def write_json(path, payload):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_np_default)
    return path


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ---------------------------------------------------------------- CLI

def cli_argv():
    """取 `--` 之后的参数（Blender 自身参数在前）。同时兼容 K.args。"""
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1:]
    try:
        k = globals().get("K")
        if k is not None and isinstance(getattr(k, "args", None), list):
            return list(k.args)
    except Exception:
        pass
    return []


def parse_args_lenient(ap, argv):
    """blender_rt_headless 会把 --outdir 之类的宿主参数追加到 `--` 之后，
    这里用 parse_known_args 宽容吸收，未知参数记进 extras 供 evidence 用。"""
    args, extras = ap.parse_known_args(argv)
    args.extras = [e for e in extras if e]
    return args


def base_parser(desc):
    ap = argparse.ArgumentParser(prog=desc, add_help=True)
    ap.add_argument("--blend", default=None, help="要体检的 .blend；省略则用当前已打开的")
    ap.add_argument("--rules", default=None, help="qc_rules.json 路径")
    ap.add_argument("--scope", default=None, help="集合名（C_Seating）或物体通配（TB_*）；可逗号分隔多个")
    ap.add_argument("--out", default=None, help="结果 JSON 路径；省略写 .scratch/qc/results/")
    ap.add_argument("--tag", default="", help="本轮标签，例如 v1")
    ap.add_argument("--limit", type=int, default=200, help="单类 finding 最多输出条数")
    ap.add_argument("--include-hidden", action="store_true", help="把 hide_viewport/hide_render 的对象也纳入")
    ap.add_argument("--quiet", action="store_true")
    return ap


def open_scene(args):
    """按 --blend 打开场景；返回 scene_info dict（含 md5/版本证据）。"""
    want = args.blend
    info = {"opened": False, "requested": want}
    cur = bpy.data.filepath
    if want:
        wp = want if os.path.isabs(want) else os.path.join(project_root(), want)
        if not os.path.isfile(wp):
            raise FileNotFoundError("blend 不存在: %s" % wp)
        if os.path.normcase(os.path.abspath(cur or "")) != os.path.normcase(os.path.abspath(wp)):
            bpy.ops.wm.open_mainfile(filepath=wp)
            info["opened"] = True
        info["path"] = wp
    info["path"] = info.get("path") or bpy.data.filepath or None
    if info["path"] and os.path.isfile(info["path"]):
        st = os.stat(info["path"])
        info["bytes"] = st.st_size
        info["mtime"] = int(st.st_mtime)
        info["md5"] = md5_file(info["path"])
        info["file"] = os.path.basename(info["path"])
    info["blender"] = bpy.app.version_string
    return info


# ---------------------------------------------------------------- 物体收集

class ObjInfo(object):
    __slots__ = ("name", "coll", "collections", "verts", "tris", "tri_count",
                 "vcount", "aabb_min", "aabb_max", "matrix_world", "hide_viewport",
                 "hide_render", "parent", "role", "reason", "kind")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @property
    def size(self):
        return self.aabb_max - self.aabb_min

    @property
    def center(self):
        return (self.aabb_max + self.aabb_min) * 0.5

    def as_dict(self):
        return {
            "name": self.name,
            "collection": self.coll,
            "collections": self.collections,
            "aabb": [r(self.aabb_min), r(self.aabb_max)],
            "tris": self.tri_count,
            "verts": self.vcount,
            "role": self.role,
            "kind": self.kind,
            "hidden": bool(self.hide_viewport or self.hide_render),
        }


def r(vec, nd=5):
    """np array / Vector -> 圆整 list（报告可读）"""
    try:
        return [round(float(x), nd) for x in vec]
    except Exception:
        return vec


def _enum_collections(ob):
    return [c.name for c in ob.users_collection]


def _primary_coll(ob, rules):
    colls = _enum_collections(ob)
    mods = rules.get("modules", {})
    for c in colls:
        if c in mods:
            return c
    return colls[0] if colls else ""


def collect_objects(rules, include_hidden=False):
    """收集所有可参与体检的 mesh 物体，提取世界坐标三角形 + AABB。

    返回 dict name -> ObjInfo。内存：50 万三角 ≈ 30MB，可接受。

    **取 matrix_world 前必须 view_layer.update()**（env-decor-v2 反馈，已验证成立）：
    若场景刚被脚本改动（运行时新建/移动对象），depsgraph 未刷新时 matrix_world 可能还是
    旧值、新建对象甚至仍是单位阵，会令 AABB 全落到局部坐标，穿透判定整体失效。
    """
    assert bpy.context.scene is not None
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    out = {}
    skipped = []
    for ob in list(bpy.data.objects):
        if ob.type != 'MESH':
            skipped.append({"name": ob.name, "reason": "type:" + ob.type})
            continue
        if not include_hidden and (ob.hide_viewport or ob.hide_render):
            skipped.append({"name": ob.name, "reason": "hidden"})
            continue
        ob_eval = ob.evaluated_get(deps)
        try:
            me = ob_eval.to_mesh()
        except Exception as e:
            skipped.append({"name": ob.name, "reason": "to_mesh_fail:" + str(e)})
            continue
        try:
            nv = len(me.vertices)
            npoly = len(me.polygons)
            if nv == 0 or npoly == 0:
                skipped.append({"name": ob.name, "reason": "empty_mesh"})
                continue
            co = np.empty(nv * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(nv, 3)
            me.calc_loop_triangles()
            nt = len(me.loop_triangles)
            tri = np.empty(nt * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("vertices", tri)
            tri = tri.reshape(nt, 3)
            mw = np.array(ob_eval.matrix_world, dtype=np.float64)
            wv = (co.astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]).astype(np.float64)
            amin = wv.min(axis=0)
            amax = wv.max(axis=0)
        finally:
            ob_eval.to_mesh_clear()
        out[ob.name] = ObjInfo(
            name=ob.name,
            coll=_primary_coll(ob, rules),
            collections=_enum_collections(ob),
            verts=wv,
            tris=tri,
            tri_count=int(nt),
            vcount=int(nv),
            aabb_min=amin,
            aabb_max=amax,
            matrix_world=mw,
            hide_viewport=bool(ob.hide_viewport),
            hide_render=bool(ob.hide_render),
            parent=ob.parent.name if ob.parent else None,
            role=None, reason=None, kind=None,
        )
    return out, skipped


def load_manifest_colliders(root, rules):
    """读 scene_manifest.json 的 colliders：提供 kind(solid/soft) 与模块声明的 AABB。"""
    p = os.path.join(root, "scene", "scene_manifest.json")
    man = read_json(p)
    if not man:
        return None, {}, {}
    kinds = {}
    detail = {}
    for c in man.get("colliders", []) or []:
        n = c.get("name")
        if not n:
            continue
        kinds[n] = c.get("kind", "solid")
        detail[n] = c
    return man, kinds, detail


# ---------------------------------------------------------------- 空间判据

def aabb_gap_axis(a_min, a_max, b_min, b_max):
    """逐轴间隙：正值=分离距离，负值=重叠长度。返回 (per_axis, max_sep, max_overlap)"""
    gap = np.maximum(b_min - a_max, a_min - b_max)
    return gap, float(gap.max()), float(-gap.max()) if gap.max() < 0 else 0.0


def inflated_overlap(a, b, inflate_m):
    return bool(np.all(a.aabb_min - inflate_m <= b.aabb_max) and np.all(b.aabb_min - inflate_m <= a.aabb_max))


def aabb_containment(inner_min, inner_max, outer_min, outer_max):
    """inner 的 AABB 体积有多少比例落在 outer 的 AABB 内（0..1）。"""
    size = np.maximum(inner_max - inner_min, 1e-9)
    vol_in = float(np.prod(size))
    if vol_in <= 0:
        return 0.0
    clip_min = np.maximum(inner_min, outer_min)
    clip_max = np.minimum(inner_max, outer_max)
    inter = np.maximum(clip_max - clip_min, 0.0)
    return float(np.prod(inter)) / vol_in


def footprint_fraction(inner_min, inner_max, outer_min, outer_max):
    """inner 的水平投影有多少比例被 outer 的水平投影覆盖（0..1）。"""
    sx = max(float(inner_max[0]) - float(inner_min[0]), 1e-9)
    sy = max(float(inner_max[1]) - float(inner_min[1]), 1e-9)
    area = sx * sy
    ix = max(0.0, min(float(inner_max[0]), float(outer_max[0])) - max(float(inner_min[0]), float(outer_min[0])))
    iy = max(0.0, min(float(inner_max[1]), float(outer_max[1])) - max(float(inner_min[1]), float(outer_min[1])))
    return (ix * iy) / area


def annotate_components(objects, rules):
    """标出「装配子部件」：嵌入同集合另一个更大物体、或整个立在它顶面上。

    为什么必须做（v3 实测教训，这是本工具最重要的一条口径）：
      场景里 1252 个 mesh，但**全部是根节点**（parent 全为 null），层级不携带装配信息。
      于是「落地物」判据必须靠几何判断「这是独立落地家具，还是它的一颗把手」。
      v1 用纯体积判据，漏掉「嵌在柜门里的小把手」（把手比柜门小、但没被整体包住），
      产出 138 条 floating 误报；v3 不修会到 206 条。

    两条判据：
      (a) 体积包含：物体 AABB ≥85% 落在同集合另一更大物体的 AABB 内 → 装着（螺丝在板里）
      (b) 足印覆盖：物体水平投影 ≥95% 落在另一物体的水平投影内、且底面高于其顶面附近
          → 立在它上面（糖罐盖在糖罐上、花瓶叶在花瓶上）
    父件选**体积最小**的合格者（最具体的父级），避免一律归到最大那个。

    返回 {子件名: {"component_of": 父件名, "by": "enclosed"|"on_top",
                   "volume_frac"|"footprint_frac": 比例}}
    """
    tol = rules["tolerances"]
    thr_vol = tol.get("component_containment_min", 0.85)
    thr_foot = tol.get("component_footprint_min", 0.95)
    thr_foot_over = tol.get("component_footprint_over", 0.85)
    attach_mm = tol.get("component_attach_mm", 3.0) / 1000.0
    by_coll = {}
    for n, o in objects.items():
        by_coll.setdefault(o.coll, []).append(o)

    def vol_of(o):
        return float(np.prod(np.maximum(o.aabb_max - o.aabb_min, 1e-9)))

    comp = {}
    for n, o in objects.items():
        vol = vol_of(o)
        best = None
        for c in by_coll.get(o.coll, []):
            if c.name == n:
                continue
            cvol = vol_of(c)
            if cvol <= vol * 1.02:
                continue                      # 父件必须更大
            vf = aabb_containment(o.aabb_min, o.aabb_max, c.aabb_min, c.aabb_max)
            ff = footprint_fraction(o.aabb_min, o.aabb_max, c.aabb_min, c.aabb_max)
            on_top = (float(o.aabb_min[2]) >= float(c.aabb_max[2]) - tol.get("rest_on_sink_mm", 20) / 1000.0)
            by = None
            if vf >= thr_vol:
                by = "enclosed"
            elif ff >= thr_foot and on_top:
                by = "on_top"
            elif ff >= thr_foot_over:
                # 水平投影几乎完全落在父件内 → 视为其构件/表面装饰。
                # v3 实测必须加这条：桌面垂布的 min_z=622mm（垂下来），椅子装饰球 min_z=424mm，
                # 它们并不「立在父件顶面上」，但显然是父件的一部分，不能各自判落地。
                by = "within_footprint"
            elif _attached(o, c, attach_mm):
                # 表面贴合：抽屉把手凸出柜门外、吧台边条贴在台面前沿 ——
                # 既不在父件内、投影也没被盖住，但确实是贴在它表面上的构件（v3 实测 8 条）。
                by = "attached"
            if by is None:
                continue
            order = ["enclosed", "on_top", "within_footprint", "attached"]
            score = (order.index(by), cvol)
            if best is None or score < best[0]:
                best = (score, c.name, by, round(vf, 4), round(ff, 4))
            if by == "enclosed":
                break                      # 已是最强判据，无需再试
        if best:
            comp[n] = {"component_of": best[1], "by": best[2],
                       "volume_frac": best[3], "footprint_frac": best[4]}
    return comp


def _attached(o, c, attach_m):
    """AABB 层面的「表面贴合」判定：两 AABB 的间隙 ≤ attach_mm（直接贴着）。
    等同于「小件的某个面紧贴大件的某个面」，是把手/边条/贴纸类构件的特征。"""
    gap = np.maximum(c.aabb_min - o.aabb_max, o.aabb_min - c.aabb_max)
    return float(gap.max()) <= attach_m


class Checker(object):
    def __init__(self, rules, objects, manifest=None, kinds=None, skipped=None,
                 colliders_detail=None):
        self.rules = rules
        self.root = project_root(rules)
        self.objects = objects
        self.manifest = manifest
        self.kinds = kinds or {}
        self.colliders_detail = colliders_detail or {}
        self.skipped = skipped or []
        self._bvh = {}
        self._role_cache = {}
        self.components = {}      # 由 annotate_components 填入
        self.containment_cache = {}

    # ---- BVH
    def bvh(self, name):
        b = self._bvh.get(name)
        if b is not None:
            return b
        info = self.objects[name]
        b = BVHTree.FromPolygons(
            info.verts.tolist(), info.tris.reshape(-1, 3).tolist(),
            all_triangles=True, epsilon=0.0,
        )
        self._bvh[name] = b
        return b

    # ---- 配对豁免
    def allow_pair(self, a, b):
        rules = self.rules["collide"]
        an, bn = a, b
        for ent in rules.get("allow_pairs", []):
            pat_a, pat_b, why = ent[0], ent[1], (ent[2] if len(ent) > 2 else "")
            if (fnmatch.fnmatchcase(an, pat_a) and fnmatch.fnmatchcase(bn, pat_b)) or \
               (fnmatch.fnmatchcase(an, pat_b) and fnmatch.fnmatchcase(bn, pat_a)):
                return why
        return None

    def same_coll_exempt(self, ia, ib):
        allow = self.rules["collide"].get("allow_same_collection", [])
        if ia.coll and ia.coll == ib.coll and ia.coll in allow:
            return "same_collection_exempt:" + ia.coll
        return None

    def kind_of(self, name):
        """kind 来源优先级：manifest(真声明) > fallback 通配(校准/无 manifest 时)"""
        if name in self.kinds:
            return self.kinds[name], "manifest"
        for pat in self.rules["collide"].get("soft_fallback_patterns", []):
            if fnmatch.fnmatchcase(name, pat):
                return "soft", "fallback"
        return None, None

    def soft_exempt(self, ia, ib):
        """§11.1 椅子插桌下：kind=soft 的豁免。

        **豁免范围受 qc_rules.collide.soft_exempt_against 限制**（默认 same_module）——
        v1 实测教训：manifest 把 MD_Body 声明 soft，若无条件豁免，女仆穿吧台
        BA_BarMain 会被无声放过，而 Lead 明确要求这条必须判。
        """
        c = self.rules["collide"]
        if not c.get("soft_kind_exempt", True):
            return None
        scope = c.get("soft_exempt_against", ["same_module"])
        for i, other in ((ia, ib), (ib, ia)):
            k, src = self.kind_of(i.name)
            if k != "soft":
                continue
            # 显式白名单：colliders[].allow_overlap_with 里点名放过
            allow_with = (self.colliders_detail.get(i.name) or {}).get("allow_overlap_with") or []
            if other.name in allow_with:
                return "soft_allow_overlap_with:%s" % i.name
            if "all" in scope:
                return "soft_kind:%s(%s)" % (i.name, src)
            if "same_module" in scope and i.coll and i.coll == other.coll:
                return "soft_kind:%s(%s,same_module)" % (i.name, src)
        return None

    def ignored(self, name):
        """该物体是否不参与干涉配对（按 ignore_patterns / ignore_collections）。"""
        rules = self.rules["collide"]
        for pat in rules.get("ignore_patterns", []):
            if fnmatch.fnmatchcase(name, pat):
                return True
        info = self.objects.get(name)
        if info and info.coll in rules.get("ignore_collections", []):
            return True
        return False

    def component_exempt(self, a, b):
        """同一装配体内的子件互穿是正常的，不判干涉。

        三层豁免（全部要求**同集合**，且 C_Maid 一律不豁免）：
          1. 父子关系：a 是 b 的子件，或 b 是 a 的子件（螺丝在板里）
          2. 同父兄弟：a、b 是同一父件的子件（两块拼板相接）
          3. **同族前缀**：a、b 共享命名前缀（TB_01_* / BA_CupRailRod* 等），
             是同一次装配出的结构件。v3 实测：TB_01 与 TB_01 有 13 对互穿、
             BA_CupRailRod 与 BA_Hook 有 12 对 —— 都是「挂钩穿过挂杆」这类设计意图。

        为什么 C_Maid 必须排除（v3 实测教训）：
          女仆 106 网格的体积包含关系会把「托盘」误判成「围裙的子件」，
          于是「托盘穿围裙 7.98mm」这条真问题就被无声放过 —— Lead 明确要求必须判。
        """
        if a not in self.objects or b not in self.objects:
            return None
        ia, ib = self.objects[a], self.objects[b]
        if ia.coll != ib.coll:
            return None
        if ia.coll in self.rules["collide"].get("component_exempt_collections_excluded",
                                                ["C_Maid"]):
            return None
        ca = self.components.get(a)
        cb = self.components.get(b)
        if ca and ca["component_of"] == b:
            return "component_in_parent:%s⊂%s" % (a, b)
        if cb and cb["component_of"] == a:
            return "component_in_parent:%s⊂%s" % (b, a)
        if ca and cb and ca["component_of"] == cb["component_of"]:
            return "sibling_components:%s" % ca["component_of"]
        # 3. 同族前缀
        ta, tb = self.assembly_tag(a), self.assembly_tag(b)
        if ta and ta == tb:
            return "same_assembly:%s" % ta
        return None

    _TAG_RE = None

    def assembly_tag(self, name):
        """取名字里的「装配标签」：TB_01_Vase_Leaf0 → TB_01；BA_CupRailRod → BA_CupRailRod。

        规则（qc_rules.collide.assembly_tag_rules 可覆盖）：
          名字按 _ 分段；若第 2 段是纯数字（实例编号），标签 = 前两段（TB_01 / CH_03）；
          否则标签 = None（不按族豁免，避免 BA_ 前缀把整个吧台当一族而掩盖真穿模）。
        """
        import re
        for rule in (self.rules["collide"].get("assembly_tag_rules") or []):
            pat, tmpl = rule[0], rule[1]
            if fnmatch.fnmatchcase(name, pat):
                m = re.match(tmpl, name)
                if m:
                    return m.group(1)
                return None
        parts = name.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return "%s_%s" % (parts[0], parts[1])
        return None

    # ---- 角色分类
    def classify(self, name):
        if name in self._role_cache:
            return self._role_cache[name]
        info = self.objects[name]
        rules = self.rules
        role, reason = None, ""
        for pat, rl, why in rules["classify"]["overrides"]:
            if fnmatch.fnmatchcase(name, pat):
                role, reason = rl, why
                break
        # 装配子部件（抽屉把手/柜门/杯架钩）：不是独立落地物，靠父件支撑
        if role is None and name in self.components:
            comp = self.components[name]
            frac = comp.get("volume_frac") if comp.get("by") == "enclosed" else comp.get("footprint_frac")
            role = "component"
            reason = "装配子件（%s）：%s %.0f%% 落在 %s" % (
                comp.get("by"), "体积" if comp.get("by") == "enclosed" else "足印",
                (frac or 0) * 100, comp.get("component_of"))
        if role is None:
            room = rules["room"]
            z0, z1 = room["z"]
            c = rules["classify"]
            wall_d = c["wall_side_detect_mm"] / 1000.0
            hang_d = c["hang_ceil_detect_mm"] / 1000.0
            mn, mx = info.aabb_min, info.aabb_max
            near_floor = abs(mn[2] - z0) <= 0.35
            near_ceil = (z1 - mx[2]) <= hang_d
            # 贴墙：物体某个面贴近内墙面
            near_wall = (abs(mn[0] - room["x"][0]) <= wall_d or abs(mx[0] - room["x"][1]) <= wall_d or
                         abs(mn[1] - room["y"][0]) <= wall_d or abs(mx[1] - room["y"][1]) <= wall_d)
            if near_ceil and mn[2] > 1.4:
                role, reason = "hang", "几何: 顶面距天花 %.0fmm" % ((z1 - mx[2]) * 1000)
            elif near_wall and mn[2] > 0.55 and not near_floor:
                role, reason = "wall", "几何: 侧面距墙 ≤%0.fmm 且悬空" % (wall_d * 1000)
            elif mn[2] <= 0.35:
                role, reason = "ground", "几何: 最低点 z=%.3f 近地" % mn[2]
            else:
                role, reason = "elevated", "几何: 最低点 z=%.3f 悬空(需支撑)" % mn[2]
        info.role = role
        info.reason = reason
        self._role_cache[name] = (role, reason)
        return role, reason

    # ---- 穿透
    def penetration(self, name_a, name_b, max_pairs=8000):
        """BVH 精确求交 + 穿透深度（双估计，取更稳健者）。

        为什么用两个估计（v3 实测教训）：
          · **质心法**（重叠三角形质心到对方面、且位于内侧的最大距离）：对细密网格
            严重高估 —— 托盘穿手报 14.8mm，而真实顶点距离只有 0.0098mm。
          · **顶点法**（顶点落在对方内部的最近距离最大值）：精确，但若两物体同尺寸
            同轴对齐，顶点恰好落在对方边界面上，dist=0 → 会**漏报**（校准 01_PEN 抓到）。
        判据：
          depth_vertex  = 顶点法（精确、偏低）
          depth_centroid= 质心法（粗、偏高）
          **判定用 depth_vertex，但当质心法 ≫ 顶点法（>3×且>5mm）时，
          取几何中道 depth_used = sqrt(depth_vertex * depth_centroid)**，
          并标记 depth_uncertain=True，报告里让 Lead 用 qc_pairs 复核。
        """
        ia, ib = self.objects[name_a], self.objects[name_b]
        ov = self.bvh(name_a).overlap(self.bvh(name_b))
        n = len(ov)
        gap, sep, ovl = aabb_gap_axis(ia.aabb_min, ia.aabb_max, ib.aabb_min, ib.aabb_max)
        res = {"overlap_tris": n, "depth_mm": 0.0, "depth_vertex_mm": 0.0,
               "depth_centroid_mm": 0.0, "depth_uncertain": False,
               "n_inside_a": 0, "n_inside_b": 0,
               "overlap_aabb_mm": r(-gap * 1000.0, 3), "depth_method": "vertex"}
        if n == 0:
            return res

        # 顶点法
        dv_ab, nin_a, ns_a = self._deepest_inside(self.bvh(name_b), ia.verts)
        dv_ba, nin_b, ns_b = self._deepest_inside(self.bvh(name_a), ib.verts)
        dv = max(dv_ab, dv_ba)

        # 质心法（仅作为交叉上界）
        idx_a = np.array(sorted({p[0] for p in ov}), dtype=np.int64)
        idx_b = np.array(sorted({p[1] for p in ov}), dtype=np.int64)
        dc_ab, _, _ = self._signed_inside(self.bvh(name_b), ia.verts, ia.tris, idx_a)
        dc_ba, _, _ = self._signed_inside(self.bvh(name_a), ib.verts, ib.tris, idx_b)
        dc = max(dc_ab, dc_ba)

        used, method, uncertain = dv, "vertex", False
        # 质心法**只做诊断**，绝不参与判定：
        # 远离表面时「最近点法线符号」判定会失效，实测可给出 3518mm 这种荒谬值
        # （BA_BarFootRail 整个嵌在大块板里）。真正的穿透深度不会超过 AABB 的 MTV。
        if dc > 3.0 * dv and dc > 0.005:
            uncertain = True
            method = "vertex(depth_centroid_disagrees)"
        # 上界约束：深度不可能超过两 AABB 在该轴上的重叠量
        mtv_m = max(0.0, -float(gap.max()))
        if mtv_m > 0.0:
            used = min(used, mtv_m)
        res.update(depth_mm=round(used * 1000.0, 4),
                   depth_vertex_mm=round(dv * 1000.0, 4),
                   depth_centroid_mm=round(dc * 1000.0, 4),
                   depth_uncertain=uncertain, depth_method=method,
                   aabb_mtv_mm=round(mtv_m * 1000.0, 4),
                   n_inside_a=nin_a, n_inside_b=nin_b, sampled=ns_a + ns_b)
        return res

    @staticmethod
    def _deepest_inside(bvh_target, verts, max_samples=20000):
        """顶点落到对方内部的最大最近距离（=穿透深度）。顶点采样不遍历三角形质量分布，
        故不会像质心法那样被细密网格放大。"""
        if len(verts) == 0:
            return 0.0, 0, 0
        step = max(1, len(verts) // max_samples)
        pts = verts[::step]
        maxd, nin = 0.0, 0
        for p in pts.tolist():
            loc, nor, i, dist = bvh_target.find_nearest(p)
            if loc is None:
                continue
            if (p[0] - loc[0]) * nor[0] + (p[1] - loc[1]) * nor[1] + (p[2] - loc[2]) * nor[2] < 0.0:
                nin += 1
                if dist > maxd:
                    maxd = dist
        return maxd, nin, len(pts)

    @staticmethod
    def _signed_inside(bvh_target, verts, tris, tri_idx, max_samples=4000):
        if tri_idx.size == 0:
            return 0.0, 0, 0
        step = max(1, tri_idx.size // max_samples)
        idx = tri_idx[::step]
        cent = verts[tris[idx]].mean(axis=1)
        maxd, nin = 0.0, 0
        for p in cent.tolist():
            loc, nor, i, dist = bvh_target.find_nearest(p)
            if loc is None:
                continue
            if (p[0] - loc[0]) * nor[0] + (p[1] - loc[1]) * nor[1] + (p[2] - loc[2]) * nor[2] < 0.0:
                nin += 1
                if dist > maxd:
                    maxd = dist
        return maxd, nin, len(cent)

    def surface_distance(self, name_a, name_b, max_samples=6000):
        """最小间距 / 穿透深度（双向顶点到面）。负值=穿透。"""
        ia, ib = self.objects[name_a], self.objects[name_b]
        ba, bb = self.bvh(name_a), self.bvh(name_b)
        gap, sep, ovl = aabb_gap_axis(ia.aabb_min, ia.aabb_max, ib.aabb_min, ib.aabb_max)
        if sep > 0.0:
            # 包围盒完全分离 → 间距至少 sep（精确值由顶点采样给出上界）
            pass
        dmin = float("inf")
        dirsign = 0.0
        for sa, sb in ((ia, ib), (ib, ia)):
            bvh_t = bb if sa is ia else ba
            v = sa.verts
            step = max(1, len(v) // max_samples)
            best = float("inf")
            for p in v[::step].tolist():
                loc, nor, i, dist = bvh_t.find_nearest(p)
                if loc is None:
                    continue
                s = (p[0] - loc[0]) * nor[0] + (p[1] - loc[1]) * nor[1] + (p[2] - loc[2]) * nor[2]
                signed = -dist if s < 0 else dist
                if abs(signed) < abs(best):
                    best = signed
            if abs(best) < abs(dmin):
                dmin = best
        return {"min_dist_mm": round(dmin * 1000.0, 3), "aabb_sep_mm": round(sep * 1000.0, 3)}


# ---------------------------------------------------------------- 支撑 / 落地 / 贴墙 / 天花

def footprint_overlap(a_min, a_max, b_min, b_max, tol=1e-4):
    return (min(a_max[0], b_max[0]) - max(a_min[0], b_min[0]) > -tol and
            min(a_max[1], b_max[1]) - max(a_min[1], b_min[1]) > -tol)


def find_supports(info, candidates, tol_m):
    """在 candidates 中找把 info 托住的物体：水平投影相交 且 对方顶面 ≈ info 底面。

    返回 [(name, dz)]，dz > 0 表示底面高于支撑顶面（悬空间隙）；
    dz < 0 表示底面陷进支撑物（rest_on_sink_tol 内也算被支撑，见 qc_rules 说明）。
    """
    hits = []
    for c in candidates:
        if c.name == info.name:
            continue
        dz = info.aabb_min[2] - c.aabb_max[2]
        if abs(dz) > tol_m:
            continue
        if not footprint_overlap(info.aabb_min, info.aabb_max, c.aabb_min, c.aabb_max):
            continue
        hits.append((c.name, dz))
    hits.sort(key=lambda t: abs(t[1]))
    return hits


def nearest_below(info, candidates, max_drop_m=3.0):
    """正下方最近物体的顶面（用于诊断 FLOATING 悬空高度）"""
    best = None
    for c in candidates:
        if c.name == info.name:
            continue
        if c.aabb_max[2] > info.aabb_min[2] + 1e-6:
            continue
        if not footprint_overlap(info.aabb_min, info.aabb_max, c.aabb_min, c.aabb_max):
            continue
        drop = info.aabb_min[2] - c.aabb_max[2]
        if drop > max_drop_m:
            continue
        if best is None or drop < best[1]:
            best = (c.name, drop)
    return best


def wall_proximity(info, room):
    """返回 (wall_name, gap_m)；gap 负=已插进墙体。"""
    x0, x1 = room["x"]
    y0, y1 = room["y"]
    mn, mx = info.aabb_min, info.aabb_max
    cands = [
        ("-x", mn[0] - x0),
        ("+x", x1 - mx[0]),
        ("-y", mn[1] - y0),
        ("+y", y1 - mx[1]),
    ]
    cands.sort(key=lambda t: abs(t[1]))
    return cands


def fmt_mm(v):
    return round(float(v) * 1000.0, 2)


# ---------------------------------------------------------------- finding 统一格式

SEV_ORDER = {"FAIL": 0, "WARN": 1, "INFO": 2}


def finding(fid, kind, severity, objs, module, owner, location, metrics, rule, note,
            evidence=None, scope=None):
    return {
        "id": fid,
        "kind": kind,
        "verdict": "FAIL" if severity == "FAIL" else ("待确认" if severity == "WARN" else "INFO"),
        "severity": severity,
        "objects": objs,
        "module": module,
        "owner": owner,
        "location": r(location, 4) if location is not None else None,
        "metrics": metrics,
        "rule": rule,
        "note": note,
        "evidence": evidence or {},
        "scope": scope,
    }


def attribute(objs, objects, rules, prefer_coll=None):
    """把 finding 归到责任模块/负责人（优先非 C_Room 的那个物体）"""
    mods = rules.get("modules", {})
    owners = rules.get("module_owner", {})
    best = None
    for n in objs:
        info = objects.get(n)
        if info is None:
            continue
        coll = info.coll
        if prefer_coll and coll == prefer_coll:
            best = coll
            break
        if coll != "C_Room" and best is None:
            best = coll
    if best is None and objs:
        info = objects.get(objs[0])
        best = info.coll if info else "?"
    m = mods.get(best, {}).get("module", "?") if best in mods else "?"
    return best, m, owners.get(m, "?")


def summarize(findings):
    by_sev = {"FAIL": 0, "WARN": 0, "INFO": 0}
    by_kind = {}
    by_module = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
        by_module.setdefault("%s/%s" % (f["module"], f["owner"]), 0)
        by_module["%s/%s" % (f["module"], f["owner"])] += 1
    return {"counts": {"total": len(findings), **by_sev},
            "by_kind": by_kind, "by_module": by_module}


def verdict_of(findings):
    if any(f["severity"] == "FAIL" for f in findings):
        return "FAIL"
    if any(f["severity"] == "WARN" for f in findings):
        return "待确认"
    return "PASS"


# ---------------------------------------------------------------- 结果落盘 + 回执

def default_out(rules, name):
    return os.path.join(project_root(rules), rules["report"]["results_dir"], name + ".json")


def default_calib_out(rules, name):
    """校准/自测结果**不能**和正式体检结果混在同一个目录 ——
    否则汇总脚本会把探针场景的体检数据当成真场景结论（自测时踩到过：
    light.json 来自自建 3 物体探针场景，却被写成正式 FAIL）。"""
    return os.path.join(project_root(rules), ".scratch", "qc", "calib_results", name + ".json")


def finish(result, out_path, quiet=False):
    """写 JSON 并回一条单行 HEADLESS 回执（供 blender_rt_headless resultJson 解析）"""
    result["written"] = write_json(out_path, result) if out_path else None
    if not quiet:
        print("HEADLESS " + json.dumps(result, ensure_ascii=False, default=_np_default))
    return result


def scope_match(name, scope, objects):
    """scope: 集合名 / 物体通配 / 逗号分隔多选"""
    if not scope:
        return True
    info = objects.get(name)
    for s in [x.strip() for x in scope.split(",") if x.strip()]:
        if info and info.coll == s:
            return True
        if fnmatch.fnmatchcase(name, s):
            return True
        if s in (info.collections if info else []):
            return True
    return False


def scene_snapshot(rules, objects, skipped, info):
    coll_counts = {}
    tri_total = 0
    for n, o in objects.items():
        tri_total += o.tri_count
        coll_counts[o.coll] = coll_counts.get(o.coll, 0) + 1
    return {
        "scene": info,
        # 场景指纹：report 用它校验「这份结果是不是这一版 .blend 跑出来的」，
        # 防止拿旧结果/探针场景结果冒充本轮结论。
        "scene_md5": (info or {}).get("md5"),
        "scene_file": (info or {}).get("file"),
        "blender": bpy.app.version_string,
        "rules_md5": rules.get("_rules_md5"),
        "objects_checked": len(objects),
        "objects_skipped": len(skipped),
        "tri_total": tri_total,
        "by_collection": dict(sorted(coll_counts.items())),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
