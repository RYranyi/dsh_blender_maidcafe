"""Generate a few missing fabric textures (gingham / lace / velvet) with Pillow.

Outputs to assets/tex/generated/ as tileable PNGs.
"""
import os
import math
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "tex", "generated")
os.makedirs(OUT, exist_ok=True)
S = 512


def gingham(path, c_light=(255, 246, 238), c_mid=(240, 196, 208), c_dark=(214, 150, 168), n=16):
    """经典 gingham 格子（3 色叠加），可平铺。"""
    img = Image.new("RGB", (S, S), c_light)
    d = ImageDraw.Draw(img)
    cell = S // n
    for j in range(n):
        for i in range(n):
            # 行列叠加出 3 级色
            a = (i % 2 == 0)
            b = (j % 2 == 0)
            col = c_light
            if a and b:
                col = c_dark
            elif a or b:
                col = c_mid
            d.rectangle([i * cell, j * cell, (i + 1) * cell - 1, (j + 1) * cell - 1], fill=col)
    # 织物质感：轻微噪声 + 模糊
    px = img.load()
    import random
    random.seed(7)
    for y in range(S):
        for x in range(S):
            r, g, b = px[x, y]
            k = random.randint(-6, 6)
            px[x, y] = (max(0, min(255, r + k)), max(0, min(255, g + k)), max(0, min(255, b + k)))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img.save(path)
    print("wrote", path, img.size)


def lace(path, n=8):
    """白蕾丝：底色奶白 + 网格 + 花朵点，可平铺（不透明）。"""
    img = Image.new("RGB", (S, S), (252, 250, 245))
    d = ImageDraw.Draw(img)
    cell = S // n
    # 网格线
    for i in range(n + 1):
        x = i * cell
        d.line([(x, 0), (x, S)], fill=(238, 232, 222), width=2)
        d.line([(0, x), (S, x)], fill=(238, 232, 222), width=2)
    # 每格小花 + 镂空小圆
    for j in range(n):
        for i in range(n):
            cx = i * cell + cell // 2
            cy = j * cell + cell // 2
            for k in range(6):
                a = math.tau * k / 6
                px = cx + math.cos(a) * cell * 0.18
                py = cy + math.sin(a) * cell * 0.18
                r = cell * 0.075
                d.ellipse([px - r, py - r, px + r, py + r], outline=(231, 223, 211), width=2)
            d.ellipse([cx - cell * 0.05, cy - cell * 0.05, cx + cell * 0.05, cy + cell * 0.05],
                      fill=(255, 255, 255), outline=(232, 224, 212))
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img.save(path)
    print("wrote", path, img.size)


def velvet(path):
    """暖玫瑰色丝绒：细密纵向纹理 + 柔和噪点。"""
    img = Image.new("RGB", (S, S), (232, 197, 178))
    px = img.load()
    import random
    random.seed(11)
    for y in range(S):
        for x in range(S):
            # 纵向条纹 + 噪声
            stripe = math.sin(x * math.tau / 6.0) * 6.0
            n = random.uniform(-7, 7)
            r = 232 + stripe + n
            g = 197 + stripe * 0.75 + n * 0.8
            b = 178 + stripe * 0.6 + n * 0.7
            px[x, y] = (max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    img.save(path)
    print("wrote", path, img.size)


def wood_light(path):
    """浅色木纹（近景家具用，比下载的 1k 更细腻的浅橡木）。"""
    import random
    random.seed(23)
    img = Image.new("RGB", (S, S), (196, 158, 116))
    px = img.load()
    # 生成几条正弦木纹带
    phase = [random.uniform(0, math.tau) for _ in range(4)]
    for y in range(S):
        for x in range(S):
            v = 0.0
            for k, ph in enumerate(phase):
                v += math.sin(x * math.tau / (90 + k * 37) + ph + y * 0.004) / (k + 1.5)
            n = random.uniform(-4, 4)
            r = 196 + v * 14 + n
            g = 158 + v * 11 + n
            b = 116 + v * 8 + n
            px[x, y] = (max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    img.save(path)
    print("wrote", path, img.size)


if __name__ == "__main__":
    gingham(os.path.join(OUT, "fabric_gingham_pink.png"))
    lace(os.path.join(OUT, "fabric_lace_white.png"))
    velvet(os.path.join(OUT, "fabric_velvet_warm.png"))
    wood_light(os.path.join(OUT, "wood_light_oak.png"))
    print("DONE")
