/* NPS Analyst in a Box: front end.
 * - Every number and headline comes from /api/dashboard (Python tools), not typed in here.
 * - Charts are hand-built SVG following the dataviz rules (thin marks, validated palette,
 *   legend + direct labels, hover + keyboard tooltips, a table view for every chart).
 * - Labels from data or from the LLM go in via textContent, never innerHTML.
 */
"use strict";

// ================================================================ helpers
const $ = (sel) => document.querySelector(sel);
const SVGNS = "http://www.w3.org/2000/svg";
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v);
  }
  for (const c of children) if (c != null) n.append(typeof c === "string" ? document.createTextNode(c) : c);
  return n;
}
function s(tag, attrs = {}, style = {}) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  Object.assign(n.style, style);
  return n;
}
const MONTH = (m) => new Date(m + "-01T00:00:00").toLocaleString("en-GB", { month: "short" });
const MONTH_LONG = (m) => new Date(m + "-01T00:00:00").toLocaleString("en-GB", { month: "long", year: "numeric" });
const signed = (x) => (Math.abs(x) < 0.05 ? "0.0" : (x > 0 ? "+" : "−") + Math.abs(x).toFixed(1));
const lakh = (x) => `₹${Number(x).toFixed(2)} lakh`;
const tidy = (d) => String(d).replace(/^-/, "−");   // typographic minus for display strings from tools

function head(fig, title, sub) {
  fig.textContent = "";
  fig.append(el("figcaption", {}, el("p", { class: "card-title", text: title }), sub ? el("p", { class: "card-sub", text: sub }) : null));
}
function legend(items) {
  const box = el("div", { class: "legend" });
  for (const it of items) {
    const key = el("span", { class: "key" });
    key.style.background = `var(${it.color})`;
    box.append(el("span", {}, key, it.name));
  }
  return box;
}
function tableView(headRow, rows, numCols = []) {
  const t = el("table", { class: "data-table" });
  const tr = el("tr");
  headRow.forEach((h, i) => tr.append(el("th", { class: numCols.includes(i) ? "num" : "", text: h })));
  t.append(el("thead", {}, tr));
  const tb = el("tbody");
  for (const r of rows) {
    const row = el("tr");
    r.forEach((c, i) => {
      const td = el("td", { class: numCols.includes(i) ? "num" : "" });
      if (c instanceof Node) td.append(c); else td.textContent = c;
      row.append(td);
    });
    tb.append(row);
  }
  t.append(tb);
  return t;
}
function withTableToggle(fig, headRow, rows, numCols) {
  const d = el("details", { class: "table-view" }, el("summary", { text: "Show as table" }));
  d.append(tableView(headRow, rows, numCols));
  fig.append(d);
}

// ================================================================ reveal on scroll
const revealHooks = new WeakMap();
const revealer = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    e.target.classList.add("in");
    revealer.unobserve(e.target);
    const hook = revealHooks.get(e.target);
    if (hook) hook();
  }
}, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
function watchReveals() { document.querySelectorAll(".reveal:not(.in)").forEach((n) => revealer.observe(n)); }
function onReveal(node, fn) {
  if (node.classList.contains("in")) fn(); else revealHooks.set(node, fn);
}

// count a number up to its exact display string (the final text is always the tool's own string)
function countUp(node, display) {
  const m = display.match(/[-−+]?\d[\d,]*(\.\d+)?/);
  if (!m || reduceMotion) { node.textContent = display; return; }
  const target = parseFloat(m[0].replace(/[−]/, "-").replace(/,/g, ""));
  const decimals = (m[1] || "").length ? m[1].length - 1 : 0;
  const pre = display.slice(0, m.index), post = display.slice(m.index + m[0].length);
  const sign = m[0].startsWith("+") ? "+" : "";
  const t0 = performance.now(), dur = 900;
  const step = (t) => {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    const v = target * e;
    const txt = (v < 0 ? "−" : sign) + Math.abs(v).toFixed(decimals);
    node.textContent = p < 1 ? pre + txt + post : display;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ================================================================ tooltip
const tip = $("#tooltip");
function showTip(x, y, title, rows) {
  tip.textContent = "";
  tip.append(el("div", { class: "tt-title", text: title }));
  for (const r of rows) {
    const key = el("span", { class: "tt-key" });
    key.style.background = `var(${r.color})`;
    tip.append(el("div", { class: "tt-row" }, r.color ? key : null, el("b", { text: r.value }), el("span", { text: r.name })));
  }
  tip.hidden = false;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(x + 14, window.innerWidth - w - 8) + "px";
  tip.style.top = Math.max(8, y - h - 12) + "px";
}
const hideTip = () => { tip.hidden = true; };

// ================================================================ line chart
function niceTicks(lo, hi, count = 5) {
  const raw = (hi - lo || 1) / (count - 1);
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((st) => st >= raw);
  const out = [];
  for (let v = Math.floor(lo / step) * step; v <= Math.ceil(hi / step) * step + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

/* cfg: { title, sub, labels, labelsLong, series:[{name,color,values,band?,label?,tipName?}],
 *        legendItems?, fmt?, tickFmt?, height?, rightPad?, table:{head,rows,num} } */
function lineChart(fig, cfg) {
  if (cfg.title) head(fig, cfg.title, cfg.sub);
  if (cfg.legendItems) fig.append(legend(cfg.legendItems));
  const box = el("div", { class: "chart" });
  fig.append(box);
  const fmt = cfg.fmt || signed;
  let firstDraw = true, lastW = 0;

  const draw = () => {
    const W = Math.max(box.clientWidth, 260);
    if (W === lastW) return;            // ResizeObserver fires once on observe; skip no-op redraws
    lastW = W;
    box.textContent = "";
    const H = cfg.height || 230;
    const m = { l: 40, r: cfg.rightPad ?? 118, t: 14, b: 26 };
    const vals = cfg.series.flatMap((sr) => sr.values.concat(sr.band ? sr.band.flat() : []));
    const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals));
    const lo = ticks[0], hi = ticks[ticks.length - 1];
    const n = cfg.labels.length;
    const X = (i) => m.l + (n === 1 ? 0 : (i * (W - m.l - m.r)) / (n - 1));
    const Y = (v) => m.t + ((hi - v) / (hi - lo)) * (H - m.t - m.b);
    const anim = firstDraw && !reduceMotion;
    // End labels that would overlap are dropped (the legend + tooltip carry identity instead of stacking them).
    const endYs = cfg.series.filter((sr) => sr.label).map((sr) => Y(sr.values[sr.values.length - 1])).sort((a, b) => a - b);
    const labelsCollide = endYs.some((y, i) => i > 0 && y - endYs[i - 1] < 15);

    const svg = s("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, tabindex: 0, role: "img",
      "aria-label": `${cfg.title || cfg.aria || "Chart"}. Use the arrow keys to read values.` });
    for (const t of ticks) {
      svg.append(s("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, { stroke: t === 0 ? "var(--axis)" : "var(--grid)", strokeWidth: 1 }));
      const tx = s("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end", class: "axis-text" });
      tx.textContent = cfg.tickFmt ? cfg.tickFmt(t) : (t > 0 ? "+" : t < 0 ? "−" : "") + Math.abs(t);
      svg.append(tx);
    }
    cfg.labels.forEach((lab, i) => {
      const tx = s("text", { x: X(i), y: H - 6, "text-anchor": "middle", class: "axis-text" });
      tx.textContent = lab;
      svg.append(tx);
    });
    // context lines first, story lines on top
    const ordered = [...cfg.series].sort((a, b) => (b.color === "--deemph") - (a.color === "--deemph"));
    for (const sr of ordered) {
      if (sr.band) {
        const up = sr.band.map((b, i) => `${X(i)},${Y(b[1])}`);
        const dn = sr.band.map((b, i) => `${X(i)},${Y(b[0])}`).reverse();
        const poly = s("polygon", { points: up.concat(dn).join(" "), class: anim ? "band-fade" : "" }, { fill: `var(${sr.color})` });
        poly.style.fillOpacity = 0.1;
        svg.append(poly);
      }
      svg.append(s("polyline", { points: sr.values.map((v, i) => `${X(i)},${Y(v)}`).join(" "), pathLength: 1, class: anim ? "draw" : "" },
        { fill: "none", stroke: `var(${sr.color})`, strokeWidth: 2, strokeLinejoin: "round", strokeLinecap: "round" }));
      if (sr.color !== "--deemph") {
        sr.values.forEach((v, i) => svg.append(s("circle", { cx: X(i), cy: Y(v), r: 4 }, { fill: `var(${sr.color})`, stroke: "var(--surface-1)", strokeWidth: 2 })));
      }
      if (sr.label && !labelsCollide) {   // selective direct label at the line end
        const last = sr.values.length - 1;
        const tx = s("text", { x: X(last) + 10, y: Y(sr.values[last]) + 4, class: "end-label" });
        const v = s("tspan", { class: "v" }); v.textContent = fmt(sr.values[last]) + " ";
        const nm = s("tspan"); nm.textContent = sr.label === true ? sr.name : sr.label;
        tx.append(v, nm);
        svg.append(tx);
      }
    }
    // crosshair + one tooltip listing every series
    const cross = s("line", { y1: m.t, y2: H - m.b }, { stroke: "var(--axis)", strokeWidth: 1, visibility: "hidden" });
    const hit = s("rect", { x: m.l - 20, y: 0, width: W - m.l - m.r + 40, height: H - m.b }, { fill: "transparent" });
    svg.append(cross, hit);
    let cur = n - 1;
    const show = (i, cx, cy) => {
      cur = i;
      cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i));
      cross.style.visibility = "visible";
      const rows = cfg.series.map((sr) => ({ color: sr.color, value: fmt(sr.values[i]), name: sr.tipName ? sr.tipName(i) : sr.name, raw: sr.values[i] }))
        .sort((a, b) => b.raw - a.raw);
      showTip(cx, cy, (cfg.labelsLong || cfg.labels)[i], rows);
    };
    const pos = (i) => { const r = svg.getBoundingClientRect(); return [r.left + (X(i) / W) * r.width, r.top + 24]; };
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const px = ((e.clientX - r.left) / r.width) * W;
      let best = 0;
      for (let i = 1; i < n; i++) if (Math.abs(X(i) - px) < Math.abs(X(best) - px)) best = i;
      show(best, e.clientX, e.clientY);
    });
    hit.addEventListener("pointerleave", () => { cross.style.visibility = "hidden"; hideTip(); });
    svg.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const i = Math.max(0, Math.min(n - 1, cur + (e.key === "ArrowRight" ? 1 : -1)));
      show(i, ...pos(i));
    });
    svg.addEventListener("focus", () => show(cur, ...pos(cur)));
    svg.addEventListener("blur", () => { cross.style.visibility = "hidden"; hideTip(); });
    box.append(svg);
    firstDraw = false;
  };
  draw();
  new ResizeObserver(draw).observe(box);
  if (cfg.table) withTableToggle(fig, cfg.table.head, cfg.table.rows, cfg.table.num);
}

// ================================================================ ranked bars (one series, one hue)
function barList(fig, cfg) {
  head(fig, cfg.title, cfg.sub);
  const max = Math.max(...cfg.rows.map((r) => r.value), 1e-9);
  const list = el("div", { class: "barlist" });
  cfg.rows.forEach((r, i) => {
    const bar = el("div", { class: "bar" });
    bar.style.width = `${Math.max(0.6, (r.value / max) * 70)}%`;
    bar.style.transitionDelay = `${i * 60}ms`;
    const row = el("div", { class: "bar-row", tabindex: 0 },
      el("div", { class: "bar-label" + (r.em ? " em" : ""), text: r.label }),
      el("div", { class: "bar-track" }, bar, el("span", { class: "bar-value", text: r.display })));
    const show = (x, y) => showTip(x, y, r.label, [{ color: "--series-1", value: r.display, name: r.tip || "" }]);
    row.addEventListener("pointermove", (e) => show(e.clientX, e.clientY));
    row.addEventListener("pointerleave", hideTip);
    row.addEventListener("focus", () => { const b = row.getBoundingClientRect(); show(b.right - 160, b.top); });
    row.addEventListener("blur", hideTip);
    list.append(row);
  });
  fig.append(list);
  withTableToggle(fig, cfg.tableHead, cfg.rows.map((r) => [r.label, r.display]), [1]);
}

// ================================================================ tiles
function tile(label, display, sub, opts = {}) {
  const v = el("div", { class: "value" });
  if (opts.status) {
    v.className = `value status status-${opts.status}`;
    v.append(el("span", { class: "icon", "aria-hidden": "true" }), opts.status);
  } else v.textContent = display;
  const subEl = el("div", { class: "sub" });
  if (opts.delta) subEl.append(el("span", { class: opts.deltaClass, text: opts.delta + " " }));
  subEl.append(sub);
  const t = el("div", { class: "tile" }, el("div", { class: "label", text: label }), v, subEl);
  if (!opts.status) t._count = () => countUp(v, display);
  return t;
}

// ================================================================ dashboard
function renderDashboard(d) {
  const ov = d.overview, risk = d.risk, mm = d.mismatches, themes = d.themes, fix = d.fix;
  const months = ov.monthly_trend.map((m) => m.month);
  const labels = months.map(MONTH);
  const first = ov.monthly_trend[0], latest = ov.monthly_trend[ov.monthly_trend.length - 1];
  const prev = ov.monthly_trend[ov.monthly_trend.length - 2];
  const hv = ov.health_verdict;
  const L = (k) => d.theme_labels[k] || k;
  const O = (k) => d.theme_owners[k] || "";
  const alert = risk.overall_alert_level;

  $("#period").textContent = `${MONTH(first.month)}–${MONTH(latest.month)} ${latest.month.slice(0, 4)}`;
  $("#model-name").textContent = `${d.provider} · ${d.model}`;
  $("#footer-model").textContent = `Agents run on ${d.provider} · ${d.model} · OpenAI Agents SDK`;

  // ---------- hero
  const h1 = $("#hero-title");
  h1.textContent = "";
  h1.append("NPS fell from ", el("span", { class: "num", text: tidy(first.nps_display) }), " to ",
    el("span", { class: "num", text: tidy(latest.nps_display) }), ` in ${MONTH_LONG(latest.month).split(" ")[0]}.`);
  $("#hero-lede").textContent = `A team of AI agents read all ${ov.overall.n} survey answers and wrote a one-page brief for leadership: how bad it is, why it happened, how much money is at risk and what to fix first. Python computes every number; a code auditor checks the brief.`;
  const badges = $("#hero-badges");
  badges.textContent = "";
  badges.append(
    el("span", { class: `badge status-${alert}` }, el("span", { class: "icon", "aria-hidden": "true" }), `Alert level ${alert}`),
    el("span", { class: "badge" }, "✓ Every number checked by code"),
    el("span", { class: "badge" }, "5 specialist agents + orchestrator"));

  const hc = $("#hero-card");
  hc.textContent = "";
  const hv_el = el("div", { class: "hc-value", text: tidy(latest.nps_display) });
  hc.append(el("div", { class: "hc-label", text: `${MONTH_LONG(latest.month)} NPS` }), hv_el,
    el("div", { class: "hc-delta" }, el("span", { class: hv.month_on_month_change < 0 ? "delta-bad" : "delta-good", text: `${tidy(hv.month_on_month_change_display)} pts` }),
      ` vs ${MONTH_LONG(prev.month).split(" ")[0]} · ${latest.moe_display} margin of error`));
  lineChart(hc, {
    aria: "NPS by month with margin of error", labels, labelsLong: months, height: 190, rightPad: 56,
    series: [{ name: "NPS", color: "--series-1", values: ov.monthly_trend.map((m) => m.nps),
      band: ov.monthly_trend.map((m) => [m.nps - m.moe, m.nps + m.moe]), label: " ",
      tipName: (i) => `NPS (${ov.monthly_trend[i].moe_display}, n=${ov.monthly_trend[i].n})` }],
    table: { head: ["Month", "NPS", "Margin of error", "n"], num: [1, 2, 3], rows: ov.monthly_trend.map((m) => [m.month, tidy(m.nps_display), m.moe_display, m.n]) },
  });
  onReveal(hc, () => countUp(hv_el, tidy(latest.nps_display)));

  // ---------- KPI tiles
  const k = $("#kpis");
  k.textContent = "";
  const tiles = [
    tile("Overall NPS · all months", tidy(ov.overall.nps_display), `${ov.overall.moe_display} · n=${ov.overall.n}`),
    tile("Revenue at risk", lakh(risk.total_revenue_at_risk_lakh), `${risk.risk_verdict.share_of_revenue_at_risk_pct}% of ${lakh(risk.total_revenue_lakh)} revenue`),
    tile("Alert level", "", `NPS health ${hv.level} · revenue risk ${risk.risk_verdict.level}`, { status: alert }),
    tile("Suspicious scores", String(mm.mismatch_count), `NPS ${tidy(mm.alternative_nps.overall.if_reversed)} if they were reversed`),
  ];
  k.append(...tiles);
  onReveal(k, () => tiles.forEach((t) => t._count && t._count()));

  // ---------- 01 cause
  const rising = themes.fastest_rising_complaint;
  const trend = themes.complaint_trend_by_month;
  const rt = trend.find((t) => t.theme === rising);
  const eff = themes.latest_month_effect_of_rising_complaint;
  const chLatest = d.channel_by_month[latest.month].filter((g) => !g.low_sample);
  const worstCh = chLatest.reduce((a, b) => (b.nps < a.nps ? b : a));
  const bestCh = chLatest.reduce((a, b) => (b.nps > a.nps ? b : a));
  $("#cause-title").textContent = L(rising);
  const cl = $("#cause-lede");
  cl.textContent = "";
  cl.append("Mentions went ", el("b", { text: months.map((m) => rt.mentions_by_month[m]).join(" → ") }), ` across ${months.map(MONTH).join(", ")}. `,
    `In ${MONTH(latest.month)}, customers who mention it give an NPS of `, el("b", { text: tidy(eff.nps_with_theme) }),
    "; everyone else gives ", el("b", { text: tidy(eff.nps_without_theme) }), `. ${worstCh.channel} NPS fell to `,
    el("b", { text: tidy(worstCh.nps_display) }), ` while ${bestCh.channel} held at `, el("b", { text: tidy(bestCh.nps_display) }), ".");

  lineChart($("#chart-complaints"), {
    title: "Complaint mentions by month", sub: "One complaint broke away from the pack.",
    labels, labelsLong: months, fmt: String, tickFmt: String, rightPad: 140, height: 340,
    legendItems: [{ name: L(rising), color: "--series-1" }, { name: "Other complaint themes", color: "--deemph" }],
    series: trend.map((t) => ({ name: L(t.theme), color: t.theme === rising ? "--series-1" : "--deemph",
      values: months.map((m) => t.mentions_by_month[m] || 0), label: t.theme === rising ? "Login / OTP" : false })),
    table: { head: ["Theme", ...months], num: months.map((_, i) => i + 1), rows: trend.map((t) => [L(t.theme), ...months.map((m) => t.mentions_by_month[m] || 0)]) },
  });

  const q = $("#quotes");
  head(q, "In customers' own words", `${MONTH_LONG(latest.month)} detractors mentioning login / OTP`);
  q.append(el("div", { class: "stat-inline" },
    el("div", {}, el("div", { class: "v", text: tidy(eff.nps_with_theme) }), el("div", { class: "l", text: `NPS, mentions it (n=${eff.n_with_theme})` })),
    el("div", {}, el("div", { class: "v", text: tidy(eff.nps_without_theme) }), el("div", { class: "l", text: `NPS, everyone else (n=${eff.n_without_theme})` }))));
  const latestDet = d.themes_latest_detractors.by_bucket.detractor.top_themes;
  const risingT = latestDet.find((t) => t.theme === rising) || latestDet[0];
  for (const qt of (risingT ? risingT.quotes.slice(0, 3) : []))
    q.append(el("blockquote", { class: "quote" }, el("p", { text: `“${qt.quote}”` }),
      el("cite", { text: `${qt.response_id} · score ${qt.score} · ${qt.product}` })));

  const colors = ["--series-1", "--series-2", "--series-3"];
  const segChart = (fig, by, key, title, sub) => {
    const names = by[months[0]].map((g) => g[key]);
    const seg = (m, c) => by[m].find((g) => g[key] === c);
    lineChart(fig, {
      title, sub, labels, labelsLong: months, rightPad: 138,
      legendItems: names.map((c, i) => ({ name: c, color: colors[i] })),
      series: names.map((c, i) => ({ name: c, color: colors[i], label: true, values: months.map((m) => seg(m, c).nps),
        tipName: (j) => { const g = seg(months[j], c); return `${c} (n=${g.n}${g.low_sample ? ", low sample" : ""})`; } })),
      table: { head: ["Month", key[0].toUpperCase() + key.slice(1), "NPS", "Margin of error", "n", ""], num: [2, 3, 4],
        rows: months.flatMap((m) => names.map((c) => { const g = seg(m, c);
          return [m, c, tidy(g.nps_display), g.moe_display, g.n, g.low_sample ? el("span", { class: "flag", text: "low sample" }) : ""]; })) },
    });
  };
  segChart($("#chart-channel"), d.channel_by_month, "channel", "NPS by channel", `${worstCh.channel} collapsed; ${bestCh.channel} held steady.`);
  segChart($("#chart-product"), d.product_by_month, "product", "NPS by product", "Every product fell, so the cause is a channel, not a product.");

  // ---------- 02 money
  const topP = risk.by_product[0];
  const loud = risk.complaint_themes_ranked_by_customers[0], exp = risk.complaint_themes_ranked_by_money[0];
  $("#money-title").textContent = `${topP.product} holds ${topP.share_of_total_risk_pct}% of the money at risk`;
  const ml = $("#money-lede");
  ml.textContent = "";
  ml.append(el("b", { text: lakh(risk.total_revenue_at_risk_lakh) }), ` of ${lakh(risk.total_revenue_lakh)} yearly revenue is at risk. The loudest complaint is `,
    el("b", { text: L(loud.theme) }), ` (${loud.customers} customers), but the most expensive is `,
    el("b", { text: L(exp.theme) }), ` (${exp.customers} customers, ${lakh(exp.revenue_at_risk_lakh)} at risk). Loud is not the same as expensive.`);
  barList($("#chart-risk-product"), {
    title: "Revenue at risk by product", sub: "Yearly revenue × assumed churn chance (3% / 10% / 25%).", tableHead: ["Product", "Revenue at risk"],
    rows: risk.by_product.map((r, i) => ({ label: r.product, value: r.revenue_at_risk_lakh, em: i === 0,
      display: `${lakh(r.revenue_at_risk_lakh)} · ${r.share_of_total_risk_pct}%`, tip: `${r.customers} customers, ${r.detractors} detractors` })),
  });
  barList($("#chart-loud"), {
    title: "Loudest complaints", sub: "Customers mentioning each one.", tableHead: ["Complaint", "Customers"],
    rows: risk.complaint_themes_ranked_by_customers.map((r, i) => ({ label: L(r.theme), value: r.customers, em: i === 0,
      display: `${r.customers}`, tip: `customers · ${lakh(r.revenue_at_risk_lakh)} at risk` })),
  });
  barList($("#chart-expensive"), {
    title: "Most expensive complaints", sub: "Revenue at risk among those customers.", tableHead: ["Complaint", "Revenue at risk"],
    rows: risk.complaint_themes_ranked_by_money.map((r, i) => ({ label: L(r.theme), value: r.revenue_at_risk_lakh, em: i === 0,
      display: lakh(r.revenue_at_risk_lakh), tip: `${r.customers} customers` })),
  });

  // ---------- 03 fix
  const fp = fix.all_months.ranked_by_nps_points.filter((r) => r.detractors_fixed > 0);
  const fr = fix.all_months.ranked_by_rupees_saved.filter((r) => r.detractors_fixed > 0);
  const agree = fix.all_months.rankings_agree;
  $("#fix-title").textContent = agree ? `Fix ${L(fp[0].theme)} first` : "Two rankings disagree: run two tracks";
  const fl = $("#fix-lede");
  fl.textContent = "";
  fl.append("Ranked by NPS points, ", el("b", { text: L(fp[0].theme) }), ` comes first (${tidy(fp[0].nps_points)} points). Ranked by rupees saved, `,
    el("b", { text: L(fr[0].theme) }), ` comes first (${lakh(fr[0].rupees_saved_lakh)}). Assumes a fixed detractor becomes a passive.`);
  const tracks = $("#tracks");
  tracks.textContent = "";
  const trackCard = (kicker, r) => el("div", { class: "track" },
    el("div", { class: "t-k", text: kicker }), el("div", { class: "t-title", text: L(r.theme) }), el("div", { class: "t-owner", text: `Owner: ${O(r.theme)}` }),
    el("div", { class: "t-stats" },
      el("div", {}, el("div", { class: "v", text: tidy(r.nps_points) }), el("div", { class: "l", text: "NPS points gained" })),
      el("div", {}, el("div", { class: "v", text: lakh(r.rupees_saved_lakh) }), el("div", { class: "l", text: "revenue saved per year" })),
      el("div", {}, el("div", { class: "v", text: String(r.detractors_fixed) }), el("div", { class: "l", text: "detractors fixed" }))));
  tracks.append(trackCard("Track A · fixes the NPS drop", fp[0]));
  if (!agree) tracks.append(trackCard("Track B · protects the money", fr[0]));
  barList($("#chart-fix-points"), {
    title: "Ranked by NPS points gained", sub: "All three months.", tableHead: ["Fix", "NPS points"],
    rows: fp.map((r, i) => ({ label: L(r.theme), value: parseFloat(r.nps_points), em: i === 0,
      display: `${tidy(r.nps_points)} pts`, tip: `${r.detractors_fixed} detractors fixed · ${lakh(r.rupees_saved_lakh)} saved` })),
  });
  barList($("#chart-fix-rupees"), {
    title: "Ranked by rupees saved", sub: "All three months.", tableHead: ["Fix", "Rupees saved"],
    rows: fr.map((r, i) => ({ label: L(r.theme), value: r.rupees_saved_lakh, em: i === 0,
      display: lakh(r.rupees_saved_lakh), tip: `${r.detractors_fixed} detractors fixed · ${tidy(r.nps_points)} NPS points` })),
  });
  const cb = $("#callbacks");
  head(cb, `Call back this week: ${d.callbacks.callback_list.length} detractors from ${MONTH_LONG(d.callbacks.month)}`,
    `Ranked by revenue at risk. Together they hold ${lakh(d.callbacks.list_revenue_at_risk_lakh)}.`);
  cb.append(tableView(["#", "Customer", "Product", "Channel", "Score", "₹ lakh at risk", "What they said", ""],
    d.callbacks.callback_list.map((c) => [el("span", { class: "rank-dot", text: String(c.rank) }), c.response_id, c.product, c.channel, c.score,
      c.revenue_at_risk_lakh.toFixed(2), c.comment, c.verify_score_first ? el("span", { class: "flag", text: "verify score first" }) : ""]), [4, 5]));

  // ---------- 04 trust
  const ex = mm.mismatches[0];
  const ao = mm.alternative_nps.overall;
  $("#trust-title").textContent = `${mm.mismatch_count} scores contradict their comments`;
  const tl = $("#trust-lede");
  tl.textContent = "";
  if (ex) tl.append(`Customer ${ex.response_id} gave a score of ${ex.score} but wrote `, el("b", { text: `“${ex.comment}”` }),
    `. They probably flipped the 0–10 scale. Scores are never changed silently: NPS is ${tidy(ao.as_recorded)} as recorded, ${tidy(ao.if_reversed)} if those scores were reversed and ${tidy(ao.if_excluded)} if they are left out.`);
  const a = $("#alt-nps");
  head(a, "NPS under each assumption", "These alternatives go into the brief's caveats.");
  a.append(el("div", { class: "stat-inline" },
    el("div", {}, el("div", { class: "v", text: tidy(ao.as_recorded) }), el("div", { class: "l", text: "as recorded (official)" })),
    el("div", {}, el("div", { class: "v", text: tidy(ao.if_reversed) }), el("div", { class: "l", text: `if reversed (${tidy(ao.shift_if_reversed)} pts)` })),
    el("div", {}, el("div", { class: "v", text: tidy(ao.if_excluded) }), el("div", { class: "l", text: `if the ${mm.mismatch_count} are excluded` }))));
  a.append(tableView(["Month", "As recorded", "If reversed", "If excluded"],
    Object.entries(mm.alternative_nps.by_month).map(([m, v]) => [m, tidy(v.as_recorded), tidy(v.if_reversed), tidy(v.if_excluded)]), [1, 2, 3]));
  const mt = $("#mismatch-table");
  head(mt, "Low score, glowing comment", "Every mismatch the tool found.");
  mt.append(tableView(["ID", "Month", "Score", "Comment"], mm.mismatches.map((x) => [x.response_id, x.month, x.score, x.comment]), [2]));
}

// ================================================================ brief (safe markdown)
function inline(text) {
  const frag = document.createDocumentFragment();
  for (const part of text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)) {
    if (!part) continue;
    if (part.startsWith("**") && part.endsWith("**")) frag.append(el("b", { text: part.slice(2, -2) }));
    else if (part.startsWith("`") && part.endsWith("`")) frag.append(el("code", { text: part.slice(1, -1) }));
    else frag.append(document.createTextNode(part));
  }
  return frag;
}
const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

function renderMarkdown(md, target) {
  target.textContent = "";
  const lines = md.replace(/\r/g, "").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.trim().startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++]);
      const [h, ...rest] = rows.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r));
      const t = el("table"), tr = el("tr");
      cells(h).forEach((c) => tr.append(el("th", {}, inline(c))));
      t.append(el("thead", {}, tr));
      const tb = el("tbody");
      rest.forEach((r) => { const row = el("tr"); cells(r).forEach((c) => row.append(el("td", {}, inline(c)))); tb.append(row); });
      t.append(tb); target.append(t);
      continue;
    }
    const mh = line.match(/^(#{1,3})\s+(.*)$/);
    if (mh) { target.append(el(`h${mh[1].length}`, {}, inline(mh[2]))); i++; continue; }
    const ma = line.match(/^\**\s*ALERT LEVEL:\s*\**\s*(GREEN|AMBER|RED)/i);
    if (ma) {
      const lvl = ma[1].toUpperCase();
      target.append(el("p", {}, el("span", { class: `alert-line status status-${lvl}` }, el("span", { class: "icon", "aria-hidden": "true" }), `ALERT LEVEL: ${lvl}`)));
      i++; continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const ul = el("ul");
      let lastLi = null;
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        const indent = lines[i].match(/^\s*/)[0].length;
        const li = el("li", {}, inline(lines[i].replace(/^\s*[-*]\s+/, "")));
        if (indent >= 2 && lastLi) {
          let sub = lastLi.querySelector(":scope > ul");
          if (!sub) { sub = el("ul"); lastLi.append(sub); }
          sub.append(li);
        } else { ul.append(li); lastLi = li; }
        i++;
      }
      target.append(ul);
      continue;
    }
    target.append(el("p", {}, inline(line)));
    i++;
  }
}

function renderFactCheck(text) {
  const box = $("#fact-check");
  box.textContent = "";
  const lines = text.trim().split("\n");
  const rows = lines.slice(1).map((l) => l.match(/\[(PASS|FAIL)\]\s+(\S+)\s*(.*)/)).filter(Boolean);
  const passed = (lines[0] || "").includes("PASSED");
  const nPass = rows.filter((r) => r[1] === "PASS").length;
  const badge = el("span", { class: `fc-badge ${passed ? "ok" : "bad"}`, "aria-hidden": "true" });
  const icon = s("svg", { viewBox: "0 0 24 24", width: 18, height: 18 });
  icon.append(s("path", { d: passed ? "M5 12.5l4.5 4.5L19 7.5" : "M7 7l10 10M17 7L7 17", fill: "none", stroke: "#fff", "stroke-width": 3, "stroke-linecap": "round", "stroke-linejoin": "round" }));
  badge.append(icon);
  box.append(el("div", { class: "fc-head" }, badge,
    el("div", {}, el("b", { text: passed ? "Fact check passed" : "Fact check failed" }), el("span", { text: `${nPass} of ${rows.length} checks passed · fact_check.py` }))));
  for (const m of rows)
    box.append(el("div", { class: "fc-row" }, el("span", { class: m[1] === "PASS" ? "fc-ok" : "fc-bad", text: m[1] === "PASS" ? "✓" : "✗" }),
      el("div", {}, el("span", { text: m[2].replace(/_/g, " ") }), el("span", { class: "fc-detail", text: m[3] }))));
}

const runLabel = (id) => {
  const m = id.match(/run_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]} · ${m[4]}:${m[5]}:${m[6]}` : id;
};
async function loadRuns(selectId) {
  const runs = await (await fetch("/api/runs")).json();
  const sel = $("#run-select");
  sel.textContent = "";
  for (const r of runs) sel.append(el("option", { value: r.id, text: `${runLabel(r.id)}  ${r.passed ? "✓ passed" : "✗ failed"}` }));
  $("#run-count").textContent = runs.length ? `${runs.length} saved run${runs.length > 1 ? "s" : ""} · ${runs.filter((r) => r.passed).length} passed the fact check` : "";
  if (!runs.length) return;
  sel.value = selectId && runs.some((r) => r.id === selectId) ? selectId : runs[0].id;
  await loadRun(sel.value);
}
async function loadRun(id) {
  const r = await (await fetch(`/api/runs/${encodeURIComponent(id)}`)).json();
  renderMarkdown(r.brief, $("#brief-body"));
  renderFactCheck(r.fact_check);
  $("#trace-saved").textContent = r.trace;
}
$("#run-select").addEventListener("change", (e) => loadRun(e.target.value));

// ================================================================ live run
const nodes = () => document.querySelectorAll("#pipeline .node");
const setNode = (name, state) => {
  const n = document.querySelector(`#pipeline .node[data-node="${name}"]`);
  if (n) { n.classList.remove("running", "done", "failed"); if (state) n.classList.add(state); }
};
function handleLine(line, pre) {
  const span = el("span", { text: line + "\n" });
  if (/\bCALL\b/.test(line)) span.className = "call";
  if (/PASSED/.test(line)) span.className = "ok";
  if (/ERROR|FAILED|Traceback/.test(line)) span.className = "err";
  pre.append(span);
  pre.scrollTop = pre.scrollHeight;
  let m;
  if (/\bSTART\b/.test(line)) setNode("orchestrator", "running");
  if ((m = line.match(/CALL\s+(\w+)/))) setNode(m[1], "running");
  if ((m = line.match(/OUTPUT\s+(\w+)/))) setNode(m[1], "done");
  if (/\bGUARD\b/.test(line)) setNode("fact_check", "running");
  if ((m = line.match(/DONE\s+fact check (PASSED|FAILED)/))) { setNode("fact_check", m[1] === "PASSED" ? "done" : "failed"); setNode("orchestrator", "done"); }
}
async function startRun() {
  const btn = $("#run-btn"), pre = $("#trace-live"), timer = $("#run-timer");
  btn.disabled = true;
  btn.textContent = "Running…";
  pre.textContent = "";
  nodes().forEach((n) => n.classList.remove("running", "done", "failed"));
  const t0 = Date.now();
  const tick = setInterval(() => { timer.textContent = `Running · ${((Date.now() - t0) / 1000).toFixed(0)}s`; }, 500);
  let runId = null, exit = null;
  try {
    // fetch + stream reader, not EventSource: EventSource auto-reconnects, which would start a second run
    const res = await fetch("/api/run/stream");
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let k;
      while ((k = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, k); buf = buf.slice(k + 2);
        const data = chunk.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("\n");
        if (!data) continue;
        const ev = JSON.parse(data);
        if (ev.type === "line") handleLine(ev.text, pre);
        else if (ev.type === "error") handleLine("ERROR  " + ev.text, pre);
        else if (ev.type === "done") { runId = ev.run_id; exit = ev.exit; }
      }
    }
  } catch (err) {
    handleLine("ERROR  " + err, pre);
  } finally {
    clearInterval(tick);
    btn.disabled = false;
    btn.textContent = "▶ Run again";
  }
  const secs = ((Date.now() - t0) / 1000).toFixed(0);
  if (runId) {
    timer.textContent = `Finished in ${secs}s · ${exit === 0 ? "fact check passed ✓" : "fact check failed ✗"}`;
    await loadRuns(runId);
    handleLine(`\n→ The new brief is loaded in “The leadership brief” above (${runLabel(runId)}).`, pre);
  } else {
    timer.textContent = `Stopped after ${secs}s · run failed`;
    nodes().forEach((n) => { if (n.classList.contains("running")) { n.classList.remove("running"); n.classList.add("failed"); } });
  }
}
$("#run-btn").addEventListener("click", startRun);

// ================================================================ nav: scroll spy + theme
const links = [...document.querySelectorAll(".nav-links a")];
const spy = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${e.target.id}`));
}, { rootMargin: "-45% 0px -50% 0px" });
links.forEach((a) => { const sec = document.querySelector(a.getAttribute("href")); if (sec) spy.observe(sec); });

const root = document.documentElement;
const saved = localStorage.getItem("nps-theme");
if (saved) root.dataset.theme = saved;
$("#theme-toggle").addEventListener("click", () => {
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  localStorage.setItem("nps-theme", root.dataset.theme);
});

// ================================================================ boot
(async () => {
  try {
    renderDashboard(await (await fetch("/api/dashboard")).json());
  } catch (e) {
    console.error(e);
    $("#hero-title").textContent = "Could not load the survey data.";
    $("#hero-lede").textContent = String(e);
  }
  watchReveals();
  await loadRuns();
  watchReveals();
})();
