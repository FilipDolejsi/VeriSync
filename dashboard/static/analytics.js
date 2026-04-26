/* Analytics page — fetches /analytics/summary and renders 3 charts + a table. */
(async function () {
  "use strict";

  const fmt = new Intl.NumberFormat("en-US");

  const res = await fetch("/analytics/summary", { credentials: "same-origin" });
  if (!res.ok) {
    console.error("analytics fetch failed", res.status);
    return;
  }
  const data = await res.json();

  /* ── Severity over time (line) ── */
  new Chart(document.getElementById("severity-chart"), {
    type: "line",
    data: {
      labels: data.severity_by_day.map((p) => p.day),
      datasets: [
        line("Critical", data.severity_by_day.map((p) => p.critical), "#ef4444"),
        line("Warning",  data.severity_by_day.map((p) => p.warning),  "#eab308"),
        line("Info",     data.severity_by_day.map((p) => p.info),     "#3b82f6"),
      ],
    },
    options: chartOpts(),
  });

  /* ── Spend by model (bar) ── */
  new Chart(document.getElementById("model-spend-chart"), {
    type: "bar",
    data: {
      labels: data.model_breakdown.map((m) => m.model_id),
      datasets: [{
        label: "Sats",
        data: data.model_breakdown.map((m) => m.total_spend_sats),
        backgroundColor: "#7c6af7",
        borderRadius: 6,
      }],
    },
    options: chartOpts(false),
  });

  /* ── Findings by category (doughnut) ── */
  new Chart(document.getElementById("category-chart"), {
    type: "doughnut",
    data: {
      labels: data.category_breakdown.map((c) => c.category),
      datasets: [{
        data: data.category_breakdown.map((c) => c.count),
        backgroundColor: ["#ef4444", "#eab308", "#3b82f6", "#22c55e", "#a89bff"],
        borderColor: "#1a1d27", borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { color: "#e2e8f0" } } },
    },
  });

  /* ── Model breakdown table ── */
  const $tbody = document.getElementById("model-breakdown-body");
  $tbody.innerHTML = data.model_breakdown.map((m) => `
    <tr>
      <td class="mono">${escape(m.model_id)}</td>
      <td>${fmt.format(m.calls)}</td>
      <td>${fmt.format(m.findings)}</td>
      <td><span class="pill red">${fmt.format(m.critical)}</span></td>
      <td class="mono accent">⚡ ${fmt.format(m.total_spend_sats)}</td>
    </tr>`).join("");

  /* ── Helpers ── */
  function line(label, points, color) {
    return {
      label, data: points,
      borderColor: color,
      backgroundColor: color + "22",
      fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2,
    };
  }

  function chartOpts(showLegend = true) {
    return {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: showLegend, labels: { color: "#e2e8f0" } } },
      scales: {
        x: { grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#64748b" } },
        y: { grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#64748b" }, beginAtZero: true },
      },
    };
  }

  function escape(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }
})();
