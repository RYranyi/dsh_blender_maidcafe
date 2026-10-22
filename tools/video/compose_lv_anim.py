#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compose_lv_anim.py —— 3 分钟真 3D 动画版合成（无声版）

输入：renders/lv_anim/<shot>/####.png（30 段 × 144 帧，1600×900）
输出：renders/video/maid_cafe_lighting_180s.mp4（1920×1080, 24fps, 180s）

流程：
  ① 每段 PNG 序列 → mp4（缩放到 1920×1080，CRF 18）
  ② concat 拼接 30 段
  ③ 烧中文字幕（docs/video/subtitles.ass）

注意：本片**无音轨**（用户要求视频彻底无音频，音乐由使用者自己配）。
      网页端的音乐/雨声不在此脚本范围内。
"""
import os
import subprocess
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANIM = os.path.join(ROOT, "renders", "lv_anim")
TMP = os.path.join(ROOT, "renders", "lv_anim_tmp")
OUT = os.path.join(ROOT, "renders", "video")
ASS = os.path.join(ROOT, "docs", "video", "subtitles.ass")
FFDIR = os.path.join(os.path.dirname(ROOT), ".tools", "ffmpeg")
FF = os.path.join(FFDIR, "ffmpeg.exe")
FP = os.path.join(FFDIR, "ffprobe.exe")
if not os.path.isfile(FF):
    FF = "ffmpeg"
    FP = "ffprobe"

FPS = 24
W, H = 1920, 1080
CRF = "18"
SEG = 6.0
NF = int(SEG * FPS)

ORDER = [
    "01_wire", "02_clay", "03_clay_bar", "04_clay_disp", "05_clay_maid",
    "06_final_wide", "07_morning_wide", "08_morning_win", "09_noon_wide",
    "10_noon_win", "11_dusk_wide", "12_dusk_lamp", "13_night_wide",
    "14_night_detail", "15_clear_win", "16_clear_bar", "17_cloudy_win",
    "18_cloudy_wide", "19_rainlight_win", "20_rainmed_win", "21_rainheavy_win",
    "22_storm_win", "23_rain_wide", "24_storm_wide", "25_top_stats",
    "26_shelf", "27_maid_dusk", "28_bar_noon", "29_window_dusk", "30_end_hero",
]

os.makedirs(TMP, exist_ok=True)
os.makedirs(OUT, exist_ok=True)


def run(cmd, tag=""):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("  [FAIL %s]" % tag)
        print((r.stderr or "")[-1500:])
        return False
    return True


def encode_shot(name, i):
    d = os.path.join(ANIM, name)
    if not os.path.isdir(d):
        print("  缺目录:", name)
        return None
    n = len([f for f in os.listdir(d) if f.endswith(".png")])
    if n < NF:
        print("  ⚠ %s 只有 %d/%d 帧" % (name, n, NF))
        if n == 0:
            return None
    out = os.path.join(TMP, "s%02d_%s.mp4" % (i, name))
    if os.path.exists(out) and os.path.getsize(out) > 20000:
        return out
    vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
          "setsar=1,format=yuv420p" % (W, H, W, H))
    cmd = [FF, "-y", "-framerate", str(FPS), "-start_number", "1",
           "-i", os.path.join(d, "%04d.png"),
           "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", CRF,
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", out]
    ok = run(cmd, name)
    if ok:
        print("    %-20s %d 帧" % (name, n))
    return out if ok else None


def main():
    print("① 编码 %d 段动画（无音轨）…" % len(ORDER))
    segs = []
    for i, name in enumerate(ORDER):
        p = encode_shot(name, i)
        if p:
            segs.append(p)
    if len(segs) != len(ORDER):
        print("⚠ 只有 %d/%d 段可用" % (len(segs), len(ORDER)))

    print("② 拼接 %d 段…" % len(segs))
    lst = os.path.join(TMP, "concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in segs:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    joined = os.path.join(TMP, "joined.mp4")
    if not run([FF, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                "-c", "copy", joined], "concat"):
        return 1

    probe = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", joined], capture_output=True, text=True)
    try:
        dur = float(probe.stdout.strip())
    except Exception:
        dur = len(segs) * SEG
    print("   实际时长 %.2fs" % dur)

    print("③ 烧字幕（无音频）…")
    subs_local = os.path.join(TMP, "subs.ass")
    with open(ASS, encoding="utf-8-sig") as f:
        content = f.read().lstrip("\ufeff")
    with open(subs_local, "w", encoding="utf-8") as f:
        f.write(content)

    cwd0 = os.getcwd()
    os.chdir(TMP)
    final = os.path.join(OUT, "maid_cafe_lighting_180s.mp4")
    ok = run([FF, "-y", "-i", "joined.mp4",
              "-vf", "ass=subs.ass,fade=t=in:st=0:d=0.8,fade=t=out:st=%.2f:d=1.0" % (dur - 1.2),
              "-c:v", "libx264", "-preset", "slow", "-crf", CRF,
              "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
              "-r", str(FPS), "-an", "-shortest",
              "-movflags", "+faststart", os.path.abspath(final)], "subs")
    os.chdir(cwd0)
    if not ok:
        return 1
    sz = os.path.getsize(final) / 1048576.0
    print("")
    print("  成片：%s" % final)
    print("  %.2f MB  %dx%d  %dfps  %.2fs  无音轨" % (sz, W, H, FPS, dur))
    print("COMPOSE_ANIM_OK " + json.dumps({"file": final, "mb": round(sz, 2),
                                           "seconds": round(dur, 2),
                                           "segments": len(segs),
                                           "audio": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
