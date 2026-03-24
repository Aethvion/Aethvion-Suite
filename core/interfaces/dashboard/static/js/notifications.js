'use strict';
/**
 * Aethvion Suite — Notification System
 * Polls /api/notifications, shows a bell badge, and a dropdown list.
 */
const NotificationSystem = (() => {
    const POLL_INTERVAL = 10_000;
    let dropdownOpen = false;
    let pollTimer = null;

    // ── Icon mapping ──────────────────────────────────────────────────────────
    const ICONS = {
        info:    'ℹ️',
        success: '✅',
        warning: '⚠️',
        error:   '❌',
        default: '🔔',
    };

    function iconFor(type) { return ICONS[type] || ICONS.default; }

    // ── Relative time ──────────────────────────────────────────────────────────
    function relativeTime(ts) {
        if (!ts) return '';
        const diff = Date.now() - new Date(ts).getTime();
        const s = Math.floor(diff / 1000);
        if (s < 60)  return 'just now';
        const m = Math.floor(s / 60);
        if (m < 60)  return `${m}m ago`;
        const h = Math.floor(m / 60);
        if (h < 24)  return `${h}h ago`;
        return `${Math.floor(h / 24)}d ago`;
    }

    // ── DOM helpers ───────────────────────────────────────────────────────────
    function getBell()     { return document.getElementById('notif-bell-btn'); }
    function getBadge()    { return document.getElementById('notif-badge'); }
    function getDropdown() { return document.getElementById('notif-dropdown'); }
    function getList()     { return document.getElementById('notif-list'); }

    // ── Render dropdown ───────────────────────────────────────────────────────
    function renderDropdown(notifications) {
        const list = getList();
        if (!list) return;
        list.innerHTML = '';
        if (!notifications.length) {
            list.innerHTML = '<div class="notif-empty">No notifications</div>';
            return;
        }
        notifications.forEach(n => {
            const item = document.createElement('div');
            item.className = `notif-item${n.read ? '' : ' unread'}`;
            item.innerHTML = `
                <div class="notif-item-icon">${iconFor(n.icon)}</div>
                <div class="notif-item-body">
                    <div class="notif-item-title">${_esc(n.title || '')}</div>
                    <div class="notif-item-text">${_esc(n.body || '')}</div>
                    <div class="notif-item-time">${relativeTime(n.timestamp)}</div>
                </div>
                ${n.read ? '' : '<div class="notif-unread-dot"></div>'}`;
            item.addEventListener('click', () => {
                if (!n.read) markRead(n.id);
                if (n.action_url) window.open(n.action_url, '_blank');
                closeDropdown();
            });
            list.appendChild(item);
        });
    }

    function _esc(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    // ── API calls ─────────────────────────────────────────────────────────────
    async function fetchNotifications() {
        try {
            const res = await fetch('/api/notifications');
            if (!res.ok) return;
            const data = await res.json();
            const badge = getBadge();
            const unread = data.unread_count || 0;
            if (badge) {
                badge.textContent = unread > 99 ? '99+' : String(unread);
                badge.classList.toggle('hidden', unread === 0);
            }
            if (dropdownOpen) renderDropdown(data.notifications || []);
            return data.notifications || [];
        } catch (_) { return []; }
    }

    async function markRead(id) {
        try { await fetch(`/api/notifications/${id}/read`, { method: 'POST' }); } catch (_) {}
        fetchNotifications();
    }

    async function markAllRead() {
        try { await fetch('/api/notifications/read-all', { method: 'POST' }); } catch (_) {}
        fetchNotifications();
    }

    // ── Dropdown open/close ───────────────────────────────────────────────────
    async function openDropdown() {
        dropdownOpen = true;
        const dd = getDropdown();
        if (dd) dd.classList.remove('hidden');
        const notifications = await fetchNotifications();
        renderDropdown(notifications || []);
    }

    function closeDropdown() {
        dropdownOpen = false;
        const dd = getDropdown();
        if (dd) dd.classList.add('hidden');
    }

    // ── Browser Notification permission ───────────────────────────────────────
    function requestPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        const bell = getBell();
        if (!bell) return;

        bell.addEventListener('click', e => {
            e.stopPropagation();
            dropdownOpen ? closeDropdown() : openDropdown();
        });

        // Read-all button
        document.getElementById('notif-read-all')?.addEventListener('click', e => {
            e.stopPropagation();
            markAllRead();
        });

        // Close when clicking outside
        document.addEventListener('click', e => {
            if (dropdownOpen && !document.getElementById('notif-wrapper')?.contains(e.target)) {
                closeDropdown();
            }
        });

        requestPermission();
        fetchNotifications();
        pollTimer = setInterval(fetchNotifications, POLL_INTERVAL);
    }

    document.addEventListener('DOMContentLoaded', init);

    return { open: openDropdown, close: closeDropdown, refresh: fetchNotifications };
})();
