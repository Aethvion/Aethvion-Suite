'use strict';
/**
 * Companion Creator — mode-companion-creator.js
 * Renders a form-based UI for creating, editing, and deleting custom companions.
 */

const CompanionCreator = (() => {
    const API = '/api/companion-creator';
    let _root = null;
    let _editingId = null;

    // ── Templates ─────────────────────────────────────────────────────────────

    function _renderShell() {
        _root.innerHTML = `
<div class="cc-wrap">
  <div class="cc-header">
    <h2 class="cc-title"><i class="fas fa-plus-circle"></i> Companion Creator</h2>
    <p class="cc-subtitle">Design a new AI companion with a unique personality. Requires a server restart to activate chat.</p>
  </div>

  <div class="cc-layout">
    <div class="cc-sidebar">
      <div class="cc-section-label">Your Companions</div>
      <div id="cc-list" class="cc-list">
        <div class="cc-list-loading"><i class="fas fa-spinner fa-spin"></i></div>
      </div>
      <button id="cc-new-btn" class="cc-btn cc-btn-primary cc-btn-full">
        <i class="fas fa-plus"></i> New Companion
      </button>
    </div>

    <div class="cc-form-area" id="cc-form-area">
      <div class="cc-empty-state" id="cc-empty-state">
        <i class="fas fa-user-astronaut cc-empty-icon"></i>
        <p>Select a companion to edit, or click <strong>New Companion</strong> to create one.</p>
      </div>
      <form id="cc-form" class="cc-form" style="display:none">
        <div class="cc-form-grid">
          <div class="cc-field cc-field-full">
            <label>Name <span class="cc-required">*</span></label>
            <input type="text" id="cc-name" placeholder="e.g. Nova" maxlength="40" required>
          </div>
          <div class="cc-field cc-field-full">
            <label>Description <span class="cc-required">*</span></label>
            <input type="text" id="cc-description" placeholder="One-line description shown in UI" maxlength="120" required>
          </div>
          <div class="cc-field cc-field-full">
            <label>Personality <span class="cc-required">*</span></label>
            <textarea id="cc-personality" rows="4" placeholder="Describe how this companion thinks, speaks, and feels. Be specific — this directly shapes their responses."></textarea>
          </div>
          <div class="cc-field cc-field-full">
            <label>Speech Style</label>
            <textarea id="cc-speech-style" rows="2" placeholder="e.g. Casual and direct. Uses short sentences. Avoids filler words."></textarea>
          </div>
          <div class="cc-field cc-field-full">
            <label>Quirks <span class="cc-hint">(one per line)</span></label>
            <textarea id="cc-quirks" rows="3" placeholder="e.g. Often pauses mid-thought with '...'&#10;Makes unexpected metaphors"></textarea>
          </div>
          <div class="cc-field">
            <label>Likes <span class="cc-hint">(one per line)</span></label>
            <textarea id="cc-likes" rows="3" placeholder="e.g. Deep conversations&#10;Helping with problems"></textarea>
          </div>
          <div class="cc-field">
            <label>Dislikes <span class="cc-hint">(one per line)</span></label>
            <textarea id="cc-dislikes" rows="3" placeholder="e.g. Being ignored&#10;Repetitive questions"></textarea>
          </div>
          <div class="cc-field">
            <label>Accent Color</label>
            <div class="cc-color-row">
              <input type="color" id="cc-accent-color" value="#6366f1">
              <span id="cc-color-preview" class="cc-color-preview"></span>
              <span id="cc-color-hex" class="cc-color-hex">#6366f1</span>
            </div>
          </div>
          <div class="cc-field">
            <label>Avatar Symbol <span class="cc-hint">(emoji or character)</span></label>
            <input type="text" id="cc-avatar-symbol" placeholder="✦" maxlength="2" style="font-size:1.4em;width:60px;text-align:center;">
          </div>
          <div class="cc-field">
            <label>Default Model</label>
            <select id="cc-model">
              <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
              <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>
              <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
              <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
            </select>
          </div>
        </div>

        <div id="cc-avatar-preview-wrap" class="cc-avatar-preview-wrap">
          <div class="cc-section-label">Preview</div>
          <div class="cc-avatar-preview-box">
            <div id="cc-avatar-display" class="cc-avatar-display"></div>
            <div id="cc-avatar-name-preview" class="cc-avatar-name-preview"></div>
          </div>
        </div>

        <div class="cc-form-actions">
          <button type="button" id="cc-cancel-btn" class="cc-btn cc-btn-ghost">Cancel</button>
          <button type="button" id="cc-delete-btn" class="cc-btn cc-btn-danger" style="display:none">
            <i class="fas fa-trash"></i> Delete
          </button>
          <button type="submit" id="cc-save-btn" class="cc-btn cc-btn-primary">
            <i class="fas fa-save"></i> Save Companion
          </button>
        </div>
        <div id="cc-form-msg" class="cc-form-msg" style="display:none"></div>
      </form>
    </div>
  </div>
</div>`;
    }

    // ── List ──────────────────────────────────────────────────────────────────

    async function _loadList() {
        const listEl = document.getElementById('cc-list');
        if (!listEl) return;
        listEl.innerHTML = '<div class="cc-list-loading"><i class="fas fa-spinner fa-spin"></i></div>';
        try {
            const res = await fetch(`${API}/list`);
            const data = await res.json();
            const companions = data.companions || [];
            if (companions.length === 0) {
                listEl.innerHTML = '<div class="cc-list-empty">No custom companions yet.</div>';
                return;
            }
            listEl.innerHTML = companions.map(c => `
                <div class="cc-list-item ${_editingId === c.id ? 'active' : ''}"
                     data-id="${c.id}" role="button" tabindex="0">
                  <span class="cc-list-symbol" style="color:${c.accent_color || '#6366f1'}">${c.avatar_symbol || '✦'}</span>
                  <span class="cc-list-name">${c.name}</span>
                </div>
            `).join('');

            listEl.querySelectorAll('.cc-list-item').forEach(item => {
                item.addEventListener('click', () => _editCompanion(item.dataset.id));
                item.addEventListener('keydown', e => { if (e.key === 'Enter') _editCompanion(item.dataset.id); });
            });
        } catch (e) {
            listEl.innerHTML = `<div class="cc-list-error">Failed to load: ${e.message}</div>`;
        }
    }

    // ── Form helpers ──────────────────────────────────────────────────────────

    function _showForm(fillData = null) {
        document.getElementById('cc-empty-state').style.display = 'none';
        const form = document.getElementById('cc-form');
        form.style.display = '';
        document.getElementById('cc-delete-btn').style.display = fillData ? '' : 'none';
        document.getElementById('cc-form-msg').style.display = 'none';

        const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };

        if (fillData) {
            set('cc-name', fillData.name);
            set('cc-description', fillData.description);
            set('cc-personality', fillData.personality);
            set('cc-speech-style', fillData.speech_style);
            set('cc-quirks', (fillData.quirks || []).join('\n'));
            set('cc-likes', (fillData.likes || []).join('\n'));
            set('cc-dislikes', (fillData.dislikes || []).join('\n'));
            set('cc-accent-color', fillData.accent_color || '#6366f1');
            set('cc-avatar-symbol', fillData.avatar_symbol || '✦');
            set('cc-model', fillData.default_model || 'gemini-1.5-flash');
        } else {
            form.reset();
            document.getElementById('cc-accent-color').value = '#6366f1';
            document.getElementById('cc-avatar-symbol').value = '✦';
        }
        _updatePreview();
    }

    function _updatePreview() {
        const color  = document.getElementById('cc-accent-color')?.value || '#6366f1';
        const symbol = document.getElementById('cc-avatar-symbol')?.value || '✦';
        const name   = document.getElementById('cc-name')?.value || 'Companion';
        const hexEl  = document.getElementById('cc-color-hex');
        const prevEl = document.getElementById('cc-color-preview');
        const avatarEl = document.getElementById('cc-avatar-display');
        const nameEl   = document.getElementById('cc-avatar-name-preview');

        if (hexEl)  hexEl.textContent = color;
        if (prevEl) prevEl.style.background = color;
        if (avatarEl) {
            avatarEl.textContent = symbol;
            avatarEl.style.background = color + '22';
            avatarEl.style.border = `2px solid ${color}`;
            avatarEl.style.color  = color;
        }
        if (nameEl) nameEl.textContent = name;
    }

    function _setMsg(msg, isError = false) {
        const el = document.getElementById('cc-form-msg');
        el.style.display = '';
        el.textContent = msg;
        el.className = `cc-form-msg ${isError ? 'cc-form-msg-error' : 'cc-form-msg-ok'}`;
    }

    function _collectForm() {
        const lines = id => (document.getElementById(id)?.value || '')
            .split('\n').map(s => s.trim()).filter(Boolean);
        return {
            name:          document.getElementById('cc-name')?.value?.trim(),
            description:   document.getElementById('cc-description')?.value?.trim(),
            personality:   document.getElementById('cc-personality')?.value?.trim(),
            speech_style:  document.getElementById('cc-speech-style')?.value?.trim(),
            quirks:        lines('cc-quirks'),
            likes:         lines('cc-likes'),
            dislikes:      lines('cc-dislikes'),
            accent_color:  document.getElementById('cc-accent-color')?.value,
            avatar_symbol: document.getElementById('cc-avatar-symbol')?.value?.trim() || '✦',
            default_model: document.getElementById('cc-model')?.value,
        };
    }

    // ── Actions ───────────────────────────────────────────────────────────────

    async function _editCompanion(id) {
        _editingId = id;
        try {
            const res  = await fetch(`${API}/${id}`);
            const data = await res.json();
            _showForm(data);
            _loadList();
        } catch (e) {
            if (typeof showToast === 'function') showToast(`Failed to load companion: ${e.message}`, 'error');
        }
    }

    async function _saveCompanion(e) {
        e.preventDefault();
        const payload = _collectForm();
        if (!payload.name || !payload.description || !payload.personality) {
            _setMsg('Name, description, and personality are required.', true);
            return;
        }

        const saveBtn = document.getElementById('cc-save-btn');
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…';

        try {
            const url    = _editingId ? `${API}/${_editingId}` : `${API}/create`;
            const method = _editingId ? 'PUT' : 'POST';
            const res    = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Request failed');

            _setMsg(`✓ ${data.message}`);
            if (!_editingId) _editingId = data.id;
            await _loadList();
            if (typeof showToast === 'function') showToast(data.message, 'success');
            window.dispatchEvent(new CustomEvent('customCompanionCreated', { detail: { id: _editingId } }));
        } catch (err) {
            _setMsg(`Error: ${err.message}`, true);
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fas fa-save"></i> Save Companion';
        }
    }

    async function _deleteCompanion() {
        if (!_editingId) return;
        if (!confirm(`Delete this companion? This cannot be undone.`)) return;
        try {
            const res  = await fetch(`${API}/${_editingId}`, { method: 'DELETE' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Delete failed');
            _editingId = null;
            document.getElementById('cc-form').style.display = 'none';
            document.getElementById('cc-empty-state').style.display = '';
            await _loadList();
            if (typeof showToast === 'function') showToast(data.message, 'success');
            window.dispatchEvent(new CustomEvent('customCompanionDeleted'));
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Delete failed: ${err.message}`, 'error');
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    function init() {
        _root = document.getElementById('companion-creator-root');
        if (!_root) return;
        _renderShell();
        _loadList();

        document.getElementById('cc-new-btn')?.addEventListener('click', () => {
            _editingId = null;
            _loadList();
            _showForm(null);
        });
        document.getElementById('cc-cancel-btn')?.addEventListener('click', () => {
            _editingId = null;
            document.getElementById('cc-form').style.display = 'none';
            document.getElementById('cc-empty-state').style.display = '';
            _loadList();
        });
        document.getElementById('cc-delete-btn')?.addEventListener('click', _deleteCompanion);
        document.getElementById('cc-form')?.addEventListener('submit', _saveCompanion);

        // Live preview updates
        ['cc-accent-color', 'cc-avatar-symbol', 'cc-name'].forEach(id => {
            document.getElementById(id)?.addEventListener('input', _updatePreview);
        });
    }

    return { init };
})();

// Hook into tab switching
document.addEventListener('DOMContentLoaded', () => {
    // Initialize when the tab becomes active for the first time
    const observer = new MutationObserver(() => {
        const panel = document.getElementById('companion-creator-panel');
        if (panel && !panel.classList.contains('hidden') && getComputedStyle(panel).display !== 'none') {
            if (!document.getElementById('cc-wrap') && document.getElementById('companion-creator-root')) {
                CompanionCreator.init();
            }
        }
    });
    const panel = document.getElementById('companion-creator-panel');
    if (panel) observer.observe(panel, { attributes: true, attributeFilter: ['class', 'style'] });
});

// Also init if switchMainTab triggers
window.initializeCompanionCreator = function () {
    if (!document.getElementById('cc-wrap')) CompanionCreator.init();
};
