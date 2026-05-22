'use strict';
/**
 * Aethvion Suite — Companion Creator
 * Unified builder for creating, editing, exporting, and importing companions.
 * Built-in companions (Axiom, Lyra) can have their personality customized here.
 * Changes take effect immediately — no server restart required.
 */

const CompanionCreator = (() => {
    const API = '/api/companion-creator';
    const CHAT_API = '/api/companions';
    let _root = null;
    let _editingId = null;
    let _isBuiltin = false;
    let _activeData = null;   // full companion data for the currently open pane
    let _chatHistory = [];    // [{role, content}] for the current chat session
    let _chatStreaming = false;

    // ── Shell ─────────────────────────────────────────────────────────────────

    function _renderShell() {
        _root.innerHTML = `
<div class="cc-hub" id="cc-hub">

  <!-- ── Left roster panel ────────────────────────────────────────────── -->
  <div class="cc-roster" id="cc-roster">
    <div class="cc-roster-hdr">
      <div class="cc-roster-title">
        <i class="fas fa-users"></i>
        <span>Companions</span>
      </div>
      <div class="cc-roster-hdr-actions">
        <button id="cc-import-btn" class="cc-icon-btn" title="Import companion JSON">
          <i class="fas fa-file-import"></i>
        </button>
        <button id="cc-new-btn" class="cc-icon-btn cc-icon-btn-primary" title="New companion">
          <i class="fas fa-plus"></i>
        </button>
        <button id="cc-roster-toggle" class="cc-icon-btn" title="Collapse sidebar">
          <i class="fas fa-chevron-left"></i>
        </button>
      </div>
    </div>

    <div class="cc-search-wrap">
      <i class="fas fa-search cc-search-icon"></i>
      <input type="text" id="cc-search" class="cc-search-input" placeholder="Search companions…" autocomplete="off">
    </div>

    <div class="cc-roster-scroll">
      <div class="cc-roster-section">
        <div class="cc-roster-section-label">Built-in</div>
        <div id="cc-builtin-list" class="cc-card-list">
          <div class="cc-card-loading"><i class="fas fa-spinner fa-spin"></i></div>
        </div>
      </div>
      <div class="cc-roster-section">
        <div class="cc-roster-section-label">Your Companions</div>
        <div id="cc-custom-list" class="cc-card-list">
          <div class="cc-card-empty">No companions yet — hit <strong>+</strong> to create one.</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Right panel ──────────────────────────────────────────────────── -->
  <div class="cc-detail" id="cc-detail">

    <!-- Empty state (no companion selected) -->
    <div class="cc-empty-state" id="cc-empty-state">
      <i class="fas fa-users cc-empty-icon"></i>
      <p class="cc-empty-title">Select a companion</p>
      <p class="cc-empty-sub">Choose from the list to start chatting, or create a new one.</p>
      <button id="cc-empty-new-btn" class="cc-btn cc-btn-primary cc-btn-sm" style="margin-top:0.75rem">
        <i class="fas fa-plus"></i> New Companion
      </button>
    </div>

    <!-- Active companion pane (shown when a companion is selected) -->
    <div class="cc-active-pane hidden" id="cc-active-pane">

      <!-- Pane header: avatar + name + Chat/Settings tabs -->
      <div class="cc-pane-hdr">
        <div class="cc-pane-identity">
          <div class="cc-pane-avatar" id="cc-pane-avatar">✦</div>
          <div class="cc-pane-meta">
            <span class="cc-pane-name" id="cc-pane-name"></span>
            <span class="cc-pane-sub"  id="cc-pane-sub"></span>
          </div>
        </div>
        <div class="cc-pane-tabs">
          <button class="cc-ptab cc-ptab-active" id="cc-ptab-chat">
            <i class="fas fa-comment-dots"></i> Chat
          </button>
          <button class="cc-ptab" id="cc-ptab-settings">
            <i class="fas fa-sliders"></i> Settings
          </button>
        </div>
      </div>

      <!-- Chat view (default) -->
      <div class="cc-chat-view" id="cc-chat-view">
        <!-- Portrait panel (left) -->
        <div class="cc-chat-portrait" id="cc-chat-portrait">
          <div class="cc-portrait-avatar" id="cc-portrait-avatar">✦</div>
          <div class="cc-portrait-name" id="cc-portrait-name"></div>
          <div class="cc-portrait-sub" id="cc-portrait-sub"></div>
        </div>
        <!-- Chat column (right) -->
        <div class="cc-chat-col">
          <div class="cc-chat-msgs" id="cc-chat-msgs">
            <div class="cc-chat-hint" id="cc-chat-hint">
              <i class="fas fa-comment-dots"></i>
              <span>Start a conversation with <strong id="cc-chat-cname">your companion</strong></span>
            </div>
          </div>
          <div class="cc-chat-bar">
            <textarea id="cc-chat-input" class="cc-chat-input" placeholder="Message…" rows="1" autocomplete="off"></textarea>
            <button id="cc-chat-send" class="cc-chat-send-btn" title="Send">
              <i class="fas fa-paper-plane"></i>
            </button>
          </div>
        </div>
      </div>

      <!-- Settings view (shown when Settings tab is active) -->
      <div class="cc-settings-view hidden" id="cc-settings-view">
        <form id="cc-form" class="cc-form">
        <div id="cc-builtin-notice" class="cc-builtin-notice hidden">
          <i class="fas fa-circle-info"></i>
          Built-in companion — your changes are saved as overrides and don't modify core files.
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
            <select id="cc-model" class="control-select" style="width:100%">
              <option value="">Loading models…</option>
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

              <!-- Icon mode toggle -->
              <div style="margin-top:0.9rem;border-top:1px solid var(--border);padding-top:0.9rem">
                <label class="cc-toggle-row" for="cc-icon-mode" style="border:none;padding:0">
                  <div>
                    <div class="cc-cap-label">Icon Mode</div>
                    <div class="cc-cap-desc">Assign an image to each expression — the portrait shows the active one</div>
                  </div>
                  <span class="cc-toggle-wrap">
                    <input type="checkbox" id="cc-icon-mode" class="cc-toggle-input">
                    <span class="cc-toggle-thumb"></span>
                  </span>
                </label>
              </div>

              <!-- Expression images grid -->
              <div id="cc-expr-images-wrap" class="cc-expr-images-wrap hidden">
                <div class="cc-section-label" style="margin-top:0.9rem;margin-bottom:0.25rem">Expression Images</div>
                <p class="cc-hint" style="margin:0 0 0.6rem">Save the companion first, then upload one image per expression.</p>
                <div id="cc-expr-images-grid" class="cc-expr-images-grid"></div>
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
      </div><!-- /.cc-settings-view -->

    </div><!-- /.cc-active-pane -->

  </div><!-- /.cc-detail -->

  <!-- Import dialog (fixed overlay, outside layout flow) -->
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

</div><!-- /.cc-hub -->`;
    }

    // ── List rendering ────────────────────────────────────────────────────────

    /** Format a "YYYY-MM-DD HH:MM:SS" timestamp into a human-readable "X ago" string. */
    function _timeSince(tsStr) {
        try {
            const ts    = new Date(tsStr.replace(' ', 'T'));
            const delta = Math.floor((Date.now() - ts.getTime()) / 1000);
            if (delta < 120)    return 'Just now';
            if (delta < 3600)   return `${Math.floor(delta / 60)}m ago`;
            if (delta < 86400)  return `${Math.floor(delta / 3600)}h ago`;
            if (delta < 172800) return 'Yesterday';
            return `${Math.floor(delta / 86400)}d ago`;
        } catch { return null; }
    }

    /** Sort companions by last_interaction_ts descending; no-interaction goes to end. */
    function _sortByLastInteraction(list) {
        return [...list].sort((a, b) => {
            if (!a.last_interaction_ts && !b.last_interaction_ts) return 0;
            if (!a.last_interaction_ts) return 1;
            if (!b.last_interaction_ts) return -1;
            return b.last_interaction_ts.localeCompare(a.last_interaction_ts);
        });
    }

    async function _loadList() {
        const builtinEl = document.getElementById('cc-builtin-list');
        const customEl  = document.getElementById('cc-custom-list');
        if (!builtinEl || !customEl) return;

        try {
            const res  = await fetch(`${API}/all`);
            const data = await res.json();
            const all  = data.companions || [];

            const builtins = _sortByLastInteraction(all.filter(c =>  c._builtin));
            const customs  = _sortByLastInteraction(all.filter(c => !c._builtin));

            builtinEl.innerHTML = builtins.length
                ? builtins.map(c => _listItemHTML(c, true)).join('')
                : '<div class="cc-card-empty">None found.</div>';

            customEl.innerHTML = customs.length
                ? customs.map(c => _listItemHTML(c, false)).join('')
                : '<div class="cc-card-empty">No companions yet — hit <strong>+</strong> to create one.</div>';

            // Wire up card click handlers
            document.querySelectorAll('.cc-companion-card').forEach(item => {
                item.addEventListener('click', () =>
                    _editCompanion(item.dataset.id, item.dataset.builtin === 'true'));
                item.addEventListener('keydown', e => {
                    if (e.key === 'Enter') _editCompanion(item.dataset.id, item.dataset.builtin === 'true');
                });
            });

            // Wire up search filter
            _initSearch(all);

        } catch (e) {
            if (builtinEl) builtinEl.innerHTML = `<div class="cc-card-empty" style="color:#f87171">Error: ${e.message}</div>`;
        }
    }

    function _initSearch(allCompanions) {
        const searchEl = document.getElementById('cc-search');
        if (!searchEl) return;
        searchEl.addEventListener('input', () => {
            const q = searchEl.value.toLowerCase().trim();
            document.querySelectorAll('.cc-companion-card').forEach(card => {
                const name = (card.querySelector('.cc-card-name')?.textContent || '').toLowerCase();
                card.style.display = (!q || name.includes(q)) ? '' : 'none';
            });
        });
    }

    function _listItemHTML(c, isBuiltin) {
        const active   = _editingId === c.id ? 'active' : '';
        const color    = c.accent_color || '#6366f1';
        const desc     = c.description ? `<span class="cc-card-desc">${c.description}</span>` : '';
        const badge    = isBuiltin
            ? `<span class="cc-card-badge cc-card-badge-builtin"><i class="fas fa-lock"></i> Built-in</span>`
            : '';
        // Last interaction timestamp
        const lastLabel = c.last_interaction_ts
            ? `<span class="cc-card-last"><i class="fas fa-clock"></i>${_timeSince(c.last_interaction_ts)}</span>`
            : `<span class="cc-card-last cc-card-last-none">No chats yet</span>`;
        // Sidebar avatar: expression image (icon mode) > main icon > symbol
        const exprImgs = c.expression_images || {};
        const defExpr  = c.default_expression || 'default';
        const avatar = (c.icon_mode && exprImgs[defExpr])
            ? `<img class="cc-card-avatar cc-card-avatar-img" src="${API}/${c.id}/expression/${defExpr}?t=${Date.now()}" alt="${c.name}">`
            : c.has_icon
            ? `<img class="cc-card-avatar cc-card-avatar-img" src="${API}/${c.id}/icon?t=${Date.now()}" alt="${c.name}">`
            : `<div class="cc-card-avatar" style="background:${color}22;color:${color}">${c.avatar_symbol || '✦'}</div>`;
        return `
        <div class="cc-companion-card ${active}" data-id="${c.id}" data-builtin="${isBuiltin}" role="button" tabindex="0">
          ${avatar}
          <div class="cc-card-body">
            <span class="cc-card-name">${c.name}</span>
            ${desc}
            <div class="cc-card-footer">
              ${badge}
              ${lastLabel}
            </div>
          </div>
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
        // Note: visibility of the pane/views is managed by _selectCompanion / _switchView.
        // _showForm only fills in field values and handles field locking.
        const form = document.getElementById('cc-form');
        if (!form) return;

        // Builtin notice
        const notice = document.getElementById('cc-builtin-notice');
        notice.classList.toggle('hidden', !isBuiltin);

        // All form fields are editable — built-in changes are saved as overrides
        form.querySelectorAll('input:not([type="file"]):not([type="color"]), textarea, select').forEach(el => {
            el.disabled = false; el.style.opacity = '';
        });
        const colorPicker = document.getElementById('cc-accent-color');
        if (colorPicker) { colorPicker.disabled = false; colorPicker.style.pointerEvents = ''; }

        // Save always shown; delete/export only for existing custom companions
        document.getElementById('cc-save-btn').style.display   = '';
        document.getElementById('cc-delete-btn').style.display = (!isBuiltin && fillData) ? '' : 'none';
        const exportBtn = document.getElementById('cc-export-btn');
        exportBtn.classList.toggle('hidden', isBuiltin || !fillData);

        // Icon section — for any existing companion; "save first" hint for new ones
        const iconBtns     = document.getElementById('cc-icon-btns');
        const iconSaveHint = document.getElementById('cc-icon-save-hint');
        if (!fillData) {
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
            // Model — use the shared helper so options match the registry
            const modelSel = document.getElementById('cc-model');
            const modelVal = fillData.default_model || 'gemini-1.5-flash';
            if (modelSel) {
                if (typeof window._populateModelSelect === 'function') {
                    window._populateModelSelect(modelSel, modelVal);
                } else {
                    modelSel.value = modelVal;
                }
            }

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

            // Icon mode
            const iconModeToggle = document.getElementById('cc-icon-mode');
            if (iconModeToggle) iconModeToggle.checked = !!(fillData.icon_mode);
            const exprImgWrap = document.getElementById('cc-expr-images-wrap');
            if (exprImgWrap) exprImgWrap.classList.toggle('hidden', !fillData.icon_mode);
            if (fillData.icon_mode && _editingId) {
                _renderExpressionImages(fillData.expressions || [], fillData.expression_images || {});
            }

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
            // Icon mode off for new companions
            const iconModeEl = document.getElementById('cc-icon-mode');
            if (iconModeEl) iconModeEl.checked = false;
            document.getElementById('cc-expr-images-wrap')?.classList.add('hidden');
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
            icon_mode:          chk('cc-icon-mode'),
        };
    }

    // ── Actions ───────────────────────────────────────────────────────────────

    async function _editCompanion(id, isBuiltin = false) {
        _editingId = id;
        _isBuiltin = isBuiltin;
        try {
            const res  = await fetch(`${API}/${id}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            _activeData = data;
            // Persist selection so refresh restores it
            try { localStorage.setItem('cc_last_companion', JSON.stringify({ id, isBuiltin })); } catch {}
            _loadList(); // refresh card active state
            _selectCompanion(data, isBuiltin);
        } catch (e) {
            if (typeof showToast === 'function') showToast(`Failed to load companion: ${e.message}`, 'error');
        }
    }

    // ── View orchestration ────────────────────────────────────────────────────

    function _selectCompanion(data, isBuiltin) {
        // Show the active pane and update header
        document.getElementById('cc-empty-state').classList.add('hidden');
        document.getElementById('cc-active-pane').classList.remove('hidden');
        _updatePaneHeader(data, isBuiltin);
        // Default to chat view; for truly new (unsaved) companions switch to settings
        _switchView(data ? 'chat' : 'settings');
        if (data) _loadHistory(data.id);
    }

    function _startNewCompanion() {
        _editingId = null;
        _isBuiltin = false;
        _activeData = null;
        // Update card active states
        document.querySelectorAll('.cc-companion-card').forEach(c => c.classList.remove('active'));
        // Update pane header for "new companion" mode
        _updatePaneHeader(null, false, true);
        document.getElementById('cc-empty-state').classList.add('hidden');
        document.getElementById('cc-active-pane').classList.remove('hidden');
        // Go straight to settings (create form)
        _switchView('settings');
        _showForm(null, false);
        _loadList();
    }

    function _switchView(view) {
        const chatView     = document.getElementById('cc-chat-view');
        const settingsView = document.getElementById('cc-settings-view');
        const chatTab      = document.getElementById('cc-ptab-chat');
        const settingsTab  = document.getElementById('cc-ptab-settings');

        if (view === 'chat') {
            chatView?.classList.remove('hidden');
            settingsView?.classList.add('hidden');
            chatTab?.classList.add('cc-ptab-active');
            settingsTab?.classList.remove('cc-ptab-active');
        } else {
            chatView?.classList.add('hidden');
            settingsView?.classList.remove('hidden');
            chatTab?.classList.remove('cc-ptab-active');
            settingsTab?.classList.add('cc-ptab-active');
            // Fill form with current companion data (or blank for new)
            _showForm(_activeData, _isBuiltin);
        }
    }

    function _updatePaneHeader(data, isBuiltin, isNew = false) {
        const avatarEl   = document.getElementById('cc-pane-avatar');
        const nameEl     = document.getElementById('cc-pane-name');
        const subEl      = document.getElementById('cc-pane-sub');
        const chatTab    = document.getElementById('cc-ptab-chat');
        const portAvEl   = document.getElementById('cc-portrait-avatar');
        const portNameEl = document.getElementById('cc-portrait-name');
        const portSubEl  = document.getElementById('cc-portrait-sub');

        if (isNew || !data) {
            if (avatarEl) { avatarEl.textContent = '✦'; avatarEl.style.background = 'rgba(99,102,241,0.15)'; avatarEl.style.color = '#818cf8'; }
            if (nameEl) nameEl.textContent = 'New Companion';
            if (subEl)  subEl.textContent  = 'Fill in the settings below to create';
            if (chatTab) { chatTab.disabled = true; chatTab.title = 'Save the companion first to start chatting'; }
            if (portAvEl)   { portAvEl.textContent = '✦'; portAvEl.style.background = 'rgba(99,102,241,0.15)'; portAvEl.style.color = '#818cf8'; }
            if (portNameEl) portNameEl.textContent = '';
            if (portSubEl)  portSubEl.textContent  = '';
            return;
        }

        if (chatTab) { chatTab.disabled = false; chatTab.title = ''; }
        const color = data.accent_color || '#6366f1';

        // Header avatar
        if (data.has_icon && data.id) {
            if (avatarEl) avatarEl.innerHTML = `<img src="${API}/${data.id}/icon?t=${Date.now()}" style="width:100%;height:100%;object-fit:cover;border-radius:11px">`;
            if (avatarEl) { avatarEl.style.background = ''; avatarEl.style.color = ''; }
        } else {
            if (avatarEl) { avatarEl.textContent = data.avatar_symbol || '✦'; avatarEl.style.background = `${color}22`; avatarEl.style.color = color; }
        }
        if (nameEl) nameEl.textContent = data.name || '';
        if (subEl)  subEl.textContent  = isBuiltin ? 'Built-in' : (data.description || '');

        // Portrait panel — priority: expression image > icon > symbol
        // Use the last remembered expression if it still has an image, otherwise fall back to default
        const exprImgs   = data.expression_images || {};
        const storedExpr = (() => { try { return data.id ? localStorage.getItem(`cc_last_expr_${data.id}`) : null; } catch { return null; } })();
        const defExpr    = (storedExpr && exprImgs[storedExpr]) ? storedExpr : (data.default_expression || 'default');
        if (data.icon_mode && exprImgs[defExpr] && data.id) {
            const exprUrl = `${API}/${data.id}/expression/${defExpr}?t=${Date.now()}`;
            if (portAvEl) { portAvEl.innerHTML = `<img src="${exprUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:20px">`; portAvEl.style.background = ''; portAvEl.style.color = ''; }
        } else if (data.has_icon && data.id) {
            if (portAvEl) { portAvEl.innerHTML = `<img src="${API}/${data.id}/icon?t=${Date.now()}" style="width:100%;height:100%;object-fit:cover;border-radius:20px">`; portAvEl.style.background = ''; portAvEl.style.color = ''; }
        } else {
            if (portAvEl) { portAvEl.textContent = data.avatar_symbol || '✦'; portAvEl.style.background = `${color}22`; portAvEl.style.color = color; }
        }
        if (portNameEl) portNameEl.textContent = data.name || '';
        if (portSubEl)  portSubEl.textContent  = isBuiltin ? 'Built-in' : '';
    }

    // ── Chat ──────────────────────────────────────────────────────────────────

    async function _loadHistory(companionId) {
        const msgsEl = document.getElementById('cc-chat-msgs');
        if (!msgsEl) return;
        _chatHistory = [];
        // Reset to hint
        msgsEl.innerHTML = `
          <div class="cc-chat-hint" id="cc-chat-hint">
            <i class="fas fa-comment-dots"></i>
            <span>Start a conversation with <strong id="cc-chat-cname">${_activeData?.name || 'your companion'}</strong></span>
          </div>`;
        try {
            const res  = await fetch(`${CHAT_API}/${companionId}/history?offset_days=0&limit_days=1`);
            if (!res.ok) return;
            const data = await res.json();
            const days = data.history || [];
            let loaded = 0;
            for (const day of days) {
                for (const msg of (day.messages || [])) {
                    _chatHistory.push({ role: msg.role, content: msg.content });
                    _appendMessage(msg.role === 'user' ? 'user' : 'companion', msg.content);
                    loaded++;
                }
            }
            if (loaded > 0) {
                document.getElementById('cc-chat-hint')?.remove();
                msgsEl.scrollTop = msgsEl.scrollHeight;
            }
        } catch (err) {
            console.warn('[CompanionCreator] History load failed:', err);
        }
    }

    function _appendMessage(role, text, id = null) {
        const msgsEl = document.getElementById('cc-chat-msgs');
        if (!msgsEl) return null;
        const bubble = document.createElement('div');
        bubble.className = `cc-msg cc-msg-${role}`;
        if (id) bubble.id = id;
        const color  = _activeData?.accent_color || '#6366f1';
        const symbol = _activeData?.avatar_symbol || '✦';
        if (role === 'companion') {
            bubble.innerHTML = `
              <div class="cc-msg-avatar" style="background:${color}22;color:${color}">${symbol}</div>
              <div class="cc-msg-bubble cc-msg-md">${_renderMd(text)}</div>`;
            _applyHighlight(bubble);
        } else {
            bubble.innerHTML = `<div class="cc-msg-bubble">${_escHtml(text)}</div>`;
        }
        msgsEl.appendChild(bubble);
        msgsEl.scrollTop = msgsEl.scrollHeight;
        return bubble;
    }

    function _escHtml(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
    }

    // Strip [tool:...] blocks and <expression>/<mood> tags from text before display.
    // Tool blocks can span multiple lines and may have nested brackets inside quoted values,
    // so we handle them with a bracket-depth counter mirroring the Python parse_tool_blocks.
    function _stripToolTags(text) {
        if (!text) return '';
        let out = '';
        let i = 0;
        while (i < text.length) {
            // Look for [tool: prefix
            const idx = text.indexOf('[tool:', i);
            if (idx === -1) {
                out += text.slice(i);
                break;
            }
            // Keep everything before the tool block
            out += text.slice(i, idx);
            // Walk forward counting bracket depth
            let depth = 0;
            let j = idx;
            while (j < text.length) {
                if (text[j] === '[') depth++;
                else if (text[j] === ']') { depth--; if (depth === 0) { j++; break; } }
                j++;
            }
            // Skip the block entirely; continue after it
            i = j;
        }
        // Also strip expression, mood, and break tags
        return out
            .replace(/<expression>[\s\S]*?<\/expression>/gi, '')
            .replace(/<mood>[\s\S]*?<\/mood>/gi, '')
            .replace(/<break\s*\/?>/gi, '')
            .replace(/[ \t]{2,}/g, ' ')
            .trim();
    }

    // Render companion text as markdown (marked + optional hljs highlight)
    function _renderMd(text) {
        if (!text) return '';
        if (typeof marked !== 'undefined' && marked.parse) {
            try { return marked.parse(text); } catch { /* fall through */ }
        }
        return _escHtml(text);
    }

    // Run hljs on any code blocks inside a container element
    function _applyHighlight(container) {
        if (typeof hljs === 'undefined' || !container) return;
        container.querySelectorAll('pre code:not([data-highlighted])').forEach(
            block => hljs.highlightElement(block)
        );
    }

    async function _sendMessage() {
        if (_chatStreaming) return;
        const input = document.getElementById('cc-chat-input');
        const message = (input?.value || '').trim();
        if (!message || !_editingId) return;

        input.value = '';
        _autoResizeInput(input);

        // Remove the "start chatting" hint
        document.getElementById('cc-chat-hint')?.remove();

        // Push user message
        _appendMessage('user', message);
        _chatHistory.push({ role: 'user', content: message });

        // Streaming lock + disable UI
        _chatStreaming = true;
        const sendBtn = document.getElementById('cc-chat-send');
        if (input)   input.disabled   = true;
        if (sendBtn) sendBtn.disabled = true;

        // Create companion bubble (streaming placeholder)
        const color  = _activeData?.accent_color || '#6366f1';
        const symbol = _activeData?.avatar_symbol || '✦';
        const msgsEl = document.getElementById('cc-chat-msgs');

        function _makeBubble(streaming = true) {
            const b = document.createElement('div');
            b.className = 'cc-msg cc-msg-companion';
            b.innerHTML = `
              <div class="cc-msg-avatar" style="background:${color}22;color:${color}">${symbol}</div>
              <div class="cc-msg-bubble${streaming ? ' cc-msg-streaming' : ''}">…</div>`;
            msgsEl?.appendChild(b);
            if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
            return b;
        }

        function _makeToolIndicator(toolName) {
            const el = document.createElement('div');
            el.className = 'cc-tool-indicator';
            el.innerHTML = `<i class="fas fa-plug"></i> Using <strong>${_escHtml(toolName)}</strong>…`;
            msgsEl?.appendChild(el);
            if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
            return el;
        }

        let currentBubble    = _makeBubble(true);
        let currentBubbleText = currentBubble.querySelector('.cc-msg-bubble');
        let toolIndicator    = null;

        const histForApi = _chatHistory.slice(0, -1).map(m => ({ role: m.role, content: m.content }));

        try {
            const res = await fetch(`${CHAT_API}/${_editingId}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, history: histForApi })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const reader    = res.body.getReader();
            const decoder   = new TextDecoder();
            let fullText    = '';
            let finalText   = '';
            let finalParts  = [];   // populated when companion uses <break>

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const lines = decoder.decode(value).split('\n');
                for (const line of lines) {
                    const raw = line.trim();
                    if (!raw) continue;
                    try {
                        const evt = JSON.parse(raw);

                        if (evt.type === 'message' && evt.content) {
                            fullText += evt.content;
                            if (currentBubbleText) {
                                // Strip tool call blocks and expression tags from the live display
                                const displayText = _stripToolTags(fullText);
                                if (displayText) {
                                    currentBubbleText.innerHTML = _renderMd(displayText);
                                    currentBubbleText.classList.remove('cc-msg-streaming');
                                }
                            }

                        } else if (evt.type === 'tool_start') {
                            // Finalize the first bubble with clean text, then show the indicator
                            const cleanedFirst = _stripToolTags(fullText);
                            if (currentBubbleText) {
                                currentBubbleText.classList.add('cc-msg-md');
                                currentBubbleText.classList.remove('cc-msg-streaming');
                                currentBubbleText.innerHTML = cleanedFirst ? _renderMd(cleanedFirst) : '';
                            }
                            _applyHighlight(currentBubble);
                            toolIndicator = _makeToolIndicator(evt.tool || 'tool');

                        } else if (evt.type === 'tool_response_start') {
                            // Remove tool indicator, reset accumulator, open a new bubble
                            toolIndicator?.remove();
                            toolIndicator = null;
                            fullText = '';
                            currentBubble     = _makeBubble(true);
                            currentBubbleText = currentBubble.querySelector('.cc-msg-bubble');

                        } else if (evt.type === 'final_cleaned' && evt.content) {
                            finalText = evt.content;

                        } else if (evt.type === 'error' && evt.message) {
                            finalText = evt.message;
                            if (currentBubbleText) {
                                currentBubbleText.classList.add('cc-msg-error-text');
                                currentBubbleText.classList.remove('cc-msg-streaming');
                            }

                        } else if (evt.type === 'done') {
                            if (evt.content)  finalText  = evt.content;
                            if (evt.parts)    finalParts = evt.parts;
                            if (evt.expression) _updatePortraitExpression(evt.expression);
                        }
                    } catch { /* non-JSON chunk */ }
                }
                if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
            }

            // finalText from server is already cleaned; fullText is the raw stream fallback.
            // finalParts is set when the companion used <break> to split its response.
            const primaryText = finalText || _stripToolTags(fullText) || '(no response)';
            const parts       = finalParts.length > 1 ? finalParts : null;
            const firstPart   = parts ? parts[0] : primaryText;

            // Render the first (or only) part into the current bubble
            if (currentBubbleText) {
                currentBubbleText.classList.add('cc-msg-md');
                currentBubbleText.classList.remove('cc-msg-streaming');
                currentBubbleText.innerHTML = _renderMd(firstPart);
            }
            _applyHighlight(currentBubble);
            _chatHistory.push({ role: 'assistant', content: firstPart });

            // Render subsequent <break> parts as new bubbles with natural delays
            if (parts) {
                for (let i = 1; i < parts.length; i++) {
                    ((part, delay) => {
                        setTimeout(() => {
                            const nb = _appendMessage('companion', part);
                            if (nb) _applyHighlight(nb);
                            _chatHistory.push({ role: 'assistant', content: part });
                            if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
                        }, delay);
                    })(parts[i], i * 420);
                }
            }

        } catch (err) {
            if (currentBubbleText) { currentBubbleText.textContent = 'Failed to get a response.'; currentBubbleText.classList.add('cc-msg-error-text'); }
        } finally {
            _chatStreaming = false;
            if (input)   { input.disabled   = false; input.focus(); }
            if (sendBtn)   sendBtn.disabled  = false;
            if (msgsEl)    msgsEl.scrollTop  = msgsEl.scrollHeight;
        }
    }

    function _autoResizeInput(el) {
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 120) + 'px';
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
            let url, method, body;

            if (_editingId) {
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
            if (typeof showToast === 'function') showToast(data.message, 'success');
            // Reload fresh data (includes has_icon, etc.)
            const freshRes = await fetch(`${API}/${_editingId}`);
            if (freshRes.ok) {
                const freshData = await freshRes.json();
                _activeData = freshData;
                _updatePaneHeader(freshData, _isBuiltin);
                _showForm(freshData, _isBuiltin);
            }
            await _loadList();
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
            _activeData = null;
            document.getElementById('cc-active-pane')?.classList.add('hidden');
            document.getElementById('cc-empty-state')?.classList.remove('hidden');
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

    // ── Expression images ─────────────────────────────────────────────────────

    function _renderExpressionImages(expressions, exprImages) {
        const grid = document.getElementById('cc-expr-images-grid');
        if (!grid) return;
        if (!expressions.length) {
            grid.innerHTML = '<p class="cc-hint" style="margin:0">No expressions defined — add some in the fields above.</p>';
            return;
        }
        grid.innerHTML = expressions.map(expr => {
            const hasImg = !!(exprImages && exprImages[expr]);
            const imgUrl = hasImg ? `${API}/${_editingId}/expression/${expr}?t=${Date.now()}` : null;
            return `
            <div class="cc-expr-slot" data-expr="${expr}">
              <div class="cc-expr-slot-thumb">
                ${hasImg
                    ? `<img class="cc-expr-slot-img" src="${imgUrl}" alt="${expr}">`
                    : `<i class="fas fa-image cc-expr-slot-ph"></i>`}
              </div>
              <div class="cc-expr-slot-info">
                <div class="cc-expr-slot-name">${expr}</div>
                <div class="cc-expr-slot-btns">
                  <label class="cc-btn cc-btn-ghost cc-btn-sm cc-expr-upload-lbl" for="cc-expr-file-${expr}" title="Upload image">
                    <i class="fas fa-upload"></i>
                  </label>
                  <input type="file" id="cc-expr-file-${expr}" data-expr="${expr}" accept="image/png,image/jpeg,image/gif,image/webp" style="display:none" class="cc-expr-file-input">
                  ${hasImg ? `<button type="button" class="cc-btn cc-btn-ghost cc-btn-sm cc-expr-delete-btn" data-expr="${expr}" title="Remove image"><i class="fas fa-trash"></i></button>` : ''}
                </div>
              </div>
            </div>`;
        }).join('');

        // Wire up file inputs
        grid.querySelectorAll('.cc-expr-file-input').forEach(input => {
            input.addEventListener('change', async e => {
                const file = e.target.files?.[0];
                const exprName = e.target.dataset.expr;
                e.target.value = '';
                if (!file || !exprName || !_editingId) return;
                await _uploadExpressionImage(exprName, file);
            });
        });

        // Wire up delete buttons
        grid.querySelectorAll('.cc-expr-delete-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const exprName = btn.dataset.expr;
                if (!exprName || !_editingId) return;
                await _deleteExpressionImage(exprName);
            });
        });
    }

    async function _uploadExpressionImage(expressionName, file) {
        const fd = new FormData();
        fd.append('file', file);
        try {
            const res  = await fetch(`${API}/${_editingId}/expression/${expressionName}`, { method: 'POST', body: fd });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Upload failed');
            if (_activeData) {
                if (!_activeData.expression_images) _activeData.expression_images = {};
                _activeData.expression_images[expressionName] = data.ext;
                _activeData.icon_mode = true;
            }
            if (typeof showToast === 'function') showToast('Expression image uploaded!', 'success');
            _renderExpressionImages(_activeData?.expressions || [], _activeData?.expression_images || {});
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Upload failed: ${err.message}`, 'error');
        }
    }

    async function _deleteExpressionImage(expressionName) {
        try {
            const res  = await fetch(`${API}/${_editingId}/expression/${expressionName}`, { method: 'DELETE' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Delete failed');
            if (_activeData?.expression_images) {
                delete _activeData.expression_images[expressionName];
            }
            if (typeof showToast === 'function') showToast('Expression image removed.', 'success');
            _renderExpressionImages(_activeData?.expressions || [], _activeData?.expression_images || {});
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Failed to remove: ${err.message}`, 'error');
        }
    }

    function _updatePortraitExpression(expression) {
        if (!_activeData?.icon_mode || !expression || !_editingId) return;
        const exprImages = _activeData?.expression_images || {};
        if (!exprImages[expression]) return;
        const portAvEl = document.getElementById('cc-portrait-avatar');
        if (!portAvEl) return;
        const exprUrl = `${API}/${_editingId}/expression/${expression}?t=${Date.now()}`;
        portAvEl.innerHTML = `<img src="${exprUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:20px">`;
        portAvEl.style.background = '';
        portAvEl.style.color = '';
        // Persist so the portrait survives a page refresh
        try { localStorage.setItem(`cc_last_expr_${_editingId}`, expression); } catch {}
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    function init() {
        _root = document.getElementById('companion-creator-root');
        if (!_root || _root.dataset.ccInit) return;
        _root.dataset.ccInit = '1';

        _renderShell();

        // ── Restore collapsed roster state ────────────────────────────────────
        if (localStorage.getItem('cc_roster_collapsed') === '1') {
            document.getElementById('cc-hub')?.classList.add('roster-collapsed');
            const icon = document.querySelector('#cc-roster-toggle i');
            if (icon) icon.className = 'fas fa-chevron-right';
        }

        // ── Load list, then restore last selected companion ───────────────────
        _loadList().then(() => {
            try {
                const saved = JSON.parse(localStorage.getItem('cc_last_companion') || 'null');
                if (saved?.id) _editCompanion(saved.id, !!saved.isBuiltin);
            } catch {}
        });

        // Populate model select with the same categorized options used everywhere else in the suite
        if (typeof window.loadChatModels === 'function') window.loadChatModels();

        // Roster collapse toggle
        document.getElementById('cc-roster-toggle')?.addEventListener('click', () => {
            const hub       = document.getElementById('cc-hub');
            const collapsed = hub.classList.toggle('roster-collapsed');
            const icon      = document.querySelector('#cc-roster-toggle i');
            if (icon) icon.className = collapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left';
            try { localStorage.setItem('cc_roster_collapsed', collapsed ? '1' : '0'); } catch {}
        });

        // New companion buttons (roster header + empty-state)
        document.getElementById('cc-new-btn')?.addEventListener('click', _startNewCompanion);
        document.getElementById('cc-empty-new-btn')?.addEventListener('click', _startNewCompanion);

        // Cancel — go back to chat if editing an existing companion, else empty state
        document.getElementById('cc-cancel-btn')?.addEventListener('click', () => {
            if (_editingId) {
                _switchView('chat');
            } else {
                _activeData = null;
                document.getElementById('cc-active-pane')?.classList.add('hidden');
                document.getElementById('cc-empty-state')?.classList.remove('hidden');
                _loadList();
            }
        });

        // Chat/Settings tab buttons
        document.getElementById('cc-ptab-chat')?.addEventListener('click', () => _switchView('chat'));
        document.getElementById('cc-ptab-settings')?.addEventListener('click', () => _switchView('settings'));

        // Chat input: auto-resize + Enter to send
        document.getElementById('cc-chat-input')?.addEventListener('input', e => _autoResizeInput(e.target));
        document.getElementById('cc-chat-input')?.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _sendMessage(); }
        });
        document.getElementById('cc-chat-send')?.addEventListener('click', _sendMessage);
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
                if (_activeData) { _activeData.has_icon = true; _activeData.icon_ext = data.ext; _updatePaneHeader(_activeData, _isBuiltin); }
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
                if (_activeData) { _activeData.has_icon = false; _updatePaneHeader(_activeData, _isBuiltin); }
                await _loadList();
            } catch (err) {
                if (typeof showToast === 'function') showToast(`Failed to remove icon: ${err.message}`, 'error');
            }
        });

        // Icon mode toggle — show/hide expression images grid
        document.getElementById('cc-icon-mode')?.addEventListener('change', e => {
            const on  = e.target.checked;
            const wrap = document.getElementById('cc-expr-images-wrap');
            if (wrap) wrap.classList.toggle('hidden', !on);
            if (on && _editingId) {
                _renderExpressionImages(_activeData?.expressions || [], _activeData?.expression_images || {});
            }
        });

        // Re-render expression slots when expressions list changes (if icon mode is on)
        document.getElementById('cc-expressions')?.addEventListener('input', () => {
            if (document.getElementById('cc-icon-mode')?.checked && _editingId) {
                const exprs = (document.getElementById('cc-expressions')?.value || '')
                    .split('\n').map(s => s.trim()).filter(Boolean);
                _renderExpressionImages(exprs, _activeData?.expression_images || {});
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
