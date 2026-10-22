"""
make_manifest.py - 生成 assets/audio/manifest.json

内容：
  sounds     : {key: {file, loop, gain, fadeInMs, fadeOutMs, category, layer}}
  presets    : 时间档 -> {beds:[], events:[]}
  weather    : 天气 -> {beds:[], events:[]}
  lightning  : 闪电->雷声延迟规则（迟延区间 + 近雷概率）
  timings    : 各天气的事件随机间隔（雷阵雨 3-10s）
所有数值来自 build_report.json 的实测（时长/峰值）+ 人工分层决定。
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT_DIR = os.path.join(ROOT, 'assets', 'audio')
REPORT = os.path.join(HERE, 'build_report.json')
QC = os.path.join(HERE, 'qc_report.json')

# 优先用 QC 对"真实交付文件"的实测量（比构建时内存数据更可信）
report = {}
if os.path.exists(QC):
    with open(QC, 'r', encoding='utf-8') as f:
        qc = json.load(f)
    for r in qc.get('rows', []):
        report[r['key']] = {
            'dur': r.get('dur'), 'peak_db': r.get('peak_db'),
            'rms_db': r.get('rms_db'),
            'bytes': os.path.getsize(os.path.join(OUT_DIR, r['file'])),
        }
    print('电平数据来源: qc_report.json（实测交付文件）')
else:
    with open(REPORT, 'r', encoding='utf-8') as f:
        report = {r['key']: r for r in json.load(f)}
    print('电平数据来源: build_report.json（构建时内存）')


def meta(key, *, loop, gain, fade_in, fade_out, category, layer):
    r = report.get(key, {})
    m = {
        'file': key + '.ogg',
        'loop': loop,
        'gain': gain,
        'fadeInMs': fade_in,
        'fadeOutMs': fade_out,
        'category': category,
        'layer': layer,
    }
    if r:
        m['durationSec'] = round(r['dur'], 2)
        m['peakDbfs'] = r['peak_db']
        m['rmsDbfs'] = r['rms_db']
        m['bytes'] = r['bytes']
        # 接缝结论取 QC 行（若存在）
        seam = r.get('seam')
        if seam is not None:
            m['seamOk'] = bool(seam.get('seam_ok') and seam.get('energy_ok'))
    return m


sounds = {}

# ---------------- 环境床（时间 4 档）----------------
sounds['amb_morning'] = meta('amb_morning', loop=True, gain=0.0, fade_in=1200, fade_out=1200,
                             category='ambience', layer='time_bed')
sounds['amb_noon'] = meta('amb_noon', loop=True, gain=0.0, fade_in=1200, fade_out=1200,
                          category='ambience', layer='time_bed')
sounds['amb_dusk'] = meta('amb_dusk', loop=True, gain=0.0, fade_in=1200, fade_out=1200,
                          category='ambience', layer='time_bed')
sounds['amb_night'] = meta('amb_night', loop=True, gain=0.0, fade_in=1200, fade_out=1200,
                           category='ambience', layer='time_bed')

# ---------------- 天气床 ----------------
sounds['amb_rain_light'] = meta('amb_rain_light', loop=True, gain=0.0, fade_in=1500, fade_out=1500,
                                category='weather', layer='weather_bed')
sounds['amb_rain_med'] = meta('amb_rain_med', loop=True, gain=0.0, fade_in=1500, fade_out=1500,
                              category='weather', layer='weather_bed')
sounds['amb_rain_heavy'] = meta('amb_rain_heavy', loop=True, gain=0.0, fade_in=1500, fade_out=1500,
                                category='weather', layer='weather_bed')
sounds['amb_wind'] = meta('amb_wind', loop=True, gain=0.0, fade_in=1500, fade_out=1500,
                          category='weather', layer='weather_bed')
sounds['amb_storm'] = meta('amb_storm', loop=True, gain=0.0, fade_in=1500, fade_out=1500,
                           category='weather', layer='weather_bed')

# ---------------- 事件音 ----------------
# gain 是该 one-shot 相对 0dB 的基准衰减（放进混音时再叠加）
EV = [
    ('sfx_thunder_far', 'thunder', -4.0),
    ('sfx_thunder_mid', 'thunder', -2.0),
    ('sfx_thunder_close', 'thunder', 0.0),
    ('sfx_lightning_crack', 'thunder', -6.0),
    ('sfx_cup_clink', 'cafe_ware', -8.0),
    ('sfx_saucer', 'cafe_ware', -10.0),
    ('sfx_machine_preheat', 'cafe_machine', -9.0),
    ('sfx_espresso_extract', 'cafe_machine', -8.0),
    ('sfx_steam_wand', 'cafe_machine', -10.0),
    ('sfx_grinder', 'cafe_machine', -9.0),
    ('sfx_fridge', 'cafe_machine', -14.0),
    ('sfx_bell_chime', 'entrance', -8.0),
    ('sfx_door_bell', 'entrance', -7.0),
    ('sfx_noren', 'entrance', -12.0),
    ('sfx_cash_ding', 'counter', -8.0),
    ('sfx_page', 'paper', -13.0),
    ('sfx_chair', 'furniture', -12.0),
    ('sfx_rollup', 'shop', -6.0),
    ('sfx_clean_steam', 'shop', -9.0),
]
for key, cat, gain in EV:
    sounds[key] = meta(key, loop=False, gain=gain, fade_in=10, fade_out=60,
                       category=cat, layer='one_shot')

# ---------------- 时间档 preset ----------------
presets = {
    'morning': {
        'beds': ['amb_morning'],
        'events': [
            {'key': 'sfx_page', 'weight': 3},
            {'key': 'sfx_cup_clink', 'weight': 3},
            {'key': 'sfx_bell_chime', 'weight': 2},
            {'key': 'sfx_chair', 'weight': 2},
            {'key': 'sfx_machine_preheat', 'weight': 2},
            {'key': 'sfx_cash_ding', 'weight': 1},
        ],
    },
    'noon': {
        'beds': ['amb_noon'],
        'events': [
            {'key': 'sfx_cup_clink', 'weight': 4},
            {'key': 'sfx_saucer', 'weight': 3},
            {'key': 'sfx_door_bell', 'weight': 3},
            {'key': 'sfx_espresso_extract', 'weight': 3},
            {'key': 'sfx_fridge', 'weight': 1},
            {'key': 'sfx_cash_ding', 'weight': 2},
            {'key': 'sfx_page', 'weight': 2},
        ],
    },
    'dusk': {
        'beds': ['amb_dusk'],
        'events': [
            {'key': 'sfx_cup_clink', 'weight': 3},
            {'key': 'sfx_door_bell', 'weight': 3},
            {'key': 'sfx_noren', 'weight': 2},
            {'key': 'sfx_cash_ding', 'weight': 2},
            {'key': 'sfx_steam_wand', 'weight': 2},
            {'key': 'sfx_chair', 'weight': 2},
        ],
    },
    'night': {
        'beds': ['amb_night'],
        'events': [
            {'key': 'sfx_cup_clink', 'weight': 2},
            {'key': 'sfx_saucer', 'weight': 2},
            {'key': 'sfx_noren', 'weight': 2},
            {'key': 'sfx_page', 'weight': 2},
            {'key': 'sfx_clean_steam', 'weight': 1},
            {'key': 'sfx_fridge', 'weight': 1},
        ],
    },
}

# ---------------- 天气 preset ----------------
weather = {
    'clear': {
        'beds': [],
        'events': [],
        'note': '晴天无天气床，只保留时间床',
    },
    'cloudy': {
        'beds': ['amb_wind'],
        'gainDb': -8.0,
        'events': [],
        'note': '阴天挂一层很轻的风（音量由 gainDb 压低）',
    },
    'rain_light': {
        'beds': ['amb_rain_light'],
        'events': [{'key': 'sfx_cup_clink', 'weight': 1}],
    },
    'rain_med': {
        'beds': ['amb_rain_med'],
        'events': [],
    },
    'rain_heavy': {
        'beds': ['amb_rain_heavy'],
        'events': [],
    },
    'storm': {
        'beds': ['amb_storm'],
        'events': [
            {'key': 'sfx_thunder_close', 'weight': 3},
            {'key': 'sfx_thunder_mid', 'weight': 3},
            {'key': 'sfx_thunder_far', 'weight': 2},
        ],
    },
}

# ---------------- 闪电 -> 雷声 延迟规则 ----------------
lightning = {
    'nearProbability': 0.45,
    'near': {'minMs': 300, 'maxMs': 1200,
             'keys': ['sfx_thunder_close'],
             'note': '近雷：光后 0.3-1.2s 炸响，同时播闪电高频裂响'},
    'far': {'minMs': 800, 'maxMs': 2600,
            'keys': ['sfx_thunder_mid', 'sfx_thunder_far'],
            'note': '远雷：光后 0.8-2.6s 才听到，低频滚雷'},
    'crackKey': 'sfx_lightning_crack',
    'crackGainDb': -6,
    'nearKey': 'sfx_thunder_close',
    'midKey': 'sfx_thunder_mid',
    'farKey': 'sfx_thunder_far',
    'cooldownMs': 400,
    'note': '网页 notifyLightning() 触发：引擎 emit lightning 做白光爆闪，并按本规则延时播雷',
}

# ---------------- 事件随机间隔 ----------------
timings = {
    'weather': {
        'clear': {'minMs': 9000, 'maxMs': 20000},
        'cloudy': {'minMs': 9000, 'maxMs': 20000},
        'rain_light': {'minMs': 8000, 'maxMs': 16000},
        'rain_med': {'minMs': 8000, 'maxMs': 16000},
        'rain_heavy': {'minMs': 7000, 'maxMs': 14000},
        # 雷阵雨：闪电间隔 3-10s
        'storm': {'minMs': 3000, 'maxMs': 10000},
    },
    'timePhase': {
        'morning': {'minMs': 6000, 'maxMs': 14000},
        'noon': {'minMs': 5000, 'maxMs': 12000},
        'dusk': {'minMs': 6000, 'maxMs': 14000},
        'night': {'minMs': 10000, 'maxMs': 22000},
    },
    'note': 'storm 下引擎走闪电调度（3-10s 一次），其余按 events 权重随机',
}

# ---------------- 混音建议 ----------------
mix = {
    'bedTargetRmsDbfs': -20.0,
    'sfxPeakCeilingDbfs': -3.0,
    'defaultFadeInMs': 1200,
    'defaultFadeOutMs': 1500,
    'maxConcurrentOneShots': 6,
    'note': '床层 RMS 统一 -20dBFS；事件音峰值 -3dBFS；交叉淡化 1-2s',
}

manifest = {
    'version': 1,
    'sampleRate': 44100,
    'format': 'ogg',
    'basePath': '/assets/audio/',
    'generatedFrom': 'tools/audio/build_assets.py + make_manifest.py',
    'totalBytes': sum(m['bytes'] for m in sounds.values() if 'bytes' in m),
    'mix': mix,
    'sounds': sounds,
    'presets': presets,
    'weather': weather,
    'lightning': lightning,
    'timings': timings,
}

out_path = os.path.join(OUT_DIR, 'manifest.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print('wrote', out_path)
print('sounds:', len(sounds))
print('total MB: %.2f' % (manifest['totalBytes'] / 1048576))
print('keys:', ', '.join(sounds.keys()))
