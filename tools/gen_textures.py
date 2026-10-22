"""gen_textures.py — 女仆咖啡馆文字/标签/插画贴图生成器（Pillow + Windows 日文字体）

用法：
    python gen_textures.py                 # 生成全部
    python gen_textures.py --only menu_blackboard,chalk_open
    python gen_textures.py --out <目录>     # 默认 assets/tex/generated
    python gen_textures.py --preview        # 同时把缩略图写到 .scratch 方便肉眼检查

产物（全部 PNG，≤2048²）：
    menu_blackboard.png   手写风黑板菜单（日文+英文 14 行）
    noren_welcome.png     门帘「いらっしゃいませ」（暖白字 / 藏青底）
    sign_cafe.png         门口招牌「Maid Café めいど」
    menu_card.png         桌面菜单立牌（A6 竖版）
    label_beans.png       咖啡豆罐标签
    label_tea.png         茶叶罐标签
    picture_art_01..03.png 相框内插画：花 / 猫 / 咖啡杯
    chalk_open.png        「OPEN」挂牌（粉笔字）
    window_drops.png      窗玻璃雨滴（RGBA 透明，网页雨天叠加用）

脚本可重复运行；同样的随机种子 → 同样的输出。
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 基础设置

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "tex", "generated")
FONT_DIR = r"C:\Windows\Fonts"

FONT_FILES = {
    "jp_m": os.path.join(FONT_DIR, "YuGothM.ttc"),   # Yu Gothic Medium
    "jp_b": os.path.join(FONT_DIR, "YuGothB.ttc"),   # Yu Gothic Bold
    "jp_r": os.path.join(FONT_DIR, "YuGothR.ttc"),   # Yu Gothic Regular
    "jp_g": os.path.join(FONT_DIR, "msgothic.ttc"),  # MS Gothic
    "serif": os.path.join(FONT_DIR, "georgia.ttf"),
    "serif_b": os.path.join(FONT_DIR, "georgiab.ttf"),
    "sans": os.path.join(FONT_DIR, "segoeui.ttf"),
    "sans_b": os.path.join(FONT_DIR, "segoeuib.ttf"),
    "hand": os.path.join(FONT_DIR, "segoepr.ttf"),   # Segoe Print — 手写感拉丁
    "hand_b": os.path.join(FONT_DIR, "segoeprb.ttf"),
    "mono": os.path.join(FONT_DIR, "consola.ttf"),
}

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    """按角色取字体；缺失则逐级回退到任何可用的日文字体。"""
    key = (role, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    order = [role, "jp_b", "jp_m", "jp_r", "jp_g", "serif", "sans"]
    last_err = None
    for r in order:
        path = FONT_FILES.get(r)
        if not path or not os.path.exists(path):
            continue
        try:
            ft = ImageFont.truetype(path, size, index=0)
            _FONT_CACHE[key] = ft
            return ft
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise RuntimeError(f"no usable font for role={role}: {last_err}")


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


# ---------------------------------------------------------------- 图像工具


def linear_gradient(size, top, bottom) -> Image.Image:
    w, h = size
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    t = np.repeat(t, w, axis=1)
    a = np.asarray(top, dtype=np.float32)
    b = np.asarray(bottom, dtype=np.float32)
    rgb = a[None, None, :] * (1 - t[..., None]) + b[None, None, :] * t[..., None]
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def add_grain(img: Image.Image, amount: float = 6.0, seed: int = 0, mono: bool = True) -> Image.Image:
    """胶片/纸张颗粒。amount 为 ±亮度。"""
    r = rng(seed)
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    if mono:
        n = r.normal(0.0, amount, (arr.shape[0], arr.shape[1], 1)).astype(np.float32)
    else:
        n = r.normal(0.0, amount, arr.shape).astype(np.float32)
    arr = np.clip(arr + n, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def add_vignette(img: Image.Image, strength: float = 0.35) -> Image.Image:
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    d = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / math.sqrt(2)
    mask = np.clip(1.0 - strength * (d ** 2.2), 0.0, 1.0)[..., None]
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) * mask
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def paper_texture(img: Image.Image, seed: int = 1, strength: float = 1.0) -> Image.Image:
    """纸/布纤维：低频斑 + 高频颗粒。"""
    w, h = img.size
    r = rng(seed)
    low = r.normal(0, 1, (max(2, h // 24), max(2, w // 24))).astype(np.float32)
    low = np.array(Image.fromarray(low, "F").resize((w, h), Image.BICUBIC))
    low = (low - low.mean()) / (low.std() + 1e-6) * 3.2 * strength
    high = r.normal(0, 4.0 * strength, (h, w)).astype(np.float32)
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) + (low + high)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def rotated_ellipse(draw: ImageDraw.ImageDraw, cx, cy, rx, ry, angle_deg, fill):
    """画任意旋转角度的椭圆（多边形近似，抗锯齿靠超采样）。"""
    pts = []
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    for i in range(72):
        t = 2 * math.pi * i / 72
        px, py = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + px * ca - py * sa, cy + px * sa + py * ca))
    draw.polygon(pts, fill=fill)


def paste_rotated(base: Image.Image, layer: Image.Image, angle: float, center=None):
    center = center or (base.size[0] // 2, base.size[1] // 2)
    rot = layer.rotate(angle, resample=Image.BICUBIC, center=center, expand=False)
    base.alpha_composite(rot) if base.mode == "RGBA" else base.paste(rot, (0, 0), rot)
    return base


def text_size(draw, txt, ft) -> tuple[int, int]:
    box = draw.textbbox((0, 0), txt, font=ft)
    return box[2] - box[0], box[3] - box[1]


def draw_centered(draw, center, txt, ft, fill):
    w, h = text_size(draw, txt, ft)
    draw.text((center[0] - w / 2, center[1] - h / 2), txt, font=ft, fill=fill)


def chalk_alpha(rgba: Image.Image, seed=0, strength=0.9, blur=1.2) -> Image.Image:
    """把文字层（RGBA）的 alpha 打散成粉笔颗粒，保留原本颜色。"""
    layer = rgba.copy()
    alpha = np.asarray(layer.getchannel("A"), dtype=np.float32) / 255.0
    r = rng(seed)
    n = r.random(alpha.shape).astype(np.float32)  # 0..1
    n8 = Image.fromarray((n * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(blur))
    n = np.asarray(n8, dtype=np.float32) / 255.0
    keep = np.clip((n * 0.32 + 0.68) * strength, 0, 1)
    out_a = np.clip(alpha * keep * 255, 0, 255).astype(np.uint8)
    layer.putalpha(Image.fromarray(out_a, "L"))
    return layer


def draw_hand_line(layer: Image.Image, xy, text, ft, fill, jitter_seed=0, slope=0.0,
                   char_gap=0.0, wobble=0.7):
    """逐字绘制，带轻微旋转/位移抖动 —— 伪手写（日文没有现成手写字体时的折中）。
    layer 必须是 RGBA Image。返回下一个字的 x。"""
    r = random.Random(jitter_seed)
    x, y = xy
    for ch in text:
        w = ft.getlength(ch)
        h = ft.size
        sub = Image.new("RGBA", (int(w) + 12, int(h * 1.6) + 12), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sub)
        sd.text((4, 4), ch, font=ft, fill=fill)
        ang = r.uniform(-wobble, wobble)
        sub = sub.rotate(ang, resample=Image.BICUBIC, expand=False)
        dy = r.uniform(-1.6, 1.6)
        layer.paste(sub, (int(x - 4), int(y + dy - 4)), sub)
        x += w + char_gap
        y += slope * w
    return x


def seal(img: Image.Image, center, radius, color=(178, 58, 58, 255), inner_text=None, ft=None):
    """朱红印章圆章（日式招牌的小点缀）。"""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=color, width=max(2, radius // 12))
    if inner_text and ft:
        w, h = text_size(d, inner_text, ft)
        d.text((cx - w / 2, cy - h / 2), inner_text, font=ft, fill=color)
    img.alpha_composite(layer)
    return img


def save_png(img: Image.Image, path: str, compact: bool = True) -> str:
    """保存 PNG。compact=True 时量化到 256 色调色板 —— 插画/文字图观感几乎不变，
    但体积只有 24bit 噪声图的 1/4~1/3（网页加载友好）。带 alpha 的图保持 24bit+alpha。"""
    if compact and img.mode == "RGB":
        q = img.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
        q.save(path, "PNG", optimize=True)
    else:
        img.save(path, "PNG", optimize=True)
    return path


# ---------------------------------------------------------------- 1. 黑板菜单

MENU_LINES = [
    ("ブレンドコーヒー", "Blend Coffee", "¥480"),
    ("カフェラテ", "Café Latte", "¥520"),
    ("抹茶ラテ", "Matcha Latte", "¥560"),
    ("いちごミルク", "Strawberry Milk", "¥600"),
    ("クリームソーダ", "Cream Soda", "¥580"),
    ("ケーキセット", "Cake Set", "¥880"),
    ("フレンチトースト", "French Toast", "¥700"),
    ("オムライス", "Omurice", "¥900"),
    ("ナポリタン", "Neapolitan", "¥850"),
    ("手作りプリン", "Homemade Pudding", "¥420"),
    ("本日のケーキ", "Today's Cake", "¥450"),
    ("ほうじ茶", "Hojicha", "¥450"),
    ("紅茶", "Black Tea", "¥500"),
]


def gen_menu_blackboard(outdir: str) -> str:
    W, H = 1200, 1700
    # 黑板底：深墨绿 + 擦拭痕
    board = linear_gradient((W, H), (26, 34, 31), (16, 22, 21))
    r = rng(11)
    # 粉笔擦过的雾状痕
    haze = Image.new("L", (W, H), 0)
    hd = ImageDraw.Draw(haze)
    for _ in range(26):
        cw, ch = r.integers(160, 520), r.integers(40, 130)
        cx, cy = r.integers(-100, W), r.integers(0, H)
        hd.ellipse([cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2], fill=int(r.integers(6, 18)))
    haze = haze.filter(ImageFilter.GaussianBlur(26))
    board = ImageChops.add(board, Image.merge("RGB", (haze, haze, haze)))
    board = paper_texture(board, seed=12, strength=0.7)

    # 木框
    frame = 26
    draw = ImageDraw.Draw(board)
    draw.rectangle([0, 0, W - 1, H - 1], outline=(78, 52, 34), width=frame)
    draw.rectangle([frame, frame, W - frame - 1, H - frame - 1], outline=(120, 86, 56), width=3)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    title_ft = font("jp_b", 88)
    sub_ft = font("serif", 32)
    jp_ft = font("jp_m", 46)
    en_ft = font("serif", 23)
    price_ft = font("serif_b", 42)
    note_ft = font("jp_m", 28)

    # 标题（居中；日文大字 + 拉丁小字副标题）
    title_w = d.textlength("メニュー", font=title_ft)
    draw_hand_line(layer, ((W - title_w) / 2, 76), "メニュー", title_ft, (240, 238, 228, 235),
                   jitter_seed=1, wobble=1.3)
    tw = d.textlength("MENU", font=sub_ft)
    d.text(((W - tw) / 2, 196), "MENU", font=sub_ft, fill=(226, 222, 208, 210))
    d.line([(120, 258), (W - 120, 258)], fill=(226, 222, 208, 150), width=3)

    y = 300
    lh = 86
    for i, (jp, en, price) in enumerate(MENU_LINES):
        alpha = 234 - i * 2
        col = (238, 236, 226, alpha)
        # 日文条目（手写抖动）
        draw_hand_line(layer, (150, y), jp, jp_ft, col, jitter_seed=100 + i, wobble=0.9)
        # 英文小注（更靠下，避免压下一行）
        d.text((156, y + 52), en, font=en_ft, fill=(206, 210, 200, alpha - 70))
        # 价格（粗体，右侧右对齐）
        pw = d.textlength(price, font=price_ft)
        d.text((W - 150 - pw, y + 8), price, font=price_ft, fill=(246, 240, 226, alpha))
        # 点线只画在文字与价格之间的空档，避免压字
        x_start = int(150 + d.textlength(jp, font=jp_ft) + 62)
        x_end = int(W - 150 - pw - 20)
        if x_end > x_start + 12:
            for k in range(x_start, x_end, 14):
                d.ellipse([k, y + 32, k + 3, y + 35], fill=(214, 212, 202, 105))
        y += lh

    d.line([(120, y + 12), (W - 120, y + 12)], fill=(226, 222, 208, 150), width=3)
    d.text((160, y + 42), "ご注文はお声がけください  —  Please order at the counter", font=note_ft,
           fill=(226, 222, 208, 200))

    chalked = chalk_alpha(layer, seed=13, strength=0.93)
    board = board.convert("RGBA")
    board.alpha_composite(chalked)
    board = board.convert("RGB")
    board = add_vignette(board, 0.28)
    board = add_grain(board, 2.6, seed=14)

    path = os.path.join(outdir, "menu_blackboard.png")
    return save_png(board, path)
    return path


# ---------------------------------------------------------------- 2. 门帘


def gen_noren_welcome(outdir: str) -> str:
    W, H = 1536, 1024
    base = linear_gradient((W, H), (37, 52, 84), (24, 34, 58))
    base = paper_texture(base, seed=21, strength=1.3)

    # 织物纹理：竖纹
    arr = np.asarray(base.convert("RGB"), dtype=np.float32)
    r = rng(22)
    weave = np.tile((r.normal(0, 3.4, W)).astype(np.float32), (H, 1))
    arr = np.clip(arr + weave[..., None], 0, 255)
    base = Image.fromarray(arr.astype(np.uint8), "RGB")

    d = ImageDraw.Draw(base)
    # 上下留白边
    d.rectangle([0, 0, W, 54], fill=(236, 230, 214))
    d.rectangle([0, H - 54, W, H], fill=(236, 230, 214))
    # 中缝（门帘的帘缝）
    for x in (512, 1024):
        d.line([(x, 54), (x, H - 54)], fill=(16, 24, 42), width=10)
        d.line([(x + 2, 54), (x + 2, H - 54)], fill=(48, 64, 96), width=2)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    big = font("jp_b", 168)
    txt = "いらっしゃいませ"
    tw = ld.textlength(txt, font=big)
    ld.text(((W - tw) / 2, 250), txt, font=big, fill=(246, 240, 224, 255))
    small = font("serif", 40)
    sub = "MAID CAFÉ   ·   WELCOME"
    sw = ld.textlength(sub, font=small)
    ld.text(((W - sw) / 2, 520), sub, font=small, fill=(232, 214, 176, 235))

    # 下方小字
    tiny = font("jp_m", 34)
    t2 = "めいど かふぇ"
    t2w = ld.textlength(t2, font=tiny)
    ld.text(((W - t2w) / 2, 600), t2, font=tiny, fill=(236, 228, 208, 215))

    # 细描边（内框）
    ld.rectangle([44, 108, W - 44, H - 108], outline=(236, 228, 210, 120), width=3)

    base = base.convert("RGBA")
    base.alpha_composite(layer)
    seal(base, (W - 168, 190), 72, color=(196, 74, 66, 235), inner_text="め", ft=font("jp_b", 74))
    base = base.convert("RGB")
    base = add_vignette(base, 0.3)
    base = add_grain(base, 2.2, seed=23)

    path = os.path.join(outdir, "noren_welcome.png")
    return save_png(base, path)
    return path


# ---------------------------------------------------------------- 3. 门口招牌


def gen_sign_cafe(outdir: str) -> str:
    W, H = 1800, 1100
    # 奶油底 + 木框
    base = linear_gradient((W, H), (250, 244, 230), (238, 228, 208))
    base = paper_texture(base, seed=31, strength=0.9)
    d = ImageDraw.Draw(base)
    d.rectangle([0, 0, W - 1, H - 1], fill=None, outline=(112, 78, 50), width=46)
    d.rectangle([46, 46, W - 47, H - 47], outline=(150, 108, 70), width=4)
    d.rectangle([70, 70, W - 71, H - 71], outline=(212, 196, 170), width=2)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    t1 = "Maid Café"
    ft1 = font("serif_b", 190)
    w1 = ld.textlength(t1, font=ft1)
    ld.text(((W - w1) / 2, 168), t1, font=ft1, fill=(74, 52, 38, 255))

    t2 = "めいど"
    ft2 = font("jp_b", 132)
    w2 = ld.textlength(t2, font=ft2)
    ld.text(((W - w2) / 2, 430), t2, font=ft2, fill=(150, 58, 62, 255))

    # 分隔线与小字
    ld.line([(W / 2 - 330, 640), (W / 2 + 330, 640)], fill=(160, 120, 92, 200), width=3)
    t3 = "COFFEE  ·  CAKE  ·  TEA"
    ft3 = font("serif", 52)
    w3 = ld.textlength(t3, font=ft3)
    ld.text(((W - w3) / 2, 690), t3, font=ft3, fill=(96, 72, 56, 235))

    t4 = "since 2026"
    ft4 = font("sans", 40)
    w4 = ld.textlength(t4, font=ft4)
    ld.text(((W - w4) / 2, 780), t4, font=ft4, fill=(150, 130, 112, 220))

    # 两边的小茶杯图案
    for cx in (300, W - 300):
        cy = 560
        ld.ellipse([cx - 96, cy - 20, cx + 96, cy + 78], outline=(150, 112, 80, 220), width=6)
        ld.arc([cx - 120, cy - 90, cx + 120, cy + 40], start=200, end=340, fill=(150, 112, 80, 220), width=6)
        for k in (-40, 0, 40):
            ld.arc([cx + k - 26, cy - 170, cx + k + 26, cy - 42], start=300, end=60, fill=(176, 148, 120, 170), width=4)
        ld.line([(cx - 120, cy + 92), (cx + 120, cy + 92)], fill=(150, 112, 80, 200), width=5)

    base = base.convert("RGBA")
    base.alpha_composite(layer)
    seal(base, (W - 300, 220), 84, color=(190, 72, 66, 230), inner_text="茶", ft=font("jp_b", 82))
    base = base.convert("RGB")
    base = add_vignette(base, 0.26)
    base = add_grain(base, 2.0, seed=32)

    path = os.path.join(outdir, "sign_cafe.png")
    return save_png(base, path)
    return path


# ---------------------------------------------------------------- 4. 桌面菜单立牌（A6 竖版）


def gen_menu_card(outdir: str) -> str:
    W, H = 1050, 1484  # A6 比例 105:148
    base = linear_gradient((W, H), (252, 248, 238), (243, 234, 218))
    base = paper_texture(base, seed=41, strength=0.7)
    d = ImageDraw.Draw(base)

    # 顶部色带
    d.rectangle([0, 0, W, 196], fill=(58, 74, 92))
    d.rectangle([0, 196, W, 202], fill=(176, 138, 96))

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    t = "MAID CAFÉ"
    ft = font("serif_b", 74)
    tw = ld.textlength(t, font=ft)
    ld.text(((W - tw) / 2, 44), t, font=ft, fill=(248, 242, 228, 255))
    t2 = "めいど かふぇ"
    ft2 = font("jp_m", 34)
    tw2 = ld.textlength(t2, font=ft2)
    ld.text(((W - tw2) / 2, 134), t2, font=ft2, fill=(226, 212, 186, 240))

    # 章节
    sec = font("jp_b", 42)
    item = font("jp_m", 36)
    price = font("serif_b", 36)
    en = font("jp_m", 24)

    def section(title, en_title, y, rows):
        ld.text((78, y), title, font=sec, fill=(70, 54, 42, 255))
        ld.text((86 + ld.textlength(title, font=sec) + 22, y + 14), en_title, font=en,
                fill=(150, 126, 104, 235))
        ld.line([(78, y + 58), (W - 78, y + 58)], fill=(176, 146, 118, 190), width=2)
        yy = y + 78
        for jp, pr in rows:
            ld.text((92, yy), jp, font=item, fill=(58, 46, 38, 255))
            pw = ld.textlength(pr, font=price)
            ld.text((W - 92 - pw, yy), pr, font=price, fill=(150, 58, 62, 255))
            yy += 62
        return yy

    y = section("COFFEE", "コーヒー", 246, [
        ("ブレンドコーヒー", "¥480"),
        ("アメリカン", "¥480"),
        ("カフェラテ", "¥520"),
        ("カプチーノ", "¥520"),
    ])
    y = section("TEA", "お茶", y + 26, [
        ("紅茶（アールグレイ）", "¥500"),
        ("抹茶ラテ", "¥560"),
        ("ほうじ茶", "¥450"),
    ])
    y = section("SWEETS", "甘味", y + 26, [
        ("本日のケーキ", "¥450"),
        ("ケーキセット", "¥880"),
        ("手作りプリン", "¥420"),
    ])
    note = "All prices include tax  ·  すべて税込"
    nf = font("jp_m", 22)
    nw = ld.textlength(note, font=nf)
    ld.text(((W - nw) / 2, H - 96), note, font=nf, fill=(140, 122, 106, 230))
    ld.line([(W / 2 - 120, H - 120), (W / 2 + 120, H - 120)], fill=(190, 162, 134, 180), width=2)

    # 底部署名
    ld.text((78, H - 62), "MAID CAFÉ", font=font("serif", 20), fill=(170, 150, 130, 210))

    base = base.convert("RGBA")
    base.alpha_composite(layer)
    base = base.convert("RGB")
    base = add_vignette(base, 0.18)
    base = add_grain(base, 1.6, seed=42)

    path = os.path.join(outdir, "menu_card.png")
    return save_png(base, path)
    return path


# ---------------------------------------------------------------- 5/6. 豆罐 / 茶罐标签


def _label_frame(W, H, seed, base_color=(246, 240, 226), ink=(64, 50, 40)):
    base = linear_gradient((W, H), base_color, tuple(max(0, c - 12) for c in base_color))
    base = paper_texture(base, seed=seed, strength=0.8)
    d = ImageDraw.Draw(base)
    d.rectangle([14, 14, W - 15, H - 15], outline=ink, width=3)
    d.rectangle([26, 26, W - 27, H - 27], outline=tuple(min(255, c + 40) for c in ink), width=1)
    return base


def gen_label_beans(outdir: str) -> str:
    W, H = 1024, 640
    base = _label_frame(W, H, seed=51)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ink = (62, 48, 38, 255)
    accent = (150, 58, 62, 255)

    t = "MAID CAFÉ"
    ft = font("serif_b", 48)
    tw = ld.textlength(t, font=ft)
    ld.text((70, 52), t, font=ft, fill=ink)
    ld.text((74, 112), "ORIGINAL BLEND", font=font("serif", 26), fill=(126, 104, 84, 255))

    t = "オリジナルブレンド"
    ft = font("jp_b", 58)
    ld.text((70, 186), t, font=ft, fill=accent)

    t = "深煎り  ·  DARK ROAST  ·  200g"
    ft = font("jp_m", 32)
    ld.text((72, 276), t, font=ft, fill=(82, 66, 54, 255))

    ld.line([(72, 340), (W - 72, 340)], fill=(170, 142, 116, 200), width=2)
    ld.text((72, 366), "コーヒー豆 / COFFEE BEANS", font=font("jp_m", 34), fill=(82, 66, 54, 255))
    ld.text((72, 424), "開封後は冷暗所で保存してください", font=font("jp_m", 24), fill=(140, 120, 104, 235))

    # 咖啡豆图标
    cx, cy = W - 200, 210
    for k, ang in enumerate((-28, 12, 52)):
        px, py = cx + [-34, 34, 0][k], cy + [-38, -30, 44][k]
        rotated_ellipse(ld, px, py, 46, 30, ang, (96, 66, 46, 255))
        # 豆缝
        pa = math.radians(ang)
        dx, dy = math.cos(pa) * 40, math.sin(pa) * 40
        ld.line([(px - dx, py - dy), (px + dx, py + dy)], fill=(210, 186, 160, 235), width=3)

    base = base.convert("RGBA")
    base.alpha_composite(layer)
    base = base.convert("RGB")
    base = add_grain(base, 1.8, seed=52)
    path = os.path.join(outdir, "label_beans.png")
    return save_png(base, path)
    return path


def gen_label_tea(outdir: str) -> str:
    W, H = 1024, 640
    base = _label_frame(W, H, seed=61, base_color=(240, 238, 208))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ink = (46, 58, 44, 255)
    accent = (86, 112, 68, 255)

    t = "MAID CAFÉ"
    ld.text((70, 52), t, font=font("serif_b", 48), fill=ink)
    ld.text((74, 112), "TEA ROOM SELECTION", font=font("serif", 26), fill=(110, 122, 92, 255))

    ld.text((70, 186), "アールグレイ", font=font("jp_b", 62), fill=accent)
    ld.text((72, 278), "EARL GREY  ·  リーフ 100g", font=font("jp_m", 32), fill=(70, 84, 62, 255))

    ld.line([(72, 340), (W - 72, 340)], fill=(150, 164, 124, 200), width=2)
    ld.text((72, 366), "紅茶 / BLACK TEA  ·  ベルガモット香", font=font("jp_m", 32), fill=(70, 84, 62, 255))
    ld.text((72, 424), "90℃ ・ 3分でおいしく淹れられます", font=font("jp_m", 24), fill=(126, 138, 106, 235))

    # 茶叶枝图标
    cx, cy = W - 210, 220
    ld.line([(cx - 60, cy + 90), (cx + 40, cy - 80)], fill=(92, 118, 70, 255), width=5)
    for i, (lx, ly, ang) in enumerate([(-30, 40, -34), (12, 6, 30), (-6, -38, -26), (30, -62, 34)]):
        rotated_ellipse(ld, cx + lx, cy + ly, 40, 18, ang, (104, 132, 80, 255))
        rotated_ellipse(ld, cx + lx, cy + ly, 24, 8, ang, (150, 172, 118, 255))

    base = base.convert("RGBA")
    base.alpha_composite(layer)
    base = base.convert("RGB")
    base = add_grain(base, 1.8, seed=62)
    path = os.path.join(outdir, "label_tea.png")
    return save_png(base, path)
    return path


# ---------------------------------------------------------------- 7-9. 相框插画

SS = 3  # 超采样倍数


def _soft_blooms(size, palette, seed, n=26, blur=48, alpha=42):
    """水彩晕染底色。"""
    W, H = size
    r = rng(seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(n):
        col = palette[int(r.integers(0, len(palette)))]
        cx, cy = int(r.integers(0, W)), int(r.integers(0, H))
        rx, ry = int(r.integers(W // 12, W // 3)), int(r.integers(H // 12, H // 3))
        rotated_ellipse(d, cx, cy, rx, ry, float(r.uniform(0, 180)), col + (int(r.integers(alpha // 2, alpha)),))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def _art_base(size, top, bottom, seed, palette):
    W, H = size
    base = linear_gradient((W, H), top, bottom).convert("RGBA")
    base.alpha_composite(_soft_blooms(size, palette, seed))
    return base


def _finish_art(img: Image.Image, seed, border=True):
    W, H = img.size
    out = img.convert("RGB")
    out = add_vignette(out, 0.3)
    out = paper_texture(out, seed=seed, strength=1.1)
    out = add_grain(out, 2.0, seed=seed + 1)
    if border:
        d = ImageDraw.Draw(out)
        d.rectangle([18, 18, W - 19, H - 19], outline=(198, 182, 160), width=3)
    return out


def gen_picture_art_01(outdir: str) -> str:
    """花与花瓶。"""
    W = H = 1024
    base = _art_base((W, H), (250, 244, 236), (236, 226, 214), 71,
                     [(214, 176, 168), (198, 206, 178), (226, 200, 176), (238, 214, 198)])
    img = base.resize((W * SS, H * SS), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    s = SS

    # 桌面线
    d.ellipse([180 * s, 780 * s, 844 * s, 900 * s], fill=(206, 186, 166, 70))
    # 花瓶
    vase = [(452 * s, 470 * s)]  # center-top
    d.polygon([(468 * s, 470 * s), (556 * s, 470 * s), (580 * s, 640 * s), (546 * s, 800 * s),
               (478 * s, 800 * s), (444 * s, 640 * s)], fill=(196, 148, 140, 255))
    d.polygon([(468 * s, 470 * s), (486 * s, 470 * s), (470 * s, 640 * s), (462 * s, 800 * s),
               (478 * s, 800 * s), (500 * s, 640 * s)], fill=(216, 176, 168, 190))
    d.ellipse([444 * s, 462 * s, 580 * s, 496 * s], fill=(206, 162, 152, 255))

    # 茎
    stems = [((512, 480), (430, 330), (400, 236)), ((512, 480), (520, 320), (528, 214)),
             ((512, 480), (600, 340), (640, 250)), ((512, 480), (470, 360), (452, 300))]
    for a, b, c in stems:
        for t in np.linspace(0, 1, 24):
            x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * b[0] + t * t * c[0]
            y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * b[1] + t * t * c[1]
            d.ellipse([(x - 4) * s, (y - 4) * s, (x + 4) * s, (y + 4) * s], fill=(112, 132, 92, 255))

    # 叶子
    for lx, ly, ang, rx, ry in [(452, 400, -52, 46, 22), (580, 410, 48, 44, 20), (492, 350, -20, 34, 16),
                                (560, 356, 24, 34, 16)]:
        rotated_ellipse(d, lx * s, ly * s, rx * s, ry * s, ang, (122, 146, 102, 235))

    # 花
    blossoms = [(400, 230, (230, 176, 178), (246, 214, 186), 96),
                (528, 208, (232, 190, 168), (250, 226, 200), 104),
                (642, 244, (216, 178, 196), (244, 214, 226), 88)]
    for cx, cy, petal, center, rad in blossoms:
        for k in range(9):
            ang = k * 40 + 6
            px = cx + math.cos(math.radians(ang)) * rad * 0.52
            py = cy + math.sin(math.radians(ang)) * rad * 0.52
            rotated_ellipse(d, px * s, py * s, rad * 0.44 * s, rad * 0.26 * s, ang, petal + (235,))
        d.ellipse([(cx - rad * 0.3) * s, (cy - rad * 0.3) * s, (cx + rad * 0.3) * s, (cy + rad * 0.3) * s],
                  fill=center + (255,))

    # 零星落叶/小花点
    r = rng(72)
    for _ in range(16):
        x, y = int(r.integers(150, 880)), int(r.integers(560, 900))
        rotated_ellipse(d, x * s, y * s, float(r.integers(8, 18)) * s, float(r.integers(4, 9)) * s,
                        float(r.integers(0, 180)), (180, 158, 138, int(r.integers(60, 120))))

    out = img.resize((W, H), Image.LANCZOS)
    out = _finish_art(out, 73)
    path = os.path.join(outdir, "picture_art_01.png")
    return save_png(out, path)
    return path


def gen_picture_art_02(outdir: str) -> str:
    """打瞌睡的猫。"""
    W = H = 1024
    base = _art_base((W, H), (244, 244, 238), (226, 232, 238), 81,
                     [(206, 220, 228), (232, 224, 210), (214, 222, 208), (240, 234, 222)])
    img = base.resize((W * SS, H * SS), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    s = SS

    # 背景圆（柔和月/光斑）
    d.ellipse([300 * s, 190 * s, 724 * s, 614 * s], fill=(250, 246, 232, 120))

    cream = (246, 232, 210, 255)
    cream2 = (238, 220, 196, 255)
    ink = (110, 88, 76, 255)
    pink = (232, 176, 172, 210)

    # 身体（蜷卧）
    d.ellipse([276 * s, 560 * s, 748 * s, 812 * s], fill=cream)
    d.ellipse([276 * s, 640 * s, 748 * s, 812 * s], fill=cream2)
    # 尾巴
    for t in np.linspace(0, 1, 40):
        ang = math.pi * 0.9 * t
        x = 730 + 96 * math.cos(ang) - 30 * t
        y = 730 + 60 * math.sin(-ang + 0.4) + 26 * t
        d.ellipse([(x - 22) * s, (y - 22) * s, (x + 22) * s, (y + 22) * s], fill=cream2)
    # 头
    d.ellipse([382 * s, 380 * s, 648 * s, 646 * s], fill=cream)
    # 耳朵
    d.polygon([(398 * s, 430 * s), (408 * s, 300 * s), (500 * s, 392 * s)], fill=cream)
    d.polygon([(632 * s, 430 * s), (622 * s, 300 * s), (530 * s, 392 * s)], fill=cream)
    d.polygon([(418 * s, 414 * s), (424 * s, 336 * s), (480 * s, 396 * s)], fill=pink)
    d.polygon([(612 * s, 414 * s), (606 * s, 336 * s), (550 * s, 396 * s)], fill=pink)

    # 眼睛（闭眼弧）
    for cx in (452, 578):
        d.arc([(cx - 40) * s, (470 - 18) * s, (cx + 40) * s, (470 + 34) * s], start=190, end=350,
              fill=ink, width=7 * s)
    # 鼻子 / 嘴
    d.polygon([(500 * s, 520 * s), (530 * s, 520 * s), (515 * s, 536 * s)], fill=(214, 150, 148, 255))
    d.arc([(492 * s), (530 * s), (518 * s), (556 * s)], start=10, end=80, fill=ink, width=4 * s)
    d.arc([(514 * s), (530 * s), (540 * s), (556 * s)], start=100, end=170, fill=ink, width=4 * s)
    # 腮红
    for cx in (432, 600):
        d.ellipse([(cx - 34) * s, (500 - 14) * s, (cx + 34) * s, (500 + 14) * s], fill=pink)
    # 胡须
    for k, (dx, dy) in enumerate([(-1, -0.22), (-1, 0.05), (-1, 0.3), (1, -0.22), (1, 0.05), (1, 0.3)]):
        x0, y0 = (500 if dx < 0 else 530), 528
        d.line([(x0 * s, y0 * s), ((x0 + dx * 150) * s, (y0 + dy * 150) * s)],
               fill=(160, 138, 124, 200), width=3 * s)
    # 前爪
    for cx in (392, 470):
        d.ellipse([(cx - 46) * s, (742 - 26) * s, (cx + 46) * s, (742 + 30) * s], fill=cream)
        for k in (-1, 0, 1):
            d.line([((cx + k * 18) * s, 744 * s), ((cx + k * 20) * s, 768 * s)],
                   fill=(206, 184, 166, 220), width=3 * s)

    # 小星星
    r = rng(82)
    for _ in range(14):
        x, y = int(r.integers(120, 900)), int(r.integers(120, 420))
        rr = float(r.integers(5, 12))
        d.ellipse([(x - rr) * s, (y - rr) * s, (x + rr) * s, (y + rr) * s], fill=(250, 246, 224, 210))

    out = img.resize((W, H), Image.LANCZOS)
    out = _finish_art(out, 83)
    path = os.path.join(outdir, "picture_art_02.png")
    return save_png(out, path)
    return path


def gen_picture_art_03(outdir: str) -> str:
    """咖啡杯与拉花。"""
    W = H = 1024
    base = _art_base((W, H), (250, 240, 226), (232, 214, 192), 91,
                     [(226, 198, 166), (244, 226, 200), (212, 186, 158), (238, 220, 196)])
    img = base.resize((W * SS, H * SS), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    s = SS

    # 桌面
    d.ellipse([140 * s, 600 * s, 884 * s, 880 * s], fill=(206, 178, 148, 90))
    # 碟
    d.ellipse([238 * s, 612 * s, 786 * s, 800 * s], fill=(244, 236, 222, 255))
    d.ellipse([262 * s, 626 * s, 762 * s, 786 * s], fill=(232, 222, 206, 255))
    # 杯身
    d.polygon([(330 * s, 470 * s), (694 * s, 470 * s), (660 * s, 690 * s), (364 * s, 690 * s)],
              fill=(250, 246, 238, 255))
    d.ellipse([330 * s, 640 * s, 694 * s, 748 * s], fill=(240, 232, 220, 255))
    # 杯口 + 咖啡
    d.ellipse([330 * s, 424 * s, 694 * s, 528 * s], fill=(250, 246, 238, 255))
    d.ellipse([348 * s, 436 * s, 676 * s, 516 * s], fill=(96, 62, 44, 255))
    # 拉花心
    d.ellipse([452 * s, 448 * s, 572 * s, 508 * s], fill=(238, 226, 208, 235))
    d.polygon([(452 * s, 478 * s), (512 * s, 468 * s), (452 * s, 512 * s)], fill=(238, 226, 208, 235))
    d.polygon([(572 * s, 478 * s), (512 * s, 468 * s), (572 * s, 512 * s)], fill=(238, 226, 208, 235))
    d.polygon([(512 * s, 468 * s), (486 * s, 462 * s), (512 * s, 512 * s)], fill=(225, 210, 190, 220))
    # 把手
    d.arc([640 * s, 500 * s, 800 * s, 660 * s], start=280, end=110, fill=(246, 240, 230, 255), width=26 * s)
    # 热气
    for k, cx in enumerate((410, 512, 614)):
        for t in np.linspace(0, 1, 26):
            x = cx + 30 * math.sin(t * math.pi * 2.2 + k)
            y = 430 - t * 250
            d.ellipse([(x - 8) * s, (y - 8) * s, (x + 8) * s, (y + 8) * s],
                      fill=(250, 246, 238, int(120 * (1 - t) + 30)))
    # 咖啡豆
    for cx, cy, ang in [(210, 760, -24), (806, 720, 36), (150, 660, 60)]:
        rotated_ellipse(d, cx * s, cy * s, 54 * s, 34 * s, ang, (104, 72, 50, 255))
        pa = math.radians(ang)
        dx, dy = math.cos(pa) * 44 * s, math.sin(pa) * 44 * s
        d.line([(cx * s - dx, cy * s - dy), (cx * s + dx, cy * s + dy)], fill=(200, 176, 150, 235), width=4 * s)
    # 小叶子
    rotated_ellipse(d, 780 * s, 640 * s, 46 * s, 18 * s, 34, (126, 148, 104, 230))
    rotated_ellipse(d, 812 * s, 612 * s, 40 * s, 16 * s, -24, (146, 166, 120, 230))

    out = img.resize((W, H), Image.LANCZOS)
    out = _finish_art(out, 93)
    path = os.path.join(outdir, "picture_art_03.png")
    return save_png(out, path)
    return path


# ---------------------------------------------------------------- 10. OPEN 挂牌


def gen_chalk_open(outdir: str) -> str:
    W, H = 1200, 900
    base = linear_gradient((W, H), (32, 38, 35), (20, 25, 24))
    base = paper_texture(base, seed=101, strength=0.8)
    d = ImageDraw.Draw(base)
    d.rectangle([0, 0, W - 1, H - 1], outline=(92, 64, 42), width=34)
    d.rectangle([34, 34, W - 35, H - 35], outline=(126, 92, 60), width=3)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ft = font("hand_b", 320)
    t = "OPEN"
    tw = ld.textlength(t, font=ft)
    ld.text(((W - tw) / 2, 190), t, font=ft, fill=(246, 242, 232, 240))
    # 双下划线（手写）
    for k, wdt in ((0, 8), (1, 4)):
        y = 560 + k * 26
        pts = [((W / 2 - 300 + i * 12), y + 6 * math.sin(i / 8.0)) for i in range(50)]
        ld.line(pts, fill=(246, 242, 232, 200), width=wdt)
    ft2 = font("jp_b", 78)
    t2 = "営業中"
    tw2 = ld.textlength(t2, font=ft2)
    ld.text(((W - tw2) / 2, 640), t2, font=ft2, fill=(238, 232, 220, 225))
    ft3 = font("jp_m", 38)
    t3 = "please come in  ·  お待ちしております"
    tw3 = ld.textlength(t3, font=ft3)
    ld.text(((W - tw3) / 2, 760), t3, font=ft3, fill=(214, 208, 196, 200))

    chalked = chalk_alpha(layer, seed=102, strength=0.86)
    base = base.convert("RGBA")
    base.alpha_composite(chalked)
    base = base.convert("RGB")
    base = add_vignette(base, 0.3)
    base = add_grain(base, 2.2, seed=103)

    path = os.path.join(outdir, "chalk_open.png")
    return save_png(base, path)
    return path


# ---------------------------------------------------------------- 11. 窗玻璃雨滴（RGBA）


def gen_window_drops(outdir: str) -> str:
    W = H = 1024
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    r = rng(111)

    # 大中滴：水滴 + 高光 + 轻微下方拖影
    drops = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(drops)
    for _ in range(210):
        cx, cy = int(r.integers(-20, W + 20)), int(r.integers(-20, H + 20))
        rad = float(r.gamma(2.2, 5.0))
        rad = min(max(rad, 2.0), 26.0)
        a = int(r.integers(46, 110))
        # 水珠主体（半透明灰蓝，内亮外暗）
        dd.ellipse([cx - rad, cy - rad * 0.92, cx + rad, cy + rad * 0.92], fill=(196, 214, 226, a))
        dd.ellipse([cx - rad * 0.72, cy - rad * 0.66, cx + rad * 0.72, cy + rad * 0.66],
                   fill=(226, 238, 246, min(255, a + 26)))
        # 高光点
        hx, hy = cx - rad * 0.34, cy - rad * 0.38
        dd.ellipse([hx - rad * 0.24, hy - rad * 0.24, hx + rad * 0.24, hy + rad * 0.24],
                   fill=(255, 255, 255, 200))
        # 下缘暗边（折射）
        dd.arc([cx - rad, cy - rad * 0.92, cx + rad, cy + rad * 0.92], start=20, end=160,
               fill=(150, 170, 186, 130), width=max(1, int(rad * 0.12)))

    # 长条流痕
    streak = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(streak)
    for _ in range(46):
        cx = int(r.integers(0, W))
        y0 = int(r.integers(-100, H))
        ln = int(r.integers(80, 520))
        w0 = float(r.integers(1, 4))
        sd.line([(cx, y0), (cx + int(r.integers(-16, 16)), y0 + ln)],
                fill=(190, 210, 224, int(r.integers(22, 58))), width=max(1, int(w0)))
        sd.ellipse([cx - w0 * 1.6, y0 + ln - w0 * 1.6, cx + w0 * 1.6, y0 + ln + w0 * 1.6],
                   fill=(196, 214, 228, 90))
    streak = streak.filter(ImageFilter.GaussianBlur(0.7))

    # 整体玻璃雾
    fog = Image.new("RGBA", (W, H), (206, 220, 232, 0))
    fa = Image.fromarray((r.normal(0.5, 0.09, (H // 8, W // 8)) * 255).clip(0, 255).astype(np.uint8), "L")
    fa = fa.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))
    fog.putalpha(fa.point(lambda v: int(v * 0.10)))

    layer.alpha_composite(fog)
    layer.alpha_composite(streak)
    layer.alpha_composite(drops)
    # 边缘轻微模糊，避免"贴纸感"
    alpha = layer.getchannel("A").filter(ImageFilter.GaussianBlur(0.6))
    # 极低 alpha 压回 0：没有水滴的地方必须真透明（网页叠加才不会糊一层灰）
    a = np.asarray(alpha, dtype=np.float32)
    a = np.where(a < 14, 0.0, np.clip((a - 14) * (255.0 / 241.0), 0, 255))
    layer.putalpha(Image.fromarray(a.astype(np.uint8), "L"))

    path = os.path.join(outdir, "window_drops.png")
    layer.save(path, "PNG", optimize=True)
    return path


# ---------------------------------------------------------------- 调度

GENERATORS = [
    ("menu_blackboard", gen_menu_blackboard),
    ("noren_welcome", gen_noren_welcome),
    ("sign_cafe", gen_sign_cafe),
    ("menu_card", gen_menu_card),
    ("label_beans", gen_label_beans),
    ("label_tea", gen_label_tea),
    ("picture_art_01", gen_picture_art_01),
    ("picture_art_02", gen_picture_art_02),
    ("picture_art_03", gen_picture_art_03),
    ("chalk_open", gen_chalk_open),
    ("window_drops", gen_window_drops),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成女仆咖啡馆文字/标签/插画贴图")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--only", default=None, help="逗号分隔的产物名，只生成这些")
    ap.add_argument("--preview", action="store_true", help="额外写 400px 缩略图到 --preview-dir")
    ap.add_argument("--preview-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".scratch", "asset-scout", "preview"))
    ap.add_argument("--force", action="store_true", help="即使已存在也重新生成")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None
    if args.preview:
        os.makedirs(args.preview_dir, exist_ok=True)

    made, skipped = [], []
    for name, fn in GENERATORS:
        if only and name not in only:
            continue
        target = os.path.join(args.out, name + ".png")
        if os.path.exists(target) and os.path.getsize(target) > 1024 and not args.force:
            print(f"SKIP {name}.png ({os.path.getsize(target)}B)")
            skipped.append(target)
            continue
        p = fn(args.out)
        kb = os.path.getsize(p) / 1024
        with Image.open(p) as im:
            print(f"OK   {os.path.basename(p):24s} {im.size[0]}x{im.size[1]} {im.mode} {kb:8.1f}KB")
            if args.preview:
                im2 = im.convert("RGBA") if im.mode == "RGBA" else im.convert("RGB")
                im2.thumbnail((420, 420), Image.LANCZOS)
                bg = Image.new("RGB", im2.size, (30, 30, 30))
                bg.paste(im2, (0, 0), im2 if im2.mode == "RGBA" else None)
                bg.save(os.path.join(args.preview_dir, os.path.basename(p)))
        made.append(p)

    print(f"\nmade={len(made)} skipped={len(skipped)} out={args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
