const $ = (sel) => document.querySelector(sel);
const tbody = $("#quotes tbody");
let chart = null;
let currentCode = null;

const fmt = (value, digits = 2) =>
  Number.isFinite(value) ? value.toFixed(digits) : "-";

const sign = (value) => (value > 0 ? "up" : value < 0 ? "down" : "");

async function getJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadStats() {
  const stats = await getJSON("/api/stats");
  $("#stats").textContent =
    `收录股票 ${stats.stocks} 只 · 行情快照 ${stats.quotes} 条 · K线 ${stats.candles} 根` +
    (stats.last_fetch ? ` · 最近抓取 ${stats.last_fetch}` : "");
}

async function loadQuotes() {
  const params = new URLSearchParams({
    limit: $("#limit").value,
    sort: $("#sort").value,
    desc: $("#direction").value === "desc",
  });
  const keyword = $("#keyword").value.trim();
  if (keyword) params.set("keyword", keyword);

  const { items } = await getJSON(`/api/quotes?${params}`);
  tbody.innerHTML = "";
  $("#empty").classList.toggle("hidden", items.length > 0);

  for (const row of items) {
    const tr = document.createElement("tr");
    tr.dataset.code = row.code;
    tr.dataset.name = row.name;
    tr.innerHTML = `
      <td>${row.code}</td>
      <td>${row.name}</td>
      <td class="num ${sign(row.change)}">${fmt(row.price)}</td>
      <td class="num ${sign(row.change)}">${fmt(row.change)}</td>
      <td class="num ${sign(row.change_pct)}">${fmt(row.change_pct)}%</td>
      <td class="num">${fmt(row.open)}</td>
      <td class="num">${fmt(row.high)}</td>
      <td class="num">${fmt(row.low)}</td>
      <td class="num">${fmt(row.amount / 1e8)}</td>
      <td class="num">${fmt(row.turnover_rate)}%</td>
      <td class="num">${fmt(row.pe_ttm)}</td>
      <td class="num">${fmt(row.total_mcap)}</td>
      <td>${row.time.replace("T", " ")}</td>`;
    tr.addEventListener("click", () => showDetail(row.code, row.name));
    tbody.appendChild(tr);
  }
}

async function showDetail(code, name) {
  currentCode = code;
  $("#detail").classList.remove("hidden");
  $("#detail-title").textContent = `${name} ${code} K线`;
  await renderChart();
  $("#detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function renderChart() {
  if (!currentCode) return;
  const period = $("#period").value;
  const { items } = await getJSON(`/api/candles/${currentCode}?period=${period}&limit=240`);
  chart = chart || echarts.init($("#chart"), "dark");
  chart.setOption({
    backgroundColor: "transparent",
    animation: false,
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    grid: [
      { left: 60, right: 24, top: 20, height: "58%" },
      { left: 60, right: 24, top: "74%", height: "16%" },
    ],
    xAxis: [
      { type: "category", data: items.map((c) => c.date), boundaryGap: false },
      { type: "category", gridIndex: 1, data: items.map((c) => c.date), axisLabel: { show: false } },
    ],
    yAxis: [{ scale: true }, { gridIndex: 1, splitNumber: 2, axisLabel: { show: false } }],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 60, end: 100 },
      { type: "slider", xAxisIndex: [0, 1], bottom: 8, start: 60, end: 100 },
    ],
    series: [
      {
        type: "candlestick",
        name: currentCode,
        data: items.map((c) => [c.open, c.close, c.low, c.high]),
        itemStyle: {
          color: "#e4393c", color0: "#21a675",
          borderColor: "#e4393c", borderColor0: "#21a675",
        },
      },
      {
        type: "bar",
        name: "成交量",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: items.map((c) => c.volume),
        itemStyle: { color: "#40507a" },
      },
    ],
  });
}

async function withBusy(button, fn) {
  button.disabled = true;
  try {
    await fn();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
  }
}

$("#refresh").addEventListener("click", (event) =>
  withBusy(event.target, async () => {
    await getJSON("/api/refresh", { method: "POST" });
    await Promise.all([loadQuotes(), loadStats()]);
  })
);

for (const id of ["#sort", "#direction", "#limit"]) {
  $(id).addEventListener("change", () => loadQuotes().catch(console.error));
}
$("#period").addEventListener("change", () => renderChart().catch(console.error));
$("#close-detail").addEventListener("click", () => {
  $("#detail").classList.add("hidden");
  currentCode = null;
});

let searchTimer;
$("#keyword").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadQuotes().catch(console.error), 300);
});

window.addEventListener("resize", () => chart && chart.resize());

Promise.all([loadQuotes(), loadStats()]).catch((error) => {
  $("#stats").textContent = `加载失败：${error.message}`;
});
