'use strict';
/**
 * Aethvion Suite — Global Command Palette (Ctrl+K / Cmd+K)
 * Provides fuzzy search over tabs, actions, and recent threads.
 */
const CommandPalette = (() => {
    let overlay, input, results, selectedIdx = -1;
    let allItems = [];

    // ── Tab registry built from sidebar DOM ──────────────────────────────────
    function buildTabItems() {
        const tabs = document.querySelectorAll('[data-maintab]');
        return Array.from(tabs).map(btn => ({
            type: 'tab',
            id: btn.dataset.maintab,
            title: (btn.querySelector('.tab-label') || btn).textContent.trim() || btn.dataset.maintab,
            icon: btn.querySelector('.tab-icon')?.textContent.trim() || '🔲',
            subtitle: 'Navigate to tab',
            action() {
                if (typeof switchMainTab === 'function') {
                    switchMainTab(this.id);
                } else {
                    document.querySelector(`[data-maintab="${this.id}"]`)?.click();
                }
            }
        }));
    }

    // ── Built-in actions ──────────────────────────────────────────────────────
    const ACTIONS = [
        { type: 'action', id: 'new-thread',   title: 'New Chat Thread',      icon: '✏️',  subtitle: 'Start a fresh conversation',
          action() { if (typeof createNewThread === 'function') createNewThread(); } },
        { type: 'action', id: 'toggle-theme', title: 'Toggle Light/Dark Theme', icon: '🌓', subtitle: 'Switch colour theme',
          action() { document.getElementById('theme-toggle')?.click(); } },
        { type: 'action', id: 'focus-chat',   title: 'Focus Chat Input',     icon: '🎯',  subtitle: 'Jump to the message input',
          action() { document.querySelector('#chat-input, #message-input, textarea')?.focus(); } },
        { type: 'action', id: 'toggle-sidebar', title: 'Toggle Sidebar',     icon: '📌',  subtitle: 'Show / hide the sidebar',
          action() { document.getElementById('sidebar-toggle')?.click(); } },
        { type: 'action', id: 'shortcuts',    title: 'Keyboard Shortcuts',   icon: '⌨️',  subtitle: 'Show all keyboard shortcuts',
          action() { const m = document.getElementById('shortcuts-modal') || document.getElementById('kbd-overlay'); if (m) { m.classList.remove('hidden'); m.style.display = ''; } } },
    ];

    // ── Simple fuzzy match — returns a score (higher = better) or -1 ─────────
    function fuzzyScore(query, text) {
        if (!query) return 1;
        query = query.toLowerCase();
        text  = text.toLowerCase();
        if (text.includes(query)) return 100 - (text.indexOf(query));
        let qi = 0, score = 0;
        for (let ci = 0; ci < text.length && qi < query.length; ci++) {
            if (text[ci] === query[qi]) { score += (qi === 0 ? 10 : 1); qi++; }
        }
        return qi === query.length ? score : -1;
    }

    // ── Highlight matched characters in title ─────────────────────────────────
    function highlight(query, text) {
        if (!query) return _esc(text);
        const lower = text.toLowerCase(), ql = query.toLowerCase();
        if (lower.includes(ql)) {
            const s = lower.indexOf(ql);
            return _esc(text.slice(0, s)) +
                   `<span class="cmd-item-mark">${_esc(text.slice(s, s + ql.length))}</span>` +
                   _esc(text.slice(s + ql.length));
        }
        let res = '', qi = 0;
        for (let ci = 0; ci < text.length; ci++) {
            if (qi < ql.length && text[ci].toLowerCase() === ql[qi]) {
                res += `<span class="cmd-item-mark">${_esc(text[ci])}</span>`; qi++;
            } else {
                res += _esc(text[ci]);
            }
        }
        return res;
    }

    function _esc(s) {
        return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    // ── Render results ────────────────────────────────────────────────────────
    function render(query) {
        results.innerHTML = '';
        const q = query.trim();
        const tabItems   = buildTabItems();
        const actionItems = ACTIONS;
        let recentItems  = [];
        try {
            const raw = JSON.parse(localStorage.getItem('aethvion_recent_tabs') || '[]');
            recentItems = raw.slice(0, 5).map(id => {
                const t = tabItems.find(x => x.id === id);
                return t ? { ...t, subtitle: 'Recently visited' } : null;
            }).filter(Boolean);
        } catch (_) {}

        const score = item => fuzzyScore(q, item.title);

        const renderSection = (label, items) => {
            const scored = items.map(i => ({ item: i, s: score(i) }))
                                .filter(x => x.s > 0)
                                .sort((a, b) => b.s - a.s)
                                .slice(0, 8);
            if (!scored.length) return;
            const lbl = document.createElement('div');
            lbl.className = 'cmd-section-label';
            lbl.textContent = label;
            results.appendChild(lbl);
            scored.forEach(({ item }) => {
                const el = document.createElement('div');
                el.className = 'cmd-item';
                el.dataset.actionId = item.id;
                el.innerHTML = `
                    <div class="cmd-item-icon">${_esc(item.icon)}</div>
                    <div class="cmd-item-text">
                        <div class="cmd-item-title">${highlight(q, item.title)}</div>
                        <div class="cmd-item-subtitle">${_esc(item.subtitle)}</div>
                    </div>`;
                el.addEventListener('mouseenter', () => selectEl(el));
                el.addEventListener('click', () => { item.action.call(item); close(); });
                results.appendChild(el);
            });
        };

        if (!q && recentItems.length) renderSection('Recent', recentItems);
        renderSection('Tabs',    tabItems);
        renderSection('Actions', actionItems);

        if (!results.children.length) {
            results.innerHTML = `<div class="cmd-palette-empty">No results for "<strong>${_esc(q)}</strong>"</div>`;
        }
        allItems = Array.from(results.querySelectorAll('.cmd-item'));
        selectedIdx = allItems.length ? 0 : -1;
        if (selectedIdx >= 0) allItems[0].classList.add('selected');
    }

    function selectEl(el) {
        allItems.forEach(i => i.classList.remove('selected'));
        el.classList.add('selected');
        selectedIdx = allItems.indexOf(el);
    }

    function moveSelection(dir) {
        if (!allItems.length) return;
        allItems.forEach(i => i.classList.remove('selected'));
        selectedIdx = (selectedIdx + dir + allItems.length) % allItems.length;
        allItems[selectedIdx].classList.add('selected');
        allItems[selectedIdx].scrollIntoView({ block: 'nearest' });
    }

    function activateSelected() {
        if (selectedIdx >= 0 && allItems[selectedIdx]) allItems[selectedIdx].click();
    }

    // ── Open / close ──────────────────────────────────────────────────────────
    function open() {
        overlay.classList.remove('hidden');
        input.value = '';
        render('');
        input.focus();
    }

    function close() {
        overlay.classList.add('hidden');
        input.value = '';
        selectedIdx = -1;
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        overlay = document.getElementById('command-palette-overlay');
        if (!overlay) return;
        input   = overlay.querySelector('.cmd-palette-input');
        results = overlay.querySelector('.cmd-palette-results');

        input.addEventListener('input', () => render(input.value));

        input.addEventListener('keydown', e => {
            if (e.key === 'ArrowDown') { e.preventDefault(); moveSelection(1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); moveSelection(-1); }
            else if (e.key === 'Enter')  { e.preventDefault(); activateSelected(); }
            else if (e.key === 'Escape') { e.preventDefault(); close(); }
        });

        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

        document.addEventListener('keydown', e => {
            const isMac = navigator.platform.toUpperCase().includes('MAC');
            if ((isMac ? e.metaKey : e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                overlay.classList.contains('hidden') ? open() : close();
            }
        });
    }

    document.addEventListener('DOMContentLoaded', init);

    return { open, close };
})();
