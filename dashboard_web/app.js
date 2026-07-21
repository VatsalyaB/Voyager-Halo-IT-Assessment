/* TechSolve Support Operations — dashboard logic
   Reads window.DASHBOARD_DATA (pre-aggregated per value×year), recombines for the
   selected reporting period, and renders every chart from CSS-variable colors so
   light/dark stays consistent with the dataviz reference palette. */
(function () {
  "use strict";
  const D = window.DASHBOARD_DATA;
  const state = { years: "default", theme: null };

  // ---- helpers ------------------------------------------------------------
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const fmtInt = (x) => Math.round(x).toLocaleString("en-NZ");
  const fmtPct = (x) => (x == null || isNaN(x)) ? "–" : (x * 100).toFixed(1) + "%";
  const fmtH = (x) => (x == null || isNaN(x)) ? "–" : x.toFixed(1) + "h";

  function selectedYears() {
    if (state.years === "default") return [2024, 2025];
    if (state.years === "all") return D.meta.years.slice();
    return [parseInt(state.years, 10)];
  }
  const EMPTY = () => ({ n: 0, breach_n: 0, esc_n: 0, resolved_n: 0, res_sum: 0, res_n: 0,
    ffr_sum: 0, ffr_n: 0, csat_sum: 0, csat_n: 0, bdays_sum: 0, bdays_n: 0 });
  function addCell(a, b) { for (const k in a) a[k] += (b[k] || 0); return a; }
  function derive(c) {
    return {
      n: c.n,
      breach_rate: c.n ? c.breach_n / c.n : null,
      esc_rate: c.n ? c.esc_n / c.n : null,
      avg_res: c.res_n ? c.res_sum / c.res_n : null,
      avg_ffr: c.ffr_n ? c.ffr_sum / c.ffr_n : null,
      avg_csat: c.csat_n ? c.csat_sum / c.csat_n : null,
      avg_bdays: c.bdays_n ? c.bdays_sum / c.bdays_n : null,
      resolved_n: c.resolved_n,
    };
  }
  // combine a dimension across selected years -> [{value, ...derived}]
  function dim(name) {
    const yrs = new Set(selectedYears());
    const byVal = new Map();
    for (const r of D.dims[name]) {
      if (!yrs.has(r.year)) continue;
      if (!byVal.has(r.value)) byVal.set(r.value, EMPTY());
      addCell(byVal.get(r.value), r);
    }
    return [...byVal.entries()].map(([value, c]) => Object.assign({ value }, derive(c)));
  }
  function kpi() {
    const yrs = selectedYears(), acc = EMPTY();
    for (const y of yrs) if (D.kpi_by_year[y]) addCell(acc, D.kpi_by_year[y]);
    return { c: acc, d: derive(acc) };
  }

  // ---- chart chrome from CSS vars ----------------------------------------
  function chrome() {
    return {
      text: css("--ink"), muted: css("--muted"), ink2: css("--ink-2"),
      grid: css("--grid"), baseline: css("--baseline"), surface: css("--surface"),
      series: [css("--s1"), css("--s2"), css("--s3"), css("--s4"), css("--s5"),
               css("--s6"), css("--s7"), css("--s8")],
      good: css("--good"), critical: css("--critical"), warning: css("--warning"),
    };
  }
  function baseGrid(ch, extra) {
    return Object.assign({ left: 8, right: 16, top: 16, bottom: 8, containLabel: true }, extra || {});
  }
  function axisText(ch) { return { color: ch.muted, fontSize: 11 }; }
  function tip(ch, extra) {
    return Object.assign({
      backgroundColor: ch.surface, borderColor: css("--border"), borderWidth: 1,
      textStyle: { color: ch.text, fontSize: 12 }, confine: true,
    }, extra || {});
  }
  const charts = {};
  function inst(id) {
    if (!charts[id]) charts[id] = echarts.init(document.getElementById(id), null, { renderer: "canvas" });
    return charts[id];
  }

  // ---- individual charts --------------------------------------------------
  function hbar(id, rows, opt) {
    // horizontal bar, single hue, value labels, sorted desc
    const ch = chrome();
    rows = rows.slice().sort((a, b) => a.n - b.n);
    inst(id).setOption({
      grid: baseGrid(ch, { left: 8, right: 44 }),
      tooltip: tip(ch, { trigger: "axis", axisPointer: { type: "shadow" },
        formatter: (p) => `${p[0].name}<br/><b>${fmtInt(p[0].value)}</b> tickets` }),
      xAxis: { type: "value", axisLabel: axisText(ch), splitLine: { lineStyle: { color: ch.grid } },
        axisLine: { show: false }, axisTick: { show: false } },
      yAxis: { type: "category", data: rows.map((r) => r.value), axisLabel: { color: ch.ink2, fontSize: 12 },
        axisLine: { lineStyle: { color: ch.baseline } }, axisTick: { show: false } },
      series: [{ type: "bar", data: rows.map((r) => r.n), itemStyle: { color: (opt && opt.color) || ch.series[0], borderRadius: [0, 4, 4, 0] },
        barWidth: "62%", label: { show: true, position: "right", color: ch.ink2, fontSize: 11,
          formatter: (p) => fmtInt(p.value) } }],
    }, true);
  }
  function vbar(id, cats, vals, opt) {
    const ch = chrome(); opt = opt || {};
    inst(id).setOption({
      grid: baseGrid(ch, { bottom: 6, top: 24 }),
      tooltip: tip(ch, { trigger: "axis", axisPointer: { type: "shadow" },
        formatter: (p) => `${p[0].name}<br/><b>${opt.fmt ? opt.fmt(p[0].value) : fmtInt(p[0].value)}</b>` }),
      xAxis: { type: "category", data: cats, axisLabel: { color: ch.ink2, fontSize: 11, interval: 0 },
        axisLine: { lineStyle: { color: ch.baseline } }, axisTick: { show: false } },
      yAxis: { type: "value", axisLabel: axisText(ch), splitLine: { lineStyle: { color: ch.grid } } },
      series: [{ type: "bar", data: vals.map((v, i) => ({ value: v,
        itemStyle: { color: opt.colors ? opt.colors[i] : ch.series[0], borderRadius: [4, 4, 0, 0] } })),
        barWidth: "58%", label: { show: true, position: "top", color: ch.ink2, fontSize: 11,
          formatter: (p) => opt.fmt ? opt.fmt(p.value) : fmtInt(p.value) } }],
    }, true);
  }

  function renderKPIs() {
    const { d } = kpi();
    const resRate = d.n ? d.resolved_n / d.n : 0;
    const tiles = [
      { label: "Total tickets", value: fmtInt(d.n), sub: state.years === "default" ? "2024–2025" : (state.years === "all" ? "all years" : state.years) },
      { label: "Resolution rate", value: fmtPct(resRate), sub: `${fmtInt(d.resolved_n)} resolved/closed`, cls: "good" },
      { label: "Avg time to resolve", value: fmtH(d.avg_res), sub: "resolved tickets (provided)" },
      { label: "SLA breach rate", value: fmtPct(d.breach_rate), sub: "system-of-record flag", cls: "bad" },
      { label: "Avg CSAT", value: (d.avg_csat ? d.avg_csat.toFixed(2) : "–") + " / 5", sub: `${fmtInt((kpi().c.csat_n))} responses` },
      { label: "Escalation rate", value: fmtPct(d.esc_rate), sub: "tickets escalated" },
    ];
    document.getElementById("kpis").innerHTML = tiles.map((t) =>
      `<div class="kpi"><div class="label">${t.label}</div>
       <div class="value ${t.cls || ""}">${t.value}</div><div class="sub">${t.sub}</div></div>`).join("");
  }

  function tableFor(elId, rows, cols) {
    const head = "<tr>" + cols.map((c) => `<th>${c.h}</th>`).join("") + "</tr>";
    const body = rows.map((r) => "<tr>" + cols.map((c) => `<td>${c.f(r)}</td>`).join("") + "</tr>").join("");
    document.getElementById(elId).innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
  }

  function render() {
    const ch = chrome();
    renderKPIs();

    // trend (monthly line)
    const months = dim("created_month").sort((a, b) => a.value < b.value ? -1 : 1);
    inst("c_trend").setOption({
      grid: baseGrid(ch, { left: 8, right: 20, top: 20 }),
      tooltip: tip(ch, { trigger: "axis", formatter: (p) => `${p[0].name}<br/><b>${fmtInt(p[0].value)}</b> tickets` }),
      xAxis: { type: "category", data: months.map((m) => m.value), boundaryGap: false,
        axisLabel: { color: ch.muted, fontSize: 10, rotate: months.length > 14 ? 45 : 0 },
        axisLine: { lineStyle: { color: ch.baseline } }, axisTick: { show: false } },
      yAxis: { type: "value", axisLabel: axisText(ch), splitLine: { lineStyle: { color: ch.grid } } },
      series: [{ type: "line", data: months.map((m) => m.n), smooth: false, symbol: "circle", symbolSize: 7,
        lineStyle: { color: ch.series[0], width: 2 }, itemStyle: { color: ch.series[0] },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: ch.series[0] + "44" }, { offset: 1, color: ch.series[0] + "05" }]) } }],
    }, true);

    // theme donut
    const themes = dim("theme").sort((a, b) => b.n - a.n);
    inst("c_theme").setOption({
      tooltip: tip(ch, { trigger: "item", formatter: (p) => `${p.name}<br/><b>${fmtInt(p.value)}</b> (${p.percent}%)` }),
      legend: { bottom: 0, textStyle: { color: ch.ink2, fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
      series: [{ type: "pie", radius: ["46%", "70%"], center: ["50%", "44%"], avoidLabelOverlap: true,
        data: themes.map((t, i) => ({ name: t.value, value: t.n, itemStyle: { color: ch.series[i % 8] } })),
        label: { color: ch.ink2, fontSize: 11, formatter: (p) => `${p.percent}%` },
        itemStyle: { borderColor: ch.surface, borderWidth: 2 } }],
    }, true);

    // category + service (hbar)
    const cat = dim("category"); hbar("c_category", cat);
    tableFor("t_category", cat.slice().sort((a, b) => b.n - a.n),
      [{ h: "Category", f: (r) => r.value }, { h: "Tickets", f: (r) => fmtInt(r.n) },
       { h: "Breach", f: (r) => fmtPct(r.breach_rate) }, { h: "Avg resolve", f: (r) => fmtH(r.avg_res) }]);
    const svc = dim("service_area"); hbar("c_service", svc);
    tableFor("t_service", svc.slice().sort((a, b) => b.n - a.n),
      [{ h: "Service area", f: (r) => r.value }, { h: "Tickets", f: (r) => fmtInt(r.n) },
       { h: "Breach", f: (r) => fmtPct(r.breach_rate) }]);

    // status (ordinal blue ramp)
    const statusOrder = ["Open", "In Progress", "Pending Customer", "Resolved", "Closed"];
    const statusRamp = ["#86b6ef", "#5598e7", "#3987e5", "#256abf", "#184f95"];
    const sMap = new Map(dim("status").map((r) => [r.value, r.n]));
    vbar("c_status", statusOrder, statusOrder.map((s) => sMap.get(s) || 0), { colors: statusRamp });

    // resolution buckets
    const bucketOrder = ["0-4h", "4-8h", "8-24h", "24-48h", "48h+"];
    const bMap = new Map(dim("resolution_bucket").map((r) => [r.value, r.n]));
    vbar("c_restime", bucketOrder, bucketOrder.map((b) => bMap.get(b) || 0));

    // SLA target vs actual by priority (grouped bar, one hour axis)
    const prOrder = ["Low", "Medium", "High", "Urgent"];
    const yrs = new Set(selectedYears());
    // actual resolution avg = correctly pooled res_sum/res_n from the priority dim
    const prAvgRes = new Map(dim("priority").map((r) => [r.value, r.avg_res]));
    const tgt = [], act = [];
    for (const pr of prOrder) {
      let tw = 0, nn = 0;  // target is a per-ticket constant -> weight by n is correct
      const byY = D.sla_target_by_priority[pr] || {};
      for (const y in byY) if (yrs.has(parseInt(y, 10))) { const o = byY[y]; tw += o.target_avg * o.n; nn += o.n; }
      tgt.push(nn ? +(tw / nn).toFixed(1) : 0);
      const a = prAvgRes.get(pr);
      act.push(a != null ? +a.toFixed(1) : 0);
    }
    inst("c_sla").setOption({
      grid: baseGrid(ch, { top: 30, bottom: 6 }),
      legend: { top: 0, right: 0, textStyle: { color: ch.ink2, fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
      tooltip: tip(ch, { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => v + "h" }),
      xAxis: { type: "category", data: prOrder, axisLabel: { color: ch.ink2, fontSize: 11 },
        axisLine: { lineStyle: { color: ch.baseline } }, axisTick: { show: false } },
      yAxis: { type: "value", name: "hours", nameTextStyle: { color: ch.muted, fontSize: 10 },
        axisLabel: axisText(ch), splitLine: { lineStyle: { color: ch.grid } } },
      series: [
        { name: "SLA target", type: "bar", data: tgt, barGap: 0, itemStyle: { color: ch.series[0], borderRadius: [4, 4, 0, 0] } },
        { name: "Actual avg", type: "bar", data: act, itemStyle: { color: ch.series[3], borderRadius: [4, 4, 0, 0] } },
      ],
    }, true);

    // day-type: avg tickets per day
    const dtOrder = ["Business Day", "Weekend", "Public Holiday"];
    const dtN = new Map(dim("day_type").map((r) => [r.value, r.n]));
    const dtDays = {};
    for (const dt of dtOrder) { let d = 0; const o = D.daytype_daycounts[dt] || {};
      for (const y in o) if (yrs.has(parseInt(y, 10))) d += o[y]; dtDays[dt] = d; }
    const dtAvg = dtOrder.map((dt) => dtDays[dt] ? +( (dtN.get(dt) || 0) / dtDays[dt]).toFixed(1) : 0);
    vbar("c_daytype", dtOrder, dtAvg, { colors: [ch.series[0], ch.series[4], ch.series[5]], fmt: (v) => v + "/day" });

    // business days to resolve histogram
    const hist = {};
    for (const y of selectedYears()) { const h = D.bdays_hist[y] || {};
      for (const k in h) hist[k] = (hist[k] || 0) + h[k]; }
    const bdKeys = Object.keys(hist).map(Number).sort((a, b) => a - b);
    vbar("c_bdays", bdKeys.map(String), bdKeys.map((k) => hist[k]));

    // team performance
    const team = dim("team").sort((a, b) => b.n - a.n);
    hbar("c_team", team);
    tableFor("t_team", team,
      [{ h: "Team", f: (r) => r.value }, { h: "Tickets", f: (r) => fmtInt(r.n) },
       { h: "Breach", f: (r) => fmtPct(r.breach_rate) }, { h: "CSAT", f: (r) => r.avg_csat ? r.avg_csat.toFixed(2) : "–" }]);

    // region
    hbar("c_region", dim("region"));

    // DQ: provided vs recomputed breach
    vbar("c_dq", ["Provided flag", "Recomputed"], [D.dq.sla_breach_provided * 100, D.dq.sla_breach_recomputed * 100],
      { colors: [ch.series[0], ch.critical], fmt: (v) => v.toFixed(1) + "%" });
    document.getElementById("dqflags").innerHTML = [
      { n: fmtPct(D.dq.sla_agreement_rate), t: "SLA flag ↔ recomputation agreement" },
      { n: fmtInt(D.dq.resolved_before_created), t: "tickets resolved before created" },
      { n: fmtInt(D.dq.category_rows_renormalised), t: "category labels cleaned (of " + fmtInt(D.dq.rows_in) + ")" },
      { n: fmtInt(D.dq.rows_dropped_bad_year), t: "corrupt-date rows removed" },
    ].map((f) => `<div class="flag"><div class="n">${f.n}</div><div class="t">${f.t}</div></div>`).join("");

    renderForecast(ch);
  }

  // ---- forecast & capacity (independent of the year filter) ----------------
  function renderForecast(ch) {
    const F = window.FORECAST_DATA;
    if (!F) return;
    const hist = F.history, fc = F.forecast;
    const months = hist.map((h) => h.month).concat(fc.map((f) => f.month));
    const nH = hist.length;
    const pad = (arr) => hist.map(() => null).concat(arr);
    const histVals = hist.map((h) => h.n).concat(fc.map(() => null));
    const fcLine = hist.map((h, i) => (i === nH - 1 ? h.n : null)).concat(fc.map((f) => f.mean));
    const fcByMonth = new Map(fc.map((f) => [f.month, f]));
    const band = (c, op) => c + op;
    inst("c_forecast").setOption({
      grid: baseGrid(ch, { left: 8, right: 16, top: 24 }),
      legend: { top: 0, right: 0, data: ["Actual", "Forecast"], textStyle: { color: ch.ink2, fontSize: 11 },
        itemWidth: 18, itemHeight: 8 },
      tooltip: tip(ch, { trigger: "axis", formatter: (ps) => {
        const mo = ps[0].axisValue, f = fcByMonth.get(mo);
        if (f) return `${mo} (forecast)<br/><b>${fmtInt(f.mean)}</b>/mo<br/>` +
          `<span style="color:${ch.muted}">95%: ${fmtInt(f.lo95)}–${fmtInt(f.hi95)}</span>`;
        const a = ps.find((p) => p.seriesName === "Actual");
        return a && a.value != null ? `${mo}<br/><b>${fmtInt(a.value)}</b> tickets` : mo;
      } }),
      xAxis: { type: "category", data: months, boundaryGap: false,
        axisLabel: { color: ch.muted, fontSize: 10, rotate: 45 },
        axisLine: { lineStyle: { color: ch.baseline } }, axisTick: { show: false } },
      yAxis: { type: "value", scale: true, axisLabel: axisText(ch), splitLine: { lineStyle: { color: ch.grid } } },
      series: [
        // 95% band (base invisible + fill)
        { name: "l95", type: "line", data: pad(fc.map((f) => f.lo95)), stack: "b95", symbol: "none",
          lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true },
        { name: "95%", type: "line", data: pad(fc.map((f) => f.hi95 - f.lo95)), stack: "b95", symbol: "none",
          lineStyle: { opacity: 0 }, areaStyle: { color: band(ch.series[0], "22") }, silent: true },
        // 80% band on top
        { name: "l80", type: "line", data: pad(fc.map((f) => f.lo80)), stack: "b80", symbol: "none",
          lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true },
        { name: "80%", type: "line", data: pad(fc.map((f) => f.hi80 - f.lo80)), stack: "b80", symbol: "none",
          lineStyle: { opacity: 0 }, areaStyle: { color: band(ch.series[0], "3a") }, silent: true },
        { name: "Actual", type: "line", data: histVals, symbol: "circle", symbolSize: 5,
          lineStyle: { color: ch.series[0], width: 2 }, itemStyle: { color: ch.series[0] } },
        { name: "Forecast", type: "line", data: fcLine, symbol: "none",
          lineStyle: { color: ch.series[0], width: 2, type: "dashed" }, itemStyle: { color: ch.series[0] } },
      ],
    }, true);

    // capacity table
    const rows = F.capacity.map((c) =>
      `<tr><td>${c.quarter}</td><td>${fmtInt(c.expected_arrivals)}</td><td>${c.business_days}</td>` +
      `<td>${c.load_per_business_day}</td></tr>`).join("");
    document.getElementById("capacity").innerHTML =
      `<table><thead><tr><th>Quarter</th><th>Arrivals</th><th>Biz days</th><th>Load/day</th></tr></thead>` +
      `<tbody>${rows}</tbody></table>` +
      `<p class="hint" style="margin-top:8px">Arrival rate ≈ ${F.diagnostics.daily_rate}/day · ` +
      `trend R²=${F.diagnostics.trend_r2} (flat).</p>`;
    document.getElementById("forecastnote").textContent = F.note;
  }

  // ---- window note --------------------------------------------------------
  function updateNote() {
    const notes = {
      default: "Showing 2024–2025 per the brief. Note: this export is ~99.98% 2024 by created date (2023 has 33.7k rows, 2025 only 10) — switch to “All years” to see the full history.",
      all: "Showing all available years (2023–2025). The bulk of the data is 2023–2024.",
      2023: "Showing 2023 only.", 2024: "Showing 2024 only.", 2025: "Showing 2025 only (only 10 tickets).",
    };
    document.getElementById("windownote").textContent = notes[state.years] || "";
  }

  // ---- controls -----------------------------------------------------------
  function initTheme() {
    const saved = localStorage.getItem("ts_theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    state.theme = saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  document.getElementById("themebtn").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", state.theme);
    localStorage.setItem("ts_theme", state.theme);
    render();
  });
  document.getElementById("yearseg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    [...e.currentTarget.children].forEach((x) => x.setAttribute("aria-pressed", x === b));
    state.years = b.dataset.years; updateNote(); render();
  });
  window.addEventListener("resize", () => { for (const k in charts) charts[k].resize(); });

  // ---- footer -------------------------------------------------------------
  document.getElementById("footer").innerHTML =
    `Source: TechSolve synthetic ticket export (${fmtInt(D.meta.rows_total)} cleaned rows) · ` +
    `external join: NZ public holidays + business-day calendar · built with pandas + ECharts · ` +
    `data pre-aggregated to ${(JSON.stringify(D).length / 1024).toFixed(0)} KB.`;

  // ---- go -----------------------------------------------------------------
  initTheme(); updateNote(); render();
})();
