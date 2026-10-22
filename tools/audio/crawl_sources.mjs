// 抓取素材候选页（把 HTML 落盘便于分析，同时打印出可下载文件链接）
// 用法: node crawl_sources.mjs <outDir>
import fs from 'node:fs';
import path from 'node:path';

const outDir = process.argv[2] || '.';
fs.mkdirSync(outDir, { recursive: true });

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 maid-cafe-audio/1.0';

async function get(url) {
  const res = await fetch(url, { headers: { 'user-agent': UA }, redirect: 'follow' });
  const buf = Buffer.from(await res.arrayBuffer());
  return { status: res.status, buf, url: res.url, ct: res.headers.get('content-type') || '' };
}

const AUDIO_RE = /href="([^"]*\.(?:ogg|mp3|wav|flac|m4a))"/gi;

const pages = [];

// --- OpenGameArt 搜索：音效(13) / 音乐(12)，许可证 CC0(4) / CC-BY 3.0(5) / CC-BY 4.0(6) / OGA-BY(7)
const ogaQueries = {
  'oga_rain_cc0': 'https://opengameart.org/art-search-advanced?keys=rain&field_art_type_tid%5B%5D=13&field_art_licenses_tid%5B%5D=4',
  'oga_rain_loop_cc0': 'https://opengameart.org/art-search-advanced?keys=rain+loop&field_art_type_tid%5B%5D=13&field_art_licenses_tid%5B%5D=4',
  'oga_thunder_cc0': 'https://opengameart.org/art-search-advanced?keys=thunder&field_art_licenses_tid%5B%5D=4',
  'oga_storm_cc0': 'https://opengameart.org/art-search-advanced?keys=storm+wind&field_art_licenses_tid%5B%5D=4',
  'oga_wind_loop_cc0': 'https://opengameart.org/art-search-advanced?keys=wind+loop&field_art_type_tid%5B%5D=13&field_art_licenses_tid%5B%5D=4',
  'oga_cup_cc0': 'https://opengameart.org/art-search-advanced?keys=cup+clink&field_art_licenses_tid%5B%5D=4',
  'oga_bell_cc0': 'https://opengameart.org/art-search-advanced?keys=bell+chime&field_art_licenses_tid%5B%5D=4',
  'oga_doorbell_cc0': 'https://opengameart.org/art-search-advanced?keys=door+bell&field_art_licenses_tid%5B%5D=4',
  'oga_page_cc0': 'https://opengameart.org/art-search-advanced?keys=page+turn&field_art_licenses_tid%5B%5D=4',
  'oga_coffee_cc0': 'https://opengameart.org/art-search-advanced?keys=coffee+grinder&field_art_licenses_tid%5B%5D=4',
  'oga_register_cc0': 'https://opengameart.org/art-search-advanced?keys=cash+register&field_art_licenses_tid%5B%5D=4',
  'oga_chair_cc0': 'https://opengameart.org/art-search-advanced?keys=chair&field_art_licenses_tid%5B%5D=4',
  'oga_birds_cc0': 'https://opengameart.org/art-search-advanced?keys=birds+ambience&field_art_licenses_tid%5B%5D=4',
  'oga_city_cc0': 'https://opengameart.org/art-search-advanced?keys=city+ambience&field_art_licenses_tid%5B%5D=4',
  'oga_insects_cc0': 'https://opengameart.org/art-search-advanced?keys=insects+crickets&field_art_licenses_tid%5B%5D=4',
  'oga_train_cc0': 'https://opengameart.org/art-search-advanced?keys=train&field_art_type_tid%5B%5D=13&field_art_licenses_tid%5B%5D=4',
  'oga_cafe_cc0': 'https://opengameart.org/art-search-advanced?keys=cafe+restaurant&field_art_licenses_tid%5B%5D=4',
  'oga_lightning_cc0': 'https://opengameart.org/art-search-advanced?keys=lightning&field_art_licenses_tid%5B%5D=4',
  'oga_steam_cc0': 'https://opengameart.org/art-search-advanced?keys=steam&field_art_type_tid%5B%5D=13&field_art_licenses_tid%5B%5D=4',
};

// --- freepd 目录页
const freepdPages = {
  'freepd_index': 'https://freepd.com/',
  'freepd_jazz': 'https://freepd.com/jazz.php',
  'freepd_ambient': 'https://freepd.com/ambient.php',
  'freepd_electronic': 'https://freepd.com/electronic.php',
  'freepd_world': 'https://freepd.com/world.php',
  'freepd_horror': 'https://freepd.com/horror.php',
  'freepd_scoring': 'https://freepd.com/scoring.php',
};

const jobs = { ...ogaQueries, ...freepdPages };
for (const [name, url] of Object.entries(jobs)) {
  try {
    const r = await get(url);
    const html = r.buf.toString('utf8');
    fs.writeFileSync(path.join(outDir, name + '.html'), html);
    const files = [...new Set([...html.matchAll(AUDIO_RE)].map((m) => m[1]))];
    const submissions = [...new Set([...html.matchAll(/href="(\/content\/[^"]+)"/g)].map((m) => m[1]))];
    console.log(`\n### ${name}  status=${r.status} bytes=${html.length} audio=${files.length} subs=${submissions.length}`);
    files.slice(0, 25).forEach((f) => console.log('   FILE ' + f));
    submissions.slice(0, 30).forEach((s) => console.log('   SUB  ' + s));
  } catch (e) {
    console.log(`\n### ${name} FAIL ${e.message}`);
  }
}
