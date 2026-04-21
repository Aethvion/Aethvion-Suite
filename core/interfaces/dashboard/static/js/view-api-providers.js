/* ── API Providers View ─────────────────────────────────────────── */
(function () {
    const REGISTRY_URL       = '/api/registry';
    const AVAIL_TYPES_URL    = '/api/registry/available_types';
    const ADD_PROVIDER_URL   = '/api/registry/providers';
    const SUGGESTED_URL      = '/api/registry/suggested';

    /* Providers that are local / non-cloud — never shown on this page */
    const LOCAL_IDS = new Set(['local', 'ollama', 'audio', 'audio_models']);

    const ICONS = {
        google_ai:   'fab fa-google',
        openai:      'fab fa-openai',
        anthropic:   'fas fa-brain',
        grok:        'fas fa-bolt',
        xai:         'fas fa-bolt',
        groq:        'fas fa-bolt',
        mistral:     'fas fa-wind',
        openrouter:  'fas fa-route',
    };

    const DESCRIPTIONS = {
        google_ai:  'Gemini models — Flash for speed, Pro for complex reasoning and multimodal tasks.',
        openai:     'GPT-4o, o1, and mini variants. Industry-standard reasoning and multimodal capability.',
        anthropic:  'Claude Sonnet & Haiku. Sophisticated reasoning and reliable outputs.',
        grok:       'xAI Grok models with real-time knowledge and strong reasoning.',
        groq:       'Lightning-fast LPU inference for Llama, Mixtral, and Gemma models.',
        mistral:    'Mistral Large, Codestral, Pixtral. High-efficiency European-hosted models.',
        openrouter: 'Unified gateway to 300+ models — DeepSeek, Llama, Qwen, and more.',
    };

    const LABELS = {
        google_ai:  'Google AI',
        openai:     'OpenAI',
        anthropic:  'Anthropic',
        grok:       'Grok (xAI)',
        xai:        'xAI',
        groq:       'Groq',
        mistral:    'Mistral AI',
        openrouter: 'OpenRouter',
    };

    const TIER_LABELS = { fast: 'Fast', balanced: 'Balanced', premium: 'Premium', specialized: 'Specialized' };
    const TIER_COLORS = {
        fast:        'rgba(34,197,94,0.15)',
        balanced:    'rgba(99,179,237,0.15)',
        premium:     'rgba(168,85,247,0.15)',
        specialized: 'rgba(251,191,36,0.15)',
    };
    const TIER_TEXT = {
        fast:        '#4ade80',
        balanced:    'var(--primary,#63b3ed)',
        premium:     '#c084fc',
        specialized: '#fbbf24',
    };

    const DEFAULT_ICON  = 'fas fa-plug';
    const DEFAULT_DESC  = 'External AI service provider.';

    let _activeProvider  = null;
    let _registry        = null;
    let _suggested       = {};
    let _suggestedPanelOpen = false;

    /* ── Helpers ──────────────────────────────────────────────────── */
    function iconFor(id)  { return ICONS[id]  || DEFAULT_ICON; }
    function descFor(id)  { return DESCRIPTIONS[id] || DEFAULT_DESC; }
    function labelFor(id) {
        return LABELS[id] || id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }

    function statusInfo(provider) {
        const count = Object.keys(provider.models || {}).length;
        if (!provider.active) return { label: 'Inactive', cls: 'ap-tab-badge-inactive', count };
        if (count === 0)      return { label: 'Standby',  cls: 'ap-tab-badge-standby',  count };
        return { label: 'Connected', cls: 'ap-status-connected ap-tab-badge-connected', count };
    }

    function formatCost(val) {
        if (val === undefined || val === null || val === '') return '—';
        const n = parseFloat(val);
        if (isNaN(n)) return '—';
        return '$' + n.toFixed(n < 1 ? 4 : 2);
    }

    function escHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function escAttr(s) {
        return String(s).replace(/'/g, '&#39;').replace(/"/g, '&quot;');
    }

    /* ── Fetch ────────────────────────────────────────────────────── */
    async function fetchRegistry() {
        const r = await fetch(REGISTRY_URL);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
    }

    async function saveRegistry(reg) {
        const r = await fetch(REGISTRY_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(reg),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json().catch(() => ({}));
    }

    /* ── Render selector row ──────────────────────────────────────── */
    function renderSelectorRow(activeKeys, availTypes) {
        const row = document.getElementById('ap-selector-row');
        if (!row) return;

        let html = '';

        for (const id of activeKeys) {
            const prov  = _registry.providers[id];
            const si    = statusInfo(prov);
            const isAct = id === _activeProvider;
            html += `
            <button class="ap-tab${isAct ? ' active' : ''}" onclick="apSelectProvider('${escAttr(id)}')">
                <span class="ap-tab-icon"><i class="${escAttr(iconFor(id))}"></i></span>
                <span class="ap-tab-label">${escHtml(labelFor(id))}</span>
                <span class="ap-tab-badge ${escAttr(si.cls)}">${si.count > 0 ? si.count + ' model' + (si.count !== 1 ? 's' : '') : escHtml(si.label)}</span>
            </button>`;
        }

        if (availTypes.length > 0) {
            if (activeKeys.length > 0) html += `<span class="ap-tab-divider"></span>`;
            for (const t of availTypes) {
                html += `
                <button class="ap-tab-avail" id="ap-avail-btn-${escAttr(t)}" onclick="apAddProvider('${escAttr(t)}', this)">
                    <i class="ap-tab-avail-icon fas fa-plus"></i>
                    <span class="ap-tab-avail-label">${escHtml(labelFor(t))}</span>
                </button>`;
            }
        }

        row.innerHTML = html || '<span style="color:var(--text-tertiary);font-size:0.82rem;">No providers configured.</span>';
    }

    /* ── Render content panel ─────────────────────────────────────── */
    function renderContentPanel(providerId) {
        const panel = document.getElementById('ap-content-panel');
        if (!panel) return;

        if (!providerId || !_registry?.providers?.[providerId]) {
            panel.innerHTML = `
            <div class="ap-content-empty">
                <i class="fas fa-hand-pointer"></i>
                <span>Select a provider above to manage its models.</span>
            </div>`;
            return;
        }

        const prov   = _registry.providers[providerId];
        const models = prov.models || {};
        const hasSuggested = (_suggested.suggested || []).some(m => m.provider_id === providerId) || (_suggested[providerId] || []).length > 0;


        const entries = Object.entries(models);
        let tableBody = '';
        if (entries.length === 0) {
            tableBody = `<tr><td colspan="5" class="ap-empty-models">No models configured yet.</td></tr>`;
        } else {
            tableBody = entries.map(([modelId, cfg]) => {
                const capPills = (cfg.capabilities || [])
                    .map(c => `<span class="ap-cap-pill">${escHtml(c)}</span>`).join('');
                return `
                <tr>
                    <td><span class="ap-model-id">${escHtml(modelId)}</span></td>
                    <td class="ap-cost">${formatCost(cfg.input_cost_per_1m_tokens)}</td>
                    <td class="ap-cost">${formatCost(cfg.output_cost_per_1m_tokens)}</td>
                    <td><div class="ap-caps">${capPills || '<span class="ap-cap-pill">CHAT</span>'}</div></td>
                    <td>
                        <button class="ap-btn-delete" title="Remove model"
                            onclick="apDeleteModel('${escAttr(providerId)}','${escAttr(modelId)}',this)">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </td>
                </tr>`;
            }).join('');
        }

        panel.innerHTML = `
        <div class="ap-detail-header">
            <div class="ap-detail-icon"><i class="${escAttr(iconFor(providerId))}"></i></div>
            <div>
                <p class="ap-detail-title">${escHtml(labelFor(providerId))}</p>
                <p class="ap-detail-desc">${escHtml(descFor(providerId))}</p>
            </div>
        </div>

        <table class="ap-model-table">
            <thead>
                <tr>
                    <th>Model ID</th>
                    <th>Input / 1M</th>
                    <th>Output / 1M</th>
                    <th>Capabilities</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="ap-tbody">${tableBody}</tbody>
        </table>

        <div class="ap-add-form">
            <input class="ap-add-input id-input" id="ap-newid"
                type="text" placeholder="Model ID" autocomplete="off" />
            <label>In</label>
            <input class="ap-add-input cost-input" id="ap-incost"
                type="number" placeholder="0.00" min="0" step="0.0001" />
            <label>Out</label>
            <input class="ap-add-input cost-input" id="ap-outcost"
                type="number" placeholder="0.00" min="0" step="0.0001" />
            <button class="ap-btn-add" onclick="apAddModel('${escAttr(providerId)}', this)">
                <i class="fas fa-plus"></i> Add Model
            </button>
            ${hasSuggested ? `
            <button class="ap-btn-suggested" onclick="apToggleSuggested('${escAttr(providerId)}')">
                <i class="fas fa-magic"></i> Suggested
            </button>` : ''}
            <span class="ap-feedback" id="ap-fb"></span>
        </div>

        <div id="ap-suggested-panel" class="ap-suggested-panel" style="display:none;"></div>`;

        _suggestedPanelOpen = false;
    }

    /* ── Suggested models panel ───────────────────────────────────── */
    window.apToggleSuggested = function (providerId) {
        const panel = document.getElementById('ap-suggested-panel');
        if (!panel) return;

        if (_suggestedPanelOpen) {
            panel.style.display = 'none';
            _suggestedPanelOpen = false;
            return;
        }

        const allSuggestions = _suggested.suggested || [];
        const providerSuggestions = allSuggestions.filter(m => m.provider_id === providerId);
        
        if (providerSuggestions.length === 0) { 
            panel.innerHTML = `<div class="ap-sug-header"><span>No new suggestions for this provider.</span></div>`;
            panel.style.display = 'block';
            _suggestedPanelOpen = true;
            return;
        }

        const existing = Object.keys(_registry?.providers?.[providerId]?.models || {});

        panel.innerHTML = `
        <div class="ap-sug-header">
            <span>Suggested Models</span>
            <button class="ap-sug-close" onclick="apToggleSuggested('${escAttr(providerId)}')">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="ap-sug-grid">
            ${providerSuggestions.map(m => {
                const alreadyAdded = existing.includes(m.id);
                // The new system uses "cost" instead of specific fields in the suggested card view
                // but let's keep it robust
                const inCost  = m.input_cost  || 0;
                const outCost = m.output_cost || 0;
                
                const capPills = (m.capabilities || [])
                    .map(c => `<span class="ap-cap-pill">${escHtml(c)}</span>`).join('');
                    
                return `
                <div class="ap-sug-card${alreadyAdded ? ' added' : ''}">
                    <div class="ap-sug-card-top">
                        <span class="ap-sug-model-id">${escHtml(m.name || m.id)}</span>
                        <span class="ap-sug-id-tag">${escHtml(m.id)}</span>
                    </div>
                    <p class="ap-sug-desc">${escHtml(m.description || '')}</p>
                    <div class="ap-sug-card-footer">
                        <div class="ap-sug-costs">
                            <span title="Input cost per 1M tokens">In: ${formatCost(inCost)}</span>
                            <span title="Output cost per 1M tokens">Out: ${formatCost(outCost)}</span>
                        </div>
                        <div class="ap-caps" style="flex:1;">${capPills}</div>
                        ${alreadyAdded
                            ? `<span class="ap-sug-added-badge"><i class="fas fa-check"></i> Added</span>`
                            : `<button class="ap-sug-add-btn" onclick="apAddSuggested('${escAttr(providerId)}','${escAttr(m.id)}', this)">
                                <i class="fas fa-plus"></i> Add
                               </button>`
                        }
                    </div>
                </div>`;
            }).join('')}
        </div>`;

        panel.style.display = 'block';
        _suggestedPanelOpen = true;
    };

    window.apAddSuggested = async function (providerId, modelId, btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
        const fbEl = document.getElementById('ap-fb');

        try {
            const r = await fetch('/api/registry/suggested/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider_id: providerId, model_id: modelId }),
            });
            
            if (!r.ok) {
                const d = await r.json().catch(() => ({}));
                throw new Error(d.detail || `HTTP ${r.status}`);
            }

            /* Refresh registry local state */
            _registry = await fetchRegistry();

            /* Mark card as added */
            const card = btn.closest('.ap-sug-card');
            if (card) {
                card.classList.add('added');
                btn.outerHTML = `<span class="ap-sug-added-badge"><i class="fas fa-check"></i> Added</span>`;
            }

            /* Refresh main table */
            refreshModelTable(providerId);
            refreshTabBadge(providerId);

            if (fbEl) { fbEl.textContent = `${modelId} added.`; fbEl.className = 'ap-feedback success'; setTimeout(() => { if (fbEl) fbEl.textContent = ''; }, 2500); }
        } catch (err) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-plus"></i> Add';
            if (fbEl) { fbEl.textContent = err.message; fbEl.className = 'ap-feedback error'; }
        }
    };

    /* ── Init ─────────────────────────────────────────────────────── */
    async function apInit() {
        const row = document.getElementById('ap-selector-row');
        if (!row) return;

        row.innerHTML = '<div class="ap-selector-loading"><i class="fas fa-circle-notch fa-spin"></i></div>';

        try {
            const [registry, availRaw, suggestedRaw] = await Promise.all([
                fetchRegistry(),
                fetch(AVAIL_TYPES_URL).then(r => r.ok ? r.json() : []),
                fetch(SUGGESTED_URL).then(r => r.ok ? r.json() : {}),
            ]);

            _registry  = registry;
            _suggested = suggestedRaw || {};

            const providers  = registry.providers || {};
            const activeKeys = Object.keys(providers).filter(id => !LOCAL_IDS.has(id));
            const availTypes = availRaw.filter(t => !LOCAL_IDS.has(t) && !providers[t]);

            if (!_activeProvider || !providers[_activeProvider]) {
                _activeProvider = activeKeys[0] || null;
            }

            renderSelectorRow(activeKeys, availTypes);
            renderContentPanel(_activeProvider);

        } catch (err) {
            row.innerHTML = `<span style="color:#f87171;font-size:0.82rem;"><i class="fas fa-exclamation-triangle"></i> Failed to load: ${escHtml(err.message)}</span>`;
        }
    }

    /* ── Select provider ──────────────────────────────────────────── */
    window.apSelectProvider = function (providerId) {
        _activeProvider = providerId;
        _suggestedPanelOpen = false;
        document.querySelectorAll('.ap-tab').forEach(btn => btn.classList.remove('active'));
        const activeBtn = document.querySelector(`.ap-tab[onclick*="'${CSS.escape(providerId)}'"]`);
        if (activeBtn) activeBtn.classList.add('active');
        renderContentPanel(providerId);
    };

    /* ── Add provider (available tile) ───────────────────────────── */
    window.apAddProvider = async function (typeId, btn) {
        btn.disabled = true;
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
        try {
            const res = await fetch(ADD_PROVIDER_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: typeId }),
            });
            if (!res.ok) {
                const d = await res.json().catch(() => ({}));
                throw new Error(d.detail || `HTTP ${res.status}`);
            }
            _activeProvider = typeId;
            await apInit();
        } catch (err) {
            btn.disabled = false;
            btn.innerHTML = orig;
            if (typeof showNotification === 'function') showNotification(err.message, 'error');
        }
    };

    /* ── Delete model ─────────────────────────────────────────────── */
    window.apDeleteModel = async function (providerId, modelId, btn) {
        if (!confirm(`Remove "${modelId}" from ${labelFor(providerId)}?`)) return;
        btn.disabled = true;
        const fbEl = document.getElementById('ap-fb');
        try {
            const registry = await fetchRegistry();
            const prov = (registry.providers || {})[providerId];
            if (!prov?.models) throw new Error('Provider not found');
            delete prov.models[modelId];
            await saveRegistry(registry);
            _registry = registry;
            refreshModelTable(providerId);
            refreshTabBadge(providerId);
            /* Refresh suggested panel if open to un-mark removed model */
            if (_suggestedPanelOpen) apToggleSuggested(providerId), apToggleSuggested(providerId);
            if (fbEl) { fbEl.textContent = 'Model removed.'; fbEl.className = 'ap-feedback success'; setTimeout(() => { if (fbEl) fbEl.textContent = ''; }, 2000); }
        } catch (err) {
            if (fbEl) { fbEl.textContent = err.message; fbEl.className = 'ap-feedback error'; }
            btn.disabled = false;
        }
    };

    /* ── Add model (manual form) ──────────────────────────────────── */
    window.apAddModel = async function (providerId, btn) {
        const idEl  = document.getElementById('ap-newid');
        const inEl  = document.getElementById('ap-incost');
        const outEl = document.getElementById('ap-outcost');
        const fbEl  = document.getElementById('ap-fb');

        const modelId = idEl?.value.trim() || '';
        if (!modelId) {
            if (fbEl) { fbEl.textContent = 'Model ID is required.'; fbEl.className = 'ap-feedback error'; }
            return;
        }
        btn.disabled = true;
        try {
            const registry = await fetchRegistry();
            if (!registry.providers) registry.providers = {};
            const prov = registry.providers[providerId] ||= { models: {} };
            if (!prov.models) prov.models = {};

            const inputCost  = inEl?.value  !== '' ? parseFloat(inEl.value)  : null;
            const outputCost = outEl?.value !== '' ? parseFloat(outEl.value) : null;

            const entry = { capabilities: ['CHAT'] };
            if (inputCost  !== null && !isNaN(inputCost))  entry.input_cost_per_1m_tokens  = inputCost;
            if (outputCost !== null && !isNaN(outputCost)) entry.output_cost_per_1m_tokens = outputCost;

            prov.models[modelId] = entry;
            await saveRegistry(registry);
            _registry = registry;

            refreshModelTable(providerId);
            refreshTabBadge(providerId);

            if (idEl)  idEl.value  = '';
            if (inEl)  inEl.value  = '';
            if (outEl) outEl.value = '';

            if (fbEl) { fbEl.textContent = 'Model added.'; fbEl.className = 'ap-feedback success'; setTimeout(() => { if (fbEl) fbEl.textContent = ''; }, 2000); }
        } catch (err) {
            if (fbEl) { fbEl.textContent = err.message; fbEl.className = 'ap-feedback error'; }
        } finally {
            btn.disabled = false;
        }
    };

    /* ── Helpers ──────────────────────────────────────────────────── */
    function refreshModelTable(providerId) {
        const tbody = document.getElementById('ap-tbody');
        if (!tbody) return;
        const models  = _registry?.providers?.[providerId]?.models || {};
        const entries = Object.entries(models);
        if (entries.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="ap-empty-models">No models configured yet.</td></tr>`;
            return;
        }
        tbody.innerHTML = entries.map(([modelId, cfg]) => {
            const capPills = (cfg.capabilities || [])
                .map(c => `<span class="ap-cap-pill">${escHtml(c)}</span>`).join('');
            return `
            <tr>
                <td><span class="ap-model-id">${escHtml(modelId)}</span></td>
                <td class="ap-cost">${formatCost(cfg.input_cost_per_1m_tokens)}</td>
                <td class="ap-cost">${formatCost(cfg.output_cost_per_1m_tokens)}</td>
                <td><div class="ap-caps">${capPills || '<span class="ap-cap-pill">CHAT</span>'}</div></td>
                <td>
                    <button class="ap-btn-delete" title="Remove model"
                        onclick="apDeleteModel('${escAttr(providerId)}','${escAttr(modelId)}',this)">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </td>
            </tr>`;
        }).join('');
    }

    function refreshTabBadge(providerId) {
        const prov = _registry?.providers?.[providerId];
        if (!prov) return;
        const si  = statusInfo(prov);
        const tab = document.querySelector(`.ap-tab[onclick*="'${CSS.escape(providerId)}'"]`);
        if (!tab) return;
        const badge = tab.querySelector('.ap-tab-badge');
        if (badge) {
            badge.className = `ap-tab-badge ${si.cls}`;
            badge.textContent = si.count > 0 ? si.count + ' model' + (si.count !== 1 ? 's' : '') : si.label;
        }
    }

    /* ── Register with tab system ─────────────────────────────────── */
    if (typeof registerTabInit === 'function') {
        registerTabInit('api-providers', apInit);
    }
})();
