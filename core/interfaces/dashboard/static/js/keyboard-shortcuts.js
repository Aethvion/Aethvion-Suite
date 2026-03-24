'use strict';
/**
 * Aethvion Suite — Global Keyboard Shortcuts
 *
 * Shortcut table:
 *   Ctrl/Cmd+K   → Open command palette
 *   Ctrl+N       → New chat thread
 *   Ctrl+Enter   → Send message (when chat input focused)
 *   Ctrl+/       → Focus chat input
 *   Alt+1..9     → Switch to tab N in sidebar
 *   ?            → Open shortcut reference modal (when input not focused)
 */
const KeyboardShortcuts = (() => {

    function isInputFocused() {
        const el = document.activeElement;
        if (!el) return false;
        return el.tagName === 'INPUT' ||
               el.tagName === 'TEXTAREA' ||
               el.isContentEditable;
    }

    function getChatInput() {
        return document.querySelector('#chat-input, #message-input, .chat-input textarea, textarea[placeholder]');
    }

    function getSidebarTabs() {
        // Returns visible (non-cloned) tab buttons in DOM order, skipping pinned clones
        return Array.from(document.querySelectorAll('[data-maintab]:not([data-pinned-clone])'));
    }

    // ── Shortcut modal ────────────────────────────────────────────────────────
    function openShortcutsModal() {
        // Prefer the existing kbd-overlay if present
        const existing = document.getElementById('kbd-overlay');
        if (existing) {
            existing.style.display = '';
            existing.classList.remove('hidden');
            return;
        }
        const modal = document.getElementById('shortcuts-modal');
        if (modal) {
            modal.classList.remove('hidden');
            modal.style.display = '';
        }
    }

    function closeShortcutsModal() {
        const existing = document.getElementById('kbd-overlay');
        if (existing) { existing.style.display = 'none'; return; }
        const modal = document.getElementById('shortcuts-modal');
        if (modal) modal.classList.add('hidden');
    }

    // ── Main handler ──────────────────────────────────────────────────────────
    function handleKeyDown(e) {
        const isMac   = navigator.platform.toUpperCase().includes('MAC');
        const ctrlKey = isMac ? e.metaKey : e.ctrlKey;
        const altKey  = e.altKey;

        // Ctrl/Cmd+K → command palette (handled in command-palette.js, but guard here too)
        if (ctrlKey && e.key === 'k') {
            // command-palette.js owns this; do nothing to avoid double-handling
            return;
        }

        // Ctrl+N → New thread
        if (ctrlKey && e.key === 'n') {
            e.preventDefault();
            if (typeof createNewThread === 'function') createNewThread();
            return;
        }

        // Ctrl+Enter → Send message
        if (ctrlKey && e.key === 'Enter') {
            const chatInput = getChatInput();
            if (chatInput && document.activeElement === chatInput) {
                e.preventDefault();
                // Trigger send: look for a send button or form submit
                const form = chatInput.closest('form');
                if (form) {
                    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                } else {
                    const sendBtn = document.querySelector('#send-btn, button[type="submit"], .send-btn');
                    if (sendBtn) sendBtn.click();
                }
            }
            return;
        }

        // Ctrl+/ → Focus chat input
        if (ctrlKey && e.key === '/') {
            e.preventDefault();
            const chatInput = getChatInput();
            if (chatInput) { chatInput.focus(); chatInput.select?.(); }
            return;
        }

        // Alt+1..9 → Switch to sidebar tab N
        if (altKey && e.key >= '1' && e.key <= '9') {
            e.preventDefault();
            const tabs = getSidebarTabs();
            const idx  = parseInt(e.key, 10) - 1;
            if (tabs[idx]) tabs[idx].click();
            return;
        }

        // ? → Open shortcut modal (only when no input is focused)
        if (e.key === '?' && !isInputFocused()) {
            e.preventDefault();
            openShortcutsModal();
            return;
        }

        // Esc → Close shortcut modal (also close command palette / notif dropdown)
        if (e.key === 'Escape') {
            closeShortcutsModal();
            // Let command-palette.js handle its own Esc via input keydown listener
            return;
        }
    }

    function init() {
        document.addEventListener('keydown', handleKeyDown);
    }

    document.addEventListener('DOMContentLoaded', init);

    return { openShortcutsModal, closeShortcutsModal };
})();
