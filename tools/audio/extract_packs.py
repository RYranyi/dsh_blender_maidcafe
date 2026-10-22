# 解压素材 zip 包并盘点内容（bundled python，避免落 %TEMP%）
import os, sys, zipfile, json

DL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".scratch", "audio-dev", "dl")
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".scratch", "audio-dev", "raw")
os.makedirs(RAW, exist_ok=True)

AUDIO_EXT = ('.wav', '.ogg', '.mp3', '.flac', '.m4a', '.aiff', '.aif')

report = {}
for name in sorted(os.listdir(DL)):
    if not name.lower().endswith('.zip'):
        continue
    stem = os.path.splitext(name)[0]
    outdir = os.path.join(RAW, stem)
    zpath = os.path.join(DL, name)
    try:
        with zipfile.ZipFile(zpath) as z:
            # 防 zip slip（Windows 上文件名可能带非法字符，统一清洗）
            members = z.namelist()
            os.makedirs(outdir, exist_ok=True)
            extracted = []
            for m in members:
                if m.endswith('/'):
                    continue
                try:
                    raw_name = m.encode('cp437').decode('utf-8', 'replace')
                except Exception:
                    raw_name = m
                safe = raw_name.replace('\\', '/').lstrip('/')
                safe = ''.join(ch if ch not in '<>:"|?*' else '_' for ch in safe)
                dest = os.path.join(outdir, safe)
                if not os.path.abspath(dest).startswith(os.path.abspath(outdir)):
                    continue  # zip slip 防护
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(m) as src, open(dest, 'wb') as dst:
                    dst.write(src.read())
                extracted.append(safe)
        audio = [e for e in extracted if e.lower().endswith(AUDIO_EXT)]
        total = sum(os.path.getsize(os.path.join(outdir, e)) for e in audio)
        report[stem] = {'count': len(audio), 'bytes': total, 'files': audio}
        print(f'\n### {stem}: {len(audio)} audio files, {total/1048576:.1f} MB')
        for e in audio:
            print('   ', e, f'{os.path.getsize(os.path.join(outdir,e))/1024:.0f}KB')
    except Exception as ex:
        print(f'\n### {stem} EXTRACT FAIL: {ex}')

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".scratch", "audio-dev", "pack_inventory.json"), 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('\nTOTAL audio files:', sum(v['count'] for v in report.values()))
