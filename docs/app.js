/* 重点ETF资金看板（复制版）前端：纯原生 JS + 内联 SVG，无外部依赖。 */
(function () {
  'use strict';

  var REFRESH_SECONDS = 60;
  var board = null;
  var autoEnabled = true;
  var remain = REFRESH_SECONDS;

  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var num = function (v) { return (v == null || isNaN(v)) ? null : Number(v); };
  var fmt = function (v, d) { var n = num(v); return n == null ? '—' : n.toFixed(d == null ? 2 : d); };
  var sfmt = function (v, d) {
    var n = num(v);
    return n == null ? '—' : (n > 0 ? '+' : '') + n.toFixed(d == null ? 2 : d);
  };
  var tone = function (v) { var n = num(v) || 0; return n > 0 ? 'up' : (n < 0 ? 'down' : ''); };
  var md = function (date) { return date ? String(date).slice(5) : ''; };

  function kpi(label, value, sub, valueClass) {
    return '<div class="kpi"><div class="kpi-label">' + esc(label) + '</div>' +
      '<div class="kpi-value ' + (valueClass || '') + '">' + value + '</div>' +
      '<div class="kpi-sub">' + esc(sub || '') + '</div></div>';
  }

  /* ------------------------- SVG 图表 ------------------------- */
  function svgHBars(items, labelWidth) {
    var rowH = 20, gap = 7, W = 900, lw = labelWidth || 215;
    var H = Math.max(40, items.length * (rowH + gap) + 14);
    var chartW = W - lw - 90;
    var max = Math.max.apply(null, items.map(function (i) { return Math.abs(num(i.value) || 0); }).concat([1]));
    var out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="ETF成交额柱状图">';
    items.forEach(function (it, idx) {
      var y = 7 + idx * (rowH + gap);
      var v = num(it.value) || 0;
      var w = Math.max(2, Math.abs(v) / max * chartW);
      var color = num(it.change) > 0 ? '#d0454c' : (num(it.change) < 0 ? '#1f9d6b' : '#8291a8');
      out += '<text x="0" y="' + (y + rowH * 0.75) + '" font-size="12" fill="#33425e">' + esc(it.label) + '</text>';
      out += '<rect x="' + lw + '" y="' + y + '" width="' + chartW + '" height="' + rowH + '" rx="3" fill="#f0f3f8"/>';
      out += '<rect x="' + lw + '" y="' + y + '" width="' + w + '" height="' + rowH + '" rx="3" fill="' + color + '" opacity="0.85"/>';
      out += '<text x="' + (lw + chartW + 8) + '" y="' + (y + rowH * 0.75) + '" font-size="12" fill="#52627d">' + fmt(v, 2) + '</text>';
    });
    return out + '</svg>';
  }

  function svgVBars(items, opts) {
    var W = 900, H = 280, pad = { l: 52, r: 14, t: 22, b: 40 };
    var pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
    var vals = items.map(function (i) { return num(i.value) || 0; });
    var threshold = opts.threshold || 100;
    var lineValue = num(opts.lineValue) || 0;
    var maxV = Math.max.apply(null, vals.concat([lineValue, threshold, 1])) * 1.15;
    var minV = Math.min.apply(null, vals.concat([0])) * 1.15;
    var range = (maxV - minV) || 1;
    var y = function (v) { return pad.t + (maxV - v) / range * ph; };
    var step = pw / Math.max(items.length, 1);
    var bw = Math.max(5, Math.min(34, step * 0.62));
    var out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="日度净流入柱状图">';
    out += '<text x="2" y="12" font-size="11" fill="#8b97ab">亿元</text>';

    // 水平网格
    var tick = 0;
    while (tick <= maxV) {
      var gy = y(tick);
      out += '<line x1="' + pad.l + '" y1="' + gy + '" x2="' + (W - pad.r) + '" y2="' + gy + '" stroke="#e8edf4" stroke-width="1"/>';
      out += '<text x="' + (pad.l - 6) + '" y="' + (gy + 4) + '" font-size="10" fill="#8b97ab" text-anchor="end">' + tick + '</text>';
      tick += 200;
    }
    // 最新柱水平虚线
    var ly = y(lineValue);
    out += '<line x1="' + pad.l + '" y1="' + ly + '" x2="' + (W - pad.r) + '" y2="' + ly + '" stroke="#7a869c" stroke-width="1.5" stroke-dasharray="6 4"/>';
    out += '<text x="' + (W - pad.r - 2) + '" y="' + (ly - 6) + '" font-size="11" fill="#59677e" text-anchor="end">最新 ' + fmt(lineValue, 1) + '</text>';

    items.forEach(function (it, idx) {
      var v = num(it.value) || 0;
      var cx = pad.l + step * (idx + 0.5);
      var top = v >= 0 ? y(v) : y(0);
      var h = Math.max(1, Math.abs(y(v) - y(0)));
      var color = '#2f67c9';
      if (v > threshold) color = '#d0454c';
      else if (idx >= items.length - 5) color = '#e2ae35';
      out += '<rect x="' + (cx - bw / 2) + '" y="' + top + '" width="' + bw + '" height="' + h + '" rx="2" fill="' + color + '" opacity="0.9"><title>' + esc(it.date + '：' + sfmt(v, 1)) + '亿</title></rect>';
      if (idx % 4 === 0 || idx === items.length - 1) {
        out += '<text x="' + cx + '" y="' + (H - 16) + '" font-size="10" fill="#8b97ab" text-anchor="middle">' + esc(md(it.date)) + '</text>';
      }
    });
    out += '<line x1="' + pad.l + '" y1="' + y(0) + '" x2="' + (W - pad.r) + '" y2="' + y(0) + '" stroke="#c9d3e2" stroke-width="1"/>';
    return out + '</svg>';
  }

  function svgLine(items) {
    var W = 900, H = 250, pad = { l: 52, r: 14, t: 20, b: 36 };
    var pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
    var vals = items.map(function (i) { return num(i.value) || 0; });
    var maxV = Math.max.apply(null, vals.concat([1])) * 1.15;
    var minV = Math.min.apply(null, vals.concat([0])) * 1.2;
    var range = (maxV - minV) || 1;
    var x = function (i) { return pad.l + (items.length <= 1 ? pw / 2 : i / (items.length - 1) * pw); };
    var y = function (v) { return pad.t + (maxV - v) / range * ph; };
    var out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="日度合计净流入折线图">';
    out += '<defs><linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2f67c9" stop-opacity="0.28"/><stop offset="100%" stop-color="#2f67c9" stop-opacity="0.02"/></linearGradient></defs>';
    out += '<text x="2" y="12" font-size="11" fill="#8b97ab">亿元</text>';
    [0, 200, 400, 600].forEach(function (t) {
      if (t > maxV) return;
      var gy = y(t);
      out += '<line x1="' + pad.l + '" y1="' + gy + '" x2="' + (W - pad.r) + '" y2="' + gy + '" stroke="#e8edf4"/>';
      out += '<text x="' + (pad.l - 6) + '" y="' + (gy + 4) + '" font-size="10" fill="#8b97ab" text-anchor="end">' + t + '</text>';
    });
    var pts = items.map(function (it, i) { return x(i) + ',' + y(num(it.value) || 0); }).join(' ');
    var baseY = y(Math.max(0, minV));
    out += '<polygon points="' + x(0) + ',' + baseY + ' ' + pts + ' ' + x(items.length - 1) + ',' + baseY + '" fill="url(#areaGrad)"/>';
    out += '<polyline points="' + pts + '" fill="none" stroke="#2f67c9" stroke-width="2.2" stroke-linejoin="round"/>';
    items.forEach(function (it, i) {
      var v = num(it.value) || 0;
      out += '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="3.2" fill="' + (v >= 0 ? '#d0454c' : '#1f9d6b') + '"><title>' + esc(it.date + '：' + sfmt(v, 1)) + '亿</title></circle>';
      if (i % 4 === 0 || i === items.length - 1) {
        out += '<text x="' + x(i) + '" y="' + (H - 14) + '" font-size="10" fill="#8b97ab" text-anchor="middle">' + esc(md(it.date)) + '</text>';
      }
    });
    return out + '</svg>';
  }

  /* ------------------------- 各区块渲染 ------------------------- */
  function renderMeta(d) {
    var m = d.meta || {};
    if (m.title) { $('boardTitle').textContent = m.title; document.title = m.title; }
    if (m.contact) $('contact').textContent = m.contact;
    $('scheduleText').textContent = m.schedule || '每天两次';
    $('tradeDate').textContent = m.trade_date || (d.intraday && d.intraday.date) || '—';
    $('updatedAt').textContent = (m.generated_at || '—').replace('T', ' ').slice(0, 19) +
      (m.intraday_updated_at ? ' / 分时 ' + m.intraday_updated_at : '');
    $('sourceLabel').textContent = '来源 ' + (m.source_label || m.source || '—');
    $('generatedAt').textContent = '生成于 ' + (m.generated_at || '—').replace('T', ' ');
    $('disclaimer').textContent = m.disclaimer || '数据仅供参考，不构成投资建议。';
    var link = m.source || 'https://etf-fund-flow-board.app.workbuddy.host/';
    $('sourceLink').href = link;
    var nav = $('nav');
    nav.innerHTML = (d.sections || []).map(function (s) {
      return '<a href="#' + esc(s.id) + '">' + esc(s.nav || s.title) + '</a>';
    }).join('');
  }

  function renderPart1(d) {
    var intra = d.intraday || {}, rows = intra.rows || [];
    $('intradayDate').textContent = intra.date || '—';
    $('intradayTime').textContent = intra.updated_at ? '更新于 ' + intra.updated_at : '';
    $('intradayNote').textContent = intra.note || '';

    var maxRow = rows[0] || {};
    var ups = rows.filter(function (r) { return num(r.change_pct) > 0; }).length;
    var downs = rows.filter(function (r) { return num(r.change_pct) < 0; }).length;
    var best = rows.slice().sort(function (a, b) { return (num(b.change_pct) || 0) - (num(a.change_pct) || 0); })[0] || {};
    var worst = rows.slice().sort(function (a, b) { return (num(a.change_pct) || 0) - (num(b.change_pct) || 0); })[0] || {};
    $('kpis1').innerHTML =
      kpi('20只ETF合计成交额', fmt(intra.total_turnover_yi, 1) + '<span class="unit">亿</span>', intra.date || '') +
      kpi('成交额居首', '<span class="small">' + esc(maxRow.name || '—') + '</span>', fmt(maxRow.turnover_yi, 2) + ' 亿') +
      kpi('领涨', sfmt(best.change_pct, 2) + '<span class="unit">%</span>', best.name || '—', tone(best.change_pct)) +
      kpi('领跌', sfmt(worst.change_pct, 2) + '<span class="unit">%</span>', worst.name || '—', tone(worst.change_pct)) +
      kpi('涨 / 跌家数', '<span class="' + tone(ups - downs) + '">' + ups + '</span> / <span class="down">' + downs + '</span>', '共 ' + rows.length + ' 只');

    var cases = (intra.cases && intra.cases.length ? intra.cases : rows).map(function (r) {
      return { label: r.name || r.code, value: r.turnover_yi, change: r.change_pct };
    });
    $('caseChart').innerHTML = cases.length ? svgHBars(cases) : '<p class="hint">暂无数据</p>';

    var maxTurnover = Math.max.apply(null, rows.map(function (r) { return num(r.turnover_yi) || 0; }).concat([1]));
    $('etfTable').querySelector('tbody').innerHTML = rows.map(function (r) {
      var w = Math.max(1, (num(r.turnover_yi) || 0) / maxTurnover * 100);
      return '<tr><td class="code">' + esc(r.code) + '</td><td>' + esc(r.name) + '</td>' +
        '<td class="num bar-cell"><div class="bar-bg" style="width:' + w.toFixed(1) + '%"></div><span>' + fmt(r.turnover_yi, 2) + '</span></td>' +
        '<td class="num">' + fmt(r.share_pct, 1) + '%</td>' +
        '<td class="num ' + tone(r.change_pct) + '">' + sfmt(r.change_pct, 2) + '%</td></tr>';
    }).join('');
  }

  function renderPart2(d) {
    var sup = d.support || {}, daily = d.daily || {}, rows = daily.rows || [];
    $('supportNote').textContent = (sup.note || '') + (sup.support_days ? ' ｜ 共 ' + sup.support_days + ' 天' : '');
    $('kpis2').innerHTML =
      kpi('今日成交额（' + (sup.today_date || '实时') + '）', fmt(sup.today_turnover_yi, 1) + '<span class="unit">亿</span>', '实时') +
      kpi('最新净流入（' + (sup.net_inflow_date || 'T-1') + '）', sfmt(sup.net_inflow_yi, 1) + '<span class="unit">亿</span>', 'T-1 申赎口径', tone(sup.net_inflow_yi)) +
      kpi('前一日成交额', fmt(sup.net_inflow_turnover_yi, 1) + '<span class="unit">亿</span>', sup.net_inflow_date || '') +
      kpi('托底日样本', (sup.support_days == null ? '—' : sup.support_days) + '<span class="unit">天</span>', '净流入 > 100亿');

    var items = rows.slice(0, 30).slice().reverse().map(function (r) {
      return { date: r.date, value: num(r['合计']) || 0 };
    });
    var latest = items.length ? items[items.length - 1].value : 0;
    $('supportChart').innerHTML = items.length ? svgVBars(items, { threshold: 100, lineValue: latest }) : '<p class="hint">暂无数据</p>';
  }

  function renderComposition(d) {
    var daily = d.daily || {}, cols = daily.columns || [], rows = daily.rows || [];
    var row = rows[0] || {};
    var cats = cols.slice(1).filter(function (c) { return c !== '合计'; });
    var positives = cats.filter(function (c) { return num(row[c]) > 0; })
      .sort(function (a, b) { return (num(row[b]) || 0) - (num(row[a]) || 0); });
    var negatives = cats.filter(function (c) { return num(row[c]) < 0; });
    var total = positives.reduce(function (s, c) { return s + (num(row[c]) || 0); }, 0) || 1;
    var palette = ['#d0454c', '#e2704f', '#e8a13f', '#2f67c9', '#5a8fdf', '#7a63c9', '#c2558f', '#3fa4a0', '#8aa34a', '#b7793a', '#6b7f9e', '#9b6bb5'];
    var html = '<div style="font-size:12px;color:#69758a;margin-bottom:8px">' + esc(row.date || '') +
      ' ｜ 合计 ' + sfmt(row['合计'], 1) + ' 亿</div><div class="comp-bar">';
    positives.forEach(function (c, i) {
      var pct = (num(row[c]) || 0) / total * 100;
      html += '<div class="comp-seg" style="width:' + pct.toFixed(2) + '%;background:' + palette[i % palette.length] + '" title="' + esc(c + ' +' + fmt(row[c], 2)) + '亿"></div>';
    });
    html += '</div><div class="comp-legend">';
    positives.forEach(function (c, i) {
      html += '<span><i style="background:' + palette[i % palette.length] + '"></i>' + esc(c) + ' <b class="up">+' + fmt(row[c], 2) + '</b></span>';
    });
    html += '</div>';
    if (negatives.length) {
      html += '<div class="comp-negative">净赎回：' + negatives.map(function (c) {
        return esc(c) + ' <b class="down">' + fmt(row[c], 2) + '</b>';
      }).join('，') + '</div>';
    }
    $('composition').innerHTML = html;
  }

  function renderDailyTable(d) {
    var daily = d.daily || {}, cols = daily.columns || [], rows = daily.rows || [];
    $('dailyTitle').textContent = daily.table_title || '最近一个月 · 各类宽基ETF日度净流入（亿元）';
    $('colorNote').textContent = daily.note_color || '';
    $('panoramaNote').textContent = (d.meta && d.meta.basket_version ? d.meta.basket_version + ' ｜ ' : '') +
      (d.meta && d.meta.history_range ? '区间：' + d.meta.history_range + ' ｜ ' : '') + (daily.note || '');
    var items = rows.slice(0, 30).slice().reverse().map(function (r) {
      return { date: r.date, value: num(r['合计']) || 0 };
    });
    $('panoramaChart').innerHTML = items.length ? svgLine(items) : '<p class="hint">暂无数据</p>';
    renderComposition(d);

    var thead = '<tr><th>日期</th>' + cols.map(function (c) {
      return '<th class="num">' + esc(c) + '</th>';
    }).join('') + '</tr>';
    document.querySelector('#dailyTable thead').innerHTML = thead;

    var maxAbs = {};
    cols.forEach(function (c) {
      maxAbs[c] = Math.max.apply(null, rows.map(function (r) { return Math.abs(num(r[c]) || 0); }).concat([0.01]));
    });
    document.querySelector('#dailyTable tbody').innerHTML = rows.map(function (r) {
      var cells = cols.map(function (c, i) {
        var v = num(r[c]);
        var alpha = v == null ? 0 : Math.min(0.5, 0.06 + 0.44 * Math.abs(v) / maxAbs[c]);
        var bg = v == null ? '' : (v > 0 ? 'rgba(208,69,76,' + alpha.toFixed(3) + ')' : (v < 0 ? 'rgba(31,157,107,' + alpha.toFixed(3) + ')' : ''));
        var cls = (i === 0 ? 'total ' : '') + tone(v);
        return '<td class="num ' + cls + '" style="background:' + bg + '">' + (v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(i === 0 ? 1 : 2)) + '</td>';
      }).join('');
      return '<tr><td class="date">' + esc(r.date) + '</td>' + cells + '</tr>';
    }).join('');
  }

  function render(d) {
    renderMeta(d);
    renderPart1(d);
    renderPart2(d);
    renderDailyTable(d);
  }

  /* ------------------------- 数据加载 / 自动刷新 ------------------------- */
  function showAlert(msg) {
    var box = $('alert');
    box.textContent = msg;
    box.classList.remove('hidden');
  }
  function hideAlert() { $('alert').classList.add('hidden'); }

  function load() {
    refreshCountdown();
    fetch('data/board.json?t=' + Date.now(), { cache: 'no-store' })
      .then(function (res) { if (!res.ok) throw new Error('HTTP ' + res.status); return res.json(); })
      .then(function (data) { board = data; render(data); hideAlert(); })
      .catch(function (err) {
        if (window.__BOARD_DATA__) {
          board = window.__BOARD_DATA__;
          render(board);
          showAlert('实时数据文件读取失败，已显示随页面打包的快照数据：' + err.message);
        } else {
          showAlert('数据加载失败：' + err.message);
        }
      });
    remain = REFRESH_SECONDS;
  }

  function refreshCountdown() {
    $('countdown').textContent = autoEnabled ? '下次刷新 ' + remain + 's' : '自动刷新已暂停';
  }

  $('refreshBtn').addEventListener('click', function () { load(); });
  $('autoBtn').addEventListener('click', function () {
    autoEnabled = !autoEnabled;
    $('autoBtn').textContent = autoEnabled ? '暂停自动刷新' : '恢复自动刷新';
    remain = REFRESH_SECONDS;
    refreshCountdown();
  });
  setInterval(function () {
    if (!autoEnabled) return;
    remain -= 1;
    if (remain <= 0) load();
    else refreshCountdown();
  }, 1000);

  load();
})();
