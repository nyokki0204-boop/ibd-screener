// Data files live beside the static site. No API key or external JavaScript is needed.
const SECTOR_NAMES = {
  'Basic Materials':'素材', 'Communication Services':'通信',
  'Consumer Cyclical':'一般消費財', 'Consumer Defensive':'生活必需品',
  'Energy':'エネルギー', 'Financial Services':'金融',
  'Healthcare':'ヘルスケア', 'Industrials':'資本財',
  'Real Estate':'不動産', 'Technology':'テクノロジー',
  'Utilities':'公益', 'その他':'その他'
};
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n = value => Number(value) || 0;
const sectorName = value => `${SECTOR_NAMES[value] || value || 'その他'}${value && value !== 'その他' ? ` (${value})` : ''}`;

function parseCSV(text) {
  const rows = [];
  let row = [], cell = '', quoted = false;
  const s = String(text || '').replace(/^\uFEFF/, '');
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === '"') {
      if (quoted && s[i + 1] === '"') { cell += '"'; i++; }
      else quoted = !quoted;
    } else if (c === ',' && !quoted) { row.push(cell); cell = ''; }
    else if ((c === '\n' || c === '\r') && !quoted) {
      if (c === '\r' && s[i + 1] === '\n') i++;
      row.push(cell); if (row.some(v => v !== '')) rows.push(row);
      row = []; cell = '';
    } else cell += c;
  }
  row.push(cell); if (row.some(v => v !== '')) rows.push(row);
  if (!rows.length) return [];
  const [header, ...values] = rows;
  return values.map(cells => Object.fromEntries(header.map((key, i) => [key, cells[i] ?? ''])));
}

function appearanceInfo(results, history, date) {
  const valid = history.filter(x => x.ticker && x.ticker !== '(該当なし)' && x.date);
  const dates = [...new Set(valid.map(x => x.date).filter(x => x < date))].sort().reverse().slice(0, 4);
  const selected = new Set([date, ...dates]);
  const past = new Set(valid.filter(x => x.date < date).map(x => x.ticker));
  const counts = new Map();
  for (const record of valid) if (selected.has(record.date)) {
    if (!counts.has(record.ticker)) counts.set(record.ticker, new Set());
    counts.get(record.ticker).add(record.date);
  }
  return results.map(x => ({...x, repeat: Math.max(1, counts.get(x.ticker)?.size || 0),
                            first: valid.length ? !past.has(x.ticker) : null}));
}

function sectorComparison(metrics, date) {
  const today = metrics.filter(x => x.date === date);
  const dates = [...new Set(metrics.map(x => x.date).filter(x => x < date))].sort().reverse().slice(0, 5);
  return today.filter(x => n(x.eligible) >= 10 && x.sector !== 'その他').map(x => {
    const prior = metrics.filter(y => y.sector === x.sector && dates.includes(y.date));
    const denominator = prior.reduce((sum, y) => sum + n(y.eligible), 0);
    const baseline = denominator ? 100 * prior.reduce((sum, y) => sum + n(y.passed), 0) / denominator : null;
    return {...x, rate: n(x.eligible) ? 100 * n(x.passed) / n(x.eligible) : 0,
            days: new Set(prior.map(y => y.date)).size,
            delta: baseline == null ? null : 100 * n(x.passed) / n(x.eligible) - baseline};
  }).sort((a,b) => (b.delta ?? -Infinity) - (a.delta ?? -Infinity) || b.rate - a.rate);
}

function safeChartUrl(ticker, base) {
  const symbol = String(ticker || '').trim().toUpperCase();
  if (!/^[A-Z0-9][A-Z0-9.\-^]{0,14}$/.test(symbol)) return '';
  try {
    const u = base ? new URL(base) : new URL(`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}`);
    if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return '';
    if (base) u.searchParams.set('ticker', symbol);
    return u.href;
  } catch { return ''; }
}

function totalChart(rows) {
  const points = rows.filter(x => /^\d{4}-\d{2}-\d{2}$/.test(x.date)).slice(-60);
  if (points.length < 2) return '<p class="empty">履歴が2日分以上になると表示します。</p>';
  const w = 760, h = 185, left = 31, right = 10, top = 9, bottom = 28;
  const max = Math.max(5, ...points.map(x => n(x.total)));
  const x = i => left + (w - left - right) * i / (points.length - 1);
  const y = v => top + (h - top - bottom) * (1 - v / max);
  const coords = points.map((p,i) => [x(i), y(n(p.total))]);
  const line = coords.map(([a,b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(' ');
  const area = `${left},${h-bottom} ${line} ${w-right},${h-bottom}`;
  const last = coords.at(-1);
  const labels = [0,Math.floor((points.length-1)/2),points.length-1].map(i =>
    `<text x="${x(i)}" y="${h-4}" text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}">${escapeHtml(points[i].date.slice(5))}</text>`).join('');
  const grids = [0,.5,1].map(f => `<line class="grid" x1="${left}" x2="${w-right}" y1="${y(max*f)}" y2="${y(max*f)}"/><text x="0" y="${y(max*f)+4}">${Math.round(max*f)}</text>`).join('');
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${escapeHtml(points[0].date)}から${escapeHtml(points.at(-1).date)}の通過銘柄数"><g>${grids}</g><polygon class="area" points="${area}"/><polyline class="line" points="${line}"/><circle cx="${last[0]}" cy="${last[1]}" r="4" fill="#42d9a4"/>${labels}</svg>`;
}

let state = {results:[], history:[], metrics:[], sectorHistory:[], date:'', status:{}};
function chartBase() { try { return localStorage.getItem('ibd-mychart-url') || ''; } catch { return ''; } }

function renderQuality() {
  const s = state.status, node = $('quality');
  node.className = 'quality';
  if (s.ok === false) {
    node.classList.add('error');
    node.textContent = `最新のスキャンは未完了：${s.reason || '原因不明'}。表示中は前回の正常な結果（${state.date}）です。`;
  } else if (s.ok === true) {
    const run = s.checked_at_utc ? new Date(s.checked_at_utc) : null;
    const lag = run && state.date ? Math.floor((Date.UTC(run.getUTCFullYear(),run.getUTCMonth(),run.getUTCDate()) - Date.parse(state.date+'T00:00:00Z'))/86400000) : 0;
    if (lag >= 2) node.classList.add('warn');
    node.textContent = `${lag >= 2 ? '注意：保存済みデータが遅れている可能性があります。' : '正常に取得した保存データです。'} 判定 ${n(s.evaluated).toLocaleString()}/${n(s.universe).toLocaleString()}銘柄（${(100*n(s.coverage)).toFixed(1)}%）。`;
  } else {
    node.classList.add('warn'); node.textContent = 'スキャン状態が不明です。表示中の取引日を確認してください。';
  }
}

function renderSectors() {
  const list = sectorComparison(state.metrics, state.date);
  if (!list.length) { $('sectorView').innerHTML = '<p class="empty">この取引日の分母付き集計はありません。</p>'; return; }
  const max = Math.max(1, ...list.map(x => x.rate));
  $('sectorView').innerHTML = list.map(s => {
    const d = s.delta == null ? '比較待ち' : `前${s.days}日 ${s.delta >= 0 ? '+' : ''}${s.delta.toFixed(2)}pt`;
    const sign = s.delta == null ? '' : s.delta > 0 ? 'up' : s.delta < 0 ? 'down' : '';
    return `<div class="sector-row"><div class="sector-head"><strong>${escapeHtml(sectorName(s.sector))}</strong><span>${s.rate.toFixed(2)}%</span></div><div class="sector-bar"><i style="width:${Math.max(0,Math.min(100,100*s.rate/max))}%"></i></div><div class="sector-meta"><span>${n(s.passed)} / ${n(s.eligible)}銘柄</span><span class="delta ${sign}">${escapeHtml(d)}</span></div></div>`;
  }).join('');
}

function renderStocks() {
  const q = $('searchInput').value.trim().toUpperCase();
  const sector = $('sectorSelect').value;
  const sort = $('sortSelect').value;
  const filtered = state.results.filter(x => (!sector || x.sector === sector) &&
    (!q || `${x.ticker} ${x.sector} ${SECTOR_NAMES[x.sector] || ''} ${x.industry}`.toUpperCase().includes(q)));
  const order = {repeat:(a,b)=>b.repeat-a.repeat || n(b.RS)-n(a.RS),
                 rs:(a,b)=>n(b.RS)-n(a.RS),
                 change:(a,b)=>n(b['前日比%'])-n(a['前日比%']),
                 volume:(a,b)=>n(b.RelVol)-n(a.RelVol)};
  filtered.sort(order[sort] || order.repeat);
  $('visibleCount').textContent = `${filtered.length}銘柄`;
  if (!filtered.length) { $('stockList').innerHTML = '<p class="empty">該当する銘柄はありません。</p>'; return; }
  $('stockList').innerHTML = filtered.map(x => {
    const url = safeChartUrl(x.ticker, chartBase());
    const tags = `${x.first ? '<span class="new-tag">NEW</span>' : ''}${x.repeat >= 2 ? `<span class="repeat-tag">直近5日 ${x.repeat}回</span>` : ''}`;
    return `<a class="stock-card" href="${escapeHtml(url || '#')}" target="_blank" rel="noopener noreferrer"><div class="stock-top"><div class="stock-title"><span class="stock-symbol">${escapeHtml(x.ticker)}</span>${tags}</div><span class="stock-change">+${n(x['前日比%']).toFixed(1)}%</span></div><div class="stock-sector">${escapeHtml(sectorName(x.sector))} · ${escapeHtml(x.industry)}</div><div class="stock-bottom"><span>RS <b>${n(x.RS)}</b></span><span>RelVol <b>${n(x.RelVol).toFixed(2)}</b></span><span>株価 <b>$${n(x['株価']).toFixed(2)}</b></span></div><div class="open-label">${chartBase() ? 'マイチャートで開く ↗' : 'TradingViewで開く ↗'}</div></a>`;
  }).join('');
}

function renderHistory() {
  const day = $('historyDate').value;
  const rows = state.history.filter(x => x.date === day && x.ticker && x.ticker !== '(該当なし)');
  $('historyList').innerHTML = rows.length ? rows.map(x => {
    const url = safeChartUrl(x.ticker, chartBase());
    return `<a href="${escapeHtml(url || '#')}" target="_blank" rel="noopener noreferrer">${escapeHtml(x.ticker)}</a>`;
  }).join('') : '<span class="muted">該当銘柄なし</span>';
}

async function loadData() {
  const file = async (path, optional=false) => {
    try { const r = await fetch(`./data/${path}?v=${Date.now()}`, {cache:'no-store'}); if (!r.ok) throw new Error(`${r.status} ${path}`); return await r.text(); }
    catch (e) { if (optional) return ''; throw e; }
  };
  try {
    const [date, resultText, historyText, metricText, sectorText, statusText] = await Promise.all([
      file('last_updated.txt'), file('results.csv'), file('ticker_history.csv',true),
      file('sector_metrics.csv',true), file('sector_history.csv',true), file('scan_status.json',true)]);
    state.date = date.trim();
    const results = parseCSV(resultText);
    state.history = parseCSV(historyText);
    state.metrics = parseCSV(metricText);
    state.sectorHistory = parseCSV(sectorText);
    try { state.status = statusText ? JSON.parse(statusText) : {}; } catch { state.status = {}; }
    state.results = appearanceInfo(results, state.history, state.date);
    $('marketDate').textContent = state.date || '不明';
    $('totalCount').textContent = results.length;
    $('newCount').textContent = state.results.filter(x => x.first).length;
    const sectorCounts = new Map();
    for (const x of results) sectorCounts.set(x.sector || 'その他', (sectorCounts.get(x.sector || 'その他') || 0)+1);
    const top = [...sectorCounts].sort((a,b)=>b[1]-a[1])[0];
    $('topSector').textContent = top ? (SECTOR_NAMES[top[0]] || top[0]) : '—';
    $('topSectorCount').textContent = top ? `${top[1]}銘柄` : '該当なし';
    const currentSector = $('sectorSelect').value;
    $('sectorSelect').innerHTML = '<option value="">全セクター</option>' + [...sectorCounts.keys()].sort().map(s=>`<option value="${escapeHtml(s)}">${escapeHtml(sectorName(s))}</option>`).join('');
    $('sectorSelect').value = currentSector;
    const currentDate = $('historyDate').value;
    const dates = [...new Set(state.history.map(x=>x.date).filter(Boolean))].sort().reverse();
    $('historyDate').innerHTML = dates.map(d=>`<option value="${escapeHtml(d)}">${escapeHtml(d)}</option>`).join('');
    $('historyDate').value = dates.includes(currentDate) ? currentDate : (dates[0] || '');
    $('totalChart').innerHTML = totalChart(state.sectorHistory);
    renderQuality(); renderSectors(); renderStocks(); renderHistory();
  } catch (e) {
    $('quality').className = 'quality error';
    $('quality').textContent = `データを読み込めませんでした。公開設定または接続を確認してください（${e.message}）。`;
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    $('refreshButton').addEventListener('click', loadData);
    for (const id of ['searchInput','sectorSelect','sortSelect']) $(id).addEventListener(id==='searchInput'?'input':'change', renderStocks);
    $('historyDate').addEventListener('change', renderHistory);
    $('settingsButton').addEventListener('click',()=>{ $('chartUrl').value = chartBase(); $('settingsDialog').showModal(); });
    $('settingsDialog').addEventListener('close',()=>{
      if ($('settingsDialog').returnValue !== 'save') return;
      const value = $('chartUrl').value.trim();
      if (value && !safeChartUrl('AAPL', value)) { alert('http または https の公開URLを入力してください。'); return; }
      try { localStorage.setItem('ibd-mychart-url', value); } catch { alert('この端末にはURLを保存できませんでした。'); }
      renderStocks(); renderHistory();
    });
    loadData();
  });
}
if (typeof module !== 'undefined') module.exports = {parseCSV, appearanceInfo, sectorComparison, safeChartUrl, totalChart};
