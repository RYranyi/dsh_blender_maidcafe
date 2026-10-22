import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'blender'))
import cprop as P

print('--- expected texture availability ---')
for k, (pid, res) in P.TEXTURES.items():
    row = []
    for mp in ('diff', 'nor', 'arm', 'rough'):
        p = P.tex_path(k, mp, res)
        row.append(mp + '=' + ('OK' if p else '-'))
    print('%-22s %-26s res=%-3s %s' % (k, pid, res, ' '.join(row)))

print()
print('--- files actually present in assets/tex ---')
files = sorted(os.listdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'tex')))
from collections import defaultdict
g = defaultdict(list)
for f in files:
    parts = f.rsplit('_', 2)
    g[parts[0] if len(parts) > 2 else f].append(f)
for k in sorted(g):
    print(k, '->', len(g[k]))
