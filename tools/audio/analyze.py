"""
音频素材分析工具（bundled python + numpy）
用 ffmpeg 解码任意格式为 float32 PCM，避免依赖 soundfile/librosa。
输出：时长 / 峰值 dBFS / RMS dBFS / 直流偏移 / 频谱质心 / 谱平坦度 / 瞬态密度 / 循环接缝差
用法:
  python analyze.py <file_or_dir> [--json out.json]
  python analyze.py <dir> --glob *.ogg
"""
import os, sys, json, subprocess, glob, math
import numpy as np

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
SR = 44100


def decode(path, sr=SR, channels=None):
    """用 ffmpeg 解码成 float32 numpy，返回 (data[n, ch] or [n], sr, ch)"""
    cmd = [FFMPEG, '-v', 'error', '-i', path, '-f', 'f32le', '-acodec', 'pcm_f32le', '-ar', str(sr)]
    if channels:
        cmd += ['-ac', str(channels)]
    cmd += ['-']
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f'ffmpeg failed on {path}: {p.stderr.decode("utf-8", "replace")[:400]}')
    raw = np.frombuffer(p.stdout, dtype='<f4')
    # 探测通道数
    ch = channels
    if ch is None:
        probe = subprocess.run([FFMPEG.replace('ffmpeg', 'ffprobe'), '-v', 'error', '-select_streams', 'a:0',
                                '-show_entries', 'stream=channels,sample_rate', '-of', 'json', path],
                               capture_output=True)
        try:
            info = json.loads(probe.stdout.decode('utf-8', 'replace'))['streams'][0]
            ch = int(info['channels'])
        except Exception:
            ch = 1
    n = len(raw) // ch
    data = raw[:n * ch].reshape(n, ch) if ch > 1 else raw[:n]
    return data, sr, ch


def db(x):
    return 20.0 * math.log10(max(float(x), 1e-12))


def metrics(path, do_spectral=True):
    data, sr, ch = decode(path)
    mono = data.mean(axis=1) if data.ndim > 1 else data
    n = len(mono)
    if n == 0:
        return {'file': path, 'error': 'empty'}
    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(mono ** 2)))
    dc = float(np.mean(mono))
    out = {
        'file': os.path.basename(path),
        'path': path,
        'dur': round(n / sr, 3),
        'ch': ch,
        'sr': sr,
        'peak_dbfs': round(db(peak), 2),
        'rms_dbfs': round(db(rms), 2),
        'crest_db': round(db(peak) - db(rms), 2),
        'dc_offset': round(dc, 6),
        'clipped_pct': round(float(np.mean(np.abs(mono) >= 0.999)) * 100, 4),
    }

    # --- 循环接缝：首尾样本差 + 首尾 50ms RMS 落差 ---
    w = min(int(0.05 * sr), n // 2)
    if w > 8:
        head = mono[:w]
        tail = mono[-w:]
        seam = abs(float(mono[0]) - float(mono[-1]))
        hrms = float(np.sqrt(np.mean(head ** 2)))
        trms = float(np.sqrt(np.mean(tail ** 2)))
        out['seam_sample_diff'] = round(seam, 6)
        out['seam_db'] = round(db(seam), 2)
        out['head_rms_dbfs'] = round(db(hrms), 2)
        out['tail_rms_dbfs'] = round(db(trms), 2)
        out['head_tail_rms_delta_db'] = round(db(hrms) - db(trms), 2)
        # 首尾波形差（循环拼接点的能量跳变）
        out['seam_step_rms'] = round(float(np.sqrt(np.mean((head - tail) ** 2))), 6)

    if do_spectral:
        # --- 频谱特征（中位帧）---
        nfft = 2048
        hop = 1024
        if n >= nfft:
            frames = np.lib.stride_tricks.sliding_window_view(mono, nfft)[::hop] * np.hanning(nfft)
            mag = np.abs(np.fft.rfft(frames, axis=1)) + 1e-10
            freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
            psd = (mag ** 2).mean(axis=0)
            centroid = float(np.sum(freqs * psd) / np.sum(psd))
            # 谱平坦度（1=白噪，0=纯音）—— 判"像不像噪音"
            flat = float(np.exp(np.mean(np.log(mag.mean(axis=0)))) / np.mean(mag.mean(axis=0)))
            out['spectral_centroid_hz'] = round(centroid, 1)
            out['spectral_flatness'] = round(flat, 5)
            # 低频 (<200Hz) / 中频 / 高频能量占比
            tot = np.sum(psd) + 1e-12
            band = lambda lo, hi: float(np.sum(psd[(freqs >= lo) & (freqs < hi)]) / tot)
            out['band_low'] = round(band(20, 200), 4)
            out['band_mid'] = round(band(200, 2000), 4)
            out['band_high'] = round(band(2000, 20000), 4)

            # --- 瞬态密度：帧能量包络超过中位数 2.5 倍的帧占比 ---
            env = np.sqrt(np.sum(mag ** 2, axis=1))
            if len(env) > 4:
                med = np.median(env) + 1e-12
                out['transient_density'] = round(float(np.mean(env > med * 2.5)), 4)
            # 静音占比
            en_db = 20 * np.log10(env / (env.max() + 1e-12) + 1e-12)
            out['silence_pct'] = round(float(np.mean(en_db < -50)) * 100, 2)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    json_out = None
    if '--json' in sys.argv:
        json_out = sys.argv[sys.argv.index('--json') + 1]
    g = '*.ogg'
    if '--glob' in sys.argv:
        g = sys.argv[sys.argv.index('--glob') + 1]

    files = []
    for a in args:
        if os.path.isdir(a):
            files += sorted(glob.glob(os.path.join(a, '**', g), recursive=True))
        elif os.path.isfile(a):
            files.append(a)
    if not files:
        print('no files')
        return

    rows = []
    for f in files:
        try:
            m = metrics(f)
            rows.append(m)
            print(f"{m['file'][:44]:<44} {m['dur']:>7.2f}s {m['ch']}ch "
                  f"pk{m['peak_dbfs']:>6.1f} rms{m['rms_dbfs']:>6.1f} crest{m['crest_db']:>5.1f} "
                  f"ctr{m.get('spectral_centroid_hz', 0):>7.0f}Hz flat{m.get('spectral_flatness', 0):.4f} "
                  f"tr{m.get('transient_density', 0):.2f} sil{m.get('silence_pct', 0):>5.1f}%")
        except Exception as e:
            print(f'{os.path.basename(f)[:44]:<44} ERROR {e}')
            rows.append({'file': os.path.basename(f), 'path': f, 'error': str(e)})

    if json_out:
        with open(json_out, 'w', encoding='utf-8') as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        print(f'\nwrote {json_out} ({len(rows)} rows)')


if __name__ == '__main__':
    main()
