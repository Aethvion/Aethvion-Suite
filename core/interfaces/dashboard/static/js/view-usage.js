
let _providerChart    = null;
let _timelineChart    = null;
let _costByModelChart = null;
let _tokensByModelChart = null;
let _dailyChart       = null;
let _sparklineChart   = null;

// Cached for re-render (search filter, timeline mode switch)
let _currentHistoryEntries = [];
let _currentHourlyData     = null;

const PROVIDER_COLORS = {
    google_ai:  '#4285F4',
    anthropic:  '#d97706',
    openai:     '#10A37F',
    grok:       '#FF6600',
    local:      '#FFAA00',
};
function providerColor(p) { return PROVIDER_COLORS[p] || '#888888'; }

// ── Main loader ────────────────────────────────────────────────────────────

async function loadUsageDashboard(startDate = null, endDate = null) {
    try {
        const timeRange  = typeof prefs !== 'undefined' ? prefs.get('usage.time_range', '1w') : '1w';
        const showLocal  = document.getElementById('usage-toggle-local')?.checked ?? true;
        const showApi    = document.getElementById('usage-toggle-api')?.checked ?? true;

        let start = startDate, end = endDate;
        if (!start && !end) {
            const now = new Date();
            const ago = ms => new Date(now - ms).toISOString();
            if      (timeRange === '1d')    start = ago(1  * 24*3600*1000);
            else if (timeRange === '1w')    start = ago(7  * 24*3600*1000);
            else if (timeRange === '1m')    start = ago(30 * 24*3600*1000);
            else if (timeRange === '3m')    start = ago(90 * 24*3600*1000);
            else if (timeRange === 'total') start = '2020-01-01';
        }

        document.querySelectorAll('.date-preset-btn').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.preset === timeRange && !startDate)
        );

        const filterQ  = `&local=${showLocal}&api=${showApi}`;
        const rangeQ   = _buildRangeQuery(start, end, filterQ);
        const tlHours  = timeRange === '1d' ? 24 : timeRange === '1m' ? 720 : timeRange === '3m' ? 2160 : 168;
        const timelineQ = (start || end) ? rangeQ : `?hours=${tlHours}${filterQ}`;
        const dailyDays = timeRange === '3m' ? 90 : timeRange === '1m' ? 30 : timeRange === 'total' ? 365 : 14;

        // Previous-period bounds for delta
        let prevRangeQ = null;
        if (start) {
            const s = new Date(start).getTime();
            const e2 = end ? new Date(end).getTime() : Date.now();
            const dur = e2 - s;
            prevRangeQ = _buildRangeQuery(new Date(s - dur).toISOString(), new Date(s).toISOString(), filterQ);
        }

        const requests = [
            fetch(`/api/usage/summary${rangeQ}`),
            fetch(`/api/usage/history?limit=100${rangeQ ? '&' + rangeQ.slice(1) : ''}`),
            fetch(`/api/usage/hourly${timelineQ}`),
            fetch(`/api/usage/cost-by-model${rangeQ}`),
            fetch(`/api/usage/tokens-by-model${rangeQ}`),
            fetch(`/api/usage/daily?days=${dailyDays}${filterQ}`),
        ];
        if (prevRangeQ) requests.push(fetch(`/api/usage/summary${prevRangeQ}`));

        const responses  = await Promise.all(requests);
        const [summary, history, hourly, costModel, tokensModel, daily] =
            await Promise.all(responses.slice(0, 6).map(r => r.json()));
        const prevSummary = prevRangeQ ? await responses[6].json() : null;

        _currentHourlyData     = hourly;
        _currentHistoryEntries = history.entries || [];

        _updateHero(summary, prevSummary);
        _updateStatCards(summary);
        _renderInsights(summary, daily);
        _renderTimeline(hourly, 'tokens');
        _renderProviderChart(summary);
        _renderDailyChart(daily);
        _renderHeatmap(daily);
        _renderCostByModel(costModel);
        _renderTokensByModel(tokensModel);
        _renderModelTable(summary);
        _renderRecentTable(_currentHistoryEntries);

        if (!window._usageListenersReady) { _setupListeners(); window._usageListenersReady = true; }

    } catch (err) {
        console.error('[Usage] Load error:', err);
    }
}

function _buildRangeQuery(start, end, filterQ) {
    if (!start && !end) return `?${filterQ.slice(1)}`;
    let q = '?';
    if (start) q += `start=${encodeURIComponent(start)}`;
    if (end)   q += `${start ? '&' : ''}end=${encodeURIComponent(end)}`;
    return q + filterQ;
}

// ── Listeners ─────────────────────────────────────────────────────────────

function _setupListeners() {
    document.querySelectorAll('.date-preset-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (typeof savePreference === 'function') await savePreference('usage.time_range', btn.dataset.preset);
            document.getElementById('usage-start-date').value = '';
            document.getElementById('usage-end-date').value   = '';
            loadUsageDashboard();
        });
    });

    document.getElementById('usage-apply-btn')?.addEventListener('click', () => {
        const s = document.getElementById('usage-start-date').value;
        const e = document.getElementById('usage-end-date').value;
        if (s || e) loadUsageDashboard(s, e);
    });

    document.getElementById('usage-toggle-local')?.addEventListener('change', () => loadUsageDashboard());
    document.getElementById('usage-toggle-api')?.addEventListener('change',   () => loadUsageDashboard());
    document.getElementById('usage-refresh-btn')?.addEventListener('click',   () => loadUsageDashboard());
    document.getElementById('usage-export-btn')?.addEventListener('click',    () => _exportCSV());

    document.getElementById('usage-calls-search')?.addEventListener('input', e =>
        _renderRecentTable(_currentHistoryEntries, e.target.value)
    );

    document.getElementById('usage-timeline-seg')?.querySelectorAll('.seg-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#usage-timeline-seg .seg-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            _renderTimeline(_currentHourlyData, btn.dataset.mode);
        });
    });
}

// ── Formatters ────────────────────────────────────────────────────────────

function formatNumber(n) {
    if (n == null) return '0';
    if (n >= 1e9)  return (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6)  return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3)  return (n / 1e3).toFixed(1) + 'K';
    return n.toString();
}

function formatCost(v) {
    if (v == null || v === 0) return '$0.00';
    if (v >= 100)  return '$' + v.toFixed(0);
    if (v >= 1)    return '$' + v.toFixed(2);
    if (v >= 0.01) return '$' + v.toFixed(4);
    return '$' + v.toFixed(6);
}

function _deltaHTML(current, prev) {
    if (!prev || prev === 0) return '';
    const pct = ((current - prev) / prev) * 100;
    const cls  = pct >= 0 ? 'delta-up' : 'delta-down';
    const icon = pct >= 0 ? '↑' : '↓';
    return `<span class="${cls}">${icon} ${pct >= 0 ? '+' : ''}${pct.toFixed(1)}% vs prev period</span>`;
}

// ── Hero banner ───────────────────────────────────────────────────────────

function _updateHero(summary, prevSummary) {
    const cost  = summary.total_cost  || 0;
    const calls = summary.total_calls || 0;
    const avg   = calls > 0 ? cost / calls : 0;

    _setText('usage-hero-cost',   formatCost(cost));
    _setText('usage-hero-calls',  formatNumber(calls));
    _setText('usage-hero-tokens', formatNumber(summary.total_tokens || 0));
    _setText('usage-hero-avg',    formatCost(avg));

    const deltaEl = document.getElementById('usage-hero-delta');
    if (deltaEl) deltaEl.innerHTML = prevSummary ? _deltaHTML(cost, prevSummary.total_cost) : '';
}

// ── Stat cards ────────────────────────────────────────────────────────────

function _updateStatCards(summary) {
    const calls  = summary.total_calls  || 0;
    const tokens = summary.total_tokens || 0;
    const avg    = calls > 0 ? (summary.total_cost || 0) / calls : 0;

    // Top model
    const byModel = summary.by_model || {};
    let topModel = '—', topCalls = 0;
    for (const [name, d] of Object.entries(byModel)) {
        if (d.calls > topCalls) { topModel = name; topCalls = d.calls; }
    }
    const shortModel = topModel.length > 22 ? topModel.split('-').slice(-2).join('-') : topModel;

    _setText('usage-total-calls',    formatNumber(calls));
    _setText('usage-total-tokens',   formatNumber(tokens));
    _setText('usage-avg-cost',       formatCost(avg));
    _setText('usage-top-model',      shortModel);
    _setText('usage-success-rate',   summary.success_rate != null ? summary.success_rate + '%' : '—');

    // Sub labels
    const byProvider = summary.by_provider || {};
    const apiCalls   = Object.entries(byProvider).filter(([k]) => k !== 'local').reduce((s, [, v]) => s + v.calls, 0);
    _setText('usage-calls-sub',      calls ? `${apiCalls} API · ${calls - apiCalls} local` : '');

    const inTok  = Object.values(byModel).reduce((s, m) => s + (m.prompt_tokens     || 0), 0);
    const outTok = Object.values(byModel).reduce((s, m) => s + (m.completion_tokens || 0), 0);
    _setText('usage-tokens-sub',     `↑ ${formatNumber(inTok)} in · ↓ ${formatNumber(outTok)} out`);
    _setText('usage-avg-sub',        summary.total_cost > 0 ? formatCost(summary.total_cost) + ' total' : '');
    _setText('usage-top-model-sub',  topCalls ? `${topCalls} calls (${Math.round(topCalls / Math.max(calls, 1) * 100)}%)` : '');
    _setText('usage-success-sub',    summary.success_rate != null ? `${Math.round((summary.success_rate / 100) * calls)} / ${calls}` : '');
}

// ── Insights ──────────────────────────────────────────────────────────────

function _renderInsights(summary, dailyData) {
    const container = document.getElementById('usage-insights-row');
    if (!container) return;

    const byModel    = summary.by_model    || {};
    const totalCalls = summary.total_calls || 0;
    const insights   = [];

    // Top model
    let topModel = null, topData = null;
    for (const [name, d] of Object.entries(byModel)) {
        if (!topModel || d.calls > topData.calls) { topModel = name; topData = d; }
    }
    if (topModel) {
        const pct = Math.round(topData.calls / Math.max(totalCalls, 1) * 100);
        insights.push({ icon: 'fa-brain', text: `<b>${topModel}</b> is your most-used model — <b>${pct}%</b> of all calls` });
    }

    // Peak day
    const days = dailyData?.days || [];
    if (days.length) {
        const peak = days.reduce((mx, d) => d.cost > mx.cost ? d : mx, { cost: 0, date: '' });
        if (peak.cost > 0) {
            const label = new Date(peak.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            insights.push({ icon: 'fa-calendar-day', text: `Peak day was <b>${label}</b> at <b>${formatCost(peak.cost)}</b>` });
        }
    }

    // Avg cost per call
    if (totalCalls > 0) {
        const avg = (summary.total_cost || 0) / totalCalls;
        insights.push({ icon: 'fa-tachometer-alt', text: `Average <b>${formatCost(avg)}</b> per API call across <b>${formatNumber(totalCalls)}</b> calls` });
    }

    // Token split
    const inTok  = Object.values(byModel).reduce((s, m) => s + (m.prompt_tokens     || 0), 0);
    const outTok = Object.values(byModel).reduce((s, m) => s + (m.completion_tokens || 0), 0);
    const total  = inTok + outTok;
    if (total > 0) {
        const outPct = Math.round(outTok / total * 100);
        insights.push({ icon: 'fa-exchange-alt', text: `Token split: <b>${100 - outPct}%</b> input · <b>${outPct}%</b> output` });
    }

    container.innerHTML = insights.map(i =>
        `<div class="usage-insight-pill"><i class="fas ${i.icon}"></i><span>${i.text}</span></div>`
    ).join('');
}

// ── Charts ────────────────────────────────────────────────────────────────

function _renderProviderChart(summary) {
    const ctx = document.getElementById('chart-provider-calls');
    if (!ctx || typeof Chart === 'undefined') return;
    if (_providerChart) _providerChart.destroy();

    const providers = summary.by_provider || {};
    const labels    = Object.keys(providers);
    const data      = labels.map(k => providers[k].calls);
    const colors    = labels.map(l => providerColor(l));
    const costs     = labels.map(k => providers[k].cost || 0);

    _providerChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: 'rgba(0,0,0,0.35)', borderWidth: 2, hoverOffset: 8 }] },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '65%',
            plugins: {
                legend: { position: 'bottom', labels: { color: '#a0a0a0', font: { size: 11 }, padding: 10 } },
                tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw} calls · ${formatCost(costs[c.dataIndex])}` } }
            }
        }
    });
}

function _renderTimeline(hourlyData, mode = 'tokens') {
    const ctx = document.getElementById('chart-tokens-timeline');
    if (!ctx || typeof Chart === 'undefined') return;
    if (_timelineChart) _timelineChart.destroy();

    const hours = hourlyData?.hours || [];
    const labels = hours.map(h => {
        const d = new Date(h.hour + ':00:00Z');
        return isNaN(d) ? h.hour : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', hour12: false });
    });

    const modes = {
        tokens: { key: 'tokens', label: 'Tokens',  color: '#00d9ff', bg: 'rgba(0,217,255,0.08)',   fmt: formatNumber },
        cost:   { key: 'cost',   label: 'Cost',     color: '#a78bfa', bg: 'rgba(167,139,250,0.08)', fmt: v => formatCost(v) },
        calls:  { key: 'calls',  label: 'Calls',    color: '#ff6eb4', bg: 'rgba(255,110,180,0.08)', fmt: v => v.toString() },
    };
    const cfg  = modes[mode] || modes.tokens;
    const data = hours.map(h => h[cfg.key] || 0);

    _timelineChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [{
            label: cfg.label, data,
            borderColor: cfg.color, backgroundColor: cfg.bg,
            fill: true, tension: 0.4, borderWidth: 2,
            pointRadius: hours.length < 60 ? 3 : 0, pointBackgroundColor: cfg.color,
        }]},
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { ticks: { color: '#555', maxRotation: 0, autoSkip: true, maxTicksLimit: 10 }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { ticks: { color: '#777', callback: cfg.fmt }, grid: { color: 'rgba(255,255,255,0.04)' } }
            },
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: c => ` ${cfg.label}: ${cfg.fmt(c.raw)}` } }
            }
        }
    });
}

function _renderDailyChart(dailyData) {
    const ctx = document.getElementById('chart-daily-spend');
    if (!ctx || typeof Chart === 'undefined') return;
    if (_dailyChart) _dailyChart.destroy();

    const days   = dailyData?.days || [];
    const labels = days.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
    const costs  = days.map(d => d.cost);
    const maxC   = Math.max(...costs, 0.000001);

    _dailyChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ label: 'Daily Cost', data: costs,
            backgroundColor: costs.map(c => {
                const t = Math.min(c / maxC, 1);
                return `rgba(${Math.round(100 + 155 * t)},${Math.round(139 - 100 * t)},${Math.round(250 - 100 * t)},0.75)`;
            }),
            borderColor: 'transparent', borderRadius: 4, borderSkipped: false,
        }]},
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${formatCost(c.raw)}` } } },
            scales: {
                x: { ticks: { color: '#555', maxRotation: 0, autoSkip: true, maxTicksLimit: 20, font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: '#777', callback: v => formatCost(v) }, grid: { color: 'rgba(255,255,255,0.04)' } }
            }
        }
    });

    // Hero sparkline (last 14 days)
    _renderSparkline(days.slice(-14));
}

function _renderSparkline(days) {
    const ctx = document.getElementById('chart-hero-sparkline');
    if (!ctx || typeof Chart === 'undefined') return;
    if (_sparklineChart) _sparklineChart.destroy();

    _sparklineChart = new Chart(ctx, {
        type: 'line',
        data: { labels: days.map(d => d.date), datasets: [{ data: days.map(d => d.cost),
            borderColor: 'rgba(255,255,255,0.35)', backgroundColor: 'rgba(255,255,255,0.04)',
            fill: true, tension: 0.4, pointRadius: 0, borderWidth: 1.5,
        }]},
        options: {
            responsive: false, animation: { duration: 0 },
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { display: false }, y: { display: false } }
        }
    });
}

function _renderHeatmap(dailyData) {
    const container = document.getElementById('usage-heatmap');
    if (!container) return;

    const days      = dailyData?.days || [];
    const costByDate = {};
    days.forEach(d => { costByDate[d.date] = d.cost; });
    const maxCost = Math.max(...Object.values(costByDate), 0.000001);

    // Build 364-day grid (52 weeks × 7 days), oldest first
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const cells = [];
    for (let i = 363; i >= 0; i--) {
        const d   = new Date(today);
        d.setDate(d.getDate() - i);
        const key  = d.toISOString().slice(0, 10);
        const cost = costByDate[key] || 0;
        const lvl  = cost > 0 ? Math.min(4, Math.ceil((cost / maxCost) * 4)) : 0;
        cells.push({ date: key, cost, lvl });
    }

    // Group into 52 columns (weeks)
    const weeks = [];
    for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));

    // Month labels above grid
    let lastMonth = -1;
    const monthSpans = weeks.map((week, wi) => {
        const m = week[0] ? new Date(week[0].date).getMonth() : -1;
        if (m !== lastMonth && week[0]) {
            lastMonth = m;
            return `<span class="hm-month" style="grid-column:${wi + 1}">${new Date(week[0].date).toLocaleString('en-US', { month: 'short' })}</span>`;
        }
        return '';
    }).join('');

    const weeksHTML = weeks.map(week =>
        `<div class="hm-week">${week.map(c =>
            `<div class="hm-cell lv${c.lvl}" title="${c.date}${c.cost > 0 ? ' · ' + formatCost(c.cost) : ''}"></div>`
        ).join('')}</div>`
    ).join('');

    container.innerHTML =
        `<div class="hm-months">${monthSpans}</div>` +
        `<div class="hm-weeks">${weeksHTML}</div>`;
}

function _renderCostByModel(costData) {
    const ctx = document.getElementById('chart-cost-by-model');
    if (!ctx || typeof Chart === 'undefined') return;
    if (_costByModelChart) _costByModelChart.destroy();

    const models = (costData.models || []).slice(0, 8);
    if (!models.length) return;

    _costByModelChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: models.map(m => m.name), datasets: [
            { label: 'Input',  data: models.map(m => m.input_cost),  backgroundColor: 'rgba(0,217,255,0.7)',   borderColor: '#00d9ff', borderWidth: 1 },
            { label: 'Output', data: models.map(m => m.output_cost), backgroundColor: 'rgba(167,139,250,0.7)', borderColor: '#a78bfa', borderWidth: 1 },
        ]},
        options: {
            responsive: true, maintainAspectRatio: false, indexAxis: 'y',
            plugins: {
                legend: { labels: { color: '#a0a0a0', font: { size: 11 } } },
                tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${formatCost(c.raw)}` } }
            },
            scales: {
                x: { ticks: { color: '#777', callback: v => formatCost(v) }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { ticks: { color: '#a0a0a0', font: { family: "'Fira Code',monospace", size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } }
            }
        }
    });
}

function _renderTokensByModel(tokensData) {
    const ctx = document.getElementById('chart-tokens-by-model');
    if (!ctx || typeof Chart === 'undefined') return;
    if (_tokensByModelChart) _tokensByModelChart.destroy();

    const models = (tokensData.models || []).slice(0, 8);
    if (!models.length) return;

    _tokensByModelChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: models.map(m => m.name), datasets: [
            { label: 'Input',  data: models.map(m => m.prompt_tokens),     backgroundColor: 'rgba(0,217,255,0.7)',  borderColor: '#00d9ff', borderWidth: 1 },
            { label: 'Output', data: models.map(m => m.completion_tokens), backgroundColor: 'rgba(255,200,0,0.7)', borderColor: '#ffc800', borderWidth: 1 },
        ]},
        options: {
            responsive: true, maintainAspectRatio: false, indexAxis: 'y',
            plugins: {
                legend: { labels: { color: '#a0a0a0', font: { size: 11 } } },
                tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${formatNumber(c.raw)}` } }
            },
            scales: {
                x: { ticks: { color: '#777', callback: v => formatNumber(v) }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { ticks: { color: '#a0a0a0', font: { family: "'Fira Code',monospace", size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } }
            }
        }
    });
}

// ── Tables ────────────────────────────────────────────────────────────────

function _renderModelTable(summary) {
    const tbody = document.getElementById('usage-model-tbody');
    if (!tbody) return;

    const arr = Object.entries(summary.by_model || {})
        .map(([model, d]) => ({ model, ...d }))
        .sort((a, b) => b.cost - a.cost);

    if (!arr.length) {
        tbody.innerHTML = `<tr><td colspan="9" style="padding:0;border:none;"><div class="ae-empty"><div class="ae-empty-icon"><i class="fas fa-chart-bar"></i></div><div class="ae-empty-title">No usage recorded yet</div><div class="ae-empty-desc">Usage data appears here after your first API call.</div></div></td></tr>`;
        return;
    }

    tbody.innerHTML = arr.map(m => {
        const avgCost = m.calls > 0 ? m.cost / m.calls : 0;
        return `<tr>
            <td class="mono-sm text-muted">${m.model}</td>
            <td>${formatNumber(m.calls || 0)}</td>
            <td>${formatNumber(m.prompt_tokens     || 0)}</td>
            <td>${formatNumber(m.completion_tokens || 0)}</td>
            <td>${formatNumber(m.tokens            || 0)}</td>
            <td class="cost-cell">${formatCost(m.input_cost  || 0)}</td>
            <td class="cost-cell">${formatCost(m.output_cost || 0)}</td>
            <td class="cost-cell fw-600">${formatCost(m.cost || 0)}</td>
            <td class="mono-sm text-muted">${formatCost(avgCost)}</td>
        </tr>`;
    }).join('');
}

function _renderRecentTable(entries, filter = '') {
    const tbody = document.getElementById('usage-recent-tbody');
    if (!tbody) return;

    let rows = entries;
    if (filter) {
        const q = filter.toLowerCase();
        rows = entries.filter(e =>
            (e.model    || '').toLowerCase().includes(q) ||
            (e.source   || '').toLowerCase().includes(q) ||
            (e.provider || '').toLowerCase().includes(q)
        );
    }

    if (!rows.length) {
        tbody.innerHTML = filter
            ? `<tr><td colspan="7" style="padding:0;border:none;"><div class="ae-empty" style="min-height:100px;padding:1.5rem;"><div class="ae-empty-icon" style="width:36px;height:36px;font-size:0.9rem;"><i class="fas fa-search"></i></div><div class="ae-empty-title" style="font-size:0.85rem;">No matches for "${filter}"</div></div></td></tr>`
            : `<tr><td colspan="7" style="padding:0;border:none;"><div class="ae-empty"><div class="ae-empty-icon"><i class="fas fa-history"></i></div><div class="ae-empty-title">No API calls recorded yet</div><div class="ae-empty-desc">Recent calls will appear here after your first interaction.</div></div></td></tr>`;
        return;
    }

    tbody.innerHTML = rows.slice(0, 100).map(e => {
        const dt      = new Date(e.timestamp);
        const time    = dt.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
        const prov    = e.provider || 'unknown';
        const src     = e.source   || 'chat';
        const total   = (e.input_cost || 0) + (e.output_cost || 0);
        const approx  = e.tokens_estimated ? '<span class="approx" title="Estimated">~</span>' : '';
        return `<tr>
            <td class="mono-sm">${time}</td>
            <td><span class="source-badge ${src}">${src}</span></td>
            <td><span class="provider-badge ${prov}">${prov}</span></td>
            <td class="mono-sm text-muted model-cell" title="${e.model || ''}">${e.model || '?'}</td>
            <td>${formatNumber(e.prompt_tokens     || 0)}${approx}</td>
            <td>${formatNumber(e.completion_tokens || 0)}${approx}</td>
            <td class="cost-cell fw-500">${formatCost(total)}</td>
        </tr>`;
    }).join('');
}

// ── Export ────────────────────────────────────────────────────────────────

function _exportCSV() {
    if (!_currentHistoryEntries.length) return;
    const headers = ['timestamp','source','provider','model','prompt_tokens','completion_tokens','total_tokens','input_cost','output_cost','total_cost'];
    const rows = _currentHistoryEntries.map(e =>
        headers.map(h => {
            if (h === 'total_cost') return ((e.input_cost || 0) + (e.output_cost || 0)).toFixed(6);
            const v = e[h] ?? '';
            return (typeof v === 'string' && v.includes(',')) ? `"${v}"` : v;
        }).join(',')
    );
    const blob = new Blob([[headers.join(','), ...rows].join('\n')], { type: 'text/csv' });
    const a    = document.createElement('a');
    a.href     = URL.createObjectURL(blob);
    a.download = `aethvion-usage-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
}

// ── Util ──────────────────────────────────────────────────────────────────

function _setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
