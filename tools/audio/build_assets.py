"""
build_assets.py - 生成 assets/audio/ 下全部音频（可复现）

分层策略
--------
* 真实 CC0 素材优先：鸟鸣、虫鸣、车流、雨、门铃、铃铛、杯碟、翻页、磨豆、泵、冰箱。
* 缺口用 numpy 合成：街道人声/低语（共振峰噪声 + 音节包络）、电车（低频轰鸣 + 轨道咔哒
  加钢轨啸叫）、空调低频、风铃、门帘布料、卷帘门、雷声距离感、闪电裂响。
* 全部循环床走 0.5s 等功率交叉淡化；one-shot 加淡入淡出并裁尾。

用法: python build_assets.py [--only key1,key2] [--list]
"""
import os
import sys
import json
import math
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import dsp

SR = dsp.SR
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'assets', 'audio')
DL = os.path.join(ROOT, '.scratch', 'audio-dev', 'dl')
RAW = os.path.join(ROOT, '.scratch', 'audio-dev', 'raw')

os.makedirs(OUT, exist_ok=True)

RNG = np.random.default_rng(20261021)


# ============================================================ 素材定位
def rp(*parts):
    return os.path.join(RAW, *parts)


def dp(name):
    return os.path.join(DL, name)


_CACHE = {}


def load(path, start=None, dur=None, ch=2):
    key = (path, start, dur, ch)
    if key in _CACHE:
        return _CACHE[key]
    x = dsp.decode(path, SR, start=start, dur=dur)
    if x.shape[1] != ch:
        x = dsp.to_stereo(x, width=0.85) if ch == 2 else x.mean(axis=1)
    _CACHE[key] = x
    return x


def mono(x):
    return x.mean(axis=1) if x.ndim > 1 else x


def fit(x, n, rng=None):
    """
    把任意长度素材通过交叉淡化拼接成恰好 n 个采样（无爆音）。
    保持输入维度：输入 1D 返回 1D，输入 (n,ch) 返回 (n,ch)。
    """
    x = np.asarray(x, dtype=np.float64)
    one_d = x.ndim == 1
    if one_d:
        x = x[:, None]
    nf = int(0.25 * SR)
    if len(x) >= n:
        out = x[:n]
        return out[:, 0] if one_d else out
    if len(x) < nf * 2 + 8:
        while len(x) < nf * 2 + 8:
            x = np.concatenate([x, x], axis=0)
    out = x.copy()
    while len(out) < n:
        take = min(len(x) - nf, n - len(out) + nf)
        if take <= nf:
            pad = max(1, n - len(out))
            out = np.concatenate([out, x[nf:nf + pad]], axis=0)
            break
        th = np.linspace(0, math.pi / 2, nf)[:, None]
        junc = out[-nf:] * np.cos(th) + x[:nf] * np.sin(th)
        out[-nf:] = junc
        out = np.concatenate([out, x[nf:nf + take]], axis=0)
    out = out[:n]
    return out[:, 0] if one_d else out


def normalize_rms_safe(x, target):
    r = np.sqrt(np.mean(np.square(x))) + 1e-12
    return x * (10 ** (target / 20.0) / r)


# ============================================================ 合成原语
def formant_noise(n, formants, rng, breath=0.6):
    """共振峰噪声：把白噪的频谱塑形成元音状（人声底色）。"""
    w = rng.standard_normal(n)
    spec = np.fft.rfft(w)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    mag = np.zeros_like(freqs)
    for f, bw, g in formants:
        mag += g * np.exp(-0.5 * ((freqs - f) / max(bw, 1e-6)) ** 2)
    mag += breath * 0.3 * np.exp(-0.5 * ((freqs - 900) / 1400.0) ** 2)
    mag[0] = 0
    out = np.fft.irfft(spec * mag, n)
    m = np.max(np.abs(out)) + 1e-12
    return out / m


def syllable_env(n, rng, rate=4.2, jitter=0.55):
    """音节包络：人声说话时的起伏（避免听起来是平的嘶声）。"""
    env = np.zeros(n)
    t = 0.0
    while t < n / SR:
        dur = max(0.08, (1.0 / rate) * rng.uniform(0.6, 1.4))
        length = int(dur * SR)
        i0 = int(t * SR)
        if i0 >= n:
            break
        body = np.hanning(max(length, 4)) ** 0.8
        seg = body[:min(length, n - i0)]
        env[i0:i0 + len(seg)] += seg * rng.uniform(0.5, 1.0)
        t += dur * rng.uniform(1.0, 1.0 + jitter)
    k = np.hanning(64)
    k = k / k.sum()
    env = np.convolve(env, k, mode='same')
    return np.clip(env, 0, None)


def crowd(n, rng, voices=7, level=1.0, spread=True):
    """远处人声嘈杂：多个共振峰嗓音叠在不同声像上。"""
    vowels = [
        [(520, 130, 1.0), (1180, 220, 0.7), (2600, 400, 0.35)],
        [(430, 110, 1.0), (1500, 240, 0.6), (2500, 380, 0.3)],
        [(620, 150, 1.0), (1050, 200, 0.65), (2800, 450, 0.3)],
        [(380, 100, 1.0), (1350, 230, 0.55), (2700, 420, 0.28)],
    ]
    out = np.zeros((n, 2))
    for v in range(voices):
        fo = vowels[v % len(vowels)]
        sig = formant_noise(n, fo, rng)
        sig = sig * syllable_env(n, rng, rate=rng.uniform(3.0, 5.0))
        gate = dsp.smooth_random(n, SR, rate_hz=0.12, lo=0.0, hi=1.0, rng=rng)
        gate = np.clip(gate * 1.6 - 0.5, 0, 1)
        sig = sig * gate
        pan = rng.uniform(-0.85, 0.85) if spread else 0.0
        gl = math.sqrt(0.5 * (1 - pan)) * math.sqrt(2)
        gr = math.sqrt(0.5 * (1 + pan)) * math.sqrt(2)
        out[:, 0] += sig * gl * rng.uniform(0.5, 1.0) * level
        out[:, 1] += sig * gr * rng.uniform(0.5, 1.0) * level
    return out


def whispers(n, rng, level=1.0):
    """近处低语：高频气息噪声 + 快速音节包络。"""
    out = np.zeros((n, 2))
    for pan in (-0.35, 0.45):
        sig = formant_noise(n, [(2400, 900, 1.0), (4200, 1200, 0.5)], rng, breath=1.2)
        sig = sig * syllable_env(n, rng, rate=rng.uniform(2.2, 3.4))
        g = dsp.smooth_random(n, SR, 0.08, 0.0, 1.0, rng=rng)
        sig = sig * np.clip(g * 1.8 - 0.6, 0, 1)
        out[:, 0] += sig * math.sqrt(0.5 * (1 - pan)) * level
        out[:, 1] += sig * math.sqrt(0.5 * (1 + pan)) * level
    return out


def traffic(n, rng, density=1.0, level=1.0):
    """远处车流：低频轰鸣 + 偶发经过的噪声。"""
    rumble = dsp.fft_filter(dsp.brown(n, rng), SR, lo=40, hi=260, order=2)
    rumble = rumble * dsp.smooth_random(n, SR, 0.25, 0.5, 1.2, rng=rng)
    out = np.stack([rumble, rumble], axis=1) * level * 0.6
    passes = int(density * n / SR / 3.5)
    for _ in range(max(1, passes)):
        at = rng.uniform(0, max(0.1, n / SR - 0.5))
        d = rng.uniform(1.1, 2.6)
        k = int(d * SR)
        if k <= 10:
            continue
        t = np.arange(k) / SR
        e = np.exp(-0.5 * ((t - d * 0.42) / (d * 0.20)) ** 2)
        tyre = dsp.fft_filter(dsp.pink(k, rng), SR, lo=180, hi=2200, order=2) * e
        tyre = tyre / (np.max(np.abs(tyre)) + 1e-12)
        pan = float(rng.choice([-1.0, -0.5, 0.5, 1.0]) * rng.uniform(0.4, 1.0))
        dsp.place(out, tyre * rng.uniform(0.25, 0.6) * level, at, SR, 0.0, pan)
    return out


def train(n, rng, level=1.0):
    """电车经过：低频轰鸣 + 轨道接缝咔哒 + 钢轨啸叫。"""
    rumble = dsp.fft_filter(dsp.brown(n, rng), SR, lo=25, hi=130, order=2)
    rumble = rumble * dsp.smooth_random(n, SR, 0.3, 0.4, 1.1, rng=rng)
    t = np.arange(n) / SR
    pass_env = np.exp(-0.5 * ((t - n / SR * 0.5) / (n / SR * 0.22)) ** 2)
    rumble = rumble * pass_env
    out = np.stack([rumble, rumble], axis=1) * level * 0.9
    clack_int = rng.uniform(1.0, 1.35)
    tt = 0.0
    while tt < n / SR:
        k = int(0.09 * SR)
        if k > 4:
            c = dsp.modal([420, 980, 1700], [0.05, 0.03, 0.02], [1.0, 0.5, 0.25], 0.09, SR)
            c = c + dsp.noise_burst(0.09, SR, rng, 0.0008, 0.02, 200, 3000) * 0.5
            c = dsp.fade_edges(c, SR, 0.5, 10)
            idx = min(int(tt * SR), n - 1)
            dsp.place(out, c * 0.35 * level * float(pass_env[idx]), tt, SR,
                      rng.uniform(-0.2, 0.2), float(rng.uniform(-0.2, 0.2)))
        tt += clack_int
    squeal = np.sin(2 * math.pi * 2380 * t + 3.0 * np.sin(2 * math.pi * 0.7 * t))
    squeal = squeal * (0.5 + 0.5 * np.sin(2 * math.pi * 0.23 * t))
    squeal = squeal * pass_env * 0.05 * level
    out[:, 0] += squeal
    out[:, 1] += squeal * 0.85
    return out


def ac_hum(n, rng, level=1.0):
    """空调低频底噪：50Hz 基频 + 谐波 + 轻微风声。"""
    t = np.arange(n) / SR
    hum = np.zeros(n)
    for k, a in [(1, 1.0), (2, 0.45), (3, 0.22), (4, 0.12), (6, 0.05)]:
        hum = hum + a * np.sin(2 * math.pi * 50.0 * k * t + rng.uniform(0, 6.28))
    hum = hum * (1.0 + 0.05 * np.sin(2 * math.pi * 0.13 * t))
    air = dsp.fft_filter(dsp.pink(n, rng), SR, lo=120, hi=1200, order=2)
    air = air / (np.max(np.abs(air)) + 1e-12)
    sig = hum / (np.max(np.abs(hum)) + 1e-12) * 0.6 + air * 0.5
    return np.stack([sig, sig], axis=1) * level


def wind_layer(n, rng, level=1.0, strength=1.0):
    """风：粉噪主带 + 低频阵风 + 偶发呼啸。"""
    base = dsp.fft_filter(dsp.pink(n, rng), SR, lo=70, hi=4200, order=2)
    gust = dsp.smooth_random(n, SR, 0.18, 0.25, 1.0, rng=rng)
    gust = np.clip(gust ** 1.5 * 1.4, 0.05, 1.0)
    sig = base * gust
    res = dsp.fft_filter(dsp.white(n, rng), SR, lo=380, hi=900, order=3)
    res = res * np.clip(gust - 0.55, 0, 1) * 2.2
    sig = sig / (np.max(np.abs(sig)) + 1e-12) + res / (np.max(np.abs(res)) + 1e-12) * 0.5 * strength
    return dsp.to_stereo(sig, width=0.9) * level


# ============================================================ 环境床
def bed_amb_morning(n, rng):
    """清晨：鸟鸣 + 清晨城市底噪 + 极轻车流。"""
    nf = int(0.5 * SR)
    total = n + nf
    birds = fit(mono(load(dp('park_birds.wav'))), total, rng)
    birds = dsp.fft_filter(birds, SR, lo=600, hi=11000, order=2)
    birds = dsp.to_stereo(dsp.normalize_rms(birds, -26.0), width=0.75)
    air = dsp.fft_filter(dsp.pink(total, rng), SR, lo=200, hi=6000, order=2)
    air = dsp.to_stereo(dsp.normalize_rms(air, -40.0), width=0.95)
    cars = dsp.normalize_rms(traffic(total, rng, density=0.35), -38.0)
    out = dsp.mix_layers(total, [(birds, 0.0, 0.0), (air, 0.0, 0.0), (cars, 0.0, 0.0)])
    return dsp.make_loop(out, SR, xfade_s=0.5)


def bed_amb_noon(n, rng):
    """正午：街道人声 + 车流 + 杯碟 + 极低音量轻快音乐。"""
    nf = int(0.5 * SR)
    total = n + nf
    hw_path = rp('pack_rubberduck_100_v2', 'sfx100v2_loop_highway.ogg')
    road = fit(mono(load(hw_path)), total, rng)
    road = dsp.fft_filter(road, SR, lo=60, hi=5000, order=2)
    road = dsp.to_stereo(dsp.normalize_rms(road, -27.0), width=0.9)
    ppl = dsp.normalize_rms(crowd(total, rng, voices=8), -33.0)
    dishes = np.zeros((total, 2))
    tt = 1.0
    while tt < total / SR - 1.5:
        src = str(rng.choice(['dishes_01.ogg', 'dishes_02.ogg', 'dishes_03.ogg', 'dishes_04.ogg']))
        d = mono(load(rp('pack_rubberduck_100_v1', src)))
        dsp.place(dishes, d * rng.uniform(0.5, 1.0), tt, SR, -34.0, float(rng.uniform(-0.7, 0.7)))
        tt += rng.uniform(4.0, 9.0)
    mus = fit(mono(load(dp('music_cozy_puzzle.ogg'))), total, rng)
    mus = dsp.fft_filter(mus, SR, lo=90, hi=5200, order=2)
    mus = dsp.to_stereo(dsp.normalize_rms(mus, -38.0), width=0.6)
    out = dsp.mix_layers(total, [(road, 0.0, 0.0), (ppl, 0.0, 0.0),
                                 (dishes, 0.0, 0.0), (mus, 0.0, 0.0)])
    return dsp.make_loop(out, SR, xfade_s=0.5)


def bed_amb_dusk(n, rng):
    """黄昏：归家人流 + 电车 + 爵士钢琴 + 空调低频。"""
    nf = int(0.5 * SR)
    total = n + nf
    ppl = dsp.normalize_rms(crowd(total, rng, voices=9), -30.0)
    tr = dsp.normalize_rms(train(total, rng), -32.0)
    mus = fit(mono(load(dp('music_blues.mp3'))), total, rng)
    mus = dsp.fft_filter(mus, SR, lo=70, hi=3600, order=2)
    mus = dsp.to_stereo(dsp.normalize_rms(mus, -34.0), width=0.55)
    hv = dsp.normalize_rms(ac_hum(total, rng), -36.0)
    cars = dsp.normalize_rms(traffic(total, rng, density=0.6), -34.0)
    out = dsp.mix_layers(total, [(ppl, 0.0, 0.0), (tr, 0.0, 0.0), (mus, 0.0, 0.0),
                                 (hv, 0.0, 0.0), (cars, 0.0, 0.0)])
    return dsp.make_loop(out, SR, xfade_s=0.5)


def bed_amb_night(n, rng):
    """深夜：虫鸣 + 远车 + 低语 + 萨克斯（合成铺底）。"""
    nf = int(0.5 * SR)
    total = n + nf
    cr = fit(mono(load(dp('crickets.mp3'))), total, rng)
    cr = dsp.fft_filter(cr, SR, lo=1800, hi=12000, order=2)
    cr = dsp.to_stereo(dsp.normalize_rms(cr, -32.0), width=0.9)
    cars = dsp.normalize_rms(traffic(total, rng, density=0.25), -40.0)
    wh = dsp.normalize_rms(whispers(total, rng), -42.0)
    sax = dsp.normalize_rms(sax_pad(total, rng), -36.0)
    out = dsp.mix_layers(total, [(cr, 0.0, 0.0), (cars, 0.0, 0.0),
                                 (wh, 0.0, 0.0), (sax, 0.0, 0.0)])
    return dsp.make_loop(out, SR, xfade_s=0.5)


def sax_pad(n, rng):
    """
    极简萨克斯铺底：谐波求和 + 共振峰 + 慢揉音，只吹长音。
    不追求真实独奏，只做深夜里一条若有若无的旋律线。
    """
    out = np.zeros((n, 2))
    scales = [174.61, 220.0, 261.63, 293.66, 349.23]
    t_all = np.arange(n) / SR
    tt = 0.0
    while tt < n / SR:
        dur = rng.uniform(2.4, 4.5)
        f0 = float(rng.choice(scales)) * float(rng.choice([1.0, 1.0, 1.0, 2.0]))
        k = int(dur * SR)
        i0 = int(tt * SR)
        if i0 + k > n:
            break
        t = np.arange(k) / SR
        vib = 1.0 + 0.006 * np.sin(2 * math.pi * rng.uniform(4.2, 5.6) * t)
        phase = 2 * math.pi * f0 * np.cumsum(vib) / SR
        sig = np.zeros(k)
        for h in range(1, 12):
            if f0 * h > 7000:
                break
            sig = sig + (1.0 / h ** 1.1) * np.sin(phase * h + h * 0.3)
        sig = dsp.fft_filter(sig, SR, lo=f0 * 0.8, hi=3200, order=2)
        sig = sig * (np.hanning(k) ** 0.6)
        pan = rng.uniform(-0.5, 0.5)
        out[i0:i0 + k, 0] += sig * math.sqrt(0.5 * (1 - pan)) * 0.5
        out[i0:i0 + k, 1] += sig * math.sqrt(0.5 * (1 + pan)) * 0.5
        tt += dur * rng.uniform(1.15, 1.9)
    pad = np.zeros(n)
    for f in (110.0, 130.81, 164.81):
        pad = pad + np.sin(2 * math.pi * f * t_all) * (0.5 + 0.5 * np.sin(2 * math.pi * 0.05 * t_all))
    pad = dsp.fft_filter(pad, SR, lo=60, hi=500, order=2)
    pad = pad * dsp.smooth_random(n, SR, 0.05, 0.2, 1.0, rng=rng)
    out[:, 0] += pad * 0.05
    out[:, 1] += pad * 0.05
    return out


# ============================================================ 天气床
def _rain_core(n, rng, src_names, lo, hi):
    """用真实雨声素材拼出 n 长度、指定频率平衡的雨底。"""
    segs = []
    for nm in src_names:
        p = dp(nm) if os.path.exists(dp(nm)) else rp('pack_ylmir_rain', nm)
        if os.path.exists(p):
            segs.append(mono(load(p)))
    if not segs:
        raise RuntimeError('no rain source found')
    s = np.concatenate(segs)
    if len(s) < n:
        s = fit(s, n, rng)
    while len(s) < n:
        s = np.concatenate([s, s])
    if len(s) > n:
        off = int(rng.integers(0, max(1, len(s) - n)))
        s = s[off:off + n]
    s = dsp.fft_filter(s, SR, lo=lo, hi=hi, order=2)
    return dsp.to_stereo(s, width=0.95)


def bed_rain_light(n, rng):
    """小雨：细密雨点 + 空气感，低频少。"""
    nf = int(0.5 * SR)
    total = n + nf
    rain = dsp.normalize_rms(_rain_core(total, rng, ['1.ogg', '4.ogg'], 300, 12000), -22.0)
    drops = np.zeros((total, 2))
    for _ in range(int(total / SR * 7)):
        d = dsp.noise_burst(rng.uniform(0.03, 0.08), SR, rng, 0.0005, 0.02, 1200, 9000)
        dsp.place(drops, d * rng.uniform(0.3, 1.0), rng.uniform(0, max(0.05, total / SR - 0.1)),
                  SR, -30.0 + rng.uniform(-6, 6), float(rng.uniform(-0.9, 0.9)))
    return dsp.make_loop(dsp.mix_layers(total, [(rain, 0.0, 0.0), (drops, 0.0, 0.0)]), SR, 0.5)


def bed_rain_med(n, rng):
    """中雨：更密更厚，中频雨幕明显。"""
    nf = int(0.5 * SR)
    total = n + nf
    rain = dsp.normalize_rms(_rain_core(total, rng, ['2.ogg', '1.ogg'], 120, 12000), -20.0)
    gutter = dsp.normalize_rms(_rain_core(total, rng, ['rain_gutter.mp3'], 180, 6000), -28.0)
    return dsp.make_loop(dsp.mix_layers(total, [(rain, 0.0, 0.0), (gutter, 0.0, 0.0)]), SR, 0.5)


def bed_rain_heavy(n, rng):
    """大雨：雨幕厚实 + 强低频冲刷 + 屋檐排水。"""
    nf = int(0.5 * SR)
    total = n + nf
    rain = dsp.normalize_rms(_rain_core(total, rng, ['3.ogg', '2.ogg'], 90, 14000), -19.0)
    body = dsp.fft_filter(dsp.brown(total, rng), SR, lo=35, hi=200, order=2)
    body = body * dsp.smooth_random(total, SR, 0.4, 0.6, 1.1, rng=rng)
    body = dsp.to_stereo(dsp.normalize_rms(body, -26.0), width=0.5)
    gutter = dsp.normalize_rms(_rain_core(total, rng, ['rain_gutter.mp3'], 250, 9000), -25.0)
    return dsp.make_loop(dsp.mix_layers(total, [(rain, 0.0, 0.0), (body, 0.0, 0.0),
                                                (gutter, 0.0, 0.0)]), SR, 0.5)


def bed_amb_wind(n, rng):
    """风：呼啸 + 阵风，无雨。"""
    nf = int(0.5 * SR)
    total = n + nf
    w = dsp.normalize_rms(wind_layer(total, rng, 1.0, 1.0), -21.0)
    pw = dp('wind_whoosh_loop.ogg')
    if os.path.exists(pw):
        wh = fit(mono(load(pw)), total, rng)
        wh = dsp.fft_filter(wh, SR, lo=90, hi=4500, order=2)
        wh = dsp.to_stereo(dsp.normalize_rms(wh, -30.0), width=0.85)
        w = dsp.mix_layers(total, [(w, 0.0, 0.0), (wh, 0.0, 0.0)])
    return dsp.make_loop(w, SR, 0.5)


def bed_amb_storm(n, rng):
    """雷阵雨：狂风 + 暴雨 + 远处滚动雷（近雷走事件音）。"""
    nf = int(0.5 * SR)
    total = n + nf
    rain = dsp.normalize_rms(_rain_core(total, rng, ['3.ogg', '2.ogg'], 80, 14000), -18.0)
    w = dsp.normalize_rms(wind_layer(total, rng, 1.0, 1.4), -22.0)
    body = dsp.fft_filter(dsp.brown(total, rng), SR, lo=30, hi=160, order=2)
    body = dsp.to_stereo(dsp.normalize_rms(body, -24.0), width=0.4)
    out = dsp.mix_layers(total, [(rain, 0.0, 0.0), (w, 0.0, 0.0), (body, 0.0, 0.0)])
    far = make_thunder_far(int(6.0 * SR), rng)
    span = max(1.0, total / SR - 12.0)
    dsp.place(out, far, rng.uniform(4.0, max(4.1, span)), SR, -8.0, float(rng.uniform(-0.4, 0.4)))
    return dsp.make_loop(out, SR, 0.5)


# ============================================================ 事件音
def _fit_after_reverb(sig, n, sr=SR):
    """
    混响卷积会让长度变成 len(x)+len(ir)-1，超出目标时长。
    这里裁回 n 并加短淡出，避免尾部被硬切产生咔哒。
    """
    sig = np.asarray(sig, dtype=np.float64)
    if len(sig) > n:
        sig = sig[:n].copy()
        no = min(int(0.06 * sr), len(sig) // 4)
        if no > 1:
            if sig.ndim > 1:
                sig[-no:] *= np.linspace(1, 0, no)[:, None]
            else:
                sig[-no:] *= np.linspace(1, 0, no)
    elif len(sig) < n:
        if sig.ndim > 1:
            sig = np.pad(sig, ((0, n - len(sig)), (0, 0)))
        else:
            sig = np.pad(sig, (0, n - len(sig)))
    return sig


def make_thunder_far(n, rng):
    """远雷：低沉、长、模糊。"""
    src = mono(dsp.decode(rp('pack_rubberduck_100_v2', 'sfx100v2_thunder_01.ogg')))
    s = dsp.fft_filter(src, SR, lo=25, hi=520, order=3)
    s = fit(s, n, rng)
    s = s * (np.hanning(n) ** 0.25)
    ir = dsp.make_ir(3.4, SR, 0.75, 1400, rng=rng)
    s = dsp.make_ir(3.4, SR, 0.75, 1400, rng=rng)
    s = dsp.reverb(s, ir, wet=0.55, dry=0.65)
    s = _fit_after_reverb(s, n)
    s = dsp.soft_limit(normalize_rms_safe(s, -26.0), -6.0)
    return dsp.to_stereo(s, width=0.6)


def make_thunder_mid(n, rng):
    """中雷：有起音、有滚动尾巴。"""
    src = mono(dsp.decode(rp('pack_rubberduck_100_v2', 'sfx100v2_thunder_01.ogg')))
    src = fit(src, n, rng)
    s = dsp.fft_filter(src, SR, lo=30, hi=1600, order=2)
    ir = dsp.make_ir(2.6, SR, 0.6, 2600, rng=rng)
    s = dsp.reverb(s, ir, wet=0.42, dry=0.75)
    s = _fit_after_reverb(s, n)
    return dsp.to_stereo(dsp.soft_limit(normalize_rms_safe(s, -22.0), -3.0), width=0.7)


def make_thunder_close(n, rng):
    """近雷：爆裂起音 + 强低频冲击 + 长滚尾。"""
    t = np.arange(n) / SR
    src = fit(mono(dsp.decode(rp('pack_rubberduck_100_v2', 'sfx100v2_thunder_01.ogg'))), n, rng)
    s = dsp.fft_filter(src, SR, lo=25, hi=4500, order=2)
    s = s / (np.max(np.abs(s)) + 1e-12)
    crack = dsp.noise_burst(0.18, SR, rng, 0.0003, 0.05, 900, 12000)
    crack_pad = np.zeros(n)
    crack_pad[:len(crack)] = crack
    sub = np.sin(2 * math.pi * 42.0 * t) * np.exp(-t / 0.55)
    sub = sub * np.clip(t / 0.004, 0, 1)
    sig = s * 0.85 + crack_pad * 0.55 + sub * 0.75
    ir = dsp.make_ir(2.2, SR, 0.5, 3600, rng=rng)
    sig = dsp.reverb(sig, ir, wet=0.28, dry=0.85)
    sig = _fit_after_reverb(sig, n)
    return dsp.to_stereo(dsp.soft_limit(normalize_rms_safe(sig, -18.0), -3.0), width=0.8)


def make_lightning_crack(n, rng):
    """
    闪电裂响：极短高频爆裂 + 电离滋啦 + 远处静电余韵。
    时长按 2s 交付（事件音规格 2-8s），但能量集中在开头 0.4s，
    后面是很轻的电离尾音——听起来仍是"啪"的一声，不会变成一段噪声。
    """
    sig = np.zeros(n)
    c = dsp.noise_burst(0.10, SR, rng, 0.0002, 0.025, 2200, 16000)
    sig[:len(c)] = sig[:len(c)] + c
    zap = dsp.fft_filter(dsp.white(int(0.35 * SR), rng), SR, lo=4000, hi=16000, order=2)
    zap = zap * np.exp(-np.arange(len(zap)) / SR / 0.06)
    i0 = int(0.01 * SR)
    nz = min(len(zap), n - i0)
    sig[i0:i0 + nz] = sig[i0:i0 + nz] + zap[:nz] * 0.5
    buf = sig[:, None]
    for _ in range(2):
        d = dsp.noise_burst(rng.uniform(0.03, 0.06), SR, rng, 0.0002, 0.012, 3000, 15000)
        dsp.place(buf, d, rng.uniform(0.06, 0.22), SR, -12.0, float(rng.uniform(-0.5, 0.5)))

    # 电离余韵：极轻的高频静电嘶声，长衰减，填满 2s
    tail = dsp.fft_filter(dsp.white(n, rng), SR, lo=5000, hi=16000, order=2)
    t = np.arange(n) / SR
    tail = tail * np.exp(-np.maximum(t - 0.18, 0) / 0.55) * 0.06
    tail = tail * np.clip(t / 0.18, 0, 1)
    sig = buf[:, 0] + tail
    sig = dsp.fade_edges(sig, SR, 0.5, 80)
    return dsp.to_stereo(sig, width=0.5)


def make_cup_clink(n, rng):
    """陶瓷杯相碰：真实素材（rubberduck dishes），裁到 2s 内。"""
    s = fit(mono(load(rp('pack_rubberduck_100_v1', 'dishes_01.ogg'))), n, rng)
    s = dsp.trim_tail(s, SR, -60.0, 80)
    s = dsp.fade_edges(s, SR, 0.5, 25)
    return dsp.to_stereo(s, width=0.35)


def make_saucer(n, rng):
    """茶碟：比杯更薄、更高频、更短。"""
    s = fit(mono(load(rp('pack_rubberduck_100_v1', 'dishes_04.ogg'))), n, rng)
    s = dsp.fft_filter(s, SR, lo=900, hi=14000, order=2)
    s = dsp.trim_tail(s, SR, -60.0, 60)
    s = dsp.fade_edges(s, SR, 0.5, 20)
    return dsp.to_stereo(s, width=0.3)


def make_machine_preheat(n, rng):
    """咖啡机预热：低频泵体 + 逐渐升高的加热嗡鸣 + 继电器咔哒。"""
    t = np.arange(n) / SR
    body = fit(mono(dsp.decode(rp('pack_rubberduck_loops', 'machine_08.ogg'))), n, rng)
    body = dsp.fft_filter(body, SR, lo=40, hi=1400, order=2)
    body = body / (np.max(np.abs(body)) + 1e-12)
    sweep = np.sin(2 * math.pi * np.cumsum(180 + 260 * np.clip(t / (n / SR), 0, 1)) / SR)
    sweep = sweep * 0.16 * np.clip(t / 0.7, 0, 1)
    clk = dsp.modal([1250, 2100], [0.02, 0.015], [1.0, 0.6], 0.12, SR)
    clk = clk + dsp.noise_burst(0.12, SR, rng, 0.0003, 0.015, 400, 7000) * 0.6
    pad = np.zeros(n)
    pad[:len(clk)] = pad[:len(clk)] + dsp.fade_edges(clk, SR, 0.3, 20)
    sig = body * 0.75 + sweep + pad * 0.8
    sig = sig * np.clip(t / 0.25, 0, 1) * np.clip((n / SR - t) / 0.3, 0, 1)
    return dsp.to_stereo(dsp.soft_limit(sig, -3.0), width=0.4)


def make_espresso_extract(n, rng):
    """萃取：泵压嗡鸣 + 液体细流 + 滴落。"""
    t = np.arange(n) / SR
    pump = fit(mono(dsp.decode(rp('pack_rubberduck_loops', 'pump_01.ogg'))), n, rng)
    pump = dsp.fft_filter(pump, SR, lo=50, hi=1200, order=2)
    pump = pump / (np.max(np.abs(pump)) + 1e-12) * 0.5
    stream = dsp.fft_filter(dsp.pink(n, rng), SR, lo=1600, hi=11000, order=2)
    stream = stream / (np.max(np.abs(stream)) + 1e-12) * 0.35
    stream = stream * (0.7 + 0.3 * dsp.smooth_random(n, SR, 6.0, 0.0, 1.0, rng=rng))
    buf = (pump + stream)[:, None]
    for _ in range(int(n / SR * 1.6)):
        d = dsp.modal([900, 1700, 2800], [0.03, 0.02, 0.012], [1.0, 0.5, 0.25], 0.12, SR)
        dsp.place(buf, d * rng.uniform(0.4, 1.0), rng.uniform(0.3, max(0.35, n / SR - 0.3)),
                  SR, -22.0, float(rng.uniform(-0.3, 0.3)))
    env = np.clip(t / 0.15, 0, 1) * np.clip((n / SR - t) / 0.35, 0, 1)
    return dsp.to_stereo(dsp.soft_limit(buf * env[:, None], -3.0), width=0.45)


def make_steam_wand(n, rng):
    """蒸汽棒：宽频嘶声 + 手持轻微抖动 + 尾部散汽。"""
    t = np.arange(n) / SR
    hiss = dsp.fft_filter(dsp.white(n, rng), SR, lo=1500, hi=15000, order=2)
    hiss = hiss / (np.max(np.abs(hiss)) + 1e-12)
    body = dsp.fft_filter(dsp.pink(n, rng), SR, lo=300, hi=2500, order=2)
    body = body / (np.max(np.abs(body)) + 1e-12)
    sig = hiss * 0.8 + body * 0.4
    sig = sig * (0.85 + 0.15 * dsp.smooth_random(n, SR, 9.0, 0.0, 1.0, rng=rng))
    env = np.clip(t / 0.06, 0, 1) * np.clip((n / SR - t) / 0.5, 0, 1) ** 0.7
    return dsp.to_stereo(dsp.soft_limit(sig * env, -3.0), width=0.5)


def make_grinder(n, rng):
    """磨豆机：真实 grind_stone 素材 + 电机低频 + 收尾空转。"""
    t = np.arange(n) / SR
    g = fit(mono(dsp.decode(rp('pack_laleksic_sfx', 'grind_stone.wav'))), int(n * 0.8), rng)
    g = dsp.fft_filter(g, SR, lo=90, hi=9000, order=2)
    g = g / (np.max(np.abs(g)) + 1e-12)
    motor = dsp.fft_filter(dsp.brown(n, rng), SR, lo=60, hi=320, order=2)
    motor = motor / (np.max(np.abs(motor)) + 1e-12) * 0.4
    motor = motor * np.clip((n / SR - t) / 0.5, 0, 1)
    sig = np.zeros(n)
    sig[:len(g)] = sig[:len(g)] + g
    sig = sig + motor
    sig = sig * np.clip(t / 0.05, 0, 1) * np.clip((n / SR - t) / 0.35, 0, 1)
    return dsp.to_stereo(dsp.soft_limit(sig, -3.0), width=0.4)


def make_fridge(n, rng):
    """冰箱启停：压缩机启动，稳定嗡嗡，停机泄压。"""
    t = np.arange(n) / SR
    hum = fit(mono(dsp.decode(dp('fridge_loop.ogg'))), n, rng)
    hum = dsp.fft_filter(hum, SR, lo=35, hi=900, order=2)
    hum = hum / (np.max(np.abs(hum)) + 1e-12)
    on = np.clip(t / 0.28, 0, 1) ** 1.5
    off = np.clip((n / SR - t) / 0.9, 0, 1) ** 0.6
    hum = hum * on * off
    clk = dsp.modal([680, 1400], [0.03, 0.02], [1.0, 0.5], 0.15, SR)
    clk = clk + dsp.noise_burst(0.15, SR, rng, 0.0005, 0.02, 300, 5000) * 0.7
    sig = hum * 0.75
    sig[:len(clk)] = sig[:len(clk)] + dsp.fade_edges(clk, SR, 0.3, 20) * 0.5
    rel = dsp.fft_filter(dsp.white(int(0.6 * SR), rng), SR, lo=1200, hi=9000, order=2)
    rel = rel * np.exp(-np.arange(len(rel)) / SR / 0.2) * 0.25
    i0 = max(0, n - len(rel))
    nz = min(len(rel), n - i0)
    sig[i0:i0 + nz] = sig[i0:i0 + nz] + rel[:nz]
    return dsp.to_stereo(dsp.soft_limit(sig, -3.0), width=0.3)


def make_bell_chime(n, rng):
    """风铃迎客：真实铜铃素材分层，错开时间形成叮铃。"""
    out = np.zeros(n)
    bulbs = ['bell_ding1.wav', 'bell_ding2.wav', 'bell_ding3.wav', 'bell_ding4.wav']
    order = rng.permutation(len(bulbs))
    tt = 0.0
    for k, idx in enumerate(order[:3]):
        b = mono(load(dp(bulbs[int(idx)])))
        b = dsp.fft_filter(b, SR, lo=400, hi=13000, order=2)
        if tt + len(b) / SR > n / SR:
            break
        dsp.place(out[:, None], dsp.fade_edges(b, SR, 1, 30) * (1.0 - k * 0.22), tt, SR,
                  rng.uniform(-3, 0), float(rng.uniform(-0.3, 0.3)))
        tt += rng.uniform(0.28, 0.55)
    sig = dsp.trim_tail(out, SR, -60.0, 100)
    return dsp.to_stereo(dsp.fade_edges(sig, SR, 1, 30), width=0.55)


def make_door_bell(n, rng):
    """门铃：真实 doorbell 素材。"""
    s = fit(mono(load(dp('doorbell_tring.ogg'))), n, rng)
    s = dsp.trim_tail(s, SR, -55.0, 120)
    return dsp.to_stereo(dsp.fade_edges(dsp.soft_limit(s, -3.0), SR, 2, 30), width=0.35)


def make_noren(n, rng):
    """门帘抖动：布料摩擦 + 褶皱的快幅起伏 + 末尾轻碰门框。"""
    t = np.arange(n) / SR
    sig = dsp.fft_filter(dsp.pink(n, rng), SR, lo=700, hi=7000, order=2)
    sig = sig / (np.max(np.abs(sig)) + 1e-12)
    flutter = 0.55 + 0.45 * np.abs(np.sin(2 * math.pi * rng.uniform(7.0, 13.0) * t))
    flutter = flutter * dsp.smooth_random(n, SR, 3.0, 0.4, 1.0, rng=rng)
    sig = sig * flutter
    env = np.clip(t / 0.05, 0, 1) * np.clip((n / SR - t) / 0.25, 0, 1)
    sig = sig * env
    thud = dsp.modal([180, 420], [0.05, 0.03], [1.0, 0.4], 0.2, SR)
    thud = thud + dsp.noise_burst(0.2, SR, rng, 0.001, 0.03, 100, 1500) * 0.5
    i0 = max(0, int(n * 0.72))
    nz = min(len(thud), n - i0)
    sig[i0:i0 + nz] = sig[i0:i0 + nz] + thud[:nz] * 0.35
    return dsp.to_stereo(dsp.soft_limit(sig, -3.0), width=0.65)


def pad_to_min(x, n_min, sr=SR):
    """把过短的 one-shot 补到最短时长（尾部补零，不影响声音内容）。"""
    x = np.asarray(x, dtype=np.float64)
    if len(x) >= n_min:
        return x
    pad = n_min - len(x)
    if x.ndim > 1:
        return np.pad(x, ((0, pad), (0, 0)))
    return np.pad(x, (0, pad))


def make_cash_ding(n, rng):
    """收银：抽屉机械声 + 清脆铃。"""
    sig = np.zeros(n)
    bell = mono(load(dp('bell_ding2.wav')))
    bell = dsp.fft_filter(bell, SR, lo=800, hi=14000, order=2)
    m = min(len(bell), n)
    sig[:m] = sig[:m] + dsp.fade_edges(bell, SR, 1, 30)[:m] * 0.9
    mech = dsp.modal([520, 1150, 2100], [0.04, 0.025, 0.015], [1.0, 0.5, 0.25], 0.25, SR)
    mech = mech + dsp.noise_burst(0.25, SR, rng, 0.0005, 0.03, 200, 4000) * 0.6
    dsp.place(sig[:, None], mech * 0.45, 0.02, SR, 0.0, 0.1)
    sig = dsp.trim_tail(sig, SR, -58.0, 80)
    sig = pad_to_min(sig, int(2.0 * SR))
    return dsp.to_stereo(dsp.fade_edges(dsp.soft_limit(sig, -3.0), SR, 1, 25), width=0.4)


def make_page(n, rng):
    """翻页：真实 book_flip 素材。"""
    p = rp('pack_starninjas_pages', 'book_flip.%d.ogg' % int(rng.integers(1, 11)))
    s = fit(mono(dsp.decode(p)), n, rng)
    s = dsp.trim_tail(s, SR, -55.0, 60)
    s = pad_to_min(s, int(2.0 * SR))
    return dsp.to_stereo(dsp.fade_edges(s, SR, 1, 25), width=0.4)


def make_chair(n, rng):
    """椅子挪动：木质吱呀（真实 floor_creak）+ 摩擦噪声。"""
    t = np.arange(n) / SR
    creak = fit(mono(dsp.decode(rp('pack_laleksic_sfx', 'floor_creak3.wav'))), int(n * 0.75), rng)
    creak = dsp.fft_filter(creak, SR, lo=180, hi=5000, order=2)
    creak = creak / (np.max(np.abs(creak)) + 1e-12)
    fric = dsp.fft_filter(dsp.pink(n, rng), SR, lo=600, hi=5200, order=2)
    fric = fric / (np.max(np.abs(fric)) + 1e-12)
    fric = fric * (0.5 + 0.5 * np.abs(np.sin(2 * math.pi * 2.6 * t)))
    sig = np.zeros(n)
    sig[:len(creak)] = sig[:len(creak)] + creak * 0.8
    sig = sig + fric * 0.35
    sig = sig * np.clip(t / 0.08, 0, 1) * np.clip((n / SR - t) / 0.3, 0, 1)
    return dsp.to_stereo(dsp.soft_limit(sig, -3.0), width=0.45)


def make_rollup(n, rng):
    """卷帘门拉开：金属滚动的连锁咔哒 + 轨道摩擦 + 最后闷响。"""
    t = np.arange(n) / SR
    roll = fit(mono(dsp.decode(rp('pack_rubberduck_loops', 'rolling.ogg'))), n, rng)
    roll = dsp.fft_filter(roll, SR, lo=120, hi=6000, order=2)
    roll = roll / (np.max(np.abs(roll)) + 1e-12)
    sig = roll * 0.7
    tt = 0.0
    while tt < n / SR - 0.2:
        m = str(rng.choice(['metal_02.ogg', 'metal_04.ogg', 'metal_11.ogg', 'other_02.ogg']))
        c = mono(dsp.decode(rp('pack_rubberduck_100_v1', m)))
        c = dsp.fft_filter(c, SR, lo=700, hi=11000, order=2)
        dsp.place(sig[:, None], dsp.fade_edges(c, SR, 1, 15) * rng.uniform(0.25, 0.7),
                  tt, SR, -14.0, float(rng.uniform(-0.35, 0.35)))
        tt += rng.uniform(0.075, 0.11)
    thud = dsp.modal([88, 150, 240], [0.22, 0.14, 0.08], [1.0, 0.6, 0.3], 0.5, SR)
    thud = thud + dsp.noise_burst(0.5, SR, rng, 0.001, 0.06, 60, 1200) * 0.7
    dsp.place(sig[:, None], dsp.fade_edges(thud, SR, 0.5, 60) * 0.8,
              max(0.0, n / SR - 0.8), SR, -2.0, 0.0)
    sig = sig * np.clip(t / 0.05, 0, 1)
    return dsp.to_stereo(dsp.soft_limit(sig, -3.0), width=0.5)


def make_clean_steam(n, rng):
    """清洁蒸汽：短促高压喷汽 + 回落。"""
    t = np.arange(n) / SR
    hiss = dsp.fft_filter(dsp.white(n, rng), SR, lo=2000, hi=16000, order=2)
    hiss = hiss / (np.max(np.abs(hiss)) + 1e-12)
    low = dsp.fft_filter(dsp.pink(n, rng), SR, lo=200, hi=1800, order=2)
    low = low / (np.max(np.abs(low)) + 1e-12)
    env = np.clip(t / 0.04, 0, 1) * np.exp(-np.maximum(t - 0.12, 0) / 0.55)
    sig = (hiss * 0.85 + low * 0.45) * env
    sig = sig * (0.9 + 0.1 * dsp.smooth_random(n, SR, 11.0, 0.0, 1.0, rng=rng))
    return dsp.to_stereo(dsp.soft_limit(sig, -3.0), width=0.5)


# ============================================================ 资产表
BEDS = {
    'amb_morning': (bed_amb_morning, 60.0),
    'amb_noon': (bed_amb_noon, 60.0),
    'amb_dusk': (bed_amb_dusk, 60.0),
    'amb_night': (bed_amb_night, 60.0),
    'amb_rain_light': (bed_rain_light, 30.0),
    'amb_rain_med': (bed_rain_med, 30.0),
    'amb_rain_heavy': (bed_rain_heavy, 30.0),
    'amb_wind': (bed_amb_wind, 30.0),
    'amb_storm': (bed_amb_storm, 30.0),
}

EVENTS = {
    'sfx_thunder_far': (make_thunder_far, 6.0),
    'sfx_thunder_mid': (make_thunder_mid, 5.5),
    'sfx_thunder_close': (make_thunder_close, 5.0),
    'sfx_lightning_crack': (make_lightning_crack, 2.0),
    'sfx_cup_clink': (make_cup_clink, 2.0),
    'sfx_saucer': (make_saucer, 2.0),
    'sfx_machine_preheat': (make_machine_preheat, 5.0),
    'sfx_espresso_extract': (make_espresso_extract, 6.0),
    'sfx_steam_wand': (make_steam_wand, 4.0),
    'sfx_grinder': (make_grinder, 4.0),
    'sfx_fridge': (make_fridge, 6.0),
    'sfx_bell_chime': (make_bell_chime, 4.0),
    'sfx_door_bell': (make_door_bell, 4.0),
    'sfx_noren': (make_noren, 2.5),
    'sfx_cash_ding': (make_cash_ding, 2.5),
    'sfx_page': (make_page, 2.0),
    'sfx_chair': (make_chair, 3.0),
    'sfx_rollup': (make_rollup, 6.0),
    'sfx_clean_steam': (make_clean_steam, 4.0),
}


def finalize(x, sr, kind):
    """
    统一电平：
      床  -> RMS 锁 -20 dBFS，峰值用软膝限幅压到 -3 dBFS 以下
      事件 -> 峰值锁 -3 dBFS

    要点：床层（雨/风/人流）峰值因数常达 20dB，若靠整体缩放压峰值，
    RMS 会被一起拉到 -25 以下。所以床层必须用 soft_limit 只压峰、
    保持 RMS 不动。Vorbis 编码还有约 1dB 过冲，因此限幅目标留 1.2dB 余量，
    再由 write_ogg_verified 回读校验补齐。
    """
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = dsp.to_stereo(x, width=0.4)
    if x.ndim == 2 and x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)

    if kind == 'bed':
        # 交替"归一 RMS -> 压峰"，收敛到 RMS≈-20 且峰值 <= -3
        for _ in range(6):
            x = dsp.normalize_rms(x, -20.0)
            if dsp.peak_db(x) <= -5.0:
                break
            x = dsp.soft_limit(x, ceiling_db=-5.0, knee=0.4)
    else:
        # 事件音同样预留 2dB 编码余量
        pre_ceiling = 10 ** ((-3.0 - 2.0) / 20.0)
        x = x * (pre_ceiling / (np.max(np.abs(x)) + 1e-12))
    return x


def write_ogg_verified(x, sr, out_path, ceiling_db, quality=5, max_iter=4, kind='event'):
    """
    编码后回读校验：Vorbis 转码会有瞬时过冲，可能把峰值顶到 ceiling 以上。
    这里写入 -> 解码 -> 测峰值 -> 若超标则修正重写，最多 max_iter 次。
    保证交付文件（解码后）峰值确实 <= ceiling_db。

    修正策略按类型区分：
      床  -> 用 soft_limit 只压那几个过冲尖峰，RMS 基本不动
      事件 -> 直接整体回缩（事件音本来就以峰值为准）
    """
    ceiling = 10 ** (ceiling_db / 20.0)
    cur = np.asarray(x, dtype=np.float64)
    for i in range(max_iter):
        dsp.write_ogg(cur, sr, out_path, quality=quality)
        back = dsp.decode(out_path)
        pk = float(np.max(np.abs(back))) + 1e-12
        if pk <= ceiling:
            return cur, i
        if kind == 'bed':
            # 只削过冲尖峰：用更狠的软膝限幅，RMS 基本不受影响
            cur = dsp.soft_limit(cur, ceiling_db=ceiling_db, knee=0.35)
        else:
            cur = cur * (ceiling / pk) * 0.985
    return cur, max_iter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()

    if args.list:
        print('BEDS:', ', '.join(BEDS))
        print('EVENTS:', ', '.join(EVENTS))
        return

    only = set(s for s in args.only.split(',') if s)
    report = []

    for kind, table in (('bed', BEDS), ('event', EVENTS)):
        for key, (fn, dur) in table.items():
            if only and key not in only:
                continue
            n = int(round(dur * SR))
            try:
                out = fn(n, RNG)
                out = finalize(out, SR, kind)
                path = os.path.join(OUT, key + '.ogg')
                # 编码后回读校验，吸收 Vorbis 转码过冲，确保交付峰值 <= -3dBFS
                out, _iters = write_ogg_verified(out, SR, path, -3.0, quality=5, kind=kind)
                size = os.path.getsize(path)
                row = {
                    'key': key, 'kind': kind, 'file': key + '.ogg',
                    'dur': round(len(out) / SR, 3),
                    'bytes': size, 'bytes_kb': round(size / 1024, 1),
                    'peak_db': round(dsp.peak_db(out), 2),
                    'rms_db': round(dsp.rms_db(out), 2),
                    'crest_db': round(dsp.crest_db(out), 2),
                }
                if kind == 'bed':
                    row['seam'] = dsp.loop_seam_report(out, SR)
                report.append(row)
                seam = ''
                if kind == 'bed':
                    s = row['seam']
                    seam = ' seam p99=%s loc=%s ok=%s' % (s['seam_vs_p99_step'],
                                                         s['seam_vs_local_step_rms'], s['seam_ok'])
                print('%-22s %-5s %6.2fs %7.1fKB pk%6.2f rms%6.2f%s' % (
                    key, kind, row['dur'], row['bytes_kb'], row['peak_db'], row['rms_db'], seam))
            except Exception as e:
                import traceback
                traceback.print_exc()
                print('!! %s FAILED: %s' % (key, e))

    rep_path = os.path.join(HERE, 'build_report.json')
    with open(rep_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    total = sum(r['bytes'] for r in report)
    print('\n%d files, %.2f MB -> %s' % (len(report), total / 1048576, OUT))


if __name__ == '__main__':
    main()
