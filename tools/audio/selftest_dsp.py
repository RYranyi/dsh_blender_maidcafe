# 快速自测 dsp.py：交叉淡化接缝 / 滤波器响应 / 模态合成
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import dsp

SR = dsp.SR
rng = np.random.default_rng(7)

print('=== 1) 交叉淡化循环接缝测试（理想情况：接缝跳变应远低于主体电平）===')
# 平滑噪声床：粉噪 + 慢调制
n = int(30.5 * SR)
x = dsp.pink(n, rng=rng) * dsp.smooth_random(n, SR, 0.2, 0.5, 1.0, rng=rng)
x = dsp.fft_filter(x, SR, lo=80, hi=9000)
x = dsp.normalize_rms(x, -20)
y = dsp.make_loop(x, SR, xfade_s=0.5)
rep = dsp.loop_seam_report(y, SR)
print('  loop len =', len(y) / SR, 's')
print(' ', json.dumps(rep, ensure_ascii=False))
print('  -> 判定：seam_step_rel_db < -40dB 视为无爆音')

print('\n=== 2) 对照：暴力截断（不交叉淡化）的接缝 ===')
y_bad = x[:int(30 * SR)]
rep_bad = dsp.loop_seam_report(y_bad, SR)
print(' ', json.dumps(rep_bad, ensure_ascii=False))

print('\n=== 3) FFT 滤波器响应验证 ===')
w = dsp.white(SR, rng=rng)
for lo, hi in [(None, 200), (200, None), (300, 3000)]:
    f = dsp.fft_filter(w, SR, lo=lo, hi=hi, order=2)
    bands = dsp.band_energy(f, SR)
    print(f'  lo={lo} hi={hi} -> bands(20-120,120-400,400-1200,1200-4k,4k-16k) =',
          [b[2] for b in bands])

print('\n=== 4) 模态合成：杯碟碰撞 ===')
cup = dsp.modal([1850, 2740, 3920, 5230], [0.22, 0.16, 0.11, 0.07],
                [1.0, 0.6, 0.35, 0.2], 0.8, SR)
cup += dsp.noise_burst(0.8, SR, rng=rng, attack=0.0008, decay=0.012, lo=2500, hi=14000) * 0.35
cup = dsp.fade_edges(cup, SR, 1, 30)
print('  cup peak_db =', round(dsp.peak_db(cup), 2), 'rms_db =', round(dsp.rms_db(cup), 2))

print('\n=== 5) 混响 IR ===')
ir = dsp.make_ir(1.6, SR, 0.45, 3500, rng=rng)
print('  IR len', len(ir) / SR, 's  energy', round(float(np.sum(ir ** 2)), 4))

print('\n=== 6) soft_limit 峰值保底 ===')
hot = x * 8
lim = dsp.soft_limit(hot, ceiling_db=-3.0)
print('  输入峰值', round(dsp.peak_db(hot), 2), 'dB -> 限幅后', round(dsp.peak_db(lim), 2), 'dB')

print('\n=== 7) 编码往返（ogg -> decode 应保持时长/电平）===')
tmp_ogg = os.path.join(dsp.TMP, 'selftest.ogg')
st = dsp.to_stereo(dsp.normalize_rms(y, -20), width=0.9)
dsp.write_ogg(st, SR, tmp_ogg, quality=5)
back = dsp.decode(tmp_ogg)
print('  写出', os.path.getsize(tmp_ogg) / 1024, 'KB  时长', round(len(back) / SR, 3), 's',
      ' rms', round(dsp.rms_db(back.mean(axis=1)), 2), 'dB')
