/**
 * mode-physics-lab.js
 * Physics & Math Lab — real symbolic/numeric computing (sympy/scipy/matplotlib)
 * with an optional AI formalize/interpret layer.
 *
 * API prefix: /api/physics-lab
 */
(function () {
    'use strict';

    const API = '/api/physics-lab';
    const $ = id => document.getElementById(id);

    // Last computed result, fed to the "Interpret" AI action.
    let _lastContext = '';

    function esc(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // Render a LaTeX string with KaTeX if it's loaded, else fall back to text.
    function renderMath(el, latex, fallbackText) {
        if (window.katex && latex) {
            try {
                window.katex.render(latex, el, { throwOnError: false, displayMode: true });
                return;
            } catch (_) { /* fall through */ }
        }
        el.textContent = fallbackText || latex || '';
    }

    // ── Tab switching ─────────────────────────────────────────────────────────
    function switchTab(tabId) {
        document.querySelectorAll('.pl-nav-tab').forEach(b =>
            b.classList.toggle('active', b.dataset.plTab === tabId));
        ['symbolic', 'plot', 'simulate'].forEach(id => {
            const el = $(`pl-pane-${id}`);
            if (el) el.classList.toggle('active', id === tabId);
        });
    }

    // ── Symbolic ──────────────────────────────────────────────────────────────
    function syncSymbolicFields() {
        const op = $('pl-sym-op').value;
        const pointWrap = $('pl-sym-point-wrap');
        const orderWrap = $('pl-sym-order-wrap');
        const pointLabel = $('pl-sym-point-label');

        const needsPoint = (op === 'limit' || op === 'evaluate');
        const needsOrder = (op === 'derivative');
        pointWrap.classList.toggle('pl-hide', !needsPoint);
        orderWrap.classList.toggle('pl-hide', !needsOrder);
        if (needsPoint) pointLabel.textContent = (op === 'limit') ? 'x →' : 'At point';
    }

    async function runSymbolic() {
        const expr = $('pl-sym-expr').value.trim();
        const out = $('pl-sym-result');
        if (!expr) { out.innerHTML = emptyState('square-root-variable', 'Enter an expression first.'); return; }

        out.innerHTML = loadingState('Computing…');
        const body = {
            expression: expr,
            operation: $('pl-sym-op').value,
            variable: $('pl-sym-var').value.trim() || 'x',
            point: $('pl-sym-point').value.trim() || null,
            order: parseInt($('pl-sym-order').value, 10) || 1,
        };

        try {
            const res = await fetch(`${API}/symbolic`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!data.ok) { out.innerHTML = errorState(data.error); return; }

            const mathDiv = document.createElement('div');
            mathDiv.className = 'pl-result-math';

            const wrap = document.createElement('div');
            wrap.appendChild(mathDiv);

            if (data.text) {
                const pre = document.createElement('div');
                pre.className = 'pl-result-text';
                pre.textContent = data.text;
                wrap.appendChild(pre);
            }

            if (Array.isArray(data.steps) && data.steps.length) {
                const steps = document.createElement('div');
                steps.className = 'pl-steps';
                data.steps.forEach(s => {
                    const d = document.createElement('div');
                    d.className = 'pl-step';
                    d.textContent = s;
                    steps.appendChild(d);
                });
                wrap.appendChild(steps);
            }

            if (data.numeric !== null && data.numeric !== undefined) {
                const meta = document.createElement('div');
                meta.className = 'pl-result-meta';
                meta.innerHTML = `<span class="pl-chip"><i class="fas fa-hashtag"></i> ${data.numeric}</span>`;
                wrap.appendChild(meta);
            }

            out.innerHTML = '';
            out.appendChild(wrap);
            renderMath(mathDiv, data.latex, data.text || data.result_str);

            _lastContext = `Problem: ${body.operation} of ${expr} (variable ${body.variable}).\n`
                + `Result: ${data.result_str}`;
        } catch (err) {
            out.innerHTML = errorState(err.message);
        }
    }

    // ── Plot ──────────────────────────────────────────────────────────────────
    async function runPlot() {
        const raw = $('pl-plot-exprs').value.split('\n').map(s => s.trim()).filter(Boolean);
        const out = $('pl-plot-result');
        if (!raw.length) { out.innerHTML = emptyState('chart-line', 'Add at least one function.'); return; }

        out.innerHTML = loadingState('Plotting…');
        const body = {
            expressions: raw,
            variable: $('pl-plot-var').value.trim() || 'x',
            x_min: parseFloat($('pl-plot-xmin').value),
            x_max: parseFloat($('pl-plot-xmax').value),
        };

        try {
            const res = await fetch(`${API}/plot`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!data.ok) { out.innerHTML = errorState(data.error); return; }
            out.innerHTML = `<img src="${data.image}" alt="plot">`;
            _lastContext = `Plotted ${raw.join(', ')} over ${body.variable} ∈ [${body.x_min}, ${body.x_max}].`;
        } catch (err) {
            out.innerHTML = errorState(err.message);
        }
    }

    // ── Simulate (ODE) ────────────────────────────────────────────────────────
    function makeOdeRow(name, rhs, init) {
        const row = document.createElement('div');
        row.className = 'pl-ode-eq';
        row.innerHTML =
            `<input class="pl-ode-name" value="${esc(name)}" spellcheck="false" title="state variable">` +
            `<span class="pl-ode-prime">′ =</span>` +
            `<input class="pl-ode-rhs" value="${esc(rhs)}" spellcheck="false" placeholder="f(t, …)">` +
            `<input class="pl-ode-init" value="${esc(init)}" spellcheck="false" title="initial value">` +
            `<button class="pl-ode-del" title="remove"><i class="fas fa-xmark"></i></button>`;
        row.querySelector('.pl-ode-del').addEventListener('click', () => {
            const eqs = $('pl-ode-eqs');
            if (eqs.children.length > 1) row.remove();
        });
        return row;
    }

    function setOdeRows(rows) {
        const container = $('pl-ode-eqs');
        container.innerHTML = '';
        rows.forEach(r => container.appendChild(makeOdeRow(r[0], r[1], r[2])));
    }

    const PRESETS = {
        pendulum: {
            rows: [['y0', 'y1', '2.5'], ['y1', '-0.3*y1 - sin(y0)', '0']],
            params: '', tmin: 0, tmax: 30, phase: true,
        },
        lotka: {
            rows: [['x', 'a*x - b*x*y', '10'], ['y', '-c*y + d*x*y', '5']],
            params: 'a=1.1\nb=0.4\nc=0.4\nd=0.1', tmin: 0, tmax: 40, phase: true,
        },
        lorenz: {
            rows: [['x', 's*(y - x)', '1'], ['y', 'x*(r - z) - y', '1'], ['z', 'x*y - b*z', '1']],
            params: 's=10\nr=28\nb=2.667', tmin: 0, tmax: 40, phase: true,
        },
    };

    function applyPreset(name) {
        const p = PRESETS[name];
        if (!p) return;
        setOdeRows(p.rows);
        $('pl-ode-params').value = p.params;
        $('pl-ode-tmin').value = p.tmin;
        $('pl-ode-tmax').value = p.tmax;
        $('pl-ode-phase').checked = p.phase;
    }

    function parseParams(text) {
        const out = {};
        text.split('\n').map(s => s.trim()).filter(Boolean).forEach(line => {
            const m = line.split('=');
            if (m.length === 2) {
                const v = parseFloat(m[1]);
                if (!isNaN(v)) out[m[0].trim()] = v;
            }
        });
        return out;
    }

    async function runOde() {
        const out = $('pl-ode-result');
        const rows = [...$('pl-ode-eqs').children];
        const state_vars = [], equations = [], initial = [];
        for (const row of rows) {
            const name = row.querySelector('.pl-ode-name').value.trim();
            const rhs = row.querySelector('.pl-ode-rhs').value.trim();
            const init = parseFloat(row.querySelector('.pl-ode-init').value);
            if (!name || !rhs) continue;
            state_vars.push(name); equations.push(rhs); initial.push(isNaN(init) ? 0 : init);
        }
        if (!state_vars.length) { out.innerHTML = emptyState('wave-square', 'Define at least one equation.'); return; }

        out.innerHTML = loadingState('Integrating…');
        const body = {
            equations, state_vars, initial,
            t_min: parseFloat($('pl-ode-tmin').value),
            t_max: parseFloat($('pl-ode-tmax').value),
            params: parseParams($('pl-ode-params').value),
            phase: $('pl-ode-phase').checked,
        };

        try {
            const res = await fetch(`${API}/ode`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!data.ok) { out.innerHTML = errorState(data.error); return; }

            let html = '<div class="pl-plot-imgs">';
            html += `<img src="${data.image}" alt="time evolution">`;
            if (data.phase_image) html += `<img src="${data.phase_image}" alt="phase portrait">`;
            html += '</div>';

            if (data.final_state) {
                const chips = Object.entries(data.final_state)
                    .map(([k, v]) => `<span class="pl-chip">${esc(k)} = ${v.toFixed(4)}</span>`).join('');
                html += `<div class="pl-result-meta"><span class="pl-muted" style="align-self:center;font-size:.76rem">final&nbsp;state</span>${chips}</div>`;
            }
            out.innerHTML = html;

            const sys = equations.map((e, i) => `${state_vars[i]}' = ${e}`).join(', ');
            _lastContext = `Simulated system: ${sys}. Initial ${state_vars.map((v, i) => `${v}=${initial[i]}`).join(', ')}. `
                + `Params ${JSON.stringify(body.params)}. Final state ${JSON.stringify(data.final_state)}.`;
        } catch (err) {
            out.innerHTML = errorState(err.message);
        }
    }

    // ── AI assist (streaming) ─────────────────────────────────────────────────
    async function streamAI(endpoint, payload) {
        const out = $('pl-ai-output');
        out.classList.remove('pl-hide');
        out.innerHTML = '<span id="pl-ai-text"></span><span class="pl-ai-cursor"></span>';
        const textEl = $('pl-ai-text');

        try {
            const res = await fetch(`${API}/${endpoint}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    const payloadStr = line.slice(5).trim();
                    if (!payloadStr) continue;
                    let msg;
                    try { msg = JSON.parse(payloadStr); } catch (_) { continue; }
                    if (msg.token) textEl.textContent += msg.token;
                    else if (msg.error) { textEl.textContent += `\n[error] ${msg.error}`; }
                }
            }
        } catch (err) {
            textEl.textContent += `\n[error] ${err.message}`;
        } finally {
            const cursor = out.querySelector('.pl-ai-cursor');
            if (cursor) cursor.remove();
        }
    }

    function aiFormalize() {
        const desc = $('pl-ai-input').value.trim();
        if (!desc) return;
        streamAI('formalize', { description: desc, model_id: $('pl-ai-model').value || 'auto' });
    }

    function aiInterpret() {
        if (!_lastContext) {
            const out = $('pl-ai-output');
            out.classList.remove('pl-hide');
            out.textContent = 'Run a computation first — then I can interpret the result.';
            return;
        }
        streamAI('interpret', { context: _lastContext, model_id: $('pl-ai-model').value || 'auto' });
    }

    // ── Shared render helpers ─────────────────────────────────────────────────
    function emptyState(icon, msg) {
        return `<div class="pl-empty"><i class="fas fa-${icon}"></i><span>${esc(msg)}</span></div>`;
    }
    function loadingState(msg) {
        return `<div class="pl-loading"><i class="fas fa-spinner fa-spin"></i> ${esc(msg)}</div>`;
    }
    function errorState(msg) {
        return `<div class="pl-error"><i class="fas fa-triangle-exclamation"></i><span>${esc(msg || 'Something went wrong.')}</span></div>`;
    }

    async function loadModels() {
        const sel = $('pl-ai-model');
        if (!sel) return;
        try {
            const res = await fetch('/api/registry/models/chat');
            if (!res.ok) return;
            const data = await res.json();
            const models = data.models || data.data || [];
            models.forEach(m => {
                const id = m.id || m.model_id || m.name;
                if (!id) return;
                const opt = document.createElement('option');
                opt.value = id;
                opt.textContent = m.name || id;
                sel.appendChild(opt);
            });
        } catch (_) { /* 'auto' stays as the only option */ }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        document.querySelectorAll('.pl-nav-tab').forEach(b =>
            b.addEventListener('click', () => switchTab(b.dataset.plTab)));

        $('pl-sym-op').addEventListener('change', syncSymbolicFields);
        $('pl-sym-run').addEventListener('click', runSymbolic);
        syncSymbolicFields();

        $('pl-plot-run').addEventListener('click', runPlot);

        $('pl-ode-add').addEventListener('click', () => {
            const n = $('pl-ode-eqs').children.length;
            $('pl-ode-eqs').appendChild(makeOdeRow(`y${n}`, '', '0'));
        });
        document.querySelectorAll('.pl-preset').forEach(b =>
            b.addEventListener('click', () => applyPreset(b.dataset.preset)));
        $('pl-ode-run').addEventListener('click', runOde);

        $('pl-ai-formalize').addEventListener('click', aiFormalize);
        $('pl-ai-interpret').addEventListener('click', aiInterpret);
        $('pl-ai-input').addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); aiFormalize(); }
        });

        applyPreset('pendulum');   // sensible default so Simulate isn't empty
        loadModels();
    }

    if ($('pl-root')) {
        init();
    } else {
        document.addEventListener('panelLoaded', function handler(e) {
            if (e.detail?.tabName === 'physics-lab') {
                document.removeEventListener('panelLoaded', handler);
                init();
            }
        });
    }
})();
