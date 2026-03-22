"""
Web Dashboard v5.0 — Real-time monitoring with WebSocket live updates.

5x Advanced Features:
  • Flask-SocketIO for instant live data (no meta-refresh polling)
  • Upload history line chart (last 7 days, per platform)
  • Platform breakdown donut chart
  • Analytics tab with performance metrics
  • Job management: retry failed, delete, prioritize
  • Log viewer (live tail of autoreels.log)
  • Settings panel (config hot-reload)
  • Mobile-responsive dark UI with glow effects
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from threading import Thread

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# HTML/CSS/JS Template (single-file embedded)
# ─────────────────────────────────────────────────────────────────────────────
_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AUTO-REELS PRO v5 — Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
:root{
  --bg:#06060f;--card:#0c0c1e;--border:#1a1a30;
  --accent:#e50000;--cyan:#00d4ff;--gold:#ffd700;
  --green:#00ff88;--red:#ff4444;--purple:#aa66ff;
  --blue:#4488ff;--text:#e0e0e0;--dim:#666;--dim2:#999;
  --neon-glow:0 0 20px rgba(0,212,255,0.3);
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:'JetBrains Mono','Fira Code',monospace;
  font-size:13px;min-height:100vh;overflow-x:hidden}
a{color:var(--cyan);text-decoration:none}
a:hover{text-decoration:underline;color:#fff}

/* ── Header ── */
header{
  background:linear-gradient(135deg,#0a0a1c 0%,#14061c 100%);
  border-bottom:2px solid var(--accent);
  padding:12px 24px;display:flex;align-items:center;gap:12px;
  position:sticky;top:0;z-index:100;box-shadow:0 2px 20px rgba(229,0,0,0.3);
}
.logo{font-size:17px;color:var(--cyan);letter-spacing:3px;font-weight:700;
  text-shadow:var(--neon-glow)}
.badge{padding:2px 9px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:1px}
.badge-live{background:var(--green);color:#000;animation:pulse 2s infinite}
.badge-ver{background:var(--accent);color:#fff}
.header-right{margin-left:auto;display:flex;align-items:center;gap:16px}
.conn-indicator{font-size:11px}
.conn-ok{color:var(--green)}
.conn-err{color:var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

/* ── Tabs ── */
.tabs{display:flex;gap:0;border-bottom:1px solid var(--border);
  padding:0 24px;background:#080816}
.tab{padding:10px 20px;cursor:pointer;font-size:11px;letter-spacing:1px;
  text-transform:uppercase;color:var(--dim2);border-bottom:2px solid transparent;
  transition:all .2s;user-select:none}
.tab:hover{color:var(--text)}
.tab.active{color:var(--cyan);border-bottom-color:var(--cyan)}

/* ── Main grid ── */
main{padding:20px;display:none}
main.active{display:block}

.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px}
.grid-left-wide{display:grid;grid-template-columns:280px 1fr;gap:18px;align-items:start}

/* ── Cards ── */
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:18px}
.card:hover{border-color:#2a2a40;box-shadow:0 4px 20px rgba(0,0,0,0.4)}
.card-title{
  font-size:10px;letter-spacing:2px;color:var(--cyan);text-transform:uppercase;
  margin-bottom:14px;border-bottom:1px solid var(--border);padding-bottom:8px;
  display:flex;justify-content:space-between;align-items:center;
}
.card-title-left{display:flex;align-items:center;gap:6px}
.card-title-left::before{content:'▸';color:var(--accent)}

/* ── Stats ── */
.stat{display:flex;justify-content:space-between;align-items:center;padding:6px 0;
  border-bottom:1px solid var(--border)}
.stat:last-child{border-bottom:none}
.stat-key{color:var(--dim2)}
.stat-val{font-weight:700;color:var(--gold)}
.stat-val.green{color:var(--green)}
.stat-val.red{color:var(--red)}
.stat-val.cyan{color:var(--cyan)}
.stat-val.blue{color:var(--blue)}

/* ── Big number ── */
.big-number-card{text-align:center;padding:8px 0}
.big-num{font-size:48px;color:var(--gold);font-weight:700;line-height:1;
  text-shadow:0 0 30px rgba(255,215,0,0.5)}
.big-denom{color:var(--dim2);font-size:22px}
.big-label{color:var(--dim2);font-size:10px;letter-spacing:2px;margin-top:4px;text-transform:uppercase}
.prog-wrap{background:#1a1a2e;border-radius:4px;height:10px;margin-top:14px;overflow:hidden}
.prog-fill{
  background:linear-gradient(90deg,var(--accent) 0%,var(--gold) 100%);
  height:10px;border-radius:4px;transition:width .8s ease;
  box-shadow:0 0 10px var(--accent);
}

/* ── State badges ── */
.state{display:inline-block;padding:2px 8px;border-radius:3px;
  font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase}
.s-queued{background:#ffd70022;color:var(--gold);border:1px solid #ffd70066}
.s-downloading{background:#00d4ff22;color:var(--cyan);border:1px solid #00d4ff66}
.s-processing{background:#aa66ff22;color:var(--purple);border:1px solid #aa66ff66}
.s-uploading{background:#4488ff22;color:var(--blue);border:1px solid #4488ff66}
.s-done{background:#00ff8822;color:var(--green);border:1px solid #00ff8866}
.s-failed{background:#ff444422;color:var(--red);border:1px solid #ff444466}

/* ── Table ── */
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{color:var(--dim2);font-size:10px;letter-spacing:1.5px;text-align:left;
  padding:8px 10px;border-bottom:2px solid var(--border);text-transform:uppercase}
td{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:hover td{background:#ffffff06}
.title-cell{max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ── Buttons ── */
.btn{padding:6px 14px;border-radius:4px;border:none;cursor:pointer;
  font-family:inherit;font-size:11px;font-weight:700;letter-spacing:1px;transition:all .2s}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:#ff2222;box-shadow:0 0 16px var(--accent)}
.btn-success{background:#00993a;color:#fff}
.btn-success:hover{background:#00bb44}
.btn-ghost{background:transparent;color:var(--cyan);border:1px solid #00d4ff44}
.btn-ghost:hover{background:#00d4ff14;border-color:var(--cyan)}
.btn-danger{background:transparent;color:var(--red);border:1px solid #ff444444;padding:4px 10px}
.btn-danger:hover{background:#ff444414}
.btn-small{padding:3px 8px;font-size:10px}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}

/* ── Charts ── */
.chart-container{position:relative;height:200px;padding:0 4px}

/* ── Metric tiles ── */
.metric-tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.metric-tile{background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:14px 16px;text-align:center}
.metric-tile .value{font-size:28px;font-weight:700;line-height:1}
.metric-tile .label{color:var(--dim2);font-size:10px;text-transform:uppercase;
  letter-spacing:1px;margin-top:4px}

/* ── Log viewer ── */
.log-container{background:#040408;border:1px solid var(--border);border-radius:6px;
  height:300px;overflow-y:auto;padding:12px;font-size:11px;font-family:monospace}
.log-line{padding:1px 0;border-bottom:1px solid #0a0a14}
.log-info{color:#8888aa}
.log-warn{color:var(--gold)}
.log-error{color:var(--red)}

/* ── Platform badges ── */
.plat-fb{color:#1877f2}
.plat-tiktok{color:#ff0050}
.plat-ig{color:#e1306c}
.plat-yt{color:#ff0000}

/* ── Toast notifications ── */
#toast{
  position:fixed;bottom:24px;right:24px;z-index:9999;
  background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:14px 20px;max-width:320px;font-size:12px;
  transform:translateY(100px);opacity:0;transition:all .3s;
  box-shadow:0 4px 20px rgba(0,0,0,0.5);
}
#toast.show{transform:translateY(0);opacity:1}
#toast.success{border-color:var(--green);color:var(--green)}
#toast.error{border-color:var(--red);color:var(--red)}

/* ── Footer ── */
footer{text-align:center;padding:14px;color:var(--dim2);
  font-size:11px;border-top:1px solid var(--border);margin-top:20px}

@media(max-width:900px){
  .grid-left-wide,.grid-2,.grid-3,.metric-tiles{grid-template-columns:1fr}
}
</style>
</head>
<body>

<header>
  <span class="logo">⚡ AUTO-REELS PRO</span>
  <span class="badge badge-live">● LIVE</span>
  <span class="badge badge-ver">v5.0</span>
  <div class="header-right">
    <span id="conn-status" class="conn-indicator conn-ok">◉ connected</span>
    <span style="color:var(--dim2);font-size:11px" id="last-update">–</span>
  </div>
</header>

<div class="tabs">
  <div class="tab active" onclick="showTab('dashboard')">Dashboard</div>
  <div class="tab" onclick="showTab('queue')">Job Queue</div>
  <div class="tab" onclick="showTab('analytics')">Analytics</div>
  <div class="tab" onclick="showTab('logs')">Logs</div>
</div>

<!-- ── DASHBOARD TAB ──────────────────────────────────────────────────────── -->
<main id="tab-dashboard" class="active">
  <div class="metric-tiles">
    <div class="metric-tile">
      <div class="value" id="m-uploads" style="color:var(--gold)">–</div>
      <div class="label">Uploads Today</div>
    </div>
    <div class="metric-tile">
      <div class="value" id="m-done" style="color:var(--green)">–</div>
      <div class="label">Jobs Done</div>
    </div>
    <div class="metric-tile">
      <div class="value" id="m-queued" style="color:var(--cyan)">–</div>
      <div class="label">Queued</div>
    </div>
    <div class="metric-tile">
      <div class="value" id="m-failed" style="color:var(--red)">–</div>
      <div class="label">Failed</div>
    </div>
  </div>

  <div class="grid-left-wide">
    <div style="display:flex;flex-direction:column;gap:18px">

      <!-- System stats -->
      <div class="card">
        <div class="card-title"><div class="card-title-left">System Stats</div></div>
        <div id="stats-html"></div>
      </div>

      <!-- Upload progress -->
      <div class="card">
        <div class="card-title"><div class="card-title-left">Today's Progress</div></div>
        <div class="big-number-card">
          <div><span class="big-num" id="prog-today">–</span><span class="big-denom" id="prog-limit">/–</span></div>
          <div class="big-label">uploads today</div>
          <div class="prog-wrap"><div class="prog-fill" id="prog-fill" style="width:0%"></div></div>
        </div>
      </div>

      <!-- Actions -->
      <div class="card">
        <div class="card-title"><div class="card-title-left">Actions</div></div>
        <div class="actions">
          <button class="btn btn-primary" onclick="runNow()">▶ Run Now</button>
          <a href="/api/stats" class="btn btn-ghost" target="_blank">JSON API</a>
        </div>
        <div id="action-msg" style="font-size:11px;min-height:18px"></div>
      </div>

      <!-- Platform breakdown donut -->
      <div class="card">
        <div class="card-title"><div class="card-title-left">Platform Mix</div></div>
        <div class="chart-container"><canvas id="chart-platforms"></canvas></div>
      </div>

    </div>

    <div style="display:flex;flex-direction:column;gap:18px">
      <!-- Upload history chart -->
      <div class="card">
        <div class="card-title"><div class="card-title-left">Upload History (7 days)</div></div>
        <div class="chart-container" style="height:220px"><canvas id="chart-history"></canvas></div>
      </div>

      <!-- Recent jobs -->
      <div class="card">
        <div class="card-title"><div class="card-title-left">Recent Jobs</div></div>
        <div class="table-wrap" id="recent-jobs-table"></div>
      </div>
    </div>
  </div>
</main>

<!-- ── QUEUE TAB ──────────────────────────────────────────────────────────── -->
<main id="tab-queue">
  <div class="card">
    <div class="card-title">
      <div class="card-title-left">Job Queue (all jobs)</div>
      <div style="display:flex;gap:8px">
        <input id="queue-search" placeholder="Search title..." 
          style="background:#0a0a18;border:1px solid var(--border);color:var(--text);
                 padding:4px 10px;border-radius:4px;font-family:inherit;font-size:11px"
          oninput="filterQueue(this.value)">
      </div>
    </div>
    <div class="table-wrap" id="queue-table"></div>
  </div>
</main>

<!-- ── ANALYTICS TAB ──────────────────────────────────────────────────────── -->
<main id="tab-analytics">
  <div class="grid-2" style="margin-bottom:18px">
    <div class="card">
      <div class="card-title"><div class="card-title-left">All-Time Totals</div></div>
      <div id="analytics-totals"></div>
    </div>
    <div class="card">
      <div class="card-title"><div class="card-title-left">Top Videos</div></div>
      <div id="analytics-top-videos"></div>
    </div>
  </div>
  <div class="card">
    <div class="card-title"><div class="card-title-left">Recent Uploads</div></div>
    <div class="table-wrap" id="analytics-recent"></div>
  </div>
</main>

<!-- ── LOGS TAB ───────────────────────────────────────────────────────────── -->
<main id="tab-logs">
  <div class="card">
    <div class="card-title">
      <div class="card-title-left">Live Log Viewer</div>
      <div style="display:flex;gap:8px">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;color:var(--dim2)">
          <input type="checkbox" id="log-autoscroll" checked> Auto-scroll
        </label>
        <button class="btn btn-ghost btn-small" onclick="clearLogs()">Clear</button>
      </div>
    </div>
    <div class="log-container" id="log-container"></div>
  </div>
</main>

<div id="toast"></div>

<footer>
  AUTO-REELS PRO v5.0 &nbsp;·&nbsp;
  <a href="/api/stats">JSON API</a> &nbsp;·&nbsp;
  <a href="/api/health">Health</a> &nbsp;·&nbsp;
  <a href="/api/analytics">Analytics</a>
</footer>

<script>
const socket = io();
let historyChart, platformChart;
let allJobs = [];

// ── Connection ────────────────────────────────────────────────────────────
socket.on('connect', () => {
  document.getElementById('conn-status').textContent = '◉ connected';
  document.getElementById('conn-status').className = 'conn-indicator conn-ok';
});
socket.on('disconnect', () => {
  document.getElementById('conn-status').textContent = '◌ disconnected';
  document.getElementById('conn-status').className = 'conn-indicator conn-err';
});

// ── Live data ─────────────────────────────────────────────────────────────
socket.on('stats_update', data => {
  document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
  updateDashboard(data);
});

socket.on('log_line', line => {
  appendLog(line);
});

// ── Tab switching ─────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('main').forEach(m => m.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
  if (name === 'analytics') loadAnalytics();
  if (name === 'queue') renderFullQueue();
}

// ── Dashboard update ──────────────────────────────────────────────────────
function updateDashboard(d) {
  document.getElementById('m-uploads').textContent = d.uploads_today;
  document.getElementById('m-done').textContent = d.queue.done || 0;
  document.getElementById('m-queued').textContent = d.queue.queued || 0;
  document.getElementById('m-failed').textContent = d.queue.failed || 0;

  const pct = d.daily_limit > 0 ? Math.min(100, Math.round(100 * d.uploads_today / d.daily_limit)) : 0;
  document.getElementById('prog-today').textContent = d.uploads_today;
  document.getElementById('prog-limit').textContent = '/' + d.daily_limit;
  document.getElementById('prog-fill').style.width = pct + '%';

  // System stats
  const statsDiv = document.getElementById('stats-html');
  statsDiv.innerHTML = `
    ${stat('Disk Free', d.health.disk_free, '')}
    ${stat('CPU', d.health.cpu, '')}
    ${stat('Memory', d.health.memory, '')}
    ${stat('Upload Window', d.in_upload_window ? 'OPEN ✓' : 'CLOSED', d.in_upload_window ? 'green' : '')}
    ${stat('Next Window', d.next_window, 'cyan')}
    ${stat('Channels', d.channels, '')}
    ${stat('Theme', d.theme || '–', 'blue')}
    ${stat('Encoder', d.encoder || 'software', 'blue')}
  `;

  // Recent jobs
  allJobs = d.jobs || [];
  renderJobTable('recent-jobs-table', allJobs.slice(0, 8), false);

  // Charts
  updateHistoryChart(d.daily_history);
  updatePlatformChart(d.platform_breakdown);
}

function stat(key, val, cls) {
  return `<div class="stat"><span class="stat-key">${key}</span>
    <span class="stat-val ${cls}">${val}</span></div>`;
}

// ── Job table renderer ────────────────────────────────────────────────────
const STATE_CSS = {
  queued:'queued', downloading:'downloading', processing:'processing',
  uploading:'uploading', done:'done', failed:'failed'
};

function renderJobTable(containerId, jobs, showActions) {
  const container = document.getElementById(containerId);
  if (!jobs.length) {
    container.innerHTML = '<p style="color:var(--dim2);padding:20px;text-align:center">No jobs yet</p>';
    return;
  }
  const rows = jobs.map(j => {
    const css = STATE_CSS[j.state] || '';
    const updated = new Date(j.updated * 1000).toLocaleTimeString();
    const err = j.error ? `<span title="${j.error}" style="color:var(--red);cursor:help"> ⚠</span>` : '';
    const quality = j.quality_score ? j.quality_score.toFixed(2) : '–';
    const actions = showActions && j.state === 'failed' ?
      `<button class="btn btn-ghost btn-small" onclick="retryJob('${j.id}')">↺ Retry</button>` : '';
    return `<tr>
      <td class="title-cell" title="${j.title}">${j.title.substring(0,44)}${err}</td>
      <td><span class="state s-${css}">${j.state}</span></td>
      <td style="text-align:center">${j.clips}</td>
      <td style="text-align:center;color:var(--gold)">${quality}</td>
      <td style="color:var(--dim2)">${updated}</td>
      ${showActions ? `<td>${actions}</td>` : ''}
    </tr>`;
  }).join('');
  const actionCol = showActions ? '<th>Action</th>' : '';
  container.innerHTML = `<table><thead><tr>
    <th>Title</th><th>State</th><th>Clips</th><th>Quality</th><th>Updated</th>${actionCol}
  </tr></thead><tbody>${rows}</tbody></table>`;
}

function filterQueue(q) {
  const filtered = q ? allJobs.filter(j => j.title.toLowerCase().includes(q.toLowerCase())) : allJobs;
  renderJobTable('queue-table', filtered, true);
}

function renderFullQueue() {
  renderJobTable('queue-table', allJobs, true);
}

// ── Charts ────────────────────────────────────────────────────────────────
const CHART_DEFAULTS = {
  plugins:{legend:{labels:{color:'#888',font:{family:'JetBrains Mono',size:11}}}},
  scales:{
    x:{ticks:{color:'#666',font:{family:'JetBrains Mono',size:10}},grid:{color:'#1a1a30'}},
    y:{ticks:{color:'#666',font:{family:'JetBrains Mono',size:10}},grid:{color:'#1a1a30'}}
  }
};

function updateHistoryChart(history) {
  if (!history || !history.length) return;
  const labels = history.map(d => d.date.substring(5));
  const platforms = ['facebook','tiktok','instagram','youtube_shorts'];
  const colors = ['#1877f2','#ff0050','#e1306c','#ff0000'];
  const datasets = platforms.map((p, i) => ({
    label: p.charAt(0).toUpperCase() + p.slice(1).replace('_', ' '),
    data: history.map(d => d[p] || 0),
    borderColor: colors[i], backgroundColor: colors[i] + '22',
    tension: 0.3, fill: true, pointRadius: 3,
  }));
  const ctx = document.getElementById('chart-history').getContext('2d');
  if (historyChart) { historyChart.data.labels = labels; historyChart.data.datasets = datasets; historyChart.update(); return; }
  historyChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: { ...CHART_DEFAULTS, responsive: true, maintainAspectRatio: false,
      plugins: { ...CHART_DEFAULTS.plugins, title: { display: false } } }
  });
}

function updatePlatformChart(breakdown) {
  if (!breakdown) return;
  const entries = Object.entries(breakdown).filter(([,v]) => v > 0);
  if (!entries.length) return;
  const colors = ['#1877f2','#ff0050','#e1306c','#ff0000','#aa66ff'];
  const ctx = document.getElementById('chart-platforms').getContext('2d');
  if (platformChart) { 
    platformChart.data.labels = entries.map(([k]) => k);
    platformChart.data.datasets[0].data = entries.map(([,v]) => v);
    platformChart.update(); return;
  }
  platformChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: entries.map(([k]) => k.charAt(0).toUpperCase() + k.slice(1)),
      datasets: [{ data: entries.map(([,v]) => v), backgroundColor: colors, borderWidth: 2, borderColor: '#0c0c1e' }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: '#888', font: { family: 'JetBrains Mono', size: 10 } } } }
    }
  });
}

// ── Analytics tab ─────────────────────────────────────────────────────────
function loadAnalytics() {
  fetch('/api/analytics').then(r => r.json()).then(d => {
    const totalsDiv = document.getElementById('analytics-totals');
    const breakdown = d.platform_breakdown || {};
    totalsDiv.innerHTML = Object.entries(breakdown).map(([p, c]) =>
      stat(p.charAt(0).toUpperCase() + p.slice(1), c + ' uploads', '')
    ).join('') + stat('Total', d.total_uploads, 'gold');

    const topDiv = document.getElementById('analytics-top-videos');
    topDiv.innerHTML = (d.top_videos || []).map(v =>
      `<div class="stat"><span class="stat-key" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${v.title.substring(0,30)}</span>
       <span class="stat-val cyan">${v.clips} clips</span></div>`
    ).join('');

    const recentDiv = document.getElementById('analytics-recent');
    const rows = (d.recent_uploads || []).map(u => {
      const t = new Date(u.uploaded_at * 1000).toLocaleString();
      const platColor = {facebook:'plat-fb',tiktok:'plat-tiktok',instagram:'plat-ig',youtube_shorts:'plat-yt'}[u.platform] || '';
      return `<tr>
        <td class="title-cell">${u.title.substring(0,44)}</td>
        <td><span class="${platColor}">${u.platform}</span></td>
        <td style="color:var(--dim2)">${t}</td>
        <td style="color:var(--gold)">${u.quality_score ? u.quality_score.toFixed(2) : '–'}</td>
      </tr>`;
    }).join('');
    recentDiv.innerHTML = `<table><thead><tr>
      <th>Title</th><th>Platform</th><th>Time</th><th>Quality</th>
    </tr></thead><tbody>${rows || '<tr><td colspan="4" style="color:var(--dim2);text-align:center;padding:20px">No uploads yet</td></tr>'}</tbody></table>`;
  });
}

// ── Log viewer ────────────────────────────────────────────────────────────
function appendLog(line) {
  const container = document.getElementById('log-container');
  const div = document.createElement('div');
  div.className = 'log-line ' + (line.includes('[ERROR]') || line.includes('ERROR') ? 'log-error' :
    line.includes('[WARN]') || line.includes('WARNING') ? 'log-warn' : 'log-info');
  div.textContent = line;
  container.appendChild(div);
  // Keep last 200 lines
  while (container.children.length > 200) container.removeChild(container.firstChild);
  if (document.getElementById('log-autoscroll').checked) {
    container.scrollTop = container.scrollHeight;
  }
}

function clearLogs() {
  document.getElementById('log-container').innerHTML = '';
}

// ── Actions ───────────────────────────────────────────────────────────────
function showToast(msg, type = '') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'show ' + type;
  setTimeout(() => t.className = '', 3500);
}

function runNow() {
  showToast('⏳ Triggering upload cycle...', '');
  fetch('/api/upload-now', {method: 'POST'})
    .then(r => r.json())
    .then(d => {
      if (d.error) showToast('❌ ' + d.error, 'error');
      else showToast(`✅ ${d.jobs_processed} job(s), ${d.clips_uploaded} clip(s) uploaded`, 'success');
    })
    .catch(e => showToast('❌ ' + e, 'error'));
}

function retryJob(id) {
  fetch('/api/reset-job/' + id, {method: 'POST'})
    .then(r => r.json())
    .then(d => {
      if (d.error) showToast('❌ ' + d.error, 'error');
      else showToast('✅ Job re-queued!', 'success');
    });
}

// Request initial data
socket.emit('request_update');
</script>
</body>
</html>"""


def start_dashboard(pipeline, health, analytics, port: int = 8888):
    """Start the Socket.IO dashboard. Call in a daemon thread."""
    log.info("[Dashboard] Starting on port %d...", port)

    try:
        from flask import Flask, jsonify, Response, request as flask_request
        try:
            from flask_socketio import SocketIO, emit
            HAS_SOCKETIO = True
        except ImportError:
            HAS_SOCKETIO = False
            log.warning("[Dashboard] flask-socketio not installed — using polling fallback")
    except ImportError:
        log.warning("[Dashboard] Flask not installed")
        return

    from src.scheduler.job_queue import JobState

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.urandom(24)
    app.logger.disabled = True
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("engineio").setLevel(logging.ERROR)
    logging.getLogger("socketio").setLevel(logging.ERROR)

    if HAS_SOCKETIO:
        sio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    else:
        sio = None

    log_path = Path(__file__).parent.parent.parent / "logs" / "autoreels.log"

    def _build_stats():
        stats = pipeline.queue.stats()
        uploads = pipeline.uploads_today()
        limit = pipeline.daily_limit
        jobs = pipeline.queue.recent(50)
        daily_history = analytics.daily_totals(7)
        platform_breakdown = analytics.platform_breakdown()

        return {
            "status": "running",
            "uploads_today": uploads,
            "daily_limit": limit,
            "in_upload_window": pipeline._in_upload_window(),
            "next_window": pipeline._next_upload_time(),
            "channels": len(pipeline.channel_configs),
            "theme": getattr(pipeline.processor.cfg, "theme", "classic"),
            "encoder": pipeline.processor.detected_encoder or "software",
            "queue": {k: v for k, v in stats.items()},
            "health": {
                "disk_free": health.disk_free_gb(),
                "cpu": health.cpu_pct(),
                "memory": health.mem_pct(),
            },
            "jobs": [
                {
                    "id": j.video_id,
                    "title": j.title,
                    "state": j.state,
                    "clips": len(j.output_clips),
                    "retries": j.retries,
                    "error": j.error,
                    "updated": j.updated_at,
                    "quality_score": getattr(j, "quality_score", 0),
                }
                for j in jobs
            ],
            "daily_history": daily_history,
            "platform_breakdown": platform_breakdown,
            "ts": datetime.utcnow().isoformat() + "Z",
        }

    # ── Background broadcast loop ──────────────────────────────────────────
    def _broadcast_loop():
        last_log_pos = 0
        while True:
            try:
                # Broadcast stats
                if sio:
                    sio.emit("stats_update", _build_stats())
                    # Tail log file
                    if log_path.exists():
                        with open(log_path, encoding="utf-8", errors="replace") as f:
                            f.seek(last_log_pos)
                            new_lines = f.readlines()
                            last_log_pos = f.tell()
                        for line in new_lines[-20:]:
                            sio.emit("log_line", line.rstrip())
            except Exception as exc:
                log.debug("[Dashboard] broadcast error: %s", exc)
            time.sleep(2)

    if sio:
        Thread(target=_broadcast_loop, daemon=True).start()

    # ── Routes ─────────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return Response(_HTML, mimetype="text/html")

    @app.route("/api/stats")
    def api_stats():
        try:
            return jsonify(_build_stats())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/health")
    def api_health():
        return jsonify({
            "disk_free": health.disk_free_gb(),
            "cpu": health.cpu_pct(),
            "memory": health.mem_pct(),
            "disk_ok": health.disk_ok(),
        })

    @app.route("/api/analytics")
    def api_analytics():
        return jsonify({
            "total_uploads": analytics.total_uploads(),
            "platform_breakdown": analytics.platform_breakdown(),
            "weekly_totals": analytics.weekly_totals(),
            "top_videos": analytics.top_videos(10),
            "recent_uploads": analytics.recent_uploads(30),
            "daily_history": analytics.daily_totals(7),
        })

    @app.route("/api/upload-now", methods=["POST"])
    def upload_now():
        try:
            results = pipeline.run_once()
            return jsonify({
                "status": "ok",
                "jobs_processed": len(results),
                "succeeded": sum(1 for r in results if r.success),
                "clips_uploaded": sum(r.clips_made for r in results),
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/reset-job/<video_id>", methods=["POST"])
    def reset_job(video_id: str):
        try:
            job = pipeline.queue.get(video_id)
            if not job:
                return jsonify({"error": "Job not found"}), 404
            pipeline.queue.update(video_id, state=JobState.QUEUED, error=None, retries=0)
            return jsonify({"status": "ok"})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    if HAS_SOCKETIO:
        @sio.on("request_update")
        def handle_request_update():
            emit("stats_update", _build_stats())

    log.info("[Dashboard] Running on http://0.0.0.0:%d", port)
    try:
        if sio:
            sio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
        else:
            app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as exc:
        log.error("[Dashboard] Failed: %s", exc)
