/* ============================================================
   A股情绪轮动终端 —— 共享前端助手
   情绪日报 / 行业轮动仪表盘 两页共用；避免重复实现。
   页面需在调用 startAuto 前设置 window.__reload = () => load(true)。
   ============================================================ */
const $ = s => document.querySelector(s);
const red = c => c > 0 ? 'pos' : (c < 0 ? 'neg' : 'mut');

const fmtPct = v => (v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(2) + '%');

const fmtMoney = wan => {
  if (wan == null) return '—';
  const a = Math.abs(wan);
  if (a >= 10000) return '¥' + (wan / 10000).toFixed(2) + '亿';
  return '¥' + wan.toFixed(1) + '万';
};

const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* 双向条形图（净买/净卖、行业净流入等） */
function divergeChart(items, kind) {
  if (!items || !items.length) return '<div class="loading">无数据</div>';
  const W = 720, cx = 360, barMax = 205, rowH = 20, padT = 6;
  const n = items.length, H = padT + n * rowH + 6;
  const max = Math.max(...items.map(x => Math.abs(x.v || 0)), 0.01);
  let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  s += `<line x1="${cx}" y1="0" x2="${cx}" y2="${H}" stroke="#2a3344" stroke-width="1"></line>`;
  items.forEach((x, i) => {
    const y = padT + i * rowH, v = x.v || 0, w = (Math.abs(v) / max) * barMax;
    const col = v >= 0 ? '#ff4d5e' : '#1fd18e';
    const val = kind === 'money' ? fmtMoney(v) : fmtPct(v);
    if (v >= 0) {
      s += `<text x="8" y="${y + 14}" fill="#e6edf3" font-size="11.5" text-anchor="start">${esc(x.name)}</text>`;
      s += `<rect x="${cx}" y="${y + 3}" width="${w}" height="14" rx="3" fill="${col}"></rect>`;
      s += `<text x="${cx + w + 5}" y="${y + 14}" fill="${col}" font-size="11.5">${val}</text>`;
    } else {
      s += `<text x="${W - 8}" y="${y + 14}" fill="#e6edf3" font-size="11.5" text-anchor="end">${esc(x.name)}</text>`;
      s += `<rect x="${cx - w}" y="${y + 3}" width="${w}" height="14" rx="3" fill="${col}"></rect>`;
      s += `<text x="${cx - w - 5}" y="${y + 14}" fill="${col}" font-size="11.5" text-anchor="end">${val}</text>`;
    }
  });
  s += `</svg>`;
  return s;
}

/* 自动刷新计时器（依赖页面 #autoStatus；到点触发 window.__reload） */
let autoSec = 0, autoLeft = 0, autoTick = null;
function startAuto(sec) {
  stopAuto();
  if (sec <= 0) return;
  autoSec = sec; autoLeft = sec;
  autoTick = setInterval(() => {
    if (--autoLeft <= 0) { autoLeft = autoSec; if (window.__reload) window.__reload(); }
    paintAuto();
  }, 1000);
  paintAuto();
}
function stopAuto() { if (autoTick) { clearInterval(autoTick); autoTick = null; } paintAuto(); }
function paintAuto() {
  const el = $('#autoStatus');
  if (el) el.textContent = autoSec > 0 ? `自动刷新 开 · 每${autoSec}s（${autoLeft}s后）` : '';
}
