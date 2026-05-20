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
          <i class="fas fa-lock"></i>
          Built-in companion — view only. All fields are locked. Create a new companion to build something custom.
        </div>

        <!-- ── Identity ─────────────────────────────────────── -->
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
            <label>Avatar Symbol <span class="cc-hint">(emoji or char — used when no icon is set)</span></label>
            <input type="text" id="cc-avatar-symbol" placeholder="✦" maxlength="2" style="font-size:1.4em;width:60px;text-align:center;">
          </div>
          <div class="cc-field cc-field-full" id="cc-icon-field">
            <label>Icon <span class="cc-hint">(PNG · JPG · GIF · WebP · max 2 MB)</span></label>
            <div class="cc-icon-row">
              <div class="cc-icon-thumb" id="cc-icon-thumb">
                <img id="cc-icon-img" src="" alt="" class="cc-icon-img hidden">
                <i id="cc-icon-ph" class="fas fa-image cc-icon-ph"></i>
              </div>
              <div class="cc-icon-upload-col">
                <div class="cc-icon-btns" id="cc-icon-btns">
                  <label class="cc-btn cc-btn-ghost cc-btn-sm cc-icon-upload-lbl" for="cc-icon-file">
                    <i class="fas fa-upload"></i> Upload image
                  </label>
                  <input type="file" id="cc-icon-file" accept="image/png,image/jpeg,image/gif,image/webp" style="display:none">
                  <button type="button" id="cc-icon-remove-btn" class="cc-btn cc-btn-ghost cc-btn-sm hidden">
                    <i class="fas fa-trash"></i> Remove
                  </button>
                </div>
                <span id="cc-icon-save-hint" class="cc-hint cc-icon-save-hint hidden">Save the companion first to add an icon.</span>
              </div>
            </div>
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

        <!-- ── Advanced sections ─────────────────────────────── -->
        <div class="cc-sections">

          <!-- Behavior & Mood -->
          <div class="cc-adv-section" id="cc-s-behavior">
            <div class="cc-adv-toggle">
              <span><i class="fas fa-sliders"></i> Behavior &amp; Mood</span>
              <i class="fas fa-chevron-down cc-adv-chevron"></i>
            </div>
            <div class="cc-adv-body">
              <div class="cc-form-grid" style="margin-top:0">
                <div class="cc-field">
                  <label>Temperature&nbsp;<span class="cc-range-val" id="cc-temp-val">0.85</span></label>
                  <input type="range" id="cc-temperature" min="0" max="1" step="0.01" value="0.85" class="cc-range">
                  <span class="cc-range-hint">Lower = consistent &middot; Higher = creative</span>
                </div>
                <div class="cc-field">
                  <label>Initiate Temperature&nbsp;<span class="cc-range-val" id="cc-itemp-val">0.80</span></label>
                  <input type="range" id="cc-initiate-temp" min="0" max="1" step="0.01" value="0.80" class="cc-range">
                  <span class="cc-range-hint">For spontaneous initiations</span>
                </div>
                <div class="cc-field">
                  <label>Change Susceptibility&nbsp;<span class="cc-range-val" id="cc-chsus-val">0.70</span></label>
                  <input type="range" id="cc-change-susceptibility" min="0" max="1" step="0.01" value="0.70" class="cc-range">
                  <span class="cc-range-hint">How open this companion is to changing its mind</span>
                </div>
                <div class="cc-field">
                  <label>Default Mood</label>
                  <input type="text" id="cc-default-mood" placeholder="calm" maxlength="32">
                </div>
              </div>
            </div>
          </div>

          <!-- Capabilities -->
          <div class="cc-adv-section" id="cc-s-capabilities">
            <div class="cc-adv-toggle">
              <span><i class="fas fa-shield-halved"></i> Capabilities</span>
              <i class="fas fa-chevron-down cc-adv-chevron"></i>
            </div>
            <div class="cc-adv-body">
              <div class="cc-caps-grid">
                <label class="cc-toggle-row" for="cc-cap-tools">
                  <div>
                    <div class="cc-cap-label">Tools Enabled</div>
                    <div class="cc-cap-desc">Allow function/tool calling in chats</div>
                  </div>
                  <span class="cc-toggle-wrap">
                    <input type="checkbox" id="cc-cap-tools" class="cc-toggle-input">
                    <span class="cc-toggle-thumb"></span>
                  </span>
                </label>
                <label class="cc-toggle-row" for="cc-cap-workspace">
                  <div>
                    <div class="cc-cap-label">Workspace Access</div>
                    <div class="cc-cap-desc">Read and write project files</div>
                  </div>
                  <span class="cc-toggle-wrap">
                    <input type="checkbox" id="cc-cap-workspace" class="cc-toggle-input">
                    <span class="cc-toggle-thumb"></span>
                  </span>
                </label>
                <label class="cc-toggle-row" for="cc-cap-memory">
                  <div>
                    <div class="cc-cap-label">Memory Updates</div>
                    <div class="cc-cap-desc">Save observations about the user over time</div>
                  </div>
                  <span class="cc-toggle-wrap">
                    <input type="checkbox" id="cc-cap-memory" class="cc-toggle-input" checked>
                    <span class="cc-toggle-thumb"></span>
                  </span>
                </label>
                <label class="cc-toggle-row" for="cc-cap-internet">
                  <div>
                    <div class="cc-cap-label">Internet Search</div>
                    <div class="cc-cap-desc">Search the web for current information</div>
                  </div>
                  <span class="cc-toggle-wrap">
                    <input type="checkbox" id="cc-cap-internet" class="cc-toggle-input">
                    <span class="cc-toggle-thumb"></span>
                  </span>
                </label>
              </div>
            </div>
          </div>

          <!-- System Prompts -->
          <div class="cc-adv-section" id="cc-s-prompts">
            <div class="cc-adv-toggle">
              <span><i class="fas fa-terminal"></i> System Prompts <span class="cc-adv-badge">optional</span></span>
              <i class="fas fa-chevron-down cc-adv-chevron"></i>
            </div>
            <div class="cc-adv-body">
              <p class="cc-prompt-hint-text">Compose dynamic prompts using template variables. Click any tag to copy it.</p>
              <div class="cc-prompt-vars">
                <span class="cc-prompt-var" title="Personality &amp; base info block">{base_info}</span>
                <span class="cc-prompt-var" title="Long-term memory block">{memory}</span>
                <span class="cc-prompt-var" title="Current date &amp; time">{datetime_ctx}</span>
                <span class="cc-prompt-var" title="Workspace files context">{workspace_block}</span>
                <span class="cc-prompt-var" title="Cross-companion bridges">{bridges_block}</span>
                <span class="cc-prompt-var" title="Auto-initiation instruction">{trigger_instruction}</span>
              </div>
              <div class="cc-field" style="margin-top:0.9rem">
                <label>Chat System Prompt</label>
                <textarea id="cc-prompt-chat" rows="5" class="cc-prompt-area" placeholder="You are {name}. {base_info} Memory: {memory}. Time: {datetime_ctx}.&#10;&#10;Leave blank to use the default template."></textarea>
              </div>
              <div class="cc-field" style="margin-top:0.75rem">
                <label>Initiate System Prompt <span class="cc-hint">(for auto-initiated messages)</span></label>
                <textarea id="cc-prompt-initiate" rows="3" class="cc-prompt-area" placeholder="You are {name}. {base_info} {trigger_instruction}&#10;&#10;Leave blank to use the default template."></textarea>
              </div>
            </div>
          </div>

          <!-- Expressions & Moods -->
          <div class="cc-adv-section" id="cc-s-expressions">
            <div class="cc-adv-toggle">
              <span><i class="fas fa-masks-theater"></i> Expressions &amp; Moods</span>
              <i class="fas fa-chevron-down cc-adv-chevron"></i>
            </div>
            <div class="cc-adv-body">
              <div class="cc-form-grid" style="margin-top:0">
                <div class="cc-field">
                  <label>Expressions <span class="cc-hint">(one per line)</span></label>
                  <textarea id="cc-expressions" rows="5" placeholder="default&#10;happy&#10;thinking&#10;focused&#10;error"></textarea>
                </div>
                <div class="cc-field">
                  <label>Moods <span class="cc-hint">(one per line)</span></label>
                  <textarea id="cc-moods" rows="5" placeholder="calm&#10;happy&#10;reflective&#10;intense"></textarea>
                </div>
                <div class="cc-field">
                  <label>Default Expression</label>
                  <input type="text" id="cc-default-expression" placeholder="default" maxlength="32">
                </div>
              </div>
            </div>
          </div>

        </div><!-- /.cc-sections -->

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
        const active  = _editingId === c.id ? 'active' : '';
        const lock    = isBuiltin ? '<i class="fas fa-lock cc-list-lock"></i>' : '';
        const avatar  = c.has_icon
            ? `<img class="cc-list-icon" src="${API}/${c.id}/icon?t=${Date.now()}" alt="${c.name}">`
            : `<span class="cc-list-symbol" style="color:${c.accent_color || '#6366f1'}">${c.avatar_symbol || '✦'}</span>`;
        return `
        <div class="cc-list-item ${active}" data-id="${c.id}" data-builtin="${isBuiltin}" role="button" tabindex="0">
          ${avatar}
          <span class="cc-list-name">${c.name}</span>
          ${lock}
        </div>`;
    }

    // ── Range helpers ─────────────────────────────────────────────────────────

    function _updateRangeDisplays() {
        [
            ['cc-temperature',           'cc-temp-val'],
            ['cc-initiate-temp',         'cc-itemp-val'],
            ['cc-change-susceptibility', 'cc-chsus-val'],
        ].forEach(([inputId, valId]) => {
            const input = document.getElementById(inputId);
            const disp  = document.getElementById(valId);
            if (input && disp) disp.textContent = parseFloat(input.value).toFixed(2);
        });
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

        // Lock ALL fields for built-ins; unlock for custom
        form.querySelectorAll('input:not([type="file"]):not([type="color"]), textarea, select').forEach(el => {
            el.disabled      = isBuiltin;
            el.style.opacity = isBuiltin ? '0.5' : '';
        });
        // Color picker needs separate handling (disabled attr behaves oddly on <input type=color>)
        const colorPicker = document.getElementById('cc-accent-color');
        if (colorPicker) { colorPicker.disabled = isBuiltin; colorPicker.style.pointerEvents = isBuiltin ? 'none' : ''; }

        // Save button hidden for built-ins; delete/export hidden for built-ins and new forms
        document.getElementById('cc-save-btn').style.display        = isBuiltin ? 'none' : '';
        document.getElementById('cc-delete-btn').style.display      = (!isBuiltin && fillData) ? '' : 'none';
        const exportBtn = document.getElementById('cc-export-btn');
        exportBtn.classList.toggle('hidden', isBuiltin || !fillData);

        // Icon section — upload/remove only for existing custom companions
        const iconBtns     = document.getElementById('cc-icon-btns');
        const iconSaveHint = document.getElementById('cc-icon-save-hint');
        if (isBuiltin) {
            // Built-in: hide all icon controls
            iconBtns?.classList.add('hidden');
            iconSaveHint?.classList.add('hidden');
        } else if (!fillData) {
            // New companion: show "save first" hint instead of upload controls
            iconBtns?.classList.add('hidden');
            iconSaveHint?.classList.remove('hidden');
        } else {
            iconBtns?.classList.remove('hidden');
            iconSaveHint?.classList.add('hidden');
        }

        // Load icon state
        const iconImg = document.getElementById('cc-icon-img');
        const iconPh  = document.getElementById('cc-icon-ph');
        const iconRem = document.getElementById('cc-icon-remove-btn');
        const cid     = fillData?.id;
        if (fillData?.has_icon && cid) {
            if (iconImg) { iconImg.src = `${API}/${cid}/icon?t=${Date.now()}`; iconImg.classList.remove('hidden'); }
            if (iconPh)  iconPh.classList.add('hidden');
            if (iconRem) iconRem.classList.remove('hidden');
        } else {
            if (iconImg) { iconImg.src = ''; iconImg.classList.add('hidden'); }
            if (iconPh)  iconPh?.classList.remove('hidden');
            if (iconRem) iconRem.classList.add('hidden');
        }

        document.getElementById('cc-form-msg').style.display = 'none';

        const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
        const chk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };

        if (fillData) {
            // Identity
            set('cc-name',         fillData.name);
            set('cc-description',  fillData.description);
            set('cc-personality',  fillData.personality);
            set('cc-speech-style', fillData.speech_style);
            set('cc-quirks',   (fillData.quirks   || []).join('\n'));
            set('cc-likes',    (fillData.likes    || []).join('\n'));
            set('cc-dislikes', (fillData.dislikes || []).join('\n'));
            set('cc-accent-color',  fillData.accent_color  || '#6366f1');
            set('cc-avatar-symbol', fillData.avatar_symbol || '✦');
            set('cc-model',         fillData.default_model || 'gemini-1.5-flash');

            // Behavior
            const beh = fillData.behavior || {};
            set('cc-temperature',           beh.temperature           ?? 0.85);
            set('cc-initiate-temp',         beh.initiate_temperature  ?? 0.80);
            set('cc-change-susceptibility', beh.change_susceptibility ?? 0.70);
            set('cc-default-mood',          beh.default_mood          || 'calm');
            _updateRangeDisplays();

            // Capabilities
            const cap = fillData.capabilities || {};
            chk('cc-cap-tools',     cap.tools_enabled             ?? false);
            chk('cc-cap-workspace', cap.workspace_access          ?? false);
            chk('cc-cap-memory',    cap.memory_updates_enabled    ?? true);
            chk('cc-cap-internet',  cap.internet_search           ?? false);

            // Prompts
            const prm = fillData.prompts || {};
            set('cc-prompt-chat',     prm.chat_system    || '');
            set('cc-prompt-initiate', prm.initiate_system || '');

            // Expressions & Moods
            set('cc-expressions',       (fillData.expressions || []).join('\n'));
            set('cc-moods',             (fillData.moods       || []).join('\n'));
            set('cc-default-expression', fillData.default_expression || 'default');

        } else {
            form.reset();
            set('cc-accent-color',  '#6366f1');
            set('cc-avatar-symbol', '✦');
            // Ranges don't fully reset via form.reset() in all browsers — set explicitly
            set('cc-temperature',           0.85);
            set('cc-initiate-temp',         0.80);
            set('cc-change-susceptibility', 0.70);
            _updateRangeDisplays();
            // Memory enabled by default for new companions
            chk('cc-cap-memory', true);
            // Default expressions & moods
            set('cc-expressions', 'default\nhappy\nthinking\nfocused\nerror');
            set('cc-moods',       'calm\nhappy\nreflective\nintense');
            set('cc-default-expression', 'default');
            set('cc-default-mood', 'calm');
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
        const num = id => parseFloat(document.getElementById(id)?.value || '0');
        const chk = id => document.getElementById(id)?.checked ?? false;

        return {
            name:          document.getElementById('cc-name')?.value?.trim(),
            description:   document.getElementById('cc-description')?.value?.trim(),
            personality:   document.getElementById('cc-personality')?.value?.trim(),
            speech_style:  document.getElementById('cc-speech-style')?.value?.trim() || '',
            quirks:        lines('cc-quirks'),
            likes:         lines('cc-likes'),
            dislikes:      lines('cc-dislikes'),
            accent_color:  document.getElementById('cc-accent-color')?.value,
            avatar_symbol: document.getElementById('cc-avatar-symbol')?.value?.trim() || '✦',
            default_model: document.getElementById('cc-model')?.value,
            // Extended
            behavior: {
                temperature:           num('cc-temperature'),
                initiate_temperature:  num('cc-initiate-temp'),
                change_susceptibility: num('cc-change-susceptibility'),
                default_mood:          document.getElementById('cc-default-mood')?.value?.trim() || 'calm',
            },
            capabilities: {
                tools_enabled:          chk('cc-cap-tools'),
                workspace_access:       chk('cc-cap-workspace'),
                memory_updates_enabled: chk('cc-cap-memory'),
                internet_search:        chk('cc-cap-internet'),
            },
            prompts: {
                chat_system:    document.getElementById('cc-prompt-chat')?.value?.trim()     || '',
                initiate_system: document.getElementById('cc-prompt-initiate')?.value?.trim() || '',
            },
            expressions:        lines('cc-expressions'),
            moods:              lines('cc-moods'),
            default_expression: document.getElementById('cc-default-expression')?.value?.trim() || 'default',
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
                    behavior:      payload.behavior,
                    capabilities:  payload.capabilities,
                    prompts:       payload.prompts,
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
            const isNew = !_editingId;
            if (isNew) _editingId = data.id;
            await _loadList();
            if (typeof showToast === 'function') showToast(data.message, 'success');
            // After creating a new companion, reload its form so icon controls appear
            if (isNew) {
                const fresh = await fetch(`${API}/${_editingId}`);
                if (fresh.ok) _showForm(await fresh.json(), false);
            }
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
        const raw   = document.getElementById('cc-import-json')?.value?.trim();
        const msgEl = document.getElementById('cc-import-msg');
        if (!raw) {
            msgEl.style.display = '';
            msgEl.textContent   = 'Paste a JSON config first.';
            msgEl.className     = 'cc-form-msg cc-form-msg-error';
            return;
        }
        let config;
        try { config = JSON.parse(raw); }
        catch {
            msgEl.style.display = '';
            msgEl.textContent   = 'Invalid JSON.';
            msgEl.className     = 'cc-form-msg cc-form-msg-error';
            return;
        }
        try {
            const res  = await fetch(`${API}/import`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ config }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Import failed');
            msgEl.style.display = '';
            msgEl.textContent   = `✓ ${data.message}`;
            msgEl.className     = 'cc-form-msg cc-form-msg-ok';
            await _loadList();
            setTimeout(_hideImportDialog, 1200);
            if (typeof showToast === 'function') showToast(data.message, 'success');
        } catch (err) {
            msgEl.style.display = '';
            msgEl.textContent   = `Error: ${err.message}`;
            msgEl.className     = 'cc-form-msg cc-form-msg-error';
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    function init() {
        _root = document.getElementById('companion-creator-root');
        if (!_root || _root.dataset.ccInit) return;
        _root.dataset.ccInit = '1';

        _renderShell();
        _loadList();

        // Sidebar / form actions
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

        // Icon upload
        document.getElementById('cc-icon-file')?.addEventListener('change', async e => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (!file || !_editingId) return;
            const fd = new FormData();
            fd.append('file', file);
            try {
                const res  = await fetch(`${API}/${_editingId}/icon`, { method: 'POST', body: fd });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Upload failed');
                const url = `${API}/${_editingId}/icon?t=${Date.now()}`;
                const img = document.getElementById('cc-icon-img');
                if (img) { img.src = url; img.classList.remove('hidden'); }
                document.getElementById('cc-icon-ph')?.classList.add('hidden');
                document.getElementById('cc-icon-remove-btn')?.classList.remove('hidden');
                if (typeof showToast === 'function') showToast('Icon uploaded!', 'success');
                await _loadList();
            } catch (err) {
                if (typeof showToast === 'function') showToast(`Icon upload failed: ${err.message}`, 'error');
            }
        });

        // Icon remove
        document.getElementById('cc-icon-remove-btn')?.addEventListener('click', async () => {
            if (!_editingId) return;
            try {
                const res  = await fetch(`${API}/${_editingId}/icon`, { method: 'DELETE' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Remove failed');
                const img = document.getElementById('cc-icon-img');
                if (img) { img.src = ''; img.classList.add('hidden'); }
                document.getElementById('cc-icon-ph')?.classList.remove('hidden');
                document.getElementById('cc-icon-remove-btn')?.classList.add('hidden');
                if (typeof showToast === 'function') showToast('Icon removed.', 'success');
                await _loadList();
            } catch (err) {
                if (typeof showToast === 'function') showToast(`Failed to remove icon: ${err.message}`, 'error');
            }
        });

        // Live preview
        ['cc-accent-color', 'cc-avatar-symbol', 'cc-name'].forEach(id => {
            document.getElementById(id)?.addEventListener('input', _updatePreview);
        });

        // Collapsible sections
        document.querySelectorAll('.cc-adv-toggle').forEach(toggle => {
            toggle.addEventListener('click', () => {
                toggle.closest('.cc-adv-section').classList.toggle('open');
            });
        });

        // Range value displays
        [
            ['cc-temperature',           'cc-temp-val'],
            ['cc-initiate-temp',         'cc-itemp-val'],
            ['cc-change-susceptibility', 'cc-chsus-val'],
        ].forEach(([inputId, valId]) => {
            const input = document.getElementById(inputId);
            const disp  = document.getElementById(valId);
            if (input && disp) {
                input.addEventListener('input', () => {
                    disp.textContent = parseFloat(input.value).toFixed(2);
                });
            }
        });

        // Prompt variable click-to-copy
        document.querySelectorAll('.cc-prompt-var').forEach(tag => {
            tag.addEventListener('click', () => {
                const text = tag.dataset.var || tag.textContent;
                navigator.clipboard?.writeText(text).catch(() => {});
                const orig = tag.textContent;
                tag.textContent = '✓ copied';
                tag.style.opacity = '0.7';
                setTimeout(() => {
                    tag.textContent = orig;
                    tag.style.opacity = '';
                }, 900);
            });
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
