# 诊断：循环接缝的真实物理判据 + 雷声超长原因
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import dsp

SR = dsp.SR
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "audio")

print('=== 床层接缝：绝对跳变 vs 信号电平（真正的爆音判据）===')
print(f'{"key":<18}{"dur":>6}{"seam_step":>12}{"seam/rms dB":>13}{"seam/peak dB":>14}{"med/p99":>12}')
for f in sorted(os.listdir(OUT)):
    if not f.startswith('amb_') or not f.endswith('.ogg'):
        continue
    x = dsp.decode(os.path.join(OUT, f)).mean(axis=1)
    seam = abs(float(x[0]) - float(x[-1]))
    rms = float(np.sqrt(np.mean(x ** 2))) + 1e-15
    peak = float(np.max(np.abs(x))) + 1e-15
    d = np.abs(np.diff(x))
    med, p99 = float(np.median(d)) + 1e-15, float(np.percentile(d, 99)) + 1e-15
    print(f'{f[:-4]:<18}{len(x)/SR:>6.1f}{seam:>12.6f}'
          f'{20*math.log10(max(seam,1e-12)/rms):>13.1f}{20*math.log10(max(seam,1e-12)/peak):>14.1f}'
          f'{seam/med:>7.2f}/{seam/p99:>5.2f}')

print('\n=== 雷声：reverb 让时长超出目标 ===')
for k in ('sfx_thunder_far', 'sfx_thunder_mid', 'sfx_thunder_close'):
    p = os.path.join(OUT, k + '.ogg')
    x = dsp.decode(p)
    print(f'  {k}: {len(x)/SR:.2f}s  (目标 6.0/5.5/5.0s)')

print('\n=== 验证交叉淡化构造本身是否严格连续 ===')
# 造一段平滑信号，检查 make_loop 输出的接缝是否等于源里相邻样本差
rng = np.random.default_rng(3)
n_sig = int(30.5 * SR)
src = dsp.pink(n_sig, rng=rng) * dsp.smooth_random(n_sig, SR, 0.2, 0.5, 1.0, rng=rng)
src = dsp.fft_filter(src, SR, lo=60, hi=9000)
nf = int(0.5 * SR)
L = len(src) - nf
y = dsp.make_loop(src, SR, 0.5)
seam_out = abs(float(y[0]) - float(y[-1]))
seam_src = abs(float(src[L]) - float(src[L - 1]))
print(f'  make_loop 输出接缝 = {seam_out:.8f}')
print(f'  源信号在拼接点相邻差 = {seam_src:.8f}')
print(f'  是否完全一致: {abs(seam_out - seam_src) < 1e-9}')

print('\n=== 交叉淡化内部两个拐点是否也连续 ===')
# 拐点1: 淡变区结束处 nt = nf-1 -> nf
print(f'  y[nf-1]={y[nf-1]:.8f} y[nf]={y[nf]:.8f} 差={abs(y[nf]-y[nf-1]):.8f}')
print(f'  源相邻差量级中位数={np.median(np.abs(np.diff(src))):.8f}')
