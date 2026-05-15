'use strict';
/**
 * Aethvion Suite — Companion Creator
 * Unified builder for creating, editing, exporting, and importing companions.
 * Built-in companions (Axiom, Lyra) can have their personality customized here.
 * Changes take effect immediately — no server restart required.
 */

const CompanionCreator = (() => {
    const API = '/api/companion-creator';
    let _root = null;
    let _editingId = null;
    let _isBuiltin = false;

    // ── Shell ─────────────────────────────────────────────────────────────────

    function _renderShell() {
        _root.innerHTML = `
<div class="cc-wrap">
  <div class="cc-header">
    <div class="cc-header-left">
      <h2 class="cc-title"><i class="fas fa-user-astronaut"></i> Companion Builder</h2>
      <p class="cc-subtitle">Craft unique AI companions. Changes are live immediately.</p>
    </div>
    <div class="cc-header-actions">
      <button id="cc-import-btn" class="cc-btn cc-btn-ghost cc-btn-sm" title="Import a shared companion JSON">
        <i class="fas fa-file-import"></i> Import
      </button>
    </div>
  </div>

  <div class="cc-layout">
    <div class="cc-sidebar">
      <div class="cc-sidebar-group">
        <div class="cc-section-label">Built-in</div>
        <div id="cc-builtin-list" class="cc-list">
          <div class="cc-list-loading"><i class="fas fa-spinner fa-spin"></i></div>
        </div>
      </div>
      <div class="cc-sidebar-group">
        <div class="cc-section-label">Custom</div>
        <div id="cc-custom-list" class="cc-list">
          <div class="cc-list-empty">No custom companions yet.</div>
        </div>
      </div>
      <button id="cc-new-btn" class="cc-btn cc-btn-primary cc-btn-full cc-btn-sm" style="margin-top:auto">
        <i class="fas fa-plus"></i> New Companion
      </button>
    </div>

    <div class="cc-form-area" id="cc-form-area">
      <div class="cc-empty-state" id="cc-empty-state">
        <i class="fas fa-user-astronaut cc-empty-icon"></i>
        <p>Select a companion to edit, or click <strong>New Companion</strong> to create one.</p>
      </div>

      <form id="cc-form" class="cc-form" style="display:none">
        <div id="cc-builtin-notice" class="cc-builtin-notice hidden">
          <i class="fas fa-shield-halved"></i>
          Built-in companion — name and ID are locked. Personality edits take effect immediately.
        </div>

        <div class="cc-form-grid">
          <div class="cc-field cc-field-full">
            <label>Name <span class="cc-required" id="cc-name-req">*</span></label>
            <input type="text" id="cc-name" placeholder="e.g. Nova" maxlength="40" required>
          </div>
          <div class="cc-field cc-field-full">
            <label>Description <span class="cc-required" id="cc-desc-req">*</span></label>
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
          <div class="cc-field" id="cc-color-field">
            <label>Accent Color</label>
            <div class="cc-color-row">
              <input type="color" id="cc-accent-color" value="#6366f1">
              <span id="cc-color-preview" class="cc-color-preview"></span>
              <span id="cc-color-hex" class="cc-color-hex">#6366f1</span>
            </div>
          </div>
          <div class="cc-field" id="cc-symbol-field">
            <label>Avatar Symbol <span class="cc-hint">(emoji or char)</span></label>
            <input type="text" id="cc-avatar-symbol" placeholder="✦" maxlength="2" style="font-size:1.4em;width:60px;text-align:center;">
          </div>
          <div class="cc-field" id="cc-model-field">
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
          <button type="button" id="cc-cancel-btn" class="cc-btn cc-btn-ghost cc-btn-sm">Cancel</button>
          <button type="button" id="cc-export-btn" class="cc-btn cc-btn-ghost cc-btn-sm hidden" title="Export as shareable JSON">
            <i class="fas fa-file-export"></i> Export
          </button>
          <button type="button" id="cc-delete-btn" class="cc-btn cc-btn-danger cc-btn-sm" style="display:none">
            <i class="fas fa-trash"></i> Delete
          </button>
          <button type="submit" id="cc-save-btn" class="cc-btn cc-btn-primary cc-btn-sm">
            <i class="fas fa-save"></i> Save
          </button>
        </div>
        <div id="cc-form-msg" class="cc-form-msg" style="display:none"></div>
      </form>
    </div>
  </div>

  <!-- Hidden import dialog -->
  <div id="cc-import-dialog" class="cc-import-dialog hidden">
    <div class="cc-import-inner">
      <div class="cc-import-header">
        <span><i class="fas fa-file-import"></i> Import Companion</span>
        <button id="cc-import-close" class="cc-btn cc-btn-ghost cc-btn-sm"><i class="fas fa-times"></i></button>
      </div>
      <p class="cc-import-hint">Paste an exported companion JSON below:</p>
      <textarea id="cc-import-json" rows="10" placeholder='{ "name": "Nova", "personality": "..." }'></textarea>
      <div class="cc-import-actions">
        <button id="cc-import-submit" class="cc-btn cc-btn-primary cc-btn-sm"><i class="fas fa-check"></i> Import</button>
      </div>
      <div id="cc-import-msg" class="cc-form-msg" style="display:none"></div>
    </div>
  </div>
</div>`;
    }

    // ── List rendering ────────────────────────────────────────────────────────

    async function _loadList() {
        const builtinEl = document.getElementById('cc-builtin-list');
        const customEl  = document.getElementById('cc-custom-list');
        if (!builtinEl || !customEl) return;

        try {
            const res  = await fetch(`${API}/all`);
            const data = await res.json();
            const all  = data.companions || [];

            const builtins = all.filter(c => c._builtin);
            const customs  = all.filter(c => !c._builtin);

            builtinEl.innerHTML = builtins.length
                ? builtins.map(c => _listItemHTML(c, true)).join('')
                : '<div class="cc-list-empty">None</div>';

            customEl.innerHTML = customs.length
                ? customs.map(c => _listItemHTML(c, false)).join('')
                : '<div class="cc-list-empty">No custom companions yet.</div>';

            document.querySelectorAll('.cc-list-item').forEach(item => {
                item.addEventListener('click', () =>
                    _editCompanion(item.dataset.id, item.dataset.builtin === 'true'));
                item.addEventListener('keydown', e => {
                    if (e.key === 'Enter') _editCompanion(item.dataset.id, item.dataset.builtin === 'true');
                });
            });
        } catch (e) {
            if (builtinEl) builtinEl.innerHTML = `<div class="cc-list-error">Error: ${e.message}</div>`;
        }
    }

    function _listItemHTML(c, isBuiltin) {
        const active = _editingId === c.id ? 'active' : '';
        const lock   = isBuiltin ? '<i class="fas fa-lock cc-list-lock"></i>' : '';
        return `
        <div class="cc-list-item ${active}" data-id="${c.id}" data-builtin="${isBuiltin}" role="button" tabindex="0">
          <span class="cc-list-symbol" style="color:${c.accent_color || '#6366f1'}">${c.avatar_symbol || '✦'}</span>
          <span class="cc-list-name">${c.name}</span>
          ${lock}
        </div>`;
    }

    // ── Form ──────────────────────────────────────────────────────────────────

    function _showForm(fillData = null, isBuiltin = false) {
        _isBuiltin = isBuiltin;
        document.getElementById('cc-empty-state').style.display = 'none';
        const form = document.getElementById('cc-form');
        form.style.display = '';

        // Builtin notice
        const notice = document.getElementById('cc-builtin-notice');
        notice.classList.toggle('hidden', !isBuiltin);

        // Lock name/description for builtins
        const nameInput = document.getElementById('cc-name');
        const descInput = document.getElementById('cc-description');
        nameInput.readOnly = isBuiltin;
        descInput.readOnly = isBuiltin;
        nameInput.style.opacity = isBuiltin ? '0.5' : '';
        descInput.style.opacity = isBuiltin ? '0.5' : '';

        // Show/hide delete & export
        document.getElementById('cc-delete-btn').style.display = (!isBuiltin && fillData) ? '' : 'none';
        const exportBtn = document.getElementById('cc-export-btn');
        exportBtn.classList.toggle('hidden', isBuiltin || !fillData);

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
            set('cc-accent-color', '#6366f1');
            set('cc-avatar-symbol', '✦');
        }
        _updatePreview();
    }

    function _updatePreview() {
        const color  = document.getElementById('cc-accent-color')?.value || '#6366f1';
        const symbol = document.getElementById('cc-avatar-symbol')?.value || '✦';
        const name   = document.getElementById('cc-name')?.value || 'Companion';

        const hexEl    = document.getElementById('cc-color-hex');
        const prevEl   = document.getElementById('cc-color-preview');
        const avatarEl = document.getElementById('cc-avatar-display');
        const nameEl   = document.getElementById('cc-avatar-name-preview');

        if (hexEl)    hexEl.textContent = color;
        if (prevEl)   prevEl.style.background = color;
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

    async function _editCompanion(id, isBuiltin = false) {
        _editingId = id;
        try {
            const res  = await fetch(`${API}/${id}`);
            const data = await res.json();
            _showForm(data, isBuiltin);
            _loadList();
        } catch (e) {
            if (typeof showToast === 'function') showToast(`Failed to load companion: ${e.message}`, 'error');
        }
    }

    async function _saveCompanion(e) {
        e.preventDefault();
        const payload = _collectForm();

        if (_isBuiltin) {
            // Builtin: only personality fields
            if (!payload.personality) {
                _setMsg('Personality is required.', true);
                return;
            }
        } else {
            if (!payload.name || !payload.description || !payload.personality) {
                _setMsg('Name, description, and personality are required.', true);
                return;
            }
        }

        const saveBtn = document.getElementById('cc-save-btn');
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…';

        try {
            let url, method, body;

            if (_isBuiltin) {
                url    = `${API}/builtin/${_editingId}`;
                method = 'PUT';
                body   = JSON.stringify({
                    personality:   payload.personality,
                    speech_style:  payload.speech_style,
                    quirks:        payload.quirks,
                    likes:         payload.likes,
                    dislikes:      payload.dislikes,
                    accent_color:  payload.accent_color,
                    avatar_symbol: payload.avatar_symbol,
                });
            } else if (_editingId) {
                url    = `${API}/${_editingId}`;
                method = 'PUT';
                body   = JSON.stringify(payload);
            } else {
                url    = `${API}/create`;
                method = 'POST';
                body   = JSON.stringify(payload);
            }

            const res  = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body });
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
            saveBtn.innerHTML = '<i class="fas fa-save"></i> Save';
        }
    }

    async function _deleteCompanion() {
        if (!_editingId || _isBuiltin) return;
        const name = document.getElementById('cc-name')?.value || _editingId;
        if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
        try {
            const res  = await fetch(`${API}/${_editingId}`, { method: 'DELETE' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Delete failed');
            _editingId = null;
            _isBuiltin = false;
            document.getElementById('cc-form').style.display = 'none';
            document.getElementById('cc-empty-state').style.display = '';
            await _loadList();
            if (typeof showToast === 'function') showToast(data.message, 'success');
            window.dispatchEvent(new CustomEvent('customCompanionDeleted'));
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Delete failed: ${err.message}`, 'error');
        }
    }

    async function _exportCompanion() {
        if (!_editingId || _isBuiltin) return;
        try {
            const res  = await fetch(`${API}/export/${_editingId}`);
            const data = await res.json();
            const json = JSON.stringify(data, null, 2);
            const blob = new Blob([json], { type: 'application/json' });
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement('a');
            a.href     = url;
            a.download = `${_editingId}_companion.json`;
            a.click();
            URL.revokeObjectURL(url);
            if (typeof showToast === 'function') showToast('Companion exported!', 'success');
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Export failed: ${err.message}`, 'error');
        }
    }

    function _showImportDialog() {
        const dialog = document.getElementById('cc-import-dialog');
        dialog.classList.remove('hidden');
        document.getElementById('cc-import-json').value = '';
        document.getElementById('cc-import-msg').style.display = 'none';
    }

    function _hideImportDialog() {
        document.getElementById('cc-import-dialog')?.classList.add('hidden');
    }

    async function _submitImport() {
        const raw  = document.getElementById('cc-import-json')?.value?.trim();
        const msgEl = document.getElementById('cc-import-msg');
        if (!raw) { msgEl.style.display=''; msgEl.textContent='Paste a JSON config first.'; msgEl.className='cc-form-msg cc-form-msg-error'; return; }

        let config;
        try { config = JSON.parse(raw); }
        catch { msgEl.style.display=''; msgEl.textContent='Invalid JSON.'; msgEl.className='cc-form-msg cc-form-msg-error'; return; }

        try {
            const res  = await fetch(`${API}/import`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ config }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Import failed');
            msgEl.style.display = '';
            msgEl.textContent = `✓ ${data.message}`;
            msgEl.className = 'cc-form-msg cc-form-msg-ok';
            await _loadList();
            setTimeout(_hideImportDialog, 1200);
            if (typeof showToast === 'function') showToast(data.message, 'success');
        } catch (err) {
            msgEl.style.display = '';
            msgEl.textContent = `Error: ${err.message}`;
            msgEl.className = 'cc-form-msg cc-form-msg-error';
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    function init() {
        _root = document.getElementById('companion-creator-root');
        if (!_root || _root.dataset.ccInit) return;
        _root.dataset.ccInit = '1';

        _renderShell();
        _loadList();

        document.getElementById('cc-new-btn')?.addEventListener('click', () => {
            _editingId = null;
            _isBuiltin = false;
            _loadList();
            _showForm(null, false);
        });
        document.getElementById('cc-cancel-btn')?.addEventListener('click', () => {
            _editingId = null;
            _isBuiltin = false;
            document.getElementById('cc-form').style.display = 'none';
            document.getElementById('cc-empty-state').style.display = '';
            _loadList();
        });
        document.getElementById('cc-delete-btn')?.addEventListener('click', _deleteCompanion);
        document.getElementById('cc-export-btn')?.addEventListener('click', _exportCompanion);
        document.getElementById('cc-form')?.addEventListener('submit', _saveCompanion);

        document.getElementById('cc-import-btn')?.addEventListener('click', _showImportDialog);
        document.getElementById('cc-import-close')?.addEventListener('click', _hideImportDialog);
        document.getElementById('cc-import-submit')?.addEventListener('click', _submitImport);

        // Live preview updates
        ['cc-accent-color', 'cc-avatar-symbol', 'cc-name'].forEach(id => {
            document.getElementById(id)?.addEventListener('input', _updatePreview);
        });
    }

    return { init };
})();

// panelLoaded fires after the lazy script injection — this is the correct pattern
document.addEventListener('panelLoaded', function (e) {
    if (e.detail && e.detail.tabName === 'companion-creator') {
        CompanionCreator.init();
    }
});
