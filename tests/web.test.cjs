const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {parseCSV, appearanceInfo, sectorComparison, safeChartUrl, totalChart} = require('../web.js');

test('CSV parser handles quoted commas, double quotes and BOM', () => {
  const rows = parseCSV('\uFEFFticker,industry,RS\r\nA,"Tools, Hardware",88\r\nB,"A ""quoted"" name",90\r\n');
  assert.deepEqual(rows, [{ticker:'A',industry:'Tools, Hardware',RS:'88'},
                          {ticker:'B',industry:'A "quoted" name',RS:'90'}]);
});

test('reappearance uses distinct market dates and excludes zero-match sentinel', () => {
  const current = [{ticker:'A'}, {ticker:'B'}];
  const history = [{date:'2026-09-24',ticker:'A'}, {date:'2026-09-23',ticker:'A'},
                   {date:'2026-09-23',ticker:'A'}, {date:'2026-09-22',ticker:'(該当なし)'},
                   {date:'2026-09-24',ticker:'B'}];
  const out = appearanceInfo(current, history, '2026-09-24');
  assert.equal(out[0].repeat, 2);
  assert.equal(out[0].first, false);
  assert.equal(out[1].first, true);
});

test('sector comparison recomputes previous rate from numerator and denominator', () => {
  const data = [
    {date:'2026-09-22',sector:'Tech',eligible:'10',passed:'1'},
    {date:'2026-09-23',sector:'Tech',eligible:'100',passed:'2'},
    {date:'2026-09-24',sector:'Tech',eligible:'50',passed:'3'}
  ];
  const one = sectorComparison(data, '2026-09-24')[0];
  assert.equal(one.rate, 6);
  assert.equal(one.days, 2);
  assert.ok(Math.abs(one.delta - (6 - 300/110)) < 1e-9);
});

test('chart URLs reject active schemes and preserve existing query', () => {
  assert.equal(safeChartUrl('AAPL','javascript:alert(1)'), '');
  assert.equal(safeChartUrl('AAPL,FOO','https://example.com/chart'), '');
  assert.equal(safeChartUrl('AAPL','https://example.com/chart?theme=dark'),
               'https://example.com/chart?theme=dark&ticker=AAPL');
});

test('real saved dataset renders a historical chart and sector comparison', () => {
  const history = parseCSV(fs.readFileSync('data/sector_history.csv','utf8'));
  const metrics = parseCSV(fs.readFileSync('data/sector_metrics.csv','utf8'));
  assert.match(totalChart(history), /<svg/);
  assert.ok(sectorComparison(metrics, '2026-09-24').length > 0);
});
