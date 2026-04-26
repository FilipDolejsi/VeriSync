/* ───────────── VeriSync dashboard live wiring ─────────────
 * Connects to /events/stream (SSE), updates the sat balance,
 * appends to the live feed, prepends new PRs to the history table,
 * and refreshes the spend chart.
 */
(function () {
  "use strict";

  const fmt = new Intl.NumberFormat("en-US");
  const state = {
    balance: window.__VERISYNC__?.initialBalance ?? 0,
    spendSeries: window.__VERISYNC__?.spendSeries ?? [],
  };

  /* ── DOM refs ── */
  const $balance = document.getElementById("sat-balance");
  const $statBal = document.getElementById("stat-balance");
  const $stream  = document.getElementById("event-stream");
  const $history = document.getElementById("pr-history");
  const $sseDot  = document.getElementById("sse-dot");
  const $sseTxt  = document.getElementById("sse-status");

  /* ── Spend chart ── */
  let spendChart = null;
  function initSpendChart() {
    const ctx = document.getElementById("spend-chart");
    if (!ctx || !window.Chart) return;

    const labels = state.spendSeries.map((p) => p.label);
    const data   = state.spendSeries.map((p) => p.sats);

    spendChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Sats spent",
          data,
          borderColor: "#7c6af7",
          backgroundColor: "rgba(124,106,247,0.15)",
          fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#64748b" } },
          y: { grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#64748b" } },
        },
      },
    });
  }

  function bumpSpendChart(sats) {
    if (!spendChart) return;
    const ds = spendChart.data.datasets[0].data;
    ds[ds.length - 1] = (ds[ds.length - 1] || 0) + sats;
    spendChart.update("none");
  }

  /* ── Helpers ── */
  function setBalance(newBalance) {
    state.balance = newBalance;
    if ($balance) {
      $balance.textContent = `⚡ ${fmt.format(newBalance)} sats`;
      $balance.dataset.balance = String(newBalance);
      $balance.classList.remove("flash");
      void $balance.offsetWidth; // restart animation
      $balance.classList.add("flash");
    }
    if ($statBal) $statBal.textContent = fmt.format(newBalance);
  }

  function nowHHMMSS() {
    const d = new Date();
    return d.toTimeString().slice(0, 8);
  }

  function pushEvent({ tag, text, kind }) {
    if (!$stream) return;
    const empty = $stream.querySelector(".empty");
    if (empty) empty.remove();

    const li = document.createElement("li");
    li.innerHTML = `
      <span class="time">${nowHHMMSS()}</span>
      <span class="tag ${kind || ""}">${tag}</span>
      <span class="text"></span>`;
    li.querySelector(".text").textContent = text;
    $stream.prepend(li);

    // cap at 80 entries
    while ($stream.children.length > 80) $stream.lastChild.remove();
  }

  function prependPR(pr) {
    if (!$history) return;
    const empty = $history.querySelector(".empty");
    if (empty) empty.parentElement.remove();

    const tr = document.createElement("tr");
    tr.classList.add("flash-row");
    tr.innerHTML = `
      <td><a href="${pr.pr_url}" target="_blank">#${pr.pr_number}</a> </td>
      <td class="mono"></td>
      <td>
        <span class="pill red">${pr.critical_count}</span>
        <span class="pill yellow">${pr.warning_count}</span>
        <span class="pill blue">${pr.info_count}</span>
      </td>
      <td class="mono accent">⚡ ${fmt.format(pr.total_cost_sats)}</td>
      <td class="muted">just now</td>`;
    tr.querySelector("td a").after(document.createTextNode(" " + (pr.title || "")));
    tr.children[1].textContent = pr.repo || "";
    $history.prepend(tr);

    while ($history.children.length > 25) $history.lastChild.remove();
  }

  /* ── SSE connection ── */
  function connect() {
    const es = new EventSource("/events/stream");

    es.addEventListener("open", () => {
      $sseDot?.classList.add("green");
      if ($sseTxt) $sseTxt.textContent = "live";
    });

    es.addEventListener("error", () => {
      if ($sseTxt) $sseTxt.textContent = "reconnecting…";
    });

    // Balance updates → { balance, delta }
    es.addEventListener("balance", (ev) => {
      try {
        const data = JSON.parse(ev.data);
        setBalance(data.balance);
        if (data.delta) {
          pushEvent({ tag: "WALLET", kind: "sats", text: `${data.delta > 0 ? "+" : ""}${data.delta} sats` });
          if (data.delta < 0) bumpSpendChart(-data.delta);
        }
      } catch (e) { console.warn(e); }
    });

    // Pipeline lifecycle
    es.addEventListener("webhook",  (ev) => withJSON(ev, (d) => pushEvent({ tag: "WEBHOOK", text: `${d.event} · ${d.repo}#${d.pr_number}` })));
    es.addEventListener("chunk",    (ev) => withJSON(ev, (d) => pushEvent({ tag: "CHUNK",   text: `${d.count} hunks · ${d.languages.join(", ")}` })));
    es.addEventListener("route",    (ev) => withJSON(ev, (d) => pushEvent({ tag: "ROUTE",   text: d.summary })));
    es.addEventListener("finding",  (ev) => withJSON(ev, (d) => {
      const kind = d.severity === "critical" ? "warn" : "";
      pushEvent({ tag: "FINDING", kind, text: `${d.severity.toUpperCase()} · ${d.category} — ${d.description}` });
    }));
    es.addEventListener("report",   (ev) => withJSON(ev, (d) => {
      pushEvent({ tag: "REPORT", kind: "ok",
        text: `Posted to PR · ${d.critical_count} critical, ${d.warning_count} warnings, ${d.info_count} info` });
      prependPR(d);
    }));

    return es;
  }

  function withJSON(ev, fn) {
    try { fn(JSON.parse(ev.data)); } catch (e) { console.warn("bad SSE payload", e); }
  }

  /* ── Boot ── */
  function boot() {
    initSpendChart();
    connect();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
