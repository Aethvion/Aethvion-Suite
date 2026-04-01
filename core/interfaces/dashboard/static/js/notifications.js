/**
 * Aethvion Suite — Notification System
 * 
 * Usage from any JS module:
 *   window.Notifications.push({ title, message, source, level, target })
 * 
 * Usage from Python (via REST):
 *   POST /api/notifications/   { title, message, source, level, target }
 * 
 * target (optional): { tab: "agents", context: "some-id" }
 * level: "info" | "success" | "warning" | "error"
 * source: any string label, e.g. "agents", "schedule", "system"
 */

window.Notifications = (() => {
    // ── State ──────────────────────────────────────────────────────────
    let _active = [];      // array of notification objects (unseen)
    let _panelOpen = false;
    let _viewMode = 'active'; // 'active' | 'history'
    let _pollInterval = null;
    const POLL_MS = 30_000;

    // DOM refs (set in init)
    let bellBtn, badge, panel, listEl, emptyEl;

    // ── Source → Icon mapping ──────────────────────────────────────────
    const SOURCE_ICONS = {
        agents:   'fa-robot',
        schedule: 'fa-clock',
        system:   'fa-microchip',
        chat:     'fa-comment',
        audio:    'fa-microphone',
        photo:    'fa-image',
        corp:     'fa-building',
        memory:   'fa-brain',
        default:  'fa-bell',
    };

    function _iconFor(source) {
        return SOURCE_ICONS[source] || SOURCE_ICONS.default;
    }

    // ── Time formatting ────────────────────────────────────────────────
    function _relTime(isoStr) {
        if (!isoStr) return '';
        const diff = Date.now() - new Date(isoStr).getTime();
        const s = Math.floor(diff / 1000);
        if (s < 60)  return 'just now';
        const m = Math.floor(s / 60);
        if (m < 60)  return `${m}m ago`;
        const h = Math.floor(m / 60);
        if (h < 24)  return `${h}h ago`;
        return new Date(isoStr).toLocaleDateString();
    }

    // ── Build element ──────────────────────────────────────────────────
    function _buildRow(notif, isHistory = false) {
        const row = document.createElement('div');
        row.className = `notif-row${notif.target ? ' has-target' : ''}${isHistory && notif.seen ? ' seen' : ''}`;
        row.dataset.id = notif.id;
        row.dataset.level = notif.level || 'info';

        const iconCls = _iconFor(notif.source);

        let messageHtml = _esc(notif.message);
        try {
            if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
                messageHtml = marked.parse(notif.message);
            }
        } catch (e) {
            console.warn('[Notifications] Markdown parse failed:', e);
        }

        row.innerHTML = `
            <div class="notif-icon"><i class="fas ${iconCls}"></i></div>
            <div class="notif-body">
                <div class="notif-title">${_esc(notif.title)}</div>
                <div class="notif-message">${messageHtml}</div>
                <div class="notif-meta">
                    <span class="notif-source-tag">${_esc(notif.source)}</span>
                    <span class="notif-time">${_relTime(notif.timestamp)}</span>
                </div>
            </div>
            ${!isHistory ? `<button class="notif-dismiss-btn" title="Dismiss"><i class="fas fa-times"></i></button>` : ''}
        `;

        // Click on body: navigate if has target, then dismiss
        if (!isHistory) {
            row.addEventListener('click', (e) => {
                if (e.target.closest('.notif-dismiss-btn')) return;
                _navigateTo(notif);
                _dismiss(notif.id, row);
            });

            const dismissBtn = row.querySelector('.notif-dismiss-btn');
            if (dismissBtn) {
                dismissBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    _dismiss(notif.id, row);
                });
            }
        }

        return row;
    }

    function _esc(str) {
        if (!str) return '';
        return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    // ── Navigation ─────────────────────────────────────────────────────
    function _navigateTo(notif) {
        if (!notif.target) return;
        const { tab, context } = notif.target;

        // Close panel first
        closePanel();

        // Use global tab switcher if available
        if (tab && typeof switchMainTab === 'function') {
            // Determine mode from tab
            const AI_TABS = ['chat','agents','agent-corp','schedule','photo','audio'];
            if (AI_TABS.includes(tab)) {
                if (typeof setDashboardMode === 'function') setDashboardMode('ai');
            }
            switchMainTab(tab);
        }

        // Optionally pass along context (e.g. thread_id) to the target system
        if (context) {
            // Dispatch a custom event so feature modules can handle deep-linking
            window.dispatchEvent(new CustomEvent('notif-navigate', {
                detail: { tab, context }
            }));
        }
    }

    // ── Dismiss ────────────────────────────────────────────────────────
    async function _dismiss(id, rowEl) {
        // Optimistic UI
        _active = _active.filter(n => n.id !== id);
        if (rowEl) {
            rowEl.style.transition = 'opacity 0.2s, transform 0.2s';
            rowEl.style.opacity = '0';
            rowEl.style.transform = 'translateX(20px)';
            setTimeout(() => rowEl.remove(), 220);
        }
        _updateBadge();
        _checkEmpty();

        // API call
        try {
            await fetch(`/api/notifications/${encodeURIComponent(id)}/dismiss`, { method: 'POST' });
        } catch (err) {
            console.warn('[Notifications] dismiss failed:', err);
        }
    }

    // ── Render list ────────────────────────────────────────────────────
    function _renderActive() {
        if (!listEl) return;
        listEl.innerHTML = '';

        if (_active.length === 0) {
            listEl.appendChild(_makeEmpty());
            return;
        }

    _active.forEach(n => {
        if (!_isHidden(n.source)) {
            const row = _buildRow(n, false);
            listEl.appendChild(row);
            _highlightRow(row);
        }
    });
}

function _highlightRow(row) {
    if (typeof hljs !== 'undefined') {
        row.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
    }
}

function _isHidden(source) {
    if (typeof prefs === 'undefined' || !source) return false;
    const hidden = prefs.get(`notification_hidden_${source}`, false);
    return hidden === true || hidden === 'true';
}

    function _makeEmpty() {
        const div = document.createElement('div');
        div.className = 'notif-empty';
        div.innerHTML = `<i class="fas fa-check-circle"></i><p>All caught up!</p>`;
        return div;
    }

    function _checkEmpty() {
        if (!listEl) return;
        if (listEl.querySelectorAll('.notif-row').length === 0) {
            if (!listEl.querySelector('.notif-empty')) {
                listEl.appendChild(_makeEmpty());
            }
        }
    }

    // ── Badge ──────────────────────────────────────────────────────────
    function _updateBadge() {
        if (!badge) return;
        // Count only non-hidden active notifications
        const count = _active.filter(n => !_isHidden(n.source)).length;
        badge.textContent = count > 99 ? '99+' : String(count);
        badge.classList.toggle('visible', count > 0);
        if (bellBtn) bellBtn.classList.toggle('has-unread', count > 0);
    }

    // ── Panel toggle ───────────────────────────────────────────────────
    function openPanel() {
        if (!panel) return;
        _panelOpen = true;
        panel.classList.add('open');
        _renderActive();
        _updateBadge();
    }

    function closePanel() {
        if (!panel) return;
        _panelOpen = false;
        panel.classList.remove('open');
    }

    function togglePanel() {
        _panelOpen ? closePanel() : openPanel();
    }

    // ── API fetch ──────────────────────────────────────────────────────
    async function _fetchActive() {
        try {
            const res = await fetch('/api/notifications/active');
            if (!res.ok) return;
            const data = await res.json();
            // Merge: add any server notifications not yet in local state
            const existingIds = new Set(_active.map(n => n.id));
            let added = 0;
            data.forEach(n => {
                if (!existingIds.has(n.id)) {
                    _active.push(n);
                    added++;
                }
            });
            if (added > 0) {
                _updateBadge();
                if (_panelOpen) _renderActive();
            }
        } catch (err) {
            // silently fail — server may be starting up
        }
    }

    async function _loadHistory() {
        if (!listEl) return;
        listEl.innerHTML = '<div class="notif-empty"><i class="fas fa-spinner fa-spin"></i><p>Loading...</p></div>';
        try {
            const res = await fetch('/api/notifications/history?days=7');
            if (!res.ok) throw new Error(res.status);
            const data = await res.json();

            listEl.innerHTML = '';
            if (data.length === 0) {
                listEl.appendChild(_makeEmpty());
                return;
            }
            data.forEach(n => {
                const row = _buildRow(n, true);
                listEl.appendChild(row);
                _highlightRow(row);
            });
        } catch (err) {
            listEl.innerHTML = '<div class="notif-empty"><i class="fas fa-exclamation-circle"></i><p>Failed to load history</p></div>';
        }
    }

    async function _clearAll() {
        try {
            await fetch('/api/notifications/active/clear', { method: 'DELETE' });
            _active = [];
            _updateBadge();
            _renderActive();
        } catch (err) {
            console.warn('[Notifications] clear all failed:', err);
        }
    }

    // ── Public push (JS-side) ──────────────────────────────────────────
    /**
     * Push a notification from JavaScript.
     * @param {Object} notif - { title, message, source?, level?, target? }
     * target: { tab: "agents", context: "..." }
     */
    async function push({ title, message, source = 'system', level = 'info', target = null }) {
        try {
            const body = { title, message, source, level };
            if (target) body.target = target;

            const res = await fetch('/api/notifications/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (res.ok) {
                const notif = await res.json();
                _active.unshift(notif);
                
                // If not hidden, update UI immediately
                if (!_isHidden(notif.source)) {
                    _updateBadge();
                    if (_panelOpen) _renderActive();
                } else {
                    // Still update badge if panel is closed to ensure consistency
                    _updateBadge();
                }
                return notif;
            }
        } catch (err) {
            console.warn('[Notifications] push failed:', err);
        }
    }

    // ── DOM Construction ───────────────────────────────────────────────
    function _buildPanel() {
        const el = document.createElement('div');
        el.className = 'notif-panel';
        el.id = 'notif-panel';
        el.innerHTML = `
            <div class="notif-panel-header">
                <div class="notif-panel-title">
                    <i class="fas fa-bell"></i>
                    Notifications
                </div>
                <div class="notif-panel-actions">
                    <button class="notif-panel-clear-btn" id="notif-clear-btn" title="Clear all">Clear all</button>
                </div>
            </div>
            <div class="notif-list" id="notif-list"></div>
            <div class="notif-panel-footer">
                <div class="notif-footer-tab-bar">
                    <button class="notif-footer-tab active" id="notif-tab-active">Active</button>
                    <button class="notif-footer-tab" id="notif-tab-history">History (7d)</button>
                </div>
            </div>
        `;
        document.body.appendChild(el);
        return el;
    }

    function _buildBell() {
        const btn = document.createElement('button');
        btn.className = 'notif-bell-btn';
        btn.id = 'notif-bell-btn';
        btn.title = 'Notifications';
        btn.innerHTML = `<i class="fas fa-bell"></i><span class="notif-badge" id="notif-badge"></span>`;
        return btn;
    }

    // ── Init ───────────────────────────────────────────────────────────
    function init() {
        // Build bell button and insert before the status indicator
        bellBtn = _buildBell();
        badge = bellBtn.querySelector('.notif-badge');

        const statusIndicator = document.getElementById('nexus-status-indicator');
        if (statusIndicator && statusIndicator.parentNode) {
            statusIndicator.parentNode.insertBefore(bellBtn, statusIndicator);
        } else {
            // Fallback: append to header-right if available
            const headerRight = document.querySelector('.header-right');
            if (headerRight) headerRight.prepend(bellBtn);
        }

        // Build panel
        panel = _buildPanel();
        listEl = document.getElementById('notif-list');

        // Bell click
        bellBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            togglePanel();
        });

        // Clear all
        document.getElementById('notif-clear-btn')?.addEventListener('click', _clearAll);

        // Tab switching
        const tabActive = document.getElementById('notif-tab-active');
        const tabHistory = document.getElementById('notif-tab-history');

        tabActive?.addEventListener('click', () => {
            tabActive.classList.add('active');
            tabHistory?.classList.remove('active');
            _viewMode = 'active';
            _renderActive();
        });

        tabHistory?.addEventListener('click', () => {
            tabHistory.classList.add('active');
            tabActive?.classList.remove('active');
            _viewMode = 'history';
            _loadHistory();
        });

        // Close panel when clicking outside
        document.addEventListener('click', (e) => {
            if (_panelOpen && !panel.contains(e.target) && e.target !== bellBtn && !bellBtn.contains(e.target)) {
                closePanel();
            }
        });

        // Initial data load
        _fetchActive().then(() => _updateBadge());

        // Poll every 30s for server-side pushes (e.g. from scheduled tasks)
        _pollInterval = setInterval(_fetchActive, POLL_MS);

        console.log('[Notifications] Initialized');
    }

    // Auto-init on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // ── Public API ─────────────────────────────────────────────────────
    return {
        push,
        open: openPanel,
        close: closePanel,
        toggle: togglePanel,
        refresh: _fetchActive,
    };
})();
