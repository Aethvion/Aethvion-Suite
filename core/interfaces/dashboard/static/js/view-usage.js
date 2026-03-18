// Misaka Cipher - Usage Dashboard View
// Handles interacting with the Usage statistics and charts

let _providerChart = null;
let _timelineChart = null;
let _costByModelChart = null;
let _tokensByModelChart = null;

async function loadUsageDashboard(startDate = null, endDate = null) {
    try {
        const timeRange = typeof prefs !== 'undefined' ? prefs.get('usage.time_range', '1w') : '1w';
        const showLocal = document.getElementById('usage-toggle-local') ? document.getElementById('usage-toggle-local').checked : true;
        const showApi   = document.getElementById('usage-toggle-api') ? document.getElementById('usage-toggle-api').checked : true;

        let start = startDate;
        let end = endDate;

        if (!start && !end) {
            // Apply presets if no custom dates
            const now = new Date();
            if (timeRange === '1d') {
                start = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
            } else if (timeRange === '1w') {
                start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
            } else if (timeRange === '1m') {
                start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString();
            } else if (timeRange === 'total') {
                start = '2020-01-01'; // Far past
            }
        }

        const filterQuery = `&local=${showLocal}&api=${showApi}`;
        const queryBase = (start || end) 
            ? `?${start ? `start=${start}` : ''}${end ? `${start ? '&' : ''}end=${end}` : ''}${filterQuery}` 
            : `?${filterQuery.slice(1)}`;
        const timelineQuery = (start || end) ? queryBase : `?hours=${timeRange === '1d' ? 24 : 168}${filterQuery}`;

        document.querySelectorAll('.date-preset-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.preset === timeRange && !startDate);
        });

        const [summaryRes, historyRes, hourlyRes, costModelRes, tokensModelRes] = await Promise.all([
            fetch(`/api/usage/summary${queryBase}`),
            fetch(`/api/usage/history?limit=50${queryBase ? `&${queryBase.slice(1)}` : ''}`),
            fetch(`/api/usage/hourly${timelineQuery}`),
            fetch(`/api/usage/cost-by-model${queryBase}`),
            fetch(`/api/usage/tokens-by-model${queryBase}`)
        ]);

        const summary = await summaryRes.json();
        const history = await historyRes.json();
        const hourly = await hourlyRes.json();
        const costModel = await costModelRes.json();
        const tokensModel = await tokensModelRes.json();

        updateUsageStatCards(summary);
        renderProviderChart(summary);
        renderTimelineChart(hourly);
        renderCostByModelChart(costModel);
        renderTokensByModelChart(tokensModel);
        renderModelUsageTable(summary);
        renderRecentCallsTable(history.entries || []);

        if (!window.usageListenersSetup) {
            setupUsageListeners();
            window.usageListenersSetup = true;
        }

    } catch (error) {
        console.error('Error loading usage dashboard:', error);
    }
}

function setupUsageListeners() {
    document.querySelectorAll('.date-preset-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const preset = e.target.dataset.preset;
            if (typeof savePreference === 'function') {
                await savePreference('usage.time_range', preset);
            }
            // Clear custom inputs when preset is clicked
            document.getElementById('usage-start-date').value = '';
            document.getElementById('usage-end-date').value = '';
            loadUsageDashboard();
        });
    });

    const applyBtn = document.getElementById('usage-apply-btn');
    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            const start = document.getElementById('usage-start-date').value;
            const end = document.getElementById('usage-end-date').value;
            if (start || end) {
                loadUsageDashboard(start, end);
            }
        });
    }

    const localToggle = document.getElementById('usage-toggle-local');
    if (localToggle) {
        localToggle.addEventListener('change', () => loadUsageDashboard());
    }
    const apiToggle = document.getElementById('usage-toggle-api');
    if (apiToggle) {
        apiToggle.addEventListener('change', () => loadUsageDashboard());
    }
}

function formatNumber(n) {
    if (n === undefined || n === null) return '0';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

function formatCost(v) {
    if (v === undefined || v === null) return '$0.00';
    if (v >= 1) return '$' + v.toFixed(2);
    if (v >= 0.01) return '$' + v.toFixed(4);
    if (v === 0) return '$0.00';
    return '$' + v.toFixed(6);
}

function updateUsageStatCards(summary) {
    const totalCalls = document.getElementById('usage-total-calls');
    if (totalCalls) totalCalls.textContent = formatNumber(summary.total_calls || 0);

    const totalTokens = document.getElementById('usage-total-tokens');
    if (totalTokens) totalTokens.textContent = formatNumber(summary.total_tokens || 0);

    const inputCost = document.getElementById('usage-input-cost');
    if (inputCost) inputCost.textContent = formatCost(summary.total_input_cost || 0);

    const outputCost = document.getElementById('usage-output-cost');
    if (outputCost) outputCost.textContent = formatCost(summary.total_output_cost || 0);

    const totalCost = document.getElementById('usage-total-cost');
    if (totalCost) totalCost.textContent = formatCost(summary.total_cost || 0);
}

function renderProviderChart(summary) {
    const ctx = document.getElementById('chart-provider-calls');
    if (!ctx || typeof Chart === 'undefined') return;

    if (_providerChart) _providerChart.destroy();

    const providers = summary.by_provider || {};
    const labels = Object.keys(providers);
    const data = labels.map(k => providers[k].calls);

    const colorMap = {
        'google_ai': '#4285F4',
        'openai': '#10A37F',
        'grok': '#FF6600',
        'local': '#FFAA00'
    };
    const colors = labels.map(l => colorMap[l] || '#888888');

    _providerChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors,
                borderColor: '#0a0e1a',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#a0a0a0', font: { size: 12 } }
                }
            }
        }
    });
}

function renderTimelineChart(hourlyData) {
    const ctx = document.getElementById('chart-tokens-timeline');
    if (!ctx || typeof Chart === 'undefined') return;

    if (_timelineChart) _timelineChart.destroy();

    const hours = hourlyData.hours || [];
    const labels = hours.map(h => {
        const parts = h.hour.split('T');
        return parts[1] ? parts[1] + ':00' : h.hour;
    });
    const tokenData = hours.map(h => h.tokens);
    const callData = hours.map(h => h.calls);

    _timelineChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Tokens',
                    data: tokenData,
                    borderColor: '#00d9ff',
                    backgroundColor: 'rgba(0, 217, 255, 0.1)',
                    fill: true,
                    tension: 0.3,
                    yAxisID: 'y'
                },
                {
                    label: 'Calls',
                    data: callData,
                    borderColor: '#ff00aa',
                    backgroundColor: 'transparent',
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.3,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { type: 'linear', display: true, position: 'left', ticks: { color: '#00d9ff' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y1: { type: 'linear', display: true, position: 'right', ticks: { color: '#ff00aa' }, grid: { drawOnChartArea: false } }
            },
            plugins: { legend: { labels: { color: '#a0a0a0' } } }
        }
    });
}

function renderCostByModelChart(costData) {
    const ctx = document.getElementById('chart-cost-by-model');
    if (!ctx || typeof Chart === 'undefined') return;

    if (_costByModelChart) _costByModelChart.destroy();

    const models = costData.models || [];
    if (!models.length) return;

    const labels = models.map(m => m.name);
    const inputCosts = models.map(m => m.input_cost);
    const outputCosts = models.map(m => m.output_cost);

    _costByModelChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Input Cost',
                    data: inputCosts,
                    backgroundColor: 'rgba(0, 217, 255, 0.7)',
                    borderColor: '#00d9ff',
                    borderWidth: 1
                },
                {
                    label: 'Output Cost',
                    data: outputCosts,
                    backgroundColor: 'rgba(255, 0, 255, 0.7)',
                    borderColor: '#ff00ff',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: {
                    labels: { color: '#a0a0a0', font: { size: 12 } }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return context.dataset.label + ': $' + context.raw.toFixed(6);
                        }
                    }
                }
            },
            scales: {
                x: {
                    stacked: false,
                    title: { display: true, text: 'Cost ($)', color: '#a0a0a0' },
                    ticks: { color: '#a0a0a0' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: {
                    ticks: { color: '#a0a0a0', font: { family: "'Fira Code', monospace", size: 11 } },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
}

function renderTokensByModelChart(tokensData) {
    const ctx = document.getElementById('chart-tokens-by-model');
    if (!ctx || typeof Chart === 'undefined') return;

    if (_tokensByModelChart) _tokensByModelChart.destroy();

    const models = tokensData.models || [];
    if (!models.length) return;

    const labels = models.map(m => m.name);
    const inputTokens = models.map(m => m.prompt_tokens);
    const outputTokens = models.map(m => m.completion_tokens);

    _tokensByModelChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Input Tokens',
                    data: inputTokens,
                    backgroundColor: 'rgba(0, 217, 255, 0.7)',
                    borderColor: '#00d9ff',
                    borderWidth: 1
                },
                {
                    label: 'Output Tokens',
                    data: outputTokens,
                    backgroundColor: 'rgba(255, 200, 0, 0.7)',
                    borderColor: '#ffc800',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: {
                    labels: { color: '#a0a0a0', font: { size: 12 } }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return context.dataset.label + ': ' + formatNumber(context.raw);
                        }
                    }
                }
            },
            scales: {
                x: {
                    stacked: false,
                    title: { display: true, text: 'Tokens', color: '#a0a0a0' },
                    ticks: { color: '#a0a0a0' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: {
                    ticks: { color: '#a0a0a0', font: { family: "'Fira Code', monospace", size: 11 } },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
}

function renderModelUsageTable(summary) {
    const tbody = document.getElementById('usage-model-tbody');
    if (!tbody) return;

    const models = summary.by_model || {};
    const arr = Object.keys(models).map(k => ({ model: k, ...models[k] }));

    arr.sort((a, b) => b.cost - a.cost);

    if (!arr.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="placeholder-text">No usage recorded</td></tr>';
        return;
    }

    tbody.innerHTML = arr.map(m => `<tr>
        <td style="font-family: 'Fira Code', monospace; font-size: 0.85rem;">${m.model}</td>
        <td>${formatNumber(m.calls || 0)}</td>
        <td>${formatNumber(m.prompt_tokens)}</td>
        <td>${formatNumber(m.completion_tokens)}</td>
        <td>${formatNumber(m.tokens)}</td>
        <td>${formatCost(m.cost)}</td>
    </tr>`).join('');
}

function renderRecentCallsTable(entries) {
    const tbody = document.getElementById('usage-recent-tbody');
    if (!tbody) return;

    if (!entries.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="placeholder-text">No API calls recorded yet</td></tr>';
        return;
    }

    tbody.innerHTML = entries.slice(0, 25).map(e => {
        const time = new Date(e.timestamp).toLocaleTimeString();
        const provider = e.provider || 'unknown';
        const source = e.source || 'chat';
        return `<tr>
            <td style="font-family: 'Fira Code', monospace; font-size: 0.8rem;">${time}</td>
            <td><span class="source-badge ${source}">${source}</span></td>
            <td><span class="provider-badge ${provider}">${provider}</span></td>
            <td style="font-family: 'Fira Code', monospace; font-size: 0.8rem;">${e.model || '?'}</td>
            <td>${formatNumber(e.prompt_tokens || 0)}${e.tokens_estimated ? ' ~' : ''}</td>
            <td>${formatNumber(e.completion_tokens || 0)}${e.tokens_estimated ? ' ~' : ''}</td>
            <td>${formatCost(e.input_cost || 0)}</td>
            <td>${formatCost(e.output_cost || 0)}</td>
        </tr>`;
    }).join('');
}
