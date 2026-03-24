'use strict';
/**
 * Aethvion Suite — Sidebar Tab Pinning & Custom Order
 * Allows users to pin favourite tabs so they appear at the top of the sidebar.
 * Preferences are saved to localStorage key "aethvion_tab_prefs".
 */
const SidebarPrefs = (() => {
    const LS_KEY = 'aethvion_tab_prefs';

    function loadPrefs() {
        try {
            const raw = localStorage.getItem(LS_KEY);
            if (raw) return JSON.parse(raw);
        } catch (_) {}
        return { pinned: [] };
    }

    function savePrefs(prefs) {
        localStorage.setItem(LS_KEY, JSON.stringify(prefs));
    }

    // ── Build the pinned section ──────────────────────────────────────────────
    function buildPinnedSection(mainTabsEl, prefs) {
        // Remove any existing pinned section
        document.getElementById('pinned-tabs-section')?.remove();

        if (!prefs.pinned.length) return;

        const section = document.createElement('div');
        section.id = 'pinned-tabs-section';
        section.className = 'pinned-tabs-section';
        section.innerHTML = '<div class="pinned-tabs-label">★ Pinned</div>';

        prefs.pinned.forEach(tabId => {
            const original = mainTabsEl.querySelector(`[data-maintab="${tabId}"]`);
            if (!original) return;
            const clone = original.cloneNode(true);
            clone.classList.add('pinned-clone');
            clone.dataset.pinnedClone = 'true';
            // Remove any existing pin buttons from clone to avoid duplication
            clone.querySelectorAll('.pin-btn').forEach(b => b.remove());
            // Clone click → delegate to original
            clone.addEventListener('click', e => {
                if (e.target.closest('.pin-btn')) return;
                original.click();
            });
            section.appendChild(clone);
        });

        const divider = document.createElement('div');
        divider.className = 'pinned-tabs-divider';
        section.appendChild(divider);

        mainTabsEl.insertBefore(section, mainTabsEl.firstChild);
    }

    // ── Attach pin buttons to all real tab buttons ────────────────────────────
    function attachPinButtons(mainTabsEl, prefs) {
        const tabs = mainTabsEl.querySelectorAll('[data-maintab]:not([data-pinned-clone])');
        tabs.forEach(tab => {
            if (tab.querySelector('.pin-btn')) return; // already has one
            const tabId = tab.dataset.maintab;
            const pinBtn = document.createElement('button');
            pinBtn.className = 'pin-btn';
            pinBtn.title = 'Pin / Unpin tab';
            pinBtn.setAttribute('aria-label', 'Pin tab');
            pinBtn.innerHTML = '★';
            updatePinBtnState(pinBtn, prefs, tabId);

            pinBtn.addEventListener('click', e => {
                e.stopPropagation();
                togglePin(tabId);
            });

            tab.appendChild(pinBtn);
        });
    }

    function updatePinBtnState(btn, prefs, tabId) {
        const pinned = prefs.pinned.includes(tabId);
        btn.classList.toggle('pinned', pinned);
        btn.title = pinned ? 'Unpin tab' : 'Pin tab';
    }

    // ── Toggle pin state ──────────────────────────────────────────────────────
    function togglePin(tabId) {
        const prefs = loadPrefs();
        const idx = prefs.pinned.indexOf(tabId);
        if (idx >= 0) {
            prefs.pinned.splice(idx, 1);
        } else {
            prefs.pinned.unshift(tabId);
        }
        savePrefs(prefs);
        applyPrefs();
    }

    // ── Apply saved preferences to the DOM ────────────────────────────────────
    function applyPrefs() {
        const mainTabsEl = document.querySelector('.main-tabs');
        if (!mainTabsEl) return;
        const prefs = loadPrefs();
        buildPinnedSection(mainTabsEl, prefs);
        attachPinButtons(mainTabsEl, prefs);
        // Refresh pin button states
        mainTabsEl.querySelectorAll('[data-maintab]:not([data-pinned-clone]) .pin-btn').forEach(btn => {
            const tabId = btn.closest('[data-maintab]')?.dataset.maintab;
            if (tabId) updatePinBtnState(btn, prefs, tabId);
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        applyPrefs();
        // Inject CSS for pin buttons inline (keeps CSS co-located)
        if (!document.getElementById('sidebar-prefs-style')) {
            const style = document.createElement('style');
            style.id = 'sidebar-prefs-style';
            style.textContent = `
.pin-btn {
    display: none;
    background: transparent;
    border: none;
    cursor: pointer;
    color: var(--text-tertiary);
    font-size: 0.75rem;
    padding: 2px 4px;
    margin-left: auto;
    flex-shrink: 0;
    border-radius: 4px;
    line-height: 1;
    transition: color 0.15s, background 0.15s;
}
[data-maintab]:hover .pin-btn,
.pin-btn.pinned {
    display: inline-flex;
}
.pin-btn:hover { background: rgba(99,102,241,0.15); }
.pin-btn.pinned { color: var(--warning); }

.pinned-tabs-section { margin-bottom: 4px; }
.pinned-tabs-label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-tertiary);
    padding: 6px 12px 2px;
    font-weight: 600;
}
.pinned-tabs-divider {
    height: 1px;
    background: var(--border);
    margin: 4px 8px 6px;
}
.pinned-clone { opacity: 0.92; }
            `;
            document.head.appendChild(style);
        }
    }

    document.addEventListener('DOMContentLoaded', init);

    return { togglePin, applyPrefs };
})();
