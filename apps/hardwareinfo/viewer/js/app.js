/**
 * Aethvion Hardware Info — Frontend v1.0.0
 * WebSocket-driven live dashboard with Chart.js charts.
 */

// Constants
const HISTORY_LEN  = 60;   // seconds of rolling history
const WS_URL       = `ws://${location.host}/ws/live`;
const GAUGE_CIRC   = 2 * Math.PI * 52;  // SVG circle r=52

// State
const history = {
  cpu:       Array(HISTORY_LEN).fill(0),
  mem:       Array(HISTORY_LEN).fill(0),
  netUp:     Array(HISTORY_LEN).fill(0),
  netDown:   Array(HISTORY_LEN).fill(0),
  diskRead:  Array(HISTORY_LEN).fill(0),
  diskWrite: Array(HISTORY_LEN).fill(0),
};

let ws            = null;
let wsRetryTimer  = null;
let staticInfo    = null;
let charts        = {};

// DOM refs
const $ = id => document.getElementById(id);

// Utility
function push(arr, val) {
  arr.push(val);
  if (arr.length > HISTORY_LEN) arr.shift();
}

function formatUptime(secs) {
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600)  / 60);
  const s = Math.floor(secs % 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}

function formatSpeed(mb_s) {
  if (mb_s >= 1000) return { val: (mb_s / 1024).toFixed(2), unit: 'GB/s' };
  if (mb_s >= 1)    return { val: mb_s.toFixed(2),          unit: 'MB/s' };
  return { val: (mb_s * 1024).toFixed(1), unit: 'KB/s' };
}

function tempClass(c) {
  if (c === null || c === undefined) return '';
  if (c < 45) return 'temp-cool';
  if (c < 65) return 'temp-ok';
  if (c < 80) return 'temp-warn';
  return 'temp-hot';
}

function usageColor(pct) {
  if (pct < 60) return 'var(--hw-good)';
  if (pct < 80) return 'var(--hw-warn)';
  return 'var(--hw-crit)';
}

function setGauge(fillEl, pct) {
  const offset = GAUGE_CIRC * (1 - Math.min(pct, 100) / 100);
  fillEl.style.strokeDashoffset = offset;
  fillEl.style.stroke = usageColor(pct);
}

function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function timeLabels() {
  return Array.from({ length: HISTORY_LEN }, (_, i) => `${HISTORY_LEN - i}s`).reverse();
}

// Chart.js setup
Chart.defaults.color           = '#52525b';
Chart.defaults.font.family     = "'JetBrains Mono', monospace";
Chart.defaults.font.size       = 10;
Chart.defaults.animation       = { duration: 0 };

function makeLineChart(id, datasets, yMax = 100) {
  const ctx = $(id).getContext('2d');
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: timeLabels(),
      datasets: datasets.map(ds => ({
        data:            [...ds.data],
        borderColor:     ds.color,
        backgroundColor: ds.color.replace(')', ',0.10)').replace('rgb', 'rgba'),
        borderWidth:     1.5,
        fill:            true,
        tension:         0.35,
        pointRadius:     0,
        ...ds.extra,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { display: false },
        y: {
          min: 0,
          max: yMax,
          ticks: { maxTicksLimit: 4, callback: v => `${v}${yMax === 100 ? '%' : ''}` },
          grid: { color: '#27272a' },
        },
      },
      plugins: { legend: { display: datasets.length > 1, position: 'top', labels: { boxWidth: 10, padding: 8 } }, tooltip: { mode: 'index', intersect: false } },
    },
  });
}

function makeDoughnutChart(id) {
  const ctx = $(id).getContext('2d');
  return new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Used', 'Free'],
      datasets: [{ data: [0, 100], backgroundColor: ['#6366f1', '#27272a'], borderWidth: 0, hoverOffset: 2 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '72%',
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw.toFixed(1)}%` } } },
    },
  });
}

function initCharts() {
  charts.cpu = makeLineChart('chartCpu',
    [{ data: history.cpu, color: 'rgb(99,102,241)', extra: {} }], 100);

  charts.memLine = makeLineChart('chartMemLine',
    [{ data: history.mem, color: 'rgb(52,211,153)', extra: {} }], 100);

  charts.mem = makeDoughnutChart('chartMem');

  charts.net = makeLineChart('chartNet', [
    { data: history.netUp,   color: 'rgb(129,140,248)', extra: { label: '↑ Upload'   } },
    { data: history.netDown, color: 'rgb(52,211,153)',  extra: { label: '↓ Download' } },
  ], null);
  charts.net.options.scales.y.max = undefined;
  charts.net.update();

  charts.disk = makeLineChart('chartDisk', [
    { data: history.diskRead,  color: 'rgb(52,211,153)',  extra: { label: '↓ Read'  } },
    { data: history.diskWrite, color: 'rgb(251,146,60)',  extra: { label: '↑ Write' } },
  ], null);
  charts.disk.options.scales.y.max = undefined;
  charts.disk.update();
}

function updateChart(chart, ...histArrays) {
  chart.data.labels = timeLabels();
  histArrays.forEach((arr, i) => {
    chart.data.datasets[i].data = [...arr];
  });
  chart.update('none');
}

// Static info rendering
function renderStaticInfo(info) {
  staticInfo = info;

  // Top bar
  $('tbHostname').textContent = info.os.hostname || '–';
  $('tbOsInfo').textContent   = `${info.os.system} ${info.os.release}`;

  // CPU card header & static stats
  const cpu = info.cpu;
  $('cpuName').textContent = cpu.name;
  $('cpuCores').textContent = `${cpu.physical_cores} / ${cpu.logical_cores}`;
  if (cpu.max_freq_mhz) {
    const base = cpu.min_freq_mhz ? `${cpu.min_freq_mhz} / ` : '';
    $('cpuMaxFreq').textContent = `${base}${cpu.max_freq_mhz} MHz`;
  } else {
    $('cpuMaxFreq').textContent = '–';
  }

  // Memory total
  $('memTotal').textContent = `${info.memory.total_gb} GB`;

  // Disk list
  renderDisks(info.disks);

  // Network interfaces
  renderNetIfaces(info.nets);

  // GPU static
  if (info.gpus.length > 0) {
    const g = info.gpus[0];
    $('gpuName').textContent     = g.name;
    $('gpuVramTotal').textContent = g.mem_total_mb ? `${g.mem_total_mb} MB` : '–';
  } else {
    $('gpuName').textContent = 'Not detected';
    $('gpuTop').style.display  = 'none';
    $('gpuNoData').style.display = '';
  }

  // Build core grid based on logical core count
  buildCoreGrid(cpu.logical_cores);
}

function buildCoreGrid(coreCount) {
  const grid = $('coresGrid');
  grid.innerHTML = '';
  for (let i = 0; i < coreCount; i++) {
    const item = document.createElement('div');
    item.className = 'core-item';
    item.innerHTML = `
      <div class="core-label">C${i}</div>
      <div class="core-bar-outer"><div class="core-bar-fill" id="core${i}" style="width:0%"></div></div>
      <div class="core-val" id="coreV${i}">0%</div>`;
    grid.appendChild(item);
  }
}

function renderDisks(disks) {
  const list = $('diskList');
  list.innerHTML = '';
  for (const d of disks) {
    const color = usageColor(d.percent);
    const item = document.createElement('div');
    item.className = 'disk-item';
    item.innerHTML = `
      <div class="disk-top">
        <span class="disk-device">${escHtml(d.mountpoint)} <span style="font-weight:400;color:var(--text-dim)">(${escHtml(d.fstype)})</span></span>
        <span class="disk-usage">${d.used_gb} / ${d.total_gb} GB &nbsp;<strong>${d.percent}%</strong></span>
      </div>
      <div class="disk-bar-outer">
        <div class="disk-bar-fill" style="width:${d.percent}%;background:${color}"></div>
      </div>`;
    list.appendChild(item);
  }
}

function renderNetIfaces(nets) {
  const el = $('netIfaces');
  el.innerHTML = '';
  for (const n of nets) {
    const row = document.createElement('div');
    row.className = 'net-iface-row';
    row.innerHTML = `
      <span class="net-iface-name">${escHtml(n.name)}</span>
      ${n.ipv4 ? `<span class="net-iface-ip">${escHtml(n.ipv4)}</span>` : ''}
      ${n.speed_mbps ? `<span class="net-iface-spd">${n.speed_mbps} Mbps</span>` : ''}`;
    el.appendChild(row);
  }
  if (!el.children.length) el.innerHTML = '<span style="color:var(--text-dim);font-size:12px">No active interfaces found</span>';
}

// Live data rendering
function renderLive(d) {
  // Uptime
  $('tbUptime').textContent = formatUptime(d.uptime_secs);

  // CPU
  const cpu = d.cpu;
  push(history.cpu, cpu.total_pct);
  $('cpuPct').textContent  = `${cpu.total_pct}%`;
  setGauge($('cpuGaugeFill'), cpu.total_pct);

  $('cpuFreq').textContent = cpu.freq_mhz ? `${cpu.freq_mhz} MHz` : '–';

  if (cpu.temp_c !== null && cpu.temp_c !== undefined) {
    const tc = $('cpuTemp');
    tc.textContent = `${cpu.temp_c}°C`;
    tc.className   = `stat-val mono ${tempClass(cpu.temp_c)}`;
  } else {
    $('cpuTemp').textContent = '–';
  }

  // Per-core bars
  cpu.per_core.forEach((pct, i) => {
    const bar = $(`core${i}`);
    const val = $(`coreV${i}`);
    if (bar) {
      bar.style.width      = `${pct}%`;
      bar.style.background = usageColor(pct);
    }
    if (val) val.textContent = `${pct}%`;
  });

  updateChart(charts.cpu, history.cpu);

  // Memory
  const mem = d.memory;
  push(history.mem, mem.percent);

  $('memPct').textContent  = `${mem.percent}%`;
  $('memUsed').textContent  = `${mem.used_gb} GB`;
  $('memAvail').textContent = `${mem.available_gb} GB`;
  $('swapUsed').textContent = `${mem.swap_used_gb} GB (${mem.swap_pct}%)`;

  charts.mem.data.datasets[0].data = [mem.percent, 100 - mem.percent];
  charts.mem.update('none');
  updateChart(charts.memLine, history.mem);

  // GPU
  if (d.gpus.length > 0) {
    const g = d.gpus[0];
    $('gpuLoad').textContent     = `${g.load_pct}%`;
    setGauge($('gpuGaugeFill'), g.load_pct);

    if (g.temp_c !== null && g.temp_c !== undefined) {
      const gt = $('gpuTemp');
      gt.textContent = `${g.temp_c}°C`;
      gt.className   = `stat-val mono ${tempClass(g.temp_c)}`;
    } else {
      $('gpuTemp').textContent = '–';
    }

    $('gpuVramUsed').textContent = `${g.mem_used_mb} MB`;
    $('gpuVramPct').textContent  = `${g.mem_pct}%`;
    $('gpuVramBar').style.width  = `${g.mem_pct}%`;
    $('gpuVramBar').style.background = usageColor(g.mem_pct);
  }

  // Network
  const net = d.network;
  push(history.netUp,   net.up_mb_s);
  push(history.netDown, net.down_mb_s);

  const up   = formatSpeed(net.up_mb_s);
  const down = formatSpeed(net.down_mb_s);
  $('netUp').textContent      = up.val;
  $('netUpUnit').textContent  = up.unit;
  $('netDown').textContent    = down.val;
  $('netDownUnit').textContent = down.unit;

  const netMax = Math.max(...history.netUp, ...history.netDown, 0.1);
  charts.net.options.scales.y.max = Math.ceil(netMax * 1.2 * 10) / 10;
  updateChart(charts.net, history.netUp, history.netDown);

  // Disk I/O
  const dio = d.disk_io;
  push(history.diskRead,  dio.read_mb_s);
  push(history.diskWrite, dio.write_mb_s);

  $('diskRead').textContent  = `${dio.read_mb_s.toFixed(2)} MB/s`;
  $('diskWrite').textContent = `${dio.write_mb_s.toFixed(2)} MB/s`;

  const dMax = Math.max(...history.diskRead, ...history.diskWrite, 0.1);
  charts.disk.options.scales.y.max = Math.ceil(dMax * 1.2 * 10) / 10;
  updateChart(charts.disk, history.diskRead, history.diskWrite);

  // Battery
  const bat = d.battery;
  if (bat) {
    $('cardBattery').style.display = '';
    $('batBarFill').style.width     = `${bat.percent}%`;
    $('batBarFill').style.background = usageColor(100 - bat.percent); // invert: low% = bad
    $('batPct').textContent          = `${bat.percent}%`;
    $('batStatus').textContent       = bat.plugged ? 'Charging / Plugged in' : 'On battery';
    if (bat.secs_left) {
      $('batTime').textContent = formatUptime(bat.secs_left);
    } else {
      $('batTime').textContent = bat.plugged ? '–' : 'Calculating…';
    }
    // Dynamic icon
    const icon = $('batIcon');
    const pct  = bat.percent;
    icon.className = `fa-solid ${pct > 87 ? 'fa-battery-full' : pct > 62 ? 'fa-battery-three-quarters' : pct > 37 ? 'fa-battery-half' : pct > 12 ? 'fa-battery-quarter' : 'fa-battery-empty'} card-icon`;
    if (bat.plugged) icon.style.color = 'var(--hw-good)';
    else             icon.style.color = pct < 20 ? 'var(--hw-crit)' : 'var(--hw-warn)';
  }

  // Processes
  renderProcesses(d.processes);
}

function renderProcesses(procs) {
  const tbody = $('procsTbody');
  if (!procs.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="no-data-msg">No data</td></tr>';
    return;
  }
  tbody.innerHTML = procs.map(p => {
    const cpuClass = p.cpu_pct > 50 ? 'proc-cpu-crit' : p.cpu_pct > 20 ? 'proc-cpu-high' : '';
    return `<tr>
      <td>${escHtml(p.name)}</td>
      <td>${p.pid}</td>
      <td class="${cpuClass}">${p.cpu_pct}%</td>
      <td>${p.mem_pct}%</td>
    </tr>`;
  }).join('');
}

// WebSocket
function setWsStatus(state) {
  const dot   = document.querySelector('.ws-dot');
  const label = $('wsLabel');
  dot.className   = `ws-dot ${state}`;
  label.textContent = state === 'connected' ? 'Live' : state === 'connecting' ? 'Connecting…' : 'Disconnected';
}

function connectWS() {
  clearTimeout(wsRetryTimer);
  setWsStatus('connecting');

  ws = new WebSocket(WS_URL);

  ws.addEventListener('open', () => {
    setWsStatus('connected');
  });

  ws.addEventListener('message', e => {
    try {
      const data = JSON.parse(e.data);
      renderLive(data);
    } catch { /* ignore malformed frame */ }
  });

  ws.addEventListener('close', () => {
    setWsStatus('disconnected');
    wsRetryTimer = setTimeout(connectWS, 2500);
  });

  ws.addEventListener('error', () => {
    ws.close();
  });
}

// Init
(async () => {
  initCharts();

  // Load static system info
  try {
    const res = await fetch('/api/info');
    if (res.ok) renderStaticInfo(await res.json());
  } catch (e) {
    console.warn('Could not load static info:', e);
  }

  // Start live WebSocket
  connectWS();
})();
