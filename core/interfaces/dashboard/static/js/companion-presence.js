'use strict';
/**
 * Aethvion Suite — Global Companion Presence & Floating Message Engine
 *
 * Runs across the entire suite from startup:
 * - Evaluates "On Startup" proactive check-in rules (hours away, chance, min/max delay)
 * - Runs a global session heartbeat for idle proactive check-ins across all enabled companions
 * - Displays an interactive Floating Companion Message Card with avatar/expression, mood badge,
 *   TTS voice playback, Quick Inline Reply, and "Open in Companions" deep-linking
 */

window.AethvionCompanionPresence = (() => {
    const CREATOR_API = '/api/companion-creator';
    const CHAT_API    = '/api/companions';

    let _companions = [];
    let _lastInteractionTs = Date.now();
    let _sessionTargetMin = null;
    let _heartbeatTimer = null;
    let _startupChecked = false;
    let _popupEl = null;
    let _activePopupCompanion = null;
    let _popupHistory = [];
    let _popupStreaming = false;
    let _popupAudio = null;

    function _esc(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function _prefGet(key, defaultVal) {
        return window.prefs?.get?.(key, defaultVal) ?? defaultVal;
    }

    function _injectStyles() {
        if (document.getElementById('cc-presence-styles')) return;
        const style = document.createElement('style');
        style.id = 'cc-presence-styles';
        style.textContent = `
            .cc-float-popup {
                position: fixed;
                right: 22px;
                bottom: 22px;
                width: 380px;
                max-width: calc(100vw - 32px);
                background: var(--bg-secondary, #111827);
                border: 1px solid rgba(99, 102, 241, 0.38);
                border-radius: 16px;
                box-shadow: 0 20px 48px rgba(0, 0, 0, 0.6), 0 0 24px rgba(99, 102, 241, 0.16);
                z-index: 9500;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                animation: ccFloatSlideIn 0.26s cubic-bezier(0.16, 1, 0.3, 1);
                color: var(--text-primary, #f8fafc);
                font-family: inherit;
            }
            @keyframes ccFloatSlideIn {
                from { opacity: 0; transform: translateY(20px) scale(0.97); }
                to   { opacity: 1; transform: translateY(0) scale(1); }
            }
            .cc-float-hdr {
                display: flex;
                align-items: center;
                gap: 0.7rem;
                padding: 0.75rem 0.9rem;
                background: rgba(15, 23, 42, 0.65);
                border-bottom: 1px solid var(--border, rgba(148, 163, 184, 0.16));
            }
            .cc-float-avatar {
                width: 44px;
                height: 44px;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.3rem;
                font-weight: 700;
                flex-shrink: 0;
                overflow: hidden;
            }
            .cc-float-avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }
            .cc-float-meta {
                flex: 1;
                min-width: 0;
            }
            .cc-float-name-row {
                display: flex;
                align-items: center;
                gap: 0.45rem;
            }
            .cc-float-name {
                font-size: 0.9rem;
                font-weight: 700;
                color: var(--text-primary, #f8fafc);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .cc-float-badges {
                display: flex;
                align-items: center;
                gap: 0.35rem;
                margin-top: 0.18rem;
                flex-wrap: wrap;
            }
            .cc-float-pill {
                display: inline-flex;
                align-items: center;
                gap: 0.25rem;
                font-size: 0.66rem;
                font-weight: 600;
                padding: 0.1rem 0.42rem;
                border-radius: 999px;
                background: rgba(99, 102, 241, 0.14);
                color: #a5b4fc;
                border: 1px solid rgba(99, 102, 241, 0.28);
            }
            .cc-float-hdr-actions {
                display: flex;
                align-items: center;
                gap: 0.25rem;
                flex-shrink: 0;
            }
            .cc-float-icon-btn {
                width: 28px;
                height: 28px;
                border-radius: 7px;
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-secondary, #94a3b8);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 0.78rem;
                transition: background 0.14s, color 0.14s, border-color 0.14s;
            }
            .cc-float-icon-btn:hover {
                background: rgba(148, 163, 184, 0.14);
                color: var(--text-primary, #f8fafc);
                border-color: var(--border, rgba(148, 163, 184, 0.2));
            }
            .cc-float-body {
                padding: 0.85rem 0.95rem;
                max-height: 240px;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 0.55rem;
                font-size: 0.84rem;
                line-height: 1.5;
            }
            .cc-float-msg {
                padding: 0.6rem 0.75rem;
                border-radius: 11px;
                background: rgba(30, 41, 59, 0.75);
                border: 1px solid rgba(148, 163, 184, 0.14);
                color: var(--text-primary, #f1f5f9);
                word-break: break-word;
            }
            .cc-float-msg p { margin: 0 0 0.4rem; }
            .cc-float-msg p:last-child { margin-bottom: 0; }
            .cc-float-msg-user {
                align-self: flex-end;
                background: rgba(99, 102, 241, 0.22);
                border-color: rgba(99, 102, 241, 0.38);
                max-width: 88%;
            }
            .cc-float-reply-bar {
                display: flex;
                align-items: center;
                gap: 0.45rem;
                padding: 0.6rem 0.8rem;
                border-top: 1px solid var(--border, rgba(148, 163, 184, 0.16));
                background: rgba(15, 23, 42, 0.45);
            }
            .cc-float-input {
                flex: 1;
                background: var(--bg-primary, #0b0d14);
                border: 1px solid var(--border, rgba(148, 163, 184, 0.22));
                border-radius: 8px;
                padding: 0.42rem 0.65rem;
                color: var(--text-primary, #f8fafc);
                font-size: 0.8rem;
                outline: none;
            }
            .cc-float-input:focus {
                border-color: var(--accent, #6366f1);
            }
            .cc-float-send-btn {
                width: 32px;
                height: 32px;
                border-radius: 8px;
                border: none;
                background: var(--accent, #6366f1);
                color: #fff;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 0.78rem;
                flex-shrink: 0;
                transition: filter 0.14s;
            }
            .cc-float-send-btn:hover { filter: brightness(1.12); }
            .cc-float-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        `;
        document.head.appendChild(style);
    }

    function _renderMd(text) {
        if (!text) return '';
        if (typeof marked !== 'undefined' && marked.parse) {
            try { return marked.parse(text); } catch {}
        }
        return _esc(text).replace(/\n/g, '<br>');
    }

    function _avatarHtml(data) {
        const cid   = data.companion_id || data.id;
        const color = data.accent_color || '#6366f1';
        const expr  = data.expression || 'default';
        const exprImgs = data.expression_images || {};
        if (data.icon_mode && exprImgs[expr] && cid) {
            return `<div class="cc-float-avatar"><img src="${CREATOR_API}/${cid}/expression/${_esc(expr)}?t=${Date.now()}" alt="${_esc(data.name)}"></div>`;
        }
        if (data.has_icon && cid) {
            return `<div class="cc-float-avatar"><img src="${CREATOR_API}/${cid}/icon?t=${Date.now()}" alt="${_esc(data.name)}"></div>`;
        }
        return `<div class="cc-float-avatar" style="background:${_esc(color)}22;color:${_esc(color)};border:1px solid ${_esc(color)}44">${_esc(data.avatar_symbol || '✦')}</div>`;
    }

    function _speakPopupMessage(text, voiceCfg) {
        if (window.AethvionVoice && typeof window.AethvionVoice.speak === 'function') {
            window.AethvionVoice.speak(text, voiceCfg);
            return;
        }
        if (typeof window.speechSynthesis !== 'undefined' && text) {
            try {
                window.speechSynthesis.cancel();
                const u = new SpeechSynthesisUtterance(text);
                u.rate = parseFloat(voiceCfg?.speed || 1.0);
                window.speechSynthesis.speak(u);
            } catch {}
        }
    }

    function closePopup() {
        if (_popupEl) {
            _popupEl.remove();
            _popupEl = null;
        }
        _activePopupCompanion = null;
        _popupHistory = [];
    }

    async function openCompanionInHub(companionId) {
        closePopup();
        if (typeof window.switchMainTab === 'function') {
            await window.switchMainTab('companion-creator');
        }
        if (window.CompanionCreator && typeof window.CompanionCreator.openCompanion === 'function') {
            window.CompanionCreator.openCompanion(companionId);
        } else {
            try {
                localStorage.setItem('cc_last_companion', JSON.stringify({
                    id: companionId,
                    isBuiltin: ['axiom', 'lyra', 'misakacipher'].includes(companionId)
                }));
            } catch {}
        }
    }

    function showPopup(payload) {
        if (!payload || !payload.response) return;
        _injectStyles();

        const cid = payload.companion_id || payload.id;
        _activePopupCompanion = payload;
        _popupHistory = [{ role: 'assistant', content: payload.response }];

        if (_popupEl) _popupEl.remove();

        const color = payload.accent_color || '#6366f1';
        const el = document.createElement('div');
        el.id = 'cc-floating-popup';
        el.className = 'cc-float-popup';
        el.style.borderColor = `${color}66`;

        el.innerHTML = `
          <div class="cc-float-hdr">
            <div id="cc-float-avatar-wrap">${_avatarHtml(payload)}</div>
            <div class="cc-float-meta">
              <div class="cc-float-name-row">
                <span class="cc-float-name">${_esc(payload.name || cid)}</span>
              </div>
              <div class="cc-float-badges">
                <span class="cc-float-pill" id="cc-float-mood-pill"><i class="fas fa-sparkles"></i> ${_esc(payload.mood || 'calm')}</span>
                <span class="cc-float-pill" id="cc-float-expr-pill"><i class="fas fa-masks-theater"></i> ${_esc(payload.expression || 'default')}</span>
              </div>
            </div>
            <div class="cc-float-hdr-actions">
              <button type="button" class="cc-float-icon-btn" id="cc-float-speak-btn" title="Listen (TTS)">
                <i class="fas fa-volume-high"></i>
              </button>
              <button type="button" class="cc-float-icon-btn" id="cc-float-open-btn" title="Open in Companions Hub">
                <i class="fas fa-arrow-up-right-from-square"></i>
              </button>
              <button type="button" class="cc-float-icon-btn" id="cc-float-close-btn" title="Dismiss">
                <i class="fas fa-times"></i>
              </button>
            </div>
          </div>
          <div class="cc-float-body" id="cc-float-body">
            <div class="cc-float-msg">${_renderMd(payload.response)}</div>
          </div>
          <div class="cc-float-reply-bar">
            <input type="text" id="cc-float-input" class="cc-float-input" data-slash-autocomplete="true" placeholder="Quick reply to ${_esc(payload.name || 'companion')}… (or / for connectors)" autocomplete="off">
            <button type="button" id="cc-float-send" class="cc-float-send-btn" style="background:${_esc(color)}" title="Send quick reply">
              <i class="fas fa-paper-plane"></i>
            </button>
          </div>
        `;

        document.body.appendChild(el);
        _popupEl = el;

        el.querySelector('#cc-float-close-btn')?.addEventListener('click', closePopup);
        el.querySelector('#cc-float-open-btn')?.addEventListener('click', () => openCompanionInHub(cid));
        el.querySelector('#cc-float-speak-btn')?.addEventListener('click', () => {
            const lastAssistant = [..._popupHistory].reverse().find(m => m.role === 'assistant');
            if (lastAssistant) _speakPopupMessage(lastAssistant.content, payload.voice);
        });

        const inputEl = el.querySelector('#cc-float-input');
        const sendBtn = el.querySelector('#cc-float-send');
        const sendQuickReply = async () => {
            if (_popupStreaming || !inputEl) return;
            const text = inputEl.value.trim();
            if (!text) return;
            inputEl.value = '';
            _popupStreaming = true;
            inputEl.disabled = true;
            if (sendBtn) sendBtn.disabled = true;

            const bodyEl = el.querySelector('#cc-float-body');
            const userDiv = document.createElement('div');
            userDiv.className = 'cc-float-msg cc-float-msg-user';
            userDiv.textContent = text;
            bodyEl?.appendChild(userDiv);

            const replyDiv = document.createElement('div');
            replyDiv.className = 'cc-float-msg';
            replyDiv.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Thinking…';
            bodyEl?.appendChild(replyDiv);
            if (bodyEl) bodyEl.scrollTop = bodyEl.scrollHeight;

            const histForApi = _popupHistory.slice(-6);
            _popupHistory.push({ role: 'user', content: text });

            try {
                const res = await fetch(`${CHAT_API}/${cid}/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, history: histForApi })
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const reader = res.body.getReader();
                const dec = new TextDecoder();
                let streamAcc = '';
                let finalContent = '';

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    const lines = dec.decode(value).split('\n');
                    for (const line of lines) {
                        if (!line.trim()) continue;
                        try {
                            const evt = JSON.parse(line);
                            if (evt.type === 'message' && evt.content) {
                                streamAcc += evt.content;
                                const cleaned = streamAcc
                                    .replace(/\[tool:[\s\S]*?\]/g, '')
                                    .replace(/<(?:expression|mood|break)[^>]*>[\s\S]*?<\/(?:expression|mood|break)>/gi, '')
                                    .replace(/<break\s*\/?>/gi, '\n\n')
                                    .trim();
                                if (cleaned) replyDiv.innerHTML = _renderMd(cleaned);
                            } else if (evt.type === 'done') {
                                finalContent = (evt.parts && evt.parts.length > 1)
                                    ? evt.parts.join('\n\n')
                                    : (evt.content || streamAcc);
                                if (evt.mood) {
                                    const mp = el.querySelector('#cc-float-mood-pill');
                                    if (mp) mp.innerHTML = `<i class="fas fa-sparkles"></i> ${_esc(evt.mood)}`;
                                }
                                if (evt.expression) {
                                    const ep = el.querySelector('#cc-float-expr-pill');
                                    if (ep) ep.innerHTML = `<i class="fas fa-masks-theater"></i> ${_esc(evt.expression)}`;
                                    payload.expression = evt.expression;
                                    const avWrap = el.querySelector('#cc-float-avatar-wrap');
                                    if (avWrap) avWrap.innerHTML = _avatarHtml(payload);
                                }
                            }
                        } catch {}
                    }
                    if (bodyEl) bodyEl.scrollTop = bodyEl.scrollHeight;
                }

                const shown = finalContent || streamAcc || '(no response)';
                replyDiv.innerHTML = _renderMd(shown);
                _popupHistory.push({ role: 'assistant', content: shown });

                // Notify open Companions tab if viewing this companion
                window.dispatchEvent(new CustomEvent('companionPopupConversationUpdated', {
                    detail: { companionId: cid, userMessage: text, assistantMessage: shown }
                }));

                if (payload.voice?.auto_speak) {
                    _speakPopupMessage(shown, payload.voice);
                }
            } catch (err) {
                replyDiv.textContent = `Error: ${err.message}`;
            } finally {
                _popupStreaming = false;
                inputEl.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
                inputEl.focus();
                if (bodyEl) bodyEl.scrollTop = bodyEl.scrollHeight;
            }
        };

        sendBtn?.addEventListener('click', sendQuickReply);
        inputEl?.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                if (window.AethvionSlashAutocomplete && window.AethvionSlashAutocomplete.isOpen()) return;
                e.preventDefault();
                sendQuickReply();
            }
        });

        if (payload.voice?.auto_speak) {
            _speakPopupMessage(payload.response, payload.voice);
        }
    }

    function _isProactiveEnabled(companion) {
        const cid = companion.id;
        const explicitPref = _prefGet(`${cid}.proactive_enabled`, null);
        if (explicitPref !== null && explicitPref !== undefined) return !!explicitPref;
        if (companion.capabilities?.proactive_enabled !== undefined) {
            return !!companion.capabilities.proactive_enabled;
        }
        return cid === 'misakacipher';
    }

    async function triggerProactiveForCompanion(companionId, triggerType = 'proactive') {
        try {
            const res = await fetch(`${CHAT_API}/${companionId}/initiate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trigger: triggerType })
            });
            if (!res.ok) return null;
            const data = await res.json();
            if (!data || !data.response) return null;

            // Dispatch live event for CompanionCreator if it is open
            window.dispatchEvent(new CustomEvent('companionProactiveMessage', {
                detail: { ...data, companion_id: companionId, trigger: triggerType }
            }));

            // Also push to Notification Center for history
            if (window.Notifications && typeof window.Notifications.push === 'function') {
                window.Notifications.push({
                    title: `${data.name || companionId} (${data.mood || 'check-in'})`,
                    message: data.response,
                    source: 'chat',
                    level: 'info',
                    target: { tab: 'companion-creator', context: companionId }
                });
            }

            // Show floating popup if enabled (default: true)
            const showAsPopup = _prefGet(`${companionId}.proactive_popup`, true);
            const creatorPanel = document.getElementById('companion-creator-panel');
            const isCreatorVisible = creatorPanel && creatorPanel.classList.contains('active');
            if (showAsPopup || !isCreatorVisible) {
                showPopup({ ...data, companion_id: companionId });
            }
            return data;
        } catch (err) {
            console.warn(`[CompanionPresence] Proactive initiate failed for ${companionId}:`, err);
            return null;
        }
    }

    async function _evaluateStartupCheckins() {
        if (_startupChecked) return;
        _startupChecked = true;
        try {
            const res = await fetch(`${CREATOR_API}/all`);
            if (!res.ok) return;
            const data = await res.json();
            _companions = data.companions || [];

            for (const c of _companions) {
                if (!_isProactiveEnabled(c)) continue;
                const cid = c.id;
                const minHoursAway = parseFloat(_prefGet(`${cid}.startup_trigger_hours`, 4)) || 4;
                const chancePct    = parseFloat(_prefGet(`${cid}.startup_chance`, 75)) || 75;
                const delayMinSec  = parseFloat(_prefGet(`${cid}.startup_delay_min`, 10)) || 10;
                const delayMaxSec  = Math.max(delayMinSec, parseFloat(_prefGet(`${cid}.startup_delay_max`, 45)) || 45);

                let hoursAway = 999;
                if (c.last_interaction_ts) {
                    const lastDate = new Date(c.last_interaction_ts.replace(' ', 'T'));
                    if (!isNaN(lastDate.getTime())) {
                        hoursAway = (Date.now() - lastDate.getTime()) / 3600000;
                    }
                }

                if (hoursAway >= minHoursAway && (Math.random() * 100) <= chancePct) {
                    const delayMs = (delayMinSec + Math.random() * (delayMaxSec - delayMinSec)) * 1000;
                    setTimeout(() => {
                        triggerProactiveForCompanion(cid, 'startup');
                    }, delayMs);
                    break; // Trigger at most one startup check-in per launch so popups don't stack
                }
            }
        } catch (err) {
            console.warn('[CompanionPresence] Startup check failed:', err);
        }
    }

    function _resetIdleTimer() {
        _lastInteractionTs = Date.now();
        _sessionTargetMin = null;
    }

    function _startGlobalHeartbeat() {
        if (_heartbeatTimer) clearInterval(_heartbeatTimer);
        ['keydown', 'mousedown'].forEach(evt => {
            document.addEventListener(evt, () => { _lastInteractionTs = Date.now(); }, { passive: true });
        });

        _heartbeatTimer = setInterval(async () => {
            if (_popupStreaming) return;
            try {
                const res = await fetch(`${CREATOR_API}/all`);
                if (res.ok) {
                    const d = await res.json();
                    _companions = d.companions || _companions;
                }
            } catch {}

            const enabledList = (_companions || []).filter(_isProactiveEnabled);
            if (!enabledList.length) return;

            // Pick a candidate companion (prefer last active or first enabled)
            let candidate = enabledList[0];
            try {
                const saved = JSON.parse(localStorage.getItem('cc_last_companion') || 'null');
                const found = saved?.id && enabledList.find(c => c.id === saved.id);
                if (found) candidate = found;
            } catch {}

            const cid = candidate.id;
            const minInt = parseFloat(_prefGet(`${cid}.session_interval_min`, 45)) || 45;
            const maxInt = Math.max(minInt, parseFloat(_prefGet(`${cid}.session_interval_max`, 90)) || 90);
            const chance = parseFloat(_prefGet(`${cid}.session_chance`, 60)) || 60;

            if (_sessionTargetMin === null) {
                _sessionTargetMin = minInt + Math.random() * (maxInt - minInt);
            }

            const idleMinutes = (Date.now() - _lastInteractionTs) / 60000;
            if (idleMinutes >= _sessionTargetMin) {
                _resetIdleTimer();
                if ((Math.random() * 100) <= chance) {
                    await triggerProactiveForCompanion(cid, 'proactive');
                }
            }
        }, 60000);
    }

    function init() {
        _injectStyles();
        _startGlobalHeartbeat();
        setTimeout(_evaluateStartupCheckins, 2500);

        // Support deep-link navigation from Notifications Center
        window.addEventListener('notif-navigate', e => {
            if (e.detail?.tab === 'companion-creator' && e.detail?.context) {
                openCompanionInHub(e.detail.context);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    document.addEventListener('systemReady', _evaluateStartupCheckins);

    return {
        showPopup,
        closePopup,
        triggerProactiveForCompanion,
        openCompanionInHub,
    };
})();
