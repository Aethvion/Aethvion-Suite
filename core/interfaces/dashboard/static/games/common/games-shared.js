/**
 * Aethvion Suite — Shared Games Framework (JS)
 * 
 * Provides the base GameSession class and shared utility functions.
 * Each game module registers itself via registerGame().
 */

// ─── Session API ──────────────────────────────────────────────────────────────

class GameSession {
    constructor() {
        this.sessionId = null;
        this.maxAttempts = 10;
        this.attempts = 0;
        this.history = [];
        this.completed = false;
        this.score = 0;
        this.hint = "";
        this.modelUsed = "auto";
    }
}

// ─── Global state per game (keyed by game type) ───────────────────────────────
const gameSessions = {};

// ─── API helpers ──────────────────────────────────────────────────────────────

async function gameApiPost(endpoint, body) {
    const res = await fetch(`/api/games/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    return await res.json();
}

async function gameApiFetch(endpoint) {
    const res = await fetch(`/api/games/${endpoint}`);
    return await res.json();
}

// ─── Model list loader ────────────────────────────────────────────────────────

let _cachedModels = null;

async function loadGameModels(selectEl) {
    if (!selectEl) return;

    if (!_cachedModels) {
        try {
            // Fetch directly from the main registry to get the same exact data as the chat (including profiles)
            const res = await fetch('/api/registry/models/chat');
            _cachedModels = await res.json();
        } catch (e) {
            _cachedModels = { models: [], chat_profiles: {} };
        }
    }

    if (typeof generateCategorizedModelOptions === 'function') {
        // Generate the identical <optgroup> architecture as the chat dropdown
        selectEl.innerHTML = generateCategorizedModelOptions(_cachedModels, 'chat', 'auto');
    } else {
        // Fallback
        const models = _cachedModels.models || [];
        selectEl.innerHTML = models.map(m =>
            `<option value="${m.id}">${m.id === 'auto' ? '⚡ Auto' : m.id}</option>`
        ).join('');
    }
}

// ─── Shared UI helpers ────────────────────────────────────────────────────────

function renderHistory(container, history) {
    if (!container) return;
    if (!history || history.length === 0) {
        container.innerHTML = '<div class="placeholder-text" style="padding:0.5rem;">No tests yet</div>';
        return;
    }
    container.innerHTML = history.map(item => `
        <div class="history-item">
            <div class="history-input">IN &nbsp;→ ${escapeHtml(String(item.input))}</div>
            <div class="history-output">OUT → ${escapeHtml(String(item.output))}</div>
            ${item.comment ? `<div class="history-comment">${escapeHtml(item.comment)}</div>` : ''}
        </div>
    `).join('');
    container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function setGameDisplay(el, text, type = '') {
    if (!el) return;
    el.textContent = text;
    el.className = 'lq-display' + (type ? ` ${type}` : '');
}

function showGameOverlay(gameType, data) {
    const el = document.getElementById(`game-overlay-${gameType}`);
    if (!el) return;

    const titleEl = el.querySelector('.overlay-title');
    const subtitleEl = el.querySelector('.overlay-subtitle');
    const scoreEl = el.querySelector('.overlay-score');

    if (titleEl) titleEl.textContent = data.title || 'SOLVED';
    if (subtitleEl) subtitleEl.textContent = data.subtitle || '';
    if (scoreEl && data.score !== undefined) scoreEl.textContent = `Score: ${data.score}`;

    el.style.display = 'flex';
}

function hideGameOverlay(gameType) {
    const el = document.getElementById(`game-overlay-${gameType}`);
    if (el) el.style.display = 'none';
}

// ─── Registration system for games ───────────────────────────────────────────

const _gameRegistry = {};
const _gameLoaded = new Set();

function registerGame(gameType, { onLoad, onTabSwitch }) {
    _gameRegistry[gameType] = { onLoad, onTabSwitch };
}

// Called by core.js when tab switches to a game panel
function handleGameTabSwitch(gameType) {
    const reg = _gameRegistry[gameType];
    if (!reg) return;
    // onLoad may not have fired yet if partial hadn't loaded on first switch
    if (reg.onLoad && !_gameLoaded.has(gameType)) {
        _gameLoaded.add(gameType);
        reg.onLoad();
    }
    if (reg.onTabSwitch) reg.onTabSwitch();
}

// Call onLoad when a game partial is first injected into the DOM
document.addEventListener('panelLoaded', function (e) {
    const panelId = e.detail.panelId; // e.g. "game-sudoku-panel"
    const gameType = panelId.replace('game-', '').replace('-panel', '');
    const reg = _gameRegistry[gameType];
    if (reg && reg.onLoad && !_gameLoaded.has(gameType)) {
        _gameLoaded.add(gameType);
        reg.onLoad();
    }
});

// Expose to core.js
window.handleGameTabSwitch = handleGameTabSwitch;
