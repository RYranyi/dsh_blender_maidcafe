"""
dsp.py —— 无外部依赖的音频 DSP 基础库（bundled python 3.12 + numpy 2.3.5，环境无 scipy）

设计要点
--------
* 所有滤波走 **FFT 零相位** 实现（离线处理，不需要 sample-by-sample 循环）：
  幅度响应直接按巴特沃斯 |H| = 1/sqrt(1+(f/fc)^(2*order)) 施加，再 irfft。
  这样既避免 numpy 里慢速 python 循环，也没有相位失真，适合噪声/环境床。
* 循环全部用 **等功率交叉淡化拼接**（make_loop）：不是砍尾巴，而是把额外生成的
  xfade 段用 cos/sin 曲线融回开头，保证 loop 点前后波形连续、能量恒定。
* 编解码统一走本机 ffmpeg 8.1.3（libvorbis），中间 wav 只落 .scratch 临时目录。
"""
import os
import json
import math
import subprocess
import numpy as np

FFMPEG = r'E:\dsh\.tools\MinGit\cmd\ffmpeg.exe'
FFPROBE = r'E:\dsh\.tools\MinGit\cmd\ffprobe.exe'
SR = 44100
TMP = r'E:\dsh\maid_cafe\.scratch\audio-dev\tmp'

os.makedirs(TMP, exist_ok=True)


# ============================================================ I/O
def probe(path):
    p = subprocess.run([FFPROBE, '-v', 'error', '-select_streams', 'a:0',
                        '-show_entries', 'stream=channels,sample_rate,duration',
                        '-of', 'json', str(path)], capture_output=True)
    try:
        st = json.loads(p.stdout.decode('utf-8', 'replace'))['streams'][0]
        return {'channels': int(st.get('channels', 1)),
                'sample_rate': int(st.get('sample_rate', SR)),
                'duration': float(st.get('duration', 0) or 0)}
    except Exception:
        return {'channels': 1, 'sample_rate': SR, 'duration': 0.0}


def decode(path, sr=SR, start=None, dur=None):
    """解码任意格式 -> float32 ndarray，形状恒为 (n, ch)。"""
    info = probe(path)
    ch = max(1, info['channels'])
    cmd = [FFMPEG, '-v', 'error']
    if start is not None:
        cmd += ['-ss', f'{start:.6f}']
    if dur is not None:
        cmd += ['-t', f'{dur:.6f}']
    cmd += ['-i', str(path), '-f', 'f32le', '-acodec', 'pcm_f32le',
            '-ar', str(sr), '-ac', str(ch), '-']
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f'decode failed {path}: {p.stderr.decode("utf-8", "replace")[:300]}')
    raw = np.frombuffer(p.stdout, dtype='<f4')
    n = len(raw) // ch
    data = raw[:n * ch].reshape(n, ch).astype(np.float64)
    return data


def write_ogg(x, sr, out_path, quality=5):
    """把 numpy 音频编码成真 Ogg Vorbis（libvorbis）。"""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    ch = x.shape[1]
    # 整形到 int32 PCM 写 wav（无损中转）
    wav_path = os.path.join(TMP, f'_enc_{os.getpid()}_{abs(hash(out_path)) % 100000}.wav')
    pcm = np.clip(x, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype('<i2')
    import wave
    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    cmd = [FFMPEG, '-v', 'error', '-y', '-i', wav_path,
           '-c:a', 'libvorbis', '-q:a', str(quality), '-ar', str(sr), '-ac', str(ch), out_path]
    p = subprocess.run(cmd, capture_output=True)
    try:
        os.remove(wav_path)
    except OSError:
        pass
    if p.returncode != 0:
        raise RuntimeError(f'encode failed {out_path}: {p.stderr.decode("utf-8", "replace")[:300]}')
    return out_path


# ============================================================ 基础测量
def db(x):
    return 20.0 * math.log10(max(float(np.max(np.abs(x))), 1e-12))


def rms_db(x):
    return 20.0 * math.log10(max(float(np.sqrt(np.mean(np.square(x)))), 1e-12))


def peak_db(x):
    return 20.0 * math.log10(max(float(np.max(np.abs(x))), 1e-12))


def crest_db(x):
    return peak_db(x) - rms_db(x)


# ============================================================ 滤波（FFT 零相位）
def fft_filter(x, sr, lo=None, hi=None, order=2):
    """
    零相位带通/低通/高通。lo/hi 单位 Hz，None 表示不限。
    order 决定斜率（order=2 -> 12dB/oct）。
    x: (n,) 或 (n,ch)
    """
    x = np.asarray(x, dtype=np.float64)
    one_d = x.ndim == 1
    if one_d:
        x = x[:, None]
    n = x.shape[0]
    if n < 8:
        return x[:, 0] if one_d else x
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    f = np.maximum(freqs, 1e-6)
    mag = np.ones_like(freqs)
    if hi is not None:
        mag *= 1.0 / np.sqrt(1.0 + (f / float(hi)) ** (2 * order))
    if lo is not None:
        # 高通：1 - 低通的幅度形状（近似，保证单调）
        hp = 1.0 / np.sqrt(1.0 + (float(lo) / f) ** (2 * order))
        mag *= hp
    mag[0] = 0.0  # 去直流
    out = np.empty_like(x)
    for c in range(x.shape[1]):
        spec = np.fft.rfft(x[:, c])
        out[:, c] = np.fft.irfft(spec * mag, n)
    return out[:, 0] if one_d else out


def band_energy(x, sr, bands=((20, 120), (120, 400), (400, 1200), (1200, 4000), (4000, 16000))):
    """返回各频带能量占比，用于判断"轻/中/重"雨声该选哪条素材。"""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    spec = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    tot = float(spec.sum()) + 1e-20
    return [(round(lo), round(hi), round(float(spec[(freqs >= lo) & (freqs < hi)].sum() / tot), 4))
            for lo, hi in bands]


# ============================================================ 噪声源
def colored_noise(n, sr, exponent=1.0, rng=None):
    """
    exponent=0 白噪（功率平坦）/ 1 粉红（1/f）/ 2 布朗（1/f^2）
    频域塑形，一次 rfft/irfft 完成。
    """
    rng = rng or np.random.default_rng()
    w = rng.standard_normal(n)
    spec = np.fft.rfft(w)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    f = np.maximum(freqs, 1.0)
    spec = spec * (f ** (-exponent / 2.0))
    spec[0] = 0.0
    out = np.fft.irfft(spec, n)
    m = np.max(np.abs(out)) + 1e-12
    return out / m


def white(n, rng=None):
    rng = rng or np.random.default_rng()
    return rng.standard_normal(n)


def pink(n, rng=None):
    return colored_noise(n, SR, exponent=1.0, rng=rng)


def brown(n, rng=None):
    return colored_noise(n, SR, exponent=2.0, rng=rng)


# ============================================================ 包络 / 调制
def env_exp(n, sr, attack=0.01, decay=0.3, curve=4.0):
    t = np.arange(n) / sr
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    attack_env = 1.0 - np.exp(-t / max(attack, 1e-4) * 3.0)
    d = np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-4) * (curve / 4.0))
    return attack_env * d


def env_adsr(n, sr, attack=0.005, decay=0.1, sustain=0.6, release=0.2):
    t = np.arange(n) / sr
    dur = n / sr
    e = np.zeros(n)
    for i, tt in enumerate(t):
        if tt < attack:
            e[i] = tt / max(attack, 1e-5)
        elif tt < attack + decay:
            k = (tt - attack) / max(decay, 1e-5)
            e[i] = 1.0 + (sustain - 1.0) * k
        elif tt < dur - release:
            e[i] = sustain
        else:
            k = (tt - (dur - release)) / max(release, 1e-5)
            e[i] = sustain * (1.0 - k)
    return np.clip(e, 0, 1)


def smooth_random(n, sr, rate_hz=0.35, lo=0.0, hi=1.0, rng=None, smooth=True):
    """低频平滑随机曲线（用于阵风/人流密度等缓慢起伏）。"""
    rng = rng or np.random.default_rng()
    npts = max(2, int(n / sr * rate_hz) + 2)
    pts = rng.uniform(lo, hi, npts)
    xs = np.linspace(0, n - 1, npts)
    out = np.interp(np.arange(n), xs, pts)
    if smooth and n > 32:
        # 三角平滑，避免折线感
        w = max(3, int(sr * 0.08))
        k = np.hanning(w * 2 + 1)
        k /= k.sum()
        out = np.convolve(out, k, mode='same')
    return out


def lfo(n, sr, freq=0.13, phase=0.0, lo=0.0, hi=1.0):
    t = np.arange(n) / sr
    return lo + (hi - lo) * (0.5 + 0.5 * np.sin(2 * math.pi * freq * t + phase))


# ============================================================ 合成原语
def modal(freqs, decays, amps, dur, sr=SR):
    """
    模态共振合成：多个指数衰减正弦叠加。
    杯碟/铃/玻璃/金属的短促撞击都用它（非谐分音比例决定"材质感"）。
    """
    n = int(dur * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    for f, d, a in zip(freqs, decays, amps):
        out += a * np.exp(-t / max(d, 1e-5)) * np.sin(2 * math.pi * f * t)
    return out


def noise_burst(dur, sr=SR, rng=None, attack=0.001, decay=0.05, lo=None, hi=None):
    rng = rng or np.random.default_rng()
    n = int(dur * sr)
    x = rng.standard_normal(n)
    x = fft_filter(x, sr, lo=lo, hi=hi, order=2)
    e = env_exp(n, sr, attack=attack, decay=decay, curve=3.0)
    x = x * e
    m = np.max(np.abs(x)) + 1e-12
    return x / m


def fftconvolve(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    n = len(a) + len(b) - 1
    N = 1 << int(math.ceil(math.log2(max(n, 2))))
    A = np.fft.rfft(a, N)
    B = np.fft.rfft(b, N)
    return np.fft.irfft(A * B, N)[:n]


def make_ir(dur=1.6, sr=SR, decay=0.45, damp=3500.0, predelay=0.012, rng=None):
    """
    合成混响脉冲响应：早期反射 + 频率相关衰减（高频衰减更快，模拟空气吸收）。
    """
    rng = rng or np.random.default_rng()
    n = int(dur * sr)
    t = np.arange(n) / sr
    noise = rng.standard_normal(n)
    lp = fft_filter(noise, sr, hi=damp, order=2)
    hp = fft_filter(noise, sr, lo=max(damp * 0.6, 200), order=1)
    ir = lp * np.exp(-t / max(decay * 1.35, 1e-3)) + 0.45 * hp * np.exp(-t / max(decay * 0.45, 1e-3))
    # 早期反射（几个离散敲击）
    for k in range(4):
        idx = int((0.004 + k * 0.009) * sr)
        if idx < n:
            ir[idx] += (0.5 - k * 0.1) * (1 - 2 * (k % 2))
    ir = np.concatenate([np.zeros(int(predelay * sr)), ir])
    e = np.sqrt(np.sum(ir ** 2)) + 1e-12
    return ir / e


def reverb(x, ir, wet=0.25, dry=1.0):
    """干湿混合混响；x 可为 (n,) 或 (n,ch)。"""
    x = np.asarray(x, dtype=np.float64)
    one_d = x.ndim == 1
    if one_d:
        x = x[:, None]
    out = np.zeros((len(x) + len(ir) - 1, x.shape[1]))
    for c in range(x.shape[1]):
        out[:, c] = fftconvolve(x[:, c], ir)[:len(out)]
    out = out * wet + np.pad(x, ((0, len(out) - len(x)), (0, 0))) * dry
    return out[:, 0] if one_d else out


# ============================================================ 立体声 / 混合 / 摆放
def to_stereo(x, width=1.0, sr=SR, rng=None, delay_ms=6.0):
    """单声道 -> 立体声；噪声类用轻微去相关获得自然宽度。"""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        if x.shape[1] == 2:
            if width >= 0.999:
                return x
            m = x.mean(axis=1, keepdims=True)
            return m + (x - m) * width
        x = x[:, 0]
    d = int(sr * delay_ms / 1000.0)
    if d < 1 or width <= 1e-6:
        return np.stack([x, x], axis=1)
    right = np.concatenate([np.zeros(d), x[:-d]]) if d < len(x) else x
    r = x * (1 - width * 0.55) + right * (width * 0.55)
    return np.stack([x, r], axis=1)


def mix_layers(n, layers):
    """
    layers: [(signal, gain_db, pan)] -> 立体声 (n,2)
    pan: -1 左 .. +1 右
    """
    out = np.zeros((n, 2))
    for sig, gain_db, pan in layers:
        s = np.asarray(sig, dtype=np.float64)
        if s.ndim == 1:
            s = np.stack([s, s], axis=1)
        if len(s) < n:
            s = np.pad(s, ((0, n - len(s)), (0, 0)))
        s = s[:n]
        gl = math.sqrt(0.5 * (1.0 - pan))
        gr = math.sqrt(0.5 * (1.0 + pan))
        g = 10 ** (gain_db / 20.0)
        out[:, 0] += s[:, 0] * g * gl * math.sqrt(2)
        out[:, 1] += s[:, 1] * g * gr * math.sqrt(2)
    return out


def place(buf, sig, at_sec, sr=SR, gain_db=0.0, pan=0.0):
    """
    把一个单声道/立体声片段叠加到缓冲区指定时间（就地修改）。
    目标缓冲可以是 (n,) 单声道或 (n,2) 立体声；单声道时把声像折叠成能量和。
    """
    s = np.asarray(sig, dtype=np.float64)
    if s.ndim == 1:
        s = np.stack([s, s], axis=1)
    i0 = int(at_sec * sr)
    if i0 < 0:
        s = s[-i0:]
        i0 = 0
    n = min(len(buf) - i0, len(s))
    if n <= 0:
        return buf
    gl = math.sqrt(0.5 * (1.0 - pan)) * math.sqrt(2)
    gr = math.sqrt(0.5 * (1.0 + pan)) * math.sqrt(2)
    g = 10 ** (gain_db / 20.0)
    if buf.ndim == 1:
        buf[i0:i0 + n] += (s[:n, 0] * gl + s[:n, 1] * gr) * g * 0.5
    elif buf.shape[1] == 1:
        buf[i0:i0 + n, 0] += (s[:n, 0] * gl + s[:n, 1] * gr) * g * 0.5
    else:
        buf[i0:i0 + n, 0] += s[:n, 0] * g * gl
        buf[i0:i0 + n, 1] += s[:n, 1] * g * gr
    return buf


# ============================================================ 循环拼接
def make_loop(x, sr=SR, xfade_s=0.5):
    """
    等功率交叉淡化循环（把接缝"包"进淡变区，因此循环点处波形连续）。

    输入长度 = L + nf，输出长度 = L：
      out[i] = x[L+i]*cos(θ) + x[i]*sin(θ) ,  0 <= i < nf    ← 淡变区
      out[i] = x[i]                        ,  nf <= i < L   ← 主体

    接缝连续性证明：loop 点 out[L-1] -> out[0]，
    out[L-1] = x[L-1]（源里紧邻 x[L]），而 out[0] = x[L]；
    因为 x[L-1] -> x[L] 在源信号里本来就连续，所以接缝无跳变。
    cos/sin 权重满足 cos²+sin²=1，两段不相关素材叠加时能量恒定（等功率）。
    """
    x = np.asarray(x, dtype=np.float64)
    one_d = x.ndim == 1
    if one_d:
        x = x[:, None]
    nf = int(xfade_s * sr)
    L = len(x) - nf
    if L <= nf:
        raise ValueError('signal too short for crossfade')
    theta = np.linspace(0.0, math.pi / 2.0, nf)[:, None]
    fade_head = np.cos(theta)   # 对新接续段（x[L:L+nf]）的权重：1 -> 0
    fade_old = np.sin(theta)    # 对原开头（x[0:nf]）的权重：0 -> 1
    head = x[L:L + nf] * fade_head + x[0:nf] * fade_old
    body = x[nf:L]
    out = np.concatenate([head, body], axis=0)
    return out[:, 0] if one_d else out


def loop_seam_report(x, sr=SR):
    """
    QC：判断循环是否真的无缝（不会爆音）。

    判据分两层：
    1) **数学连续性**：接缝跳变应等于"源信号在拼接点处的相邻采样差"——
       交叉淡化构造保证这一点，输出接缝与源内部任意采样边界不可区分。
       这里用 **接缝跳变 vs 本文件相邻采样差分布** 来衡量：
       只要 <= 该文件 99 分位步进，就说明它落在自然波形跳变的正常范围内。
    2) **能量连续性**：首尾 50ms 的 RMS 不应有明显落差（淡变后能量要接得上）。
    """
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    n = len(x)
    w = min(int(0.05 * sr), n // 4)

    seam_step = abs(float(x[0]) - float(x[-1]))
    d = np.abs(np.diff(x))
    d_p50 = float(np.percentile(d, 50)) + 1e-12
    d_p99 = float(np.percentile(d, 99)) + 1e-12
    d_max = float(np.max(d)) + 1e-12

    # 接缝附近的局部步进参考（真正决定"听起来是否突兀"的量）
    k = min(int(0.05 * sr), n // 4)
    local = np.concatenate([d[:k], d[-k:]])
    d_local_rms = float(np.sqrt(np.mean(local ** 2))) + 1e-12

    def r(v):
        return 20 * math.log10(float(np.sqrt(np.mean(v ** 2))) + 1e-12)
    head_r, tail_r = r(x[:w]), r(x[-w:])

    ratio_p99 = seam_step / d_p99
    ratio_local = seam_step / d_local_rms
    return {
        'seam_step': round(seam_step, 8),
        'step_p50': round(d_p50, 8),
        'step_p99': round(d_p99, 8),
        'seam_vs_p50_step': round(seam_step / d_p50, 2),
        'seam_vs_p99_step': round(ratio_p99, 3),
        'seam_vs_local_step_rms': round(ratio_local, 3),
        # 判据：接缝跳变落在文件自身自然步进范围内，且相对局部步进不突出
        'seam_ok': bool(ratio_p99 <= 1.0 and ratio_local <= 2.5),
        'head_rms_db': round(head_r, 2),
        'tail_rms_db': round(tail_r, 2),
        'head_tail_delta_db': round(head_r - tail_r, 2),
        'energy_ok': bool(abs(head_r - tail_r) <= 3.0),
    }


# ============================================================ 响度整形
def normalize_rms(x, target_db=-20.0):
    r = np.sqrt(np.mean(np.square(x))) + 1e-12
    return x * (10 ** (target_db / 20.0) / r)


def soft_limit(x, ceiling_db=-3.0, knee=0.5):
    """
    峰值保底：tanh 软膝压缩 + 最终严格缩放，保证 max|x| <= ceiling。
    比硬切干净，不会引入刺耳谐波。
    """
    x = np.asarray(x, dtype=np.float64)
    ceiling = 10 ** (ceiling_db / 20.0)
    pk = np.max(np.abs(x)) + 1e-12
    if pk <= ceiling:
        return x
    # 软膝：绝对值超过 knee*ceiling 的部分用 tanh 弯折
    k = ceiling * max(1.0 - knee, 0.05)
    room = ceiling - k
    a = np.abs(x)
    above = a > k
    out = x.copy()
    over = a[above] - k
    out[above] = np.sign(x[above]) * (k + room * np.tanh(over / max(room, 1e-9)))
    # 兜底严格缩放（tanh 已保证有界，这里只是数学上必成立）
    m = np.max(np.abs(out)) + 1e-12
    if m > ceiling:
        out *= ceiling / m
    return out


def fade_edges(x, sr, ms_in=20.0, ms_out=20.0):
    """给 one-shot 加淡入淡出，避免播放瞬间咔哒。支持 (n,) 与 (n,ch)。"""
    x = np.array(x, dtype=np.float64, copy=True)
    if len(x) < 4:
        return x
    ni = min(int(sr * ms_in / 1000), len(x) // 2)
    no = min(int(sr * ms_out / 1000), len(x) // 2)
    if ni > 1:
        ramp_in = (np.linspace(0, 1, ni) ** 1.5)
        if x.ndim > 1:
            ramp_in = ramp_in[:, None]
        x[:ni] *= ramp_in
    if no > 1:
        ramp_out = (np.linspace(1, 0, no) ** 1.5)
        if x.ndim > 1:
            ramp_out = ramp_out[:, None]
        x[-no:] *= ramp_out
    return x


def trim_tail(x, sr, threshold_db=-70.0, keep_ms=30.0):
    """裁掉尾部静音（one-shot 用），保留一点余韵。"""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        env = np.max(np.abs(x), axis=1)
    else:
        env = np.abs(x)
    thr = 10 ** (threshold_db / 20.0) * (np.max(env) + 1e-12)
    idx = np.where(env > thr)[0]
    if len(idx) == 0:
        return x
    end = min(len(x), idx[-1] + int(sr * keep_ms / 1000))
    return x[:end]


def resample_len(x, n_target):
    """线性重采样到指定长度（用于把素材拉成整数小节）。"""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n == n_target:
        return x
    xi = np.linspace(0, n - 1, n_target)
    if x.ndim > 1:
        return np.stack([np.interp(xi, np.arange(n), x[:, c]) for c in range(x.shape[1])], axis=1)
    return np.interp(xi, np.arange(n), x)


# ============================================================ 节拍对齐（音乐床用）
def estimate_bpm(x, sr=SR, lo=60, hi=180):
    """用起音包络自相关估 BPM（音乐循环对齐小节用）。"""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    env = np.abs(x)
    hop = 256
    n = len(env) // hop
    if n < 32:
        return None
    frames = env[:n * hop].reshape(n, hop)
    # 起音 = 帧能量的一阶正差分
    e = np.sqrt(np.mean(frames ** 2, axis=1))
    onset = np.maximum(np.diff(e), 0)
    onset = onset - onset.mean()
    ac = np.correlate(onset, onset, mode='full')[len(onset) - 1:]
    fr = sr / hop
    lag_lo, lag_hi = int(fr * 60.0 / hi), int(fr * 60.0 / lo)
    if lag_hi >= len(ac):
        return None
    seg = ac[lag_lo:lag_hi]
    if not np.any(seg > 0):
        return None
    best = lag_lo + int(np.argmax(seg))
    return 60.0 * fr / best
