import re

p = r"E:\dsh\maid_cafe\js\weather.js"
s = open(p, encoding="utf-8").read()
orig = s

# 各时段曝光（网页端观感：夜晚要真的暗下来、白天别发白）
pairs = [
    # morning
    ("    exposure: 0.98,\n    lampIntensity: 1.2,", "    exposure: 0.90,\n    lampIntensity: 1.2,"),
    # noon
    ("    exposure: 0.94,\n    lampIntensity: 0.9,", "    exposure: 0.86,\n    lampIntensity: 0.9,"),
    # dusk
    ("    exposure: 0.96,\n    lampIntensity: 2.1,", "    exposure: 0.88,\n    lampIntensity: 2.1,"),
    # night
    ("    exposure: 1.0,\n    lampIntensity: 3.4, // 室内暖灯全亮（夜景主要光源）",
     "    exposure: 0.62,\n    lampIntensity: 4.0, // 室内暖灯全亮（夜景主要光源）"),
    ("    fogDensity: 0.02,\n    exposure: 0.62,", "    fogDensity: 0.016,\n    exposure: 0.62,"),
]
n = 0
for a, b in pairs:
    if a in s:
        s = s.replace(a, b)
        n += 1
    else:
        print("MISS:", a.replace("\n", " | ")[:70])
open(p, "w", encoding="utf-8").write(s)
print("weather.js patched", n, "/", len(pairs))
