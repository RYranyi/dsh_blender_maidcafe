p = r"E:\dsh\maid_cafe\blender\cbar.py"
s = open(p, encoding="utf-8").read()
orig = s

# 实测：BA_Backsplash y=[2.96,2.99]，BA_ShelfUpright y=[2.78,2.98] → y 重叠 20mm，
# 且 x 有 30mm 重叠 → 真实穿透 10mm。
# 修：挡水板后移到贴墙（y 2.99-3.02 → 3.00±0.015），让它的前表面(=2.985)
# 落在立柱后端面(2.98)之后；同时立柱往内收 5mm（2.78-2.98 → 2.76-2.96）。
i = s.find('objs.append(C.box("BA_Backsplash"')
print(repr(s[i:i + 460]))
