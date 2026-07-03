/**
 * mode-stats-lab.js
 * Data & Statistics Lab — real stats via scipy.stats + scikit-learn, with an
 * optional AI recommend/interpret layer.
 *
 * API prefix: /api/stats-lab
 */
(function () {
    'use strict';

    const API = '/api/stats-lab';
    const $ = id => document.getElementById(id);

    let _columns = [];         // [{name, type, ...}] from /describe
    let _numeric = [];         // numeric column names
    let _lastContext = '';     // fed to "Interpret"

    // how many columns each test consumes (null = 2+)
    const TEST_ARITY = {
        ttest_1samp: 1, normality: 1, chisquare: 1,
        ttest_ind: 2, ttest_paired: 2, mannwhitney: 2, pearson: 2, spearman: 2,
        anova: null,
    };

    const SAMPLE = `height,weight,age,group
170,65,28,A
182,84,35,A
165,55,41,B
175,72,30,A
160,50,52,B
188,90,26,A
168,60,45,B
172,68,33,A
158,48,55,B
179,78,29,A
163,53,48,B
185,86,31,A`;

    function esc(s) {
        return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    const fmt = (x, p = 4) => (x === null || x === undefined || Number.isNaN(x)) ? '—'
        : (Math.abs(x) < 1e-4 && x !== 0 ? x.toExponential(2) : Number(x.toFixed(p)).toString());

    function emptyState(icon, msg) {
        return `<div class="sl-empty"><i class="fas fa-${icon}"></i><span>${esc(msg)}</span></div>`;
    }
    const loading = msg => `<div class="sl-loading"><i class="fas fa-spinner fa-spin"></i> ${esc(msg)}</div>`;
    const errorBox = msg => `<div class="sl-error"><i class="fas fa-triangle-exclamation"></i><span>${esc(msg || 'Error')}</span></div>`;

    function switchTab(tabId) {
        document.querySelectorAll('.sl-nav-tab').forEach(b => b.classList.toggle('active', b.dataset.slTab === tabId));
        ['summary', 'test', 'regression', 'explore'].forEach(id => {
            const el = $(`sl-pane-${id}`);
            if (el) el.classList.toggle('active', id === tabId);
        });
    }

    function payloadBase() {
        return { data: $('sl-data').value, has_header: $('sl-has-header').checked };
    }
    async function post(endpoint, body) {
        const res = await fetch(`${API}/${endpoint}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return res.json();
    }

    // ── Parse data → populate pickers ─────────────────────────────────────────
    async function parseData() {
        const bar = $('sl-columns-bar');
        bar.innerHTML = `<span class="sl-loading" style="min-height:auto"><i class="fas fa-spinner fa-spin"></i> parsing…</span>`;
        const data = await post('describe', payloadBase());
        if (!data.ok) { bar.innerHTML = errorBox(data.error); return; }

        _columns = data.columns;
        _numeric = data.numeric_columns;

        bar.innerHTML = _columns.map(c =>
            `<span class="sl-col-tag ${c.type}"><i class="fas fa-${c.type === 'numeric' ? 'hashtag' : 'font'}"></i>${esc(c.name)}</span>`
        ).join('');

        // Summary describe table
        renderDescribe(_columns, data.n_rows);
        // populate selects & pickers
        fillSelect($('sl-hist-col'), _numeric);
        fillSelect($('sl-reg-x'), _numeric);
        fillSelect($('sl-reg-y'), _numeric, 1);
        buildPicker($('sl-test-cols'), _numeric);
        buildPicker($('sl-explore-cols'), _numeric, true);
        syncTestFields();
    }

    function fillSelect(sel, names, defaultIdx = 0) {
        if (!sel) return;
        sel.innerHTML = names.map((n, i) =>
            `<option value="${esc(n)}"${i === defaultIdx ? ' selected' : ''}>${esc(n)}</option>`).join('');
    }

    function renderDescribe(cols, nRows) {
        const out = $('sl-describe-result');
        const numeric = cols.filter(c => c.type === 'numeric');
        if (!numeric.length && !cols.length) { out.innerHTML = emptyState('table-list', 'No columns parsed.'); return; }

        let html = `<table class="sl-table"><thead><tr>`
            + `<th>Column</th><th>N</th><th>Mean</th><th>Std</th><th>Min</th><th>25%</th>`
            + `<th>Median</th><th>75%</th><th>Max</th><th>Skew</th></tr></thead><tbody>`;
        for (const c of cols) {
            if (c.type === 'numeric') {
                html += `<tr><td>${esc(c.name)}</td><td>${c.count}</td><td>${fmt(c.mean, 3)}</td>`
                    + `<td>${fmt(c.std, 3)}</td><td>${fmt(c.min, 3)}</td><td>${fmt(c.q25, 3)}</td>`
                    + `<td>${fmt(c.median, 3)}</td><td>${fmt(c.q75, 3)}</td><td>${fmt(c.max, 3)}</td><td>${fmt(c.skew, 2)}</td></tr>`;
            } else {
                html += `<tr><td class="sl-cat">${esc(c.name)}</td><td>${c.count}</td>`
                    + `<td colspan="8" style="text-align:left;color:var(--text-tertiary)">categorical · ${c.unique} unique · top “${esc(c.top)}”</td></tr>`;
            }
        }
        html += `</tbody></table>`;
        html += `<div class="sl-meta-row"><span class="sl-chip"><i class="fas fa-list-ol"></i> ${nRows} rows</span></div>`;
        out.innerHTML = html;
    }

    // ── Ordered multi-select picker ───────────────────────────────────────────
    function buildPicker(container, names, unordered = false) {
        if (!container) return;
        container.dataset.selected = '';
        container.innerHTML = names.map(n =>
            `<span class="sl-col-pick" data-name="${esc(n)}">${esc(n)}<span class="sl-order"></span></span>`).join('');
        container.querySelectorAll('.sl-col-pick').forEach(chip => {
            chip.addEventListener('click', () => togglePick(container, chip, unordered));
        });
    }

    function getSelected(container) {
        return (container.dataset.selected || '').split('|').filter(Boolean);
    }

    function togglePick(container, chip, unordered) {
        const name = chip.dataset.name;
        let sel = getSelected(container);
        if (sel.includes(name)) sel = sel.filter(n => n !== name);
        else sel.push(name);
        container.dataset.selected = sel.join('|');
        // repaint
        container.querySelectorAll('.sl-col-pick').forEach(c => {
            const idx = sel.indexOf(c.dataset.name);
            c.classList.toggle('selected', idx >= 0);
            const ord = c.querySelector('.sl-order');
            ord.textContent = (!unordered && idx >= 0) ? `#${idx + 1}` : '';
        });
    }

    // ── Summary: histogram ────────────────────────────────────────────────────
    async function runHistogram() {
        const col = $('sl-hist-col').value;
        const out = $('sl-hist-result');
        if (!col) { out.innerHTML = emptyState('chart-column', 'Parse data first.'); return; }
        out.innerHTML = loading('Plotting…');
        const data = await post('histogram', { ...payloadBase(), column: col, bins: 30 });
        if (!data.ok) { out.innerHTML = errorBox(data.error); return; }
        let html = `<img src="${data.image}" alt="histogram">`;
        if (data.normality) {
            const n = data.normality;
            html += `<div class="sl-meta-row"><span class="sl-chip"><i class="fas fa-wave-square"></i> ${n.test}: W=${fmt(n.statistic, 3)}, p=${fmt(n.pvalue, 4)}</span>`
                + `<span class="sl-chip" style="${n.normal ? '' : 'color:#fca5a5;border-color:rgba(239,68,68,.3);background:rgba(239,68,68,.08)'}">${n.normal ? 'looks normal' : 'not normal'}</span></div>`;
        }
        out.innerHTML = html;
        _lastContext = `Histogram of ${col}. Normality ${data.normality ? JSON.stringify(data.normality) : 'n/a'}.`;
    }

    // ── Tests ─────────────────────────────────────────────────────────────────
    function syncTestFields() {
        const t = $('sl-test-type').value;
        const arity = TEST_ARITY[t];
        const label = $('sl-test-cols-label');
        $('sl-popmean-wrap').classList.toggle('sl-hide', t !== 'ttest_1samp');
        label.textContent = arity === 1 ? 'Column (pick 1)'
            : arity === 2 ? 'Columns (pick 2, in order)'
            : 'Columns (pick 2 or more)';
    }

    async function runTest() {
        const t = $('sl-test-type').value;
        const out = $('sl-test-result');
        const cols = getSelected($('sl-test-cols'));
        const arity = TEST_ARITY[t];
        if (arity && cols.length !== arity) { out.innerHTML = errorBox(`This test needs exactly ${arity} column(s).`); return; }
        if (arity === null && cols.length < 2) { out.innerHTML = errorBox('ANOVA needs at least 2 columns.'); return; }

        out.innerHTML = loading('Running…');
        const data = await post('test', {
            ...payloadBase(), test: t, columns: cols,
            popmean: parseFloat($('sl-popmean').value) || 0,
        });
        if (!data.ok) { out.innerHTML = errorBox(data.error); return; }

        let html = `<div class="sl-test-out">`;
        html += `<div class="sl-test-name">${esc(data.name)}</div>`;
        html += `<div class="sl-test-verdict ${data.significant ? 'sig' : 'nsig'}">`
            + `<i class="fas fa-${data.significant ? 'circle-check' : 'circle-minus'}"></i>${esc(data.verdict)}</div>`;

        html += `<div class="sl-metric-grid">`;
        html += metric('Statistic', fmt(data.statistic));
        html += metric('p-value', fmt(data.pvalue, 5), true);
        if (data.effect && data.effect.value !== null && data.effect.value !== undefined)
            html += metric(data.effect.name, fmt(data.effect.value, 3));
        html += `</div>`;
        if (data.detail) html += `<div class="sl-test-detail">${esc(data.detail)}</div>`;
        html += `</div>`;
        out.innerHTML = html;

        _lastContext = `${data.name} on ${cols.join(', ')}: statistic=${fmt(data.statistic)}, p=${fmt(data.pvalue, 5)}, `
            + `${data.effect ? data.effect.name + '=' + fmt(data.effect.value, 3) + ', ' : ''}${data.verdict}. ${data.detail || ''}`;
    }

    function metric(label, value, accent) {
        return `<div class="sl-metric"><div class="sl-metric-label">${esc(label)}</div>`
            + `<div class="sl-metric-value ${accent ? 'accent' : ''}">${esc(value)}</div></div>`;
    }

    // ── Regression ────────────────────────────────────────────────────────────
    async function runRegression() {
        const out = $('sl-reg-result');
        const statsEl = $('sl-reg-stats');
        const x = $('sl-reg-x').value, y = $('sl-reg-y').value;
        if (!x || !y) { out.innerHTML = emptyState('chart-line', 'Parse data first.'); return; }
        if (x === y) { out.innerHTML = errorBox('Pick different columns for X and Y.'); return; }
        out.innerHTML = loading('Fitting…'); statsEl.innerHTML = '';
        const data = await post('regression', { ...payloadBase(), x, y });
        if (!data.ok) { out.innerHTML = errorBox(data.error); return; }
        out.innerHTML = `<img src="${data.image}" alt="regression">`;
        statsEl.innerHTML =
            regStat('R²', fmt(data.r2, 4)) + regStat('r', fmt(data.r, 4))
            + regStat('slope', fmt(data.slope, 4)) + regStat('intercept', fmt(data.intercept, 4))
            + regStat('p-value', fmt(data.pvalue, 5)) + regStat('std err', fmt(data.stderr, 4));
        _lastContext = `Linear regression ${y} ~ ${x}: slope=${fmt(data.slope)}, R²=${fmt(data.r2, 4)}, p=${fmt(data.pvalue, 5)}, n=${data.n}.`;
    }
    const regStat = (k, v) => `<div class="sl-reg-stat"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`;

    // ── Explore ───────────────────────────────────────────────────────────────
    async function runExplore() {
        const out = $('sl-explore-result');
        const cols = getSelected($('sl-explore-cols'));
        if (cols.length < 2) { out.innerHTML = errorBox('Select at least 2 numeric columns.'); return; }
        out.innerHTML = loading('Reducing…');
        const data = await post('explore', {
            ...payloadBase(), columns: cols, clusters: parseInt($('sl-explore-k').value, 10) || 3,
        });
        if (!data.ok) { out.innerHTML = errorBox(data.error); return; }
        const ev = (data.explained_variance || []).map(v => (v * 100).toFixed(0) + '%').join(' + ');
        out.innerHTML = `<img src="${data.image}" alt="PCA">`
            + `<div class="sl-meta-row"><span class="sl-chip"><i class="fas fa-percent"></i> variance ${ev}</span>`
            + `<span class="sl-chip"><i class="fas fa-object-group"></i> k=${data.k} · sizes ${data.cluster_sizes.join(', ')}</span></div>`;
        _lastContext = `PCA + KMeans on ${cols.join(', ')}: explained variance ${ev}, k=${data.k}, cluster sizes ${data.cluster_sizes.join(', ')}.`;
    }

    // ── AI (streaming) ────────────────────────────────────────────────────────
    async function streamAI(endpoint, payload) {
        const out = $('sl-ai-output');
        out.classList.remove('sl-hide');
        out.innerHTML = '<span id="sl-ai-text"></span><span class="sl-ai-cursor"></span>';
        const textEl = $('sl-ai-text');
        try {
            const res = await fetch(`${API}/${endpoint}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n'); buffer = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    const s = line.slice(5).trim(); if (!s) continue;
                    let msg; try { msg = JSON.parse(s); } catch (_) { continue; }
                    if (msg.token) textEl.textContent += msg.token;
                    else if (msg.error) textEl.textContent += `\n[error] ${msg.error}`;
                }
            }
        } catch (err) {
            textEl.textContent += `\n[error] ${err.message}`;
        } finally {
            const cursor = out.querySelector('.sl-ai-cursor');
            if (cursor) cursor.remove();
        }
    }

    function aiRecommend() {
        const q = $('sl-ai-input').value.trim();
        if (!q) return;
        const summary = _columns.map(c => `${c.name} (${c.type})`).join(', ');
        streamAI('recommend', { question: q, columns_summary: summary, model_id: $('sl-ai-model').value || 'auto' });
    }
    function aiInterpret() {
        if (!_lastContext) {
            const out = $('sl-ai-output'); out.classList.remove('sl-hide');
            out.textContent = 'Run an analysis first — then I can interpret it.';
            return;
        }
        streamAI('interpret', { context: _lastContext, model_id: $('sl-ai-model').value || 'auto' });
    }

    async function loadModels() {
        const sel = $('sl-ai-model');
        if (!sel) return;
        try {
            const res = await fetch('/api/registry/models/chat');
            if (!res.ok) return;
            const data = await res.json();
            (data.models || data.data || []).forEach(m => {
                const id = m.id || m.model_id || m.name; if (!id) return;
                const opt = document.createElement('option');
                opt.value = id; opt.textContent = m.name || id; sel.appendChild(opt);
            });
        } catch (_) { /* auto stays */ }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        document.querySelectorAll('.sl-nav-tab').forEach(b =>
            b.addEventListener('click', () => switchTab(b.dataset.slTab)));

        $('sl-parse-btn').addEventListener('click', parseData);
        $('sl-sample-btn').addEventListener('click', () => { $('sl-data').value = SAMPLE; parseData(); });

        $('sl-hist-btn').addEventListener('click', runHistogram);
        $('sl-test-type').addEventListener('change', syncTestFields);
        $('sl-test-btn').addEventListener('click', runTest);
        $('sl-reg-btn').addEventListener('click', runRegression);
        $('sl-explore-btn').addEventListener('click', runExplore);

        $('sl-ai-recommend').addEventListener('click', aiRecommend);
        $('sl-ai-interpret').addEventListener('click', aiInterpret);
        $('sl-ai-input').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); aiRecommend(); } });

        syncTestFields();
        loadModels();
        // Preload the sample so the tool isn't empty on first open.
        $('sl-data').value = SAMPLE;
        parseData();
    }

    if ($('sl-root')) {
        init();
    } else {
        document.addEventListener('panelLoaded', function handler(e) {
            if (e.detail?.tabName === 'stats-lab') {
                document.removeEventListener('panelLoaded', handler);
                init();
            }
        });
    }
})();
