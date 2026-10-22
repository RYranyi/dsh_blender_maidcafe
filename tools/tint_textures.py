"""Tint existing PBR diffuse maps to match the cafe palette (keeps original detail)."""
import os
import sys
from PIL import Image, ImageEnhance

TEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "tex")
OUT = os.path.join(TEX, "tinted")
os.makedirs(OUT, exist_ok=True)


def tint(src, dst, mul=(1.0, 1.0, 1.0), sat=1.0, bright=1.0, contrast=1.0):
    im = Image.open(src).convert("RGB")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            r = min(255, int(r * mul[0]))
            g = min(255, int(g * mul[1]))
            b = min(255, int(b * mul[2]))
            px[x, y] = (r, g, b)
    if sat != 1.0:
        im = ImageEnhance.Color(im).enhance(sat)
    if bright != 1.0:
        im = ImageEnhance.Brightness(im).enhance(bright)
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    im.save(dst, quality=92)
    print("wrote", dst, im.size)


def find(pid, mp="diff", res="1k"):
    for cand in (f"{pid}_{mp}_{res}.jpg", f"{pid}_{mp}_2k.jpg", f"{pid}_nor_gl_{res}.jpg"):
        p = os.path.join(TEX, cand)
        if os.path.exists(p):
            return p
    hits = [f for f in os.listdir(TEX) if f.startswith(f"{pid}_") and mp in f]
    return os.path.join(TEX, hits[0]) if hits else None


if __name__ == "__main__":
    # 奶油墙：把白灰泥染成 #F0E4CE 的暖奶油色
    p = find("white_stucco", "diff")
    if p:
        tint(p, os.path.join(OUT, "wall_cream_diff.jpg"), mul=(1.0, 0.953, 0.878),
             sat=1.05, bright=1.02)
    # 墙裙：把木纹染成更浅的暖橡木
    p = find("wood_table", "diff")
    if p:
        tint(p, os.path.join(OUT, "wood_light_diff.jpg"), mul=(1.10, 1.04, 0.96),
             sat=0.92, bright=1.04, contrast=0.98)
    # 吧台木：略深、更红润的胡桃
    p = find("wood_table", "diff")
    if p:
        tint(p, os.path.join(OUT, "wood_walnut_diff.jpg"), mul=(0.82, 0.72, 0.66),
             sat=1.05, bright=0.98)
    # 地面：更暖更亮一点的人字拼
    p = find("herringbone_parquet", "diff", "2k")
    if p:
        tint(p, os.path.join(OUT, "floor_warm_diff.jpg"), mul=(1.08, 1.02, 0.94),
             sat=1.0, bright=1.02)
    print("DONE")
