# -*- coding: utf-8 -*-
"""体检前置检查：场景是否比模块源码旧（防「拿旧场景出结论」）。

v5 实测教训（furn-modeler 指出）：我体检的 blend mtime=12:17:50，而 cseating.py 修订
在 12:35 —— 场景比代码旧 18 分钟，导致 5 条结论里有 4 条是过期数据。
本脚本把这条检查固化，作为 qc_collide 的前置门：场景旧于任一已改动模块源码时，
报告必须在顶部标注「场景可能过期」，且结论降级为「待确认」。

用法（在 qc_collide 里以 --check-fresh 调用，或独立跑）：
  python _check_fresh.py       # 用纯 python 跑，不需要 Blender
"""
import os
import json
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCENE = os.path.join(ROOT, 'scene', 'maid_cafe.blend')
MODULES = ['cprop.py', 'ccore.py', 'cmat.py', 'croom.py', 'cbar.py', 'cdisplay.py',
           'cseating.py', 'cdecor.py', 'coutdoor.py', 'clight.py', 'cmaid.py',
           'cbuild.py', 'cassets.py']


def mtime(p):
    try:
        return os.stat(p).st_mtime
    except OSError:
        return None


def fmt(t):
    return datetime.datetime.fromtimestamp(t).strftime('%H:%M:%S') if t else '-'


def main():
    st = mtime(SCENE)
    if st is None:
        print('SCENE MISSING: %s' % SCENE)
        return 1
    rows = []
    newest_src, newest_name = 0, None
    for m in MODULES:
        t = mtime(os.path.join(ROOT, 'blender', m))
        if t is None:
            continue
        if t > newest_src:
            newest_src, newest_name = t, m
        rows.append((m, t, t - st))
    print('scene: %s  mtime=%s' % (os.path.basename(SCENE), fmt(st)))
    print('newest module src: %s  mtime=%s' % (newest_name, fmt(newest_src)))
    print('')
    print('%-14s %-10s %s' % ('module', 'mtime', 'vs scene'))
    stale = []
    for m, t, d in sorted(rows, key=lambda r: -r[1]):
        flag = ''
        if d > 0:
            flag = '  ⚠ 比场景新 %.1f 分钟' % (d / 60.0)
            stale.append(m)
        print('%-14s %-10s %+.1fs%s' % (m, fmt(t), d, flag))
    print('')
    if stale:
        print('RESULT: STALE — 场景比这些源码旧：%s' % ', '.join(stale))
        print('  → 体检结论可能对应旧几何，应重建场景后重测。')
    else:
        print('RESULT: FRESH — 场景不旧于任何模块源码。')
    out = {
        'scene_mtime': st,
        'scene_time': fmt(st),
        'newest_src': newest_name,
        'newest_src_time': fmt(newest_src),
        'stale_modules': stale,
        'verdict': 'STALE' if stale else 'FRESH',
        'checked_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(os.path.join(ROOT, '.scratch', 'qc', 'scene_freshness.json'), 'w',
              encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
