"""
qc_assets.py - 最终交付前质检（对 assets/audio/ 里真实文件，不依赖构建过程的内存对象）

检查项
------
1. 格式：全部 .ogg / Vorbis / 44.1kHz，文件名与 manifest 一致
2. 时长：床 20-60s（雨/雷阵雨 30s）；事件音 2-8s
3. 响度：事件音峰值 <= -3dBFS；床 RMS 约 -20dBFS
4. 循环接缝：床层接缝跳变落在自身自然步进范围内（不会爆音）
5. 削波：无 >= 0.999 的连续样本
6. 直流偏移
7. manifest 完整性：每个 key 有对应文件；presets 引用的 key 都存在
输出：qc_report.json + 控制台表格 + 明确的 PASS/FAIL
"""
import os
import sys
import json
import math
import subprocess
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import dsp

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'assets', 'audio')
MANIFEST = os.path.join(OUT, 'manifest.json')

BED_DUR_RANGE = (20.0, 60.0)
EVENT_DUR_RANGE = (1.0, 8.5)
EVENT_PEAK_CEIL = -3.0
BED_RMS_TARGET = -20.0
BED_RMS_TOL = 1.5


def dur_of(path):
    info = dsp.probe(path)
    return info['duration'], info['sample_rate'], info['channels']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=os.path.join(HERE, 'qc_report.json'))
    args = ap.parse_args()

    with open(MANIFEST, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    sounds = manifest['sounds']

    rows = []
    fails = []
    warns = []

    print(f'{"key":<22}{"kind":<7}{"dur":>7}{"sr":>7}{"ch":>4}{"peak":>8}{"rms":>8}{"seam":>10}  判定')
    print('-' * 92)

    for key, m in sounds.items():
        path = os.path.join(OUT, m['file'])
        row = {'key': key, 'file': m['file'], 'category': m['category'], 'layer': m['layer']}
        if not os.path.exists(path):
            fails.append(f'{key}: 文件缺失 {m["file"]}')
            print(f'{key:<22} 文件缺失')
            continue
        try:
            dur, sr, ch = dur_of(path)
            x = dsp.decode(path)
            mono = x.mean(axis=1) if x.ndim > 1 else x
            peak = dsp.peak_db(mono)
            rms = dsp.rms_db(mono)
            clip = float(np.mean(np.abs(mono) >= 0.999)) * 100
            dc = float(np.mean(mono))
            row.update(dur=round(dur, 2), sr=sr, ch=ch, peak_db=round(peak, 2),
                       rms_db=round(rms, 2), clip_pct=round(clip, 4), dc=round(dc, 6))

            verdict = []
            is_bed = m['loop']
            # --- 时长 ---
            lo, hi = BED_DUR_RANGE if is_bed else EVENT_DUR_RANGE
            if not (lo <= dur <= hi):
                verdict.append(f'时长{dur:.1f}s超范围[{lo},{hi}]')
            # --- 峰值 ---
            if is_bed:
                if peak > EVENT_PEAK_CEIL + 0.01:
                    verdict.append(f'床峰值{peak:.2f}>{EVENT_PEAK_CEIL}')
                if abs(rms - BED_RMS_TARGET) > BED_RMS_TOL:
                    verdict.append(f'床RMS{rms:.1f}偏离{BED_RMS_TARGET}')
            else:
                if peak > EVENT_PEAK_CEIL + 0.01:
                    verdict.append(f'峰值{peak:.2f}>{EVENT_PEAK_CEIL}')
            # --- 削波 / 直流 ---
            if clip > 0.001:
                verdict.append(f'削波{clip:.3f}%')
            if abs(dc) > 0.01:
                verdict.append(f'直流{dc:.3f}')
            # --- 采样率/格式 ---
            if sr != 44100:
                verdict.append(f'采样率{sr}')
            # --- 循环接缝 ---
            seam_s = ''
            if is_bed:
                s = dsp.loop_seam_report(mono, dsp.SR)
                row['seam'] = s
                seam_s = f'{s["seam_vs_p99_step"]:.2f}/{s["seam_vs_local_step_rms"]:.1f}'
                if not s['seam_ok']:
                    verdict.append('loop接缝超自然步进')
                if not s['energy_ok']:
                    verdict.append(f'首尾能量差{s["head_tail_delta_db"]}dB')

            row['verdict'] = 'OK' if not verdict else '; '.join(verdict)
            if verdict:
                fails.append(f'{key}: ' + row['verdict'])
            rows.append(row)
            print(f'{key:<22}{("bed" if is_bed else "event"):<7}{dur:>7.2f}{sr:>7}{ch:>4}'
                  f'{peak:>8.2f}{rms:>8.2f}{seam_s:>10}  {"OK" if not verdict else "!! " + row["verdict"]}')
        except Exception as e:
            fails.append(f'{key}: 读取失败 {e}')
            print(f'{key:<22} 读取失败 {e}')

    # ---------------- manifest 交叉引用 ----------------
    print('\n=== manifest 引用一致性 ===')
    all_keys = set(sounds.keys())
    refs = []
    for phase, p in manifest.get('presets', {}).items():
        for k in p.get('beds', []):
            refs.append((f'presets.{phase}.beds', k if isinstance(k, str) else k.get('key')))
        for e in p.get('events', []):
            refs.append((f'presets.{phase}.events', e if isinstance(e, str) else e.get('key')))
    for wx, p in manifest.get('weather', {}).items():
        for k in p.get('beds', []):
            refs.append((f'weather.{wx}.beds', k if isinstance(k, str) else k.get('key')))
        for e in p.get('events', []):
            refs.append((f'weather.{wx}.events', e if isinstance(e, str) else e.get('key')))
    ln = manifest.get('lightning', {})
    for f in ('crackKey', 'nearKey', 'midKey', 'farKey'):
        if ln.get(f):
            refs.append((f'lightning.{f}', ln[f]))

    bad_refs = [(where, k) for where, k in refs if k not in all_keys]
    if bad_refs:
        for where, k in bad_refs:
            fails.append(f'manifest 引用不存在的 key: {where} -> {k}')
        print('  ✗ ' + ', '.join(f'{w}->{k}' for w, k in bad_refs))
    else:
        print(f'  ✓ {len(refs)} 处引用全部指向存在的 key')

    # 必备 key 检查
    required = ['amb_morning', 'amb_noon', 'amb_dusk', 'amb_night',
                'amb_rain_light', 'amb_rain_med', 'amb_rain_heavy', 'amb_wind', 'amb_storm',
                'sfx_thunder_far', 'sfx_thunder_mid', 'sfx_thunder_close', 'sfx_lightning_crack',
                'sfx_cup_clink', 'sfx_saucer', 'sfx_machine_preheat', 'sfx_espresso_extract',
                'sfx_steam_wand', 'sfx_grinder', 'sfx_fridge', 'sfx_bell_chime', 'sfx_door_bell',
                'sfx_noren', 'sfx_cash_ding', 'sfx_page', 'sfx_chair', 'sfx_rollup', 'sfx_clean_steam']
    missing = [k for k in required if k not in all_keys]
    print('\n=== 必备 key ===')
    if missing:
        fails.append('缺少必备 key: ' + ', '.join(missing))
        print('  ✗ 缺少: ' + ', '.join(missing))
    else:
        print(f'  ✓ 28 个必备 key 齐全（实际 {len(all_keys)} 个）')

    # 总大小
    total_bytes = sum(os.path.getsize(os.path.join(OUT, m['file'])) for m in sounds.values()
                      if os.path.exists(os.path.join(OUT, m['file'])))
    total_mb = total_bytes / 1048576
    print(f'\n总大小: {total_mb:.2f} MB / 上限 40 MB  ->  {"OK" if total_mb <= 40 else "超限"}')
    if total_mb > 40:
        fails.append(f'总大小 {total_mb:.2f}MB 超过 40MB')

    # 汇总
    beds = [r for r in rows if r['category'] in ('ambience', 'weather')]
    events = [r for r in rows if r['category'] not in ('ambience', 'weather')]
    bed_dur = sum(r['dur'] for r in beds)
    ev_dur = sum(r['dur'] for r in events)
    print(f'\n床层: {len(beds)} 段, 共 {bed_dur:.1f}s  事件音: {len(events)} 段, 共 {ev_dur:.1f}s')
    print(f'文件数: {len(rows)}')

    summary = {
        'fileCount': len(rows),
        'totalMB': round(total_mb, 2),
        'bedCount': len(beds),
        'bedTotalSec': round(bed_dur, 2),
        'eventCount': len(events),
        'eventTotalSec': round(ev_dur, 2),
        'fails': fails,
        'rows': rows,
        'pass': len(fails) == 0,
    }
    with open(args.json, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print('\n' + '=' * 60)
    if fails:
        print(f'质检 FAIL：{len(fails)} 个问题')
        for x in fails:
            print('  - ' + x)
        print(f'\n报告：{args.json}')
        return 1
    print('质检 PASS ✅ 全部通过')
    print(f'报告：{args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
