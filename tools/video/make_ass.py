#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_ass.py —— 把 subtitles.srt 转成带正确分辨率的 ASS 字幕。

为什么需要：
  ffmpeg 烧 SRT 时用 force_style 的字号是基于 ASS 默认 PlayRes(384x288) 缩放的，
  结果 1080p 画面上字号/边距全错（会折行、位置偏）。
  正确做法：生成 ASS 并显式写 PlayResX=1920 / PlayResY=1080。

用法：python tools/video/make_ass.py
输出：docs/video/subtitles.ass
"""
import os
import re

# 项目根目录：从本文件位置向上推导（不再硬编码盘符）
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRT = os.path.join(ROOT, "docs", "video", "subtitles.srt")
ASS = os.path.join(ROOT, "docs", "video", "subtitles.ass")

W, H = 1920, 1080
FONT_MAIN = "Microsoft YaHei"
FONT_SIZE = 46          # 1080p 下 46px 约等于画面高度的 4.3%，舒适可读
MARGIN_V = 78           # 距底部
MARGIN_LR = 200         # 左右留白（保证不折行）
PRIMARY = "&H00E3EFF5"  # 暖白 #F5EFE3（ASS 是 BGR 顺序）
OUTLINE_COL = "&H88000000"
BACK_COL = "&H70000000"

# 字幕条目（序号, 起, 止, 文本）从 SRT 解析
def parse_srt(path):
    raw = open(path, encoding="utf-8-sig").read().replace("\r\n", "\n")
    blocks = [b for b in raw.strip().split("\n\n") if b.strip()]
    items = []
    for b in blocks:
        lines = b.strip().split("\n")
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)", lines[1])
        if not m:
            continue
        st = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000.0
        en = int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + int(m[8]) / 1000.0
        text = " ".join(lines[2:]).strip()
        items.append((st, en, text))
    return items


def ass_time(sec):
    if sec < 0:
        sec = 0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def main():
    items = parse_srt(SRT)
    print("解析到 %d 条字幕" % len(items))

    header = """[Script Info]
Title: 日式女仆咖啡馆 · 介绍视频字幕
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: %d
PlayResY: %d

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,%s,%d,%s,%s,%s,%s,0,0,0,0,100,100,1.4,0,1,1.6,1.0,2,%d,%d,%d,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" % (W, H, FONT_MAIN, FONT_SIZE, PRIMARY, PRIMARY, OUTLINE_COL, BACK_COL,
       MARGIN_LR, MARGIN_LR, MARGIN_V)

    lines = [header]
    for st, en, text in items:
        # 首条（标题）加大加粗
        if text == "日式女仆咖啡馆":
            tag = r"{\fs78\b1\fsp4\c&H00E3EFF5&\3c&H66000000&}"
        else:
            tag = ""
        lines.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s%s\n"
                     % (ass_time(st), ass_time(en), tag, text))

    open(ASS, "w", encoding="utf-8-sig").write("".join(lines))
    print("写入", ASS, os.path.getsize(ASS), "bytes")
    print("首条:", items[0], "末条:", items[-1])


if __name__ == "__main__":
    main()
