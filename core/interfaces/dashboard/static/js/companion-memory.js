/**
 * companion-memory.js
 * ════════════════════
 * Handles the Companion Memory tab — lets the user switch between
 * companions and view each one's base_info.json and memory.json.
 *
 * API contract:
 *   GET /api/companions/list          → [{ id, name, ... }]
 *   GET /api/companions/{id}/memory   → { base_info, memory }
 *   GET /api/companions/{id}/history  → [{ date, messages }]
 */

(function () {
    'use strict';

    // ── State ──────────────────────────────────────────────────────────────────
    let _currentCompanion = 'misakacipher';
    let _initialized = false;
    let _companionMap = {}; // id -> { name, label }

    // ── Public API (called from core.js on tab switch) ─────────────────────────
    window.refreshCompanionMemory = async function () {
        if (!_initialized) {
            _initialized = true;
            await _loadCompanionList();
        }
        await _fetchAndDisplay(_currentCompanion);
    };

    window.selectCompanionMemory = async function (companionId, btnEl) {
        _currentCompanion = companionId;

        // Update active button state
        document.querySelectorAll('.cm-selector-btn').forEach(b => b.classList.remove('active'));
        if (btnEl) btnEl.classList.add('active');

        await _fetchAndDisplay(companionId);
    };

    // ── Internal ───────────────────────────────────────────────────────────────

    async function _fetchAndDisplay(companionId) {
        const baseInfoEl    = document.getElementById('cm-base-info-viewer');
        const memoryEl      = document.getElementById('cm-dynamic-memory-viewer');
        const activeNameEl  = document.getElementById('cm-active-name');
        const statusEl      = document.getElementById('cm-memory-status');

        if (!baseInfoEl || !memoryEl) return;

        // Show loading state
        const loadingHtml = '<div class="cm-loading"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';
        baseInfoEl.innerHTML = loadingHtml;
        memoryEl.innerHTML   = loadingHtml;
        if (statusEl) statusEl.textContent = 'fetching…';

        // Resolve label from map
        const label = _companionMap[companionId] || companionId;
        if (activeNameEl) activeNameEl.textContent = label;

        try {
            // Unified Endpoint
            const res  = await fetch(`/api/companions/${companionId}/memory`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            // Handle possible nested data structures
            const base_info = data.base_info || data.base_info_data || data;
            const memory    = data.memory    || data.memory_data    || {};

            if (data.base_info && data.memory) {
                baseInfoEl.textContent = JSON.stringify(data.base_info, null, 2);
                memoryEl.textContent   = JSON.stringify(data.memory, null, 2);
            } else {
                baseInfoEl.textContent = JSON.stringify(base_info, null, 2);
                memoryEl.textContent   = JSON.stringify(memory, null, 2);
            }
            
            if (statusEl) statusEl.textContent = `loaded ${new Date().toLocaleTimeString()}`;

        } catch (err) {
            const errHtml = `<div class="cm-error"><i class="fas fa-exclamation-triangle"></i> ${err.message}</div>`;
            baseInfoEl.innerHTML = errHtml;
            memoryEl.innerHTML   = errHtml;
            if (statusEl) statusEl.textContent = 'error';
        }
    }

    async function _loadCompanionList() {
        const container = document.getElementById('cm-custom-btns');
        if (!container) return;
        container.innerHTML = '';

        try {
            const res  = await fetch('/api/companions/list');
            if (!res.ok) return;
            const data = await res.json();
            const companions = data.companions || [];

            for (const c of companions) {
                _companionMap[c.id] = c.name;
                const exists = document.querySelector(`.cm-selector-btn[data-companion="${c.id}"]`);
                if (exists) continue;

                const btn = document.createElement('button');
                btn.className = 'cm-selector-btn';
                btn.dataset.companion = c.id;
                btn.innerHTML = `
                    <span class="cm-btn-avatar custom">${(c.name || c.id).charAt(0).toUpperCase()}</span>
                    <span>${c.name || c.id}</span>
                `;
                btn.onclick = () => window.selectCompanionMemory(c.id, btn);
                container.appendChild(btn);
            }
        } catch (e) {
            console.error("Failed to load companions list:", e);
        }
    }

    document.addEventListener('panelLoaded', function (e) {
        if (e.detail && e.detail.panel === 'companion-memory') {
            window.refreshCompanionMemory();
        }
    });

})();
