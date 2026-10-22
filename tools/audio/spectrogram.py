"""
频谱图工具：把音频渲染成 PNG（对数频率 + dB 色阶），用于"看一眼"验证内容形态。
用法: python spectrogram.py <audio> <out.png> [--dur 10] [--start 0] [--fmax 8000] [--w 1200] [--h 420]
"""
import os, sys, json, subprocess, math
import numpy as np
from PIL import Image, ImageDraw

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def decode(path, sr=22050, start=None, dur=None):
    cmd = [FFMPEG, '-v', 'error']
    if start is not None:
        cmd += ['-ss', str(start)]
    if dur is not None:
        cmd += ['-t', str(dur)]
    cmd += ['-i', path, '-f', 'f32le', '-acodec', 'pcm_f32le', '-ar', str(sr), '-ac', '1', '-']
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode('utf-8', 'replace')[:400])
    return np.frombuffer(p.stdout, dtype='<f4').copy(), sr


def render(path, out_png, dur=None, start=None, fmax=8000, W=1200, H=420, log_freq=True, sr=22050):
    x, sr = decode(path, sr=sr, start=start, dur=dur)
    if len(x) < 2048:
        raise RuntimeError('too short')
    nfft = 2048
    hop = max(64, (len(x) - nfft) // W or 1)
    frames = np.lib.stride_tricks.sliding_window_view(x, nfft)[::hop][:W]
    # 短音频帧数不足 W 时补零帧，保证输出尺寸固定
    if len(frames) < W:
        pad = np.zeros((W - len(frames), nfft), dtype=frames.dtype)
        frames = np.vstack([frames, pad])
    win = np.hanning(nfft)
    mag = np.abs(np.fft.rfft(frames * win, axis=1))
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    db = 20 * np.log10(mag + 1e-9)
    # 每张图自适应动态范围：以 99 分位为上限、-70dB 为下限，避免整幅过曝
    hi = np.percentile(db, 99.5)
    db = np.clip((db - (hi - 70.0)) / 70.0, 0, 1)

    if log_freq:
        # 对数频率映射到像素行
        ys = np.geomspace(20, fmax, H)
        idx = np.searchsorted(freqs, ys).clip(0, len(freqs) - 1)
        img_data = db[:, idx].T[::-1]  # [H, W]
    else:
        idx = np.searchsorted(freqs, np.linspace(0, fmax, H)).clip(0, len(freqs) - 1)
        img_data = db[:, idx].T[::-1]

    # plasma 风格色阶
    stops = np.array([[0.05, 0.02, 0.15], [0.35, 0.05, 0.45], [0.85, 0.20, 0.35],
                      [1.0, 0.55, 0.15], [1.0, 0.95, 0.60]])
    pos = np.array([0.0, 0.3, 0.58, 0.8, 1.0])
    flat = img_data.ravel()
    rgb = np.stack([np.interp(flat, pos, stops[:, c]) for c in range(3)], axis=1)
    rgb = (rgb.reshape(H, W, 3) * 255).astype(np.uint8)
    im = Image.fromarray(rgb, 'RGB').resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    # 时间轴刻度
    total = len(x) / sr
    for k in range(0, 11):
        px = int(k / 10 * W)
        d.line([(px, H - 8), (px, H)], fill=(255, 255, 255), width=1)
        d.text((px + 2, H - 18), f'{total * k / 10:.1f}s', fill=(255, 255, 255))
    d.text((4, 4), f'{os.path.basename(path)}  fmax={fmax}Hz  dur={total:.2f}s', fill=(255, 255, 255))
    im.save(out_png)
    return out_png, total, len(x)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opt = {}
    for i, a in enumerate(sys.argv):
        if a.startswith('--'):
            opt[a[2:]] = sys.argv[i + 1]
    p = render(args[0], args[1],
               dur=float(opt['dur']) if 'dur' in opt else None,
               start=float(opt['start']) if 'start' in opt else None,
               fmax=int(opt.get('fmax', 8000)),
               W=int(opt.get('w', 1200)), H=int(opt.get('h', 420)))
    print('OK', p)
