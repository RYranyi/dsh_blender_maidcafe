// OGA 高级搜索：只搜音效类 + CC0，打印提交 slug
// 用法: node oga_search.mjs "keyword1" "keyword2" ...
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36';

async function search(keys, opts = {}) {
  const typeId = opts.music ? '12' : '13'; // 12=音乐 13=音效
  const lic = opts.anyLic ? '' : '&field_art_licenses_tid%5B%5D=4'; // 4=CC0
  const url = `https://opengameart.org/art-search-advanced?keys=${encodeURIComponent(keys)}` +
    `&field_art_type_tid%5B%5D=${typeId}${lic}&sort_by=count&sort_order=DESC`;
  const res = await fetch(url, { headers: { 'user-agent': UA }, redirect: 'follow' });
  const html = await res.text();
  const subs = [...new Set([...html.matchAll(/href="(\/content\/[^"]+)"/g)].map((m) => m[1]))]
    .filter((s) => !/faq|art-challenge/.test(s));
  return { url, subs };
}

const queries = process.argv.slice(2);
for (const q of queries) {
  const music = /\[music\]/.test(q);
  const anyLic = /\[any\]/.test(q);
  const kw = q.replace(/\[music\]|\[any\]/g, '');
  try {
    const r = await search(kw, { music, anyLic });
    console.log(`\n=== "${kw}"${music ? ' [music]' : ''}${anyLic ? ' [any lic]' : ' [CC0]'} -> ${r.subs.length}`);
    r.subs.slice(0, 18).forEach((s) => console.log('   ' + s));
  } catch (e) {
    console.log(`\n=== "${kw}" FAIL ${e.message}`);
  }
}
