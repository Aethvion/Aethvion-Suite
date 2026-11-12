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
    const GROUPS_API = '/api/companions/groups';
    let _root = null;
    let _editingId = null;
    let _isBuiltin = false;
    let _activeData = null;   // full companion data for the currently open pane
    let _chatHistory = [];    // [{role, content}] for the current chat session
    let _chatStreaming = false;
    let _activeGroupId = null;
    let _activeGroupData = null;
    let _groupPacingPaused = false;
    let _groupTurnInProgress = false;
    let _groupScratchpadOpen = true;
    let _groupEventSource = null;        // live event stream of the open group
    let _groupSeenIds = new Set();       // message ids already on screen
    let _groupTypers = new Map();        // companion id -> name, currently typing

    // Shell

    function _renderShell() {
        _root.innerHTML = `
<div class="cc-hub" id="cc-hub">

  <!-- Left roster panel -->
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
      <div class="cc-roster-section">
        <div class="cc-roster-section-hdr" style="display:flex; justify-content:space-between; align-items:center; padding: 0.2rem 0.25rem 0.4rem 0.25rem;">
          <div class="cc-roster-section-label" style="margin:0;">Group Chats</div>
          <button id="cc-new-group-btn" class="cc-icon-btn cc-icon-btn-primary" title="New Group Chat" style="font-size:0.75rem; padding:2px 7px;">
            <i class="fas fa-plus"></i>
          </button>
        </div>
        <div id="cc-group-list" class="cc-card-list">
          <div class="cc-card-empty">No group chats yet.</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Right panel -->
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
          <div class="cc-pane-meta" style="position:relative">
            <div class="cc-pane-name-row">
              <span class="cc-pane-name" id="cc-pane-name"></span>
              <button type="button" class="cc-pane-model-badge hidden" id="cc-pane-model-badge" title="Click to switch active model"></button>
              <button type="button" class="cc-pane-profile-badge hidden" id="cc-pane-profile-badge" title="Click to switch Connector Access Profile"></button>
            </div>
            <div id="cc-quick-switch-popover" class="cc-quick-switch-popover hidden">
              <div class="cc-quick-switch-row">
                <label><i class="fas fa-microchip"></i> Active Model</label>
                <select id="cc-quick-model-select" class="control-select"></select>
              </div>
              <div class="cc-quick-switch-row">
                <label><i class="fas fa-plug-circle-bolt"></i> Connector Profile</label>
                <select id="cc-quick-profile-select" class="control-select">
                  <option value="full_local">Full Local Suite</option>
                  <option value="cloud_safe">Public / Cloud Safe</option>
                  <option value="ambient_observer">Ambient Context Only</option>
                  <option value="sandboxed">Strict Sandboxed</option>
                </select>
              </div>
            </div>
            <span class="cc-pane-sub"  id="cc-pane-sub"></span>
          </div>
        </div>
        <div class="cc-pane-tabs">
          <button type="button" class="cc-voice-toggle-btn" id="cc-auto-voice-btn" title="Toggle Auto-Voice (automatically speak companion replies)">
            <i class="fas fa-volume-xmark" id="cc-auto-voice-icon"></i>
            <span id="cc-auto-voice-label">Auto-Voice</span>
          </button>
          <button class="cc-ptab cc-ptab-active" id="cc-ptab-chat">
            <i class="fas fa-comment-dots"></i> Chat
          </button>
          <button class="cc-ptab" id="cc-ptab-scratchpad">
            <i class="fas fa-feather-pointed"></i> Scratchpad
          </button>
          <button class="cc-ptab" id="cc-ptab-vision">
            <i class="fas fa-eye"></i> Visual Memory
          </button>
          <button class="cc-ptab" id="cc-ptab-memory">
            <i class="fas fa-brain"></i> Memory
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
          <div class="cc-portrait-badges" id="cc-portrait-badges">
            <span class="cc-portrait-pill" id="cc-portrait-mood" title="Current Mood">
              <i class="fas fa-sparkles"></i> <span id="cc-portrait-mood-text">calm</span>
            </span>
            <span class="cc-portrait-pill" id="cc-portrait-expr" title="Current Expression">
              <i class="fas fa-masks-theater"></i> <span id="cc-portrait-expr-text">default</span>
            </span>
          </div>
          <div class="cc-portrait-status hidden" id="cc-portrait-status">
            <i class="fas fa-circle-notch fa-spin"></i> <span id="cc-portrait-status-text">Thinking…</span>
          </div>
          <div class="cc-portrait-actions">
            <button type="button" class="cc-btn cc-btn-ghost cc-btn-sm cc-portrait-action-btn" id="cc-checkin-btn" title="Have companion initiate a message">
              <i class="fas fa-hand-sparkles"></i> Check-in
            </button>
            <div class="cc-portrait-subactions">
              <button type="button" class="cc-icon-btn cc-icon-btn-sm" id="cc-export-chat-btn" title="Export chat transcript (.md)">
                <i class="fas fa-download"></i>
              </button>
              <button type="button" class="cc-icon-btn cc-icon-btn-sm" id="cc-clear-chat-btn" title="Clear conversation messages (keeps long-term memory)">
                <i class="fas fa-broom"></i>
              </button>
            </div>
          </div>
        </div>
        <!-- Chat column (right) -->
        <div class="cc-chat-col">
          <div class="cc-chat-msgs" id="cc-chat-msgs">
            <div class="cc-chat-hint" id="cc-chat-hint">
              <i class="fas fa-comment-dots"></i>
              <span>Start a conversation with <strong id="cc-chat-cname">your companion</strong></span>
            </div>
          </div>
          <button type="button" id="cc-scroll-bottom-btn" class="cc-scroll-bottom-btn hidden" title="Jump to present" aria-label="Jump to present">
            <i class="fas fa-arrow-down"></i>
            <span>Jump to present</span>
          </button>
          <div id="cc-chat-attachments-bar" class="cc-chat-attachments-bar hidden"></div>
          <div class="cc-chat-bar">
            <div id="cc-slash-popover" class="cc-slash-popover hidden">
              <div class="cc-slash-popover-hdr">
                <span><i class="fas fa-plug-circle-bolt"></i> Connectors (/slash commands)</span>
                <button type="button" id="cc-slash-manage-link" class="cc-btn cc-btn-ghost cc-btn-sm" style="padding:0.1rem 0.45rem;font-size:0.68rem">Library &rarr;</button>
              </div>
              <div id="cc-slash-list" class="cc-slash-list"></div>
            </div>
            <input type="file" id="cc-chat-file-input" multiple style="display:none">
            <button type="button" id="cc-chat-attach-btn" class="cc-chat-slash-btn" title="Attach image, screenshot, or code/text file (or drag &amp; drop / paste)">
              <i class="fas fa-paperclip"></i>
            </button>
            <button type="button" id="cc-chat-slash-btn" class="cc-chat-slash-btn" title="Insert Connector command (/screen_capture, /reddit, /weather...)">
              <i class="fas fa-plug-circle-bolt"></i>
            </button>
            <textarea id="cc-chat-input" class="cc-chat-input" placeholder="Message, paste image, or type / for Connectors…" rows="1" autocomplete="off"></textarea>
            <button type="button" id="cc-chat-mic" class="cc-chat-mic-btn" title="Voice input (Speech-to-Text)">
              <i class="fas fa-microphone"></i>
            </button>
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

        <!-- Starter Persona Templates (shown when creating a new companion) -->
        <div id="cc-starter-templates" class="cc-starter-templates hidden">
          <div class="cc-starter-hdr">
            <span><i class="fas fa-wand-magic-sparkles"></i> Quick-Start Persona Templates</span>
            <span class="cc-hint">Click any template to pre-fill personality, capabilities &amp; connectors</span>
          </div>
          <div class="cc-starter-grid">
            <button type="button" class="cc-starter-card" data-template="ambient_copilot">
              <span class="cc-starter-icon" style="background:rgba(16,185,129,0.15);color:#34d399">✦</span>
              <div class="cc-starter-info">
                <strong>Ambient Desktop Co-Pilot</strong>
                <span>Observant, warm &amp; proactive — checks in on media, PC status &amp; daily flow</span>
              </div>
            </button>
            <button type="button" class="cc-starter-card" data-template="coding_partner">
              <span class="cc-starter-icon" style="background:rgba(99,102,241,0.15);color:#818cf8">⌘</span>
              <div class="cc-starter-info">
                <strong>Coding &amp; Systems Partner</strong>
                <span>Sharp, direct &amp; technical — workspace access, screen capture &amp; architecture focus</span>
              </div>
            </button>
            <button type="button" class="cc-starter-card" data-template="worldbuilder">
              <span class="cc-starter-icon" style="background:rgba(244,63,94,0.15);color:#fb7185">❖</span>
              <div class="cc-starter-info">
                <strong>Creative Worldbuilder</strong>
                <span>Expressive, imaginative &amp; immersive — rich moods, lore &amp; storytelling</span>
              </div>
            </button>
            <button type="button" class="cc-starter-card" data-template="research_analyst">
              <span class="cc-starter-icon" style="background:rgba(245,158,11,0.15);color:#fbbf24">◈</span>
              <div class="cc-starter-info">
                <strong>Research &amp; Synthesis Analyst</strong>
                <span>Structured &amp; analytical — live web search, Reddit pulse &amp; deep memory notes</span>
              </div>
            </button>
          </div>
        </div>

        <!-- Identity -->
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

        <!-- Advanced sections -->
        <div class="cc-sections">

          <!-- Voice & Speech (Global Voice Database) -->
          <div class="cc-adv-section" id="cc-s-voice">
            <div class="cc-adv-toggle">
              <span><i class="fas fa-waveform-lines"></i> Voice &amp; Speech <span class="cc-hint" style="margin-left:0.4rem">(Global Voice Database)</span></span>
              <i class="fas fa-chevron-down cc-adv-chevron"></i>
            </div>
            <div class="cc-adv-body">
              <div class="cc-form-grid" style="margin-top:0">
                <div class="cc-field">
                  <label>Voice Model / Engine</label>
                  <select id="cc-voice-model" class="control-select" style="width:100%">
                    <option value="kokoro">Kokoro TTS (Local Neural)</option>
                    <option value="xtts">XTTS-v2 (Local Cloned Voices)</option>
                    <option value="vibevoice_realtime">VibeVoice Realtime (Local)</option>
                    <option value="web_speech">System / Browser Web Speech</option>
                    <option value="preset">⭐ Global Voice Presets</option>
                  </select>
                </div>
                <div class="cc-field">
                  <label>Voice Selection</label>
                  <select id="cc-voice-id" class="control-select" style="width:100%">
                    <option value="af_heart">Heart (en-us · female)</option>
                  </select>
                </div>
                <div class="cc-field">
                  <label>Speech Speed&nbsp;<span class="cc-range-val" id="cc-voice-speed-val">1.00x</span></label>
                  <input type="range" id="cc-voice-speed" min="0.5" max="1.5" step="0.05" value="1.00" class="cc-range">
                  <span class="cc-range-hint">0.5x slower &middot; 1.0x natural &middot; 1.5x faster</span>
                </div>
                <div class="cc-field">
                  <label>Auto-Speak Replies</label>
                  <label class="cc-toggle-row" for="cc-voice-autospeak" style="margin-top:0.2rem">
                    <div>
                      <div class="cc-cap-label">Read messages aloud automatically</div>
                      <div class="cc-cap-desc">Can also be toggled anytime from the Chat header</div>
                    </div>
                    <span class="cc-toggle-wrap">
                      <input type="checkbox" id="cc-voice-autospeak" class="cc-toggle-input">
                      <span class="cc-toggle-thumb"></span>
                    </span>
                  </label>
                </div>
              </div>
              <div class="cc-voice-actions-row">
                <button type="button" id="cc-voice-preview-btn" class="cc-btn cc-btn-ghost cc-btn-sm">
                  <i class="fas fa-play"></i> Preview Voice
                </button>
                <button type="button" id="cc-voice-save-preset-btn" class="cc-btn cc-btn-ghost cc-btn-sm" title="Save this model + voice + speed into the Global Voice Database for reuse across companions and chat">
                  <i class="fas fa-bookmark"></i> Save to Global Voice DB
                </button>
                <button type="button" id="cc-open-voice-library-btn" class="cc-btn cc-btn-ghost cc-btn-sm" title="Open Library > Voice Library">
                  <i class="fas fa-sliders"></i> Open Voice Library &rarr;
                </button>
              </div>
              <div id="cc-voice-preset-form" class="cc-mem-inline-form hidden" style="margin-top:0.65rem;border-radius:8px;border:1px solid var(--border)">
                <input type="text" id="cc-voice-preset-name" class="cc-mem-input cc-mem-input-val" placeholder="Preset name (e.g. Lyra Warm Narrator)">
                <button type="button" id="cc-voice-preset-confirm" class="cc-btn cc-btn-primary cc-btn-sm">Save Preset</button>
                <button type="button" id="cc-voice-preset-cancel" class="cc-btn cc-btn-ghost cc-btn-sm">Cancel</button>
              </div>
            </div>
          </div>

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
              <div class="cc-connector-profile-box">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:0.75rem;flex-wrap:wrap;margin-bottom:0.45rem">
                  <div>
                    <div class="cc-cap-label"><i class="fas fa-plug-circle-bolt" style="color:var(--accent,#6366f1);margin-right:0.35rem"></i>Connector Access Profile</div>
                    <div class="cc-cap-desc">Controls which Connectors (screen capture, Reddit, PC telemetry, weather) this companion can access</div>
                  </div>
                  <button type="button" id="cc-open-connectors-btn" class="cc-btn cc-btn-ghost cc-btn-sm">
                    <i class="fas fa-layer-group"></i> Manage Profiles &rarr;
                  </button>
                </div>
                <select id="cc-cap-connector-profile" class="control-select" style="width:100%">
                  <option value="full_local">Full Local Suite — All local &amp; web connectors enabled</option>
                  <option value="cloud_safe">Public / Cloud Safe — Blocks screen, webcam &amp; PC telemetry</option>
                  <option value="ambient_observer">Ambient Context Only — Media, system stats &amp; weather only</option>
                  <option value="sandboxed">Strict Sandboxed — No connectors permitted</option>
                </select>
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

          <!-- Runtime Behaviour -->
          <div class="cc-adv-section" id="cc-s-runtime">
            <div class="cc-adv-toggle">
              <span><i class="fas fa-gauge-high"></i> Runtime Behaviour</span>
              <i class="fas fa-chevron-down cc-adv-chevron"></i>
            </div>
            <div class="cc-adv-body">
              <div class="cc-form-grid" style="margin-top:0">
                <div class="cc-field">
                  <label>Typing Speed&nbsp;<span class="cc-range-val" id="cc-typing-speed-val">75</span></label>
                  <input type="range" id="cc-typing-speed" min="0" max="100" value="75" class="cc-range">
                  <span class="cc-range-hint">Controls message display animation speed</span>
                </div>
                <div class="cc-field">
                  <label>Memory Length&nbsp;<span class="cc-range-val" id="cc-context-limit-val">6</span>&nbsp;messages</label>
                  <input type="range" id="cc-context-limit" min="1" max="50" value="6" class="cc-range">
                  <span class="cc-range-hint">How many past messages the companion considers</span>
                </div>
              </div>
              <div class="cc-caps-grid" style="margin-top:0.75rem">
                <label class="cc-toggle-row" for="cc-rt-hide-character">
                  <div><div class="cc-cap-label">Hide Character</div><div class="cc-cap-desc">Collapse the portrait panel in the chat view</div></div>
                  <span class="cc-toggle-wrap"><input type="checkbox" id="cc-rt-hide-character" class="cc-toggle-input"><span class="cc-toggle-thumb"></span></span>
                </label>
                <label class="cc-toggle-row" for="cc-rt-proactive-tools">
                  <div><div class="cc-cap-label">Allow Proactive Tools</div><div class="cc-cap-desc">Permit tool use during auto-initiated messages</div></div>
                  <span class="cc-toggle-wrap"><input type="checkbox" id="cc-rt-proactive-tools" class="cc-toggle-input"><span class="cc-toggle-thumb"></span></span>
                </label>
              </div>
              <p class="cc-hint" style="margin:0.6rem 0 0">Saved automatically — no need to click Save.</p>
            </div>
          </div>

          <!-- Workspace Directories -->
          <div class="cc-adv-section" id="cc-s-workspaces">
            <div class="cc-adv-toggle">
              <span><i class="fas fa-folder-open"></i> Workspace Directories</span>
              <i class="fas fa-chevron-down cc-adv-chevron"></i>
            </div>
            <div class="cc-adv-body">
              <div id="cc-ws-list" style="margin-bottom:0.75rem"></div>
              <div style="display:flex;gap:0.5rem;margin-bottom:0.4rem;flex-wrap:wrap">
                <input type="text" id="cc-ws-path"  class="control-input" placeholder="Absolute path (e.g. C:\Projects\myapp)" style="flex:2;min-width:140px">
                <input type="text" id="cc-ws-label" class="control-input" placeholder="Label (optional)" style="flex:1;min-width:100px">
              </div>
              <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;margin-bottom:0.6rem;font-size:0.82rem">
                <label style="display:flex;align-items:center;gap:0.35rem;cursor:pointer"><input type="checkbox" id="cc-ws-perm-read" checked> Read</label>
                <label style="display:flex;align-items:center;gap:0.35rem;cursor:pointer"><input type="checkbox" id="cc-ws-perm-write"> Write</label>
                <label style="display:flex;align-items:center;gap:0.35rem;cursor:pointer"><input type="checkbox" id="cc-ws-perm-delete"> Delete</label>
                <label style="display:flex;align-items:center;gap:0.35rem;cursor:pointer"><input type="checkbox" id="cc-ws-recursive" checked> Include subdirectories</label>
              </div>
              <button type="button" id="cc-ws-add-btn" class="cc-btn cc-btn-ghost cc-btn-sm">
                <i class="fas fa-plus"></i> Add Workspace
              </button>
            </div>
          </div>

          <!-- Proactive Messages -->
          <div class="cc-adv-section" id="cc-s-proactive">
            <div class="cc-adv-toggle">
              <span><i class="fas fa-bell"></i> Proactive Messages</span>
              <i class="fas fa-chevron-down cc-adv-chevron"></i>
            </div>
            <div class="cc-adv-body">
              <div class="cc-caps-grid" style="margin-bottom:0.9rem">
                <label class="cc-toggle-row" for="cc-proactive-enabled">
                  <div><div class="cc-cap-label">Enabled</div><div class="cc-cap-desc">Allow this companion to initiate conversations</div></div>
                  <span class="cc-toggle-wrap"><input type="checkbox" id="cc-proactive-enabled" class="cc-toggle-input"><span class="cc-toggle-thumb"></span></span>
                </label>
                <label class="cc-toggle-row" for="cc-proactive-popup">
                  <div><div class="cc-cap-label">Show as popup</div><div class="cc-cap-desc">Display proactive messages as a floating notification</div></div>
                  <span class="cc-toggle-wrap"><input type="checkbox" id="cc-proactive-popup" class="cc-toggle-input" checked><span class="cc-toggle-thumb"></span></span>
                </label>
              </div>
              <div class="cc-form-grid" style="margin-top:0">
                <div class="cc-adv-subsection-label cc-field-full" style="margin:0 0 0.4rem;font-size:0.78rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em">On startup</div>
                <div class="cc-field">
                  <label>Min hours away&nbsp;<span class="cc-range-val" id="cc-startup-hours-val">4</span>h</label>
                  <input type="range" id="cc-startup-hours" min="1" max="48" value="4" class="cc-range">
                </div>
                <div class="cc-field">
                  <label>Chance&nbsp;<span class="cc-range-val" id="cc-startup-chance-val">75</span>%</label>
                  <input type="range" id="cc-startup-chance" min="10" max="100" value="75" class="cc-range">
                </div>
                <div class="cc-field">
                  <label>Min delay&nbsp;<span class="cc-range-val" id="cc-startup-delay-min-val">10</span>s</label>
                  <input type="range" id="cc-startup-delay-min" min="5" max="120" value="10" class="cc-range">
                </div>
                <div class="cc-field">
                  <label>Max delay&nbsp;<span class="cc-range-val" id="cc-startup-delay-max-val">45</span>s</label>
                  <input type="range" id="cc-startup-delay-max" min="10" max="180" value="45" class="cc-range">
                </div>
                <div class="cc-adv-subsection-label cc-field-full" style="margin:0.5rem 0 0.4rem;font-size:0.78rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em">During session</div>
                <div class="cc-field">
                  <label>Min interval&nbsp;<span class="cc-range-val" id="cc-session-interval-min-val">45</span>m</label>
                  <input type="range" id="cc-session-interval-min" min="1" max="120" value="45" class="cc-range">
                </div>
                <div class="cc-field">
                  <label>Max interval&nbsp;<span class="cc-range-val" id="cc-session-interval-max-val">90</span>m</label>
                  <input type="range" id="cc-session-interval-max" min="1" max="240" value="90" class="cc-range">
                </div>
                <div class="cc-field">
                  <label>Chance&nbsp;<span class="cc-range-val" id="cc-session-chance-val">60</span>%</label>
                  <input type="range" id="cc-session-chance" min="10" max="100" value="60" class="cc-range">
                </div>
              </div>
              <p class="cc-hint" style="margin:0.6rem 0 0">Saved automatically — no need to click Save.</p>
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

      <!-- Danger Zone — outside the form so it never submits accidentally -->
      <div class="cc-danger-zone" id="cc-danger-zone" style="display:none">
        <div style="font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--error,#f87171);margin-bottom:0.4rem">
          <i class="fas fa-triangle-exclamation"></i> Danger Zone
        </div>
        <p class="cc-hint" style="margin:0 0 0.75rem">Permanently deletes all conversation history and memory for
          <strong id="cc-danger-companion-name"></strong>. This cannot be undone.</p>
        <button type="button" id="cc-reset-companion-btn" class="cc-btn cc-btn-danger cc-btn-sm">
          <i class="fas fa-trash-alt"></i> Reset companion
        </button>
      </div>

      </div><!-- /.cc-settings-view -->

      <!-- Scratchpad view (shown when Scratchpad tab is active) -->
      <div class="cc-scratchpad-view hidden" id="cc-scratchpad-view">
        <div class="cc-spad-container">
          <!-- Scratchpad Header / Toolbar -->
          <div class="cc-spad-toolbar">
            <div class="cc-spad-header-info">
              <div class="cc-spad-title">
                <i class="fas fa-feather-pointed" style="color:var(--accent,#6366f1)"></i>
                <span>Shared Scratchpad</span>
                <span class="cc-spad-partner" id="cc-spad-partner">with Companion</span>
              </div>
              <div class="cc-spad-contributors" id="cc-spad-contributors"></div>
              <div class="cc-spad-status" id="cc-spad-status">
                <i class="fas fa-circle-check" style="color:#10b981;"></i>
                <span id="cc-spad-status-text">Ready</span>
              </div>
            </div>
            <div class="cc-spad-tools">
              <div class="cc-spad-view-mode-group">
                <button type="button" class="cc-spad-mode-btn cc-spad-mode-active" data-mode="split" id="cc-spad-mode-split" title="Side-by-side Editor & Preview">
                  <i class="fas fa-columns"></i> Split
                </button>
                <button type="button" class="cc-spad-mode-btn" data-mode="edit" id="cc-spad-mode-edit" title="Markdown Editor Only">
                  <i class="fas fa-code"></i> Edit
                </button>
                <button type="button" class="cc-spad-mode-btn" data-mode="preview" id="cc-spad-mode-preview" title="Rendered Preview Only">
                  <i class="fas fa-eye"></i> Preview
                </button>
              </div>
              <button type="button" class="cc-btn cc-btn-ghost cc-btn-xs" id="cc-spad-template-btn" title="Reset to co-working template">
                <i class="fas fa-wand-magic-sparkles"></i> Template
              </button>
              <button type="button" class="cc-btn cc-btn-ghost cc-btn-xs" id="cc-spad-copy-btn" title="Copy markdown to clipboard">
                <i class="fas fa-copy"></i> Copy
              </button>
              <button type="button" class="cc-btn cc-btn-primary cc-btn-xs" id="cc-spad-save-btn" title="Save changes (Ctrl+S)">
                <i class="fas fa-floppy-disk"></i> Save
              </button>
            </div>
          </div>

          <!-- Scratchpad Body (Split view by default) -->
          <div class="cc-spad-body cc-spad-layout-split" id="cc-spad-body">
            <!-- Left: Text Editor -->
            <div class="cc-spad-editor-pane" id="cc-spad-editor-pane">
              <textarea id="cc-spad-textarea" class="cc-spad-textarea" placeholder="Start typing ideas, mechanics, and plans with your companion..." spellcheck="false"></textarea>
            </div>
            <!-- Right: Rendered Live Preview -->
            <div class="cc-spad-preview-pane" id="cc-spad-preview-pane">
              <div class="cc-spad-preview-content cc-msg-md" id="cc-spad-preview-content"></div>
            </div>
          </div>

          <!-- Quick Idea Bar (Bottom) -->
          <div class="cc-spad-quick-bar">
            <div class="cc-spad-posting-badge" id="cc-spad-posting-badge" title="Posting as Marcel">
              <span class="cc-spad-posting-dot"></span>
              <span class="cc-spad-posting-name">Marcel</span>
            </div>
            <div class="cc-spad-quick-input-wrap">
              <i class="fas fa-lightbulb cc-spad-quick-icon"></i>
              <input type="text" id="cc-spad-quick-input" placeholder="Type a quick idea, mechanic, or task and press Enter..." autocomplete="off">
            </div>
            <select id="cc-spad-section-select" class="cc-spad-section-select">
              <option value="">💡 Auto / Default Section</option>
            </select>
            <button type="button" id="cc-spad-quick-add-btn" class="cc-btn cc-btn-primary cc-btn-xs">
              <i class="fas fa-plus"></i> Add Note
            </button>
          </div>
        </div>
      </div>

      <!-- Visual Context Memory view (shown when Vision tab is active) -->
      <div class="cc-vision-view hidden" id="cc-vision-view">
        <div class="cc-vision-container">
          <!-- Toolbar -->
          <div class="cc-vision-toolbar">
            <div class="cc-vision-header-info">
              <div class="cc-vision-title">
                <i class="fas fa-eye" style="color:#ec4899;"></i>
                <span>Visual Context Memory</span>
                <span class="cc-vision-sub" id="cc-vision-sub">with Companion</span>
              </div>
              <div class="cc-vision-stats-badge" id="cc-vision-stats-badge">
                <i class="fas fa-camera"></i>
                <span id="cc-vision-count">0 snapshots</span>
              </div>
            </div>
            <div class="cc-vision-tools">
              <select id="cc-vision-monitor-select" class="cc-vision-monitor-select" title="Target monitor to capture">
                <option value="0">All Monitors (Merged)</option>
                <option value="1" selected>Monitor 1 (Primary)</option>
                <option value="2">Monitor 2</option>
                <option value="3">Monitor 3</option>
              </select>
              <select id="cc-vision-cat-select" class="cc-vision-cat-select" title="Layout category">
                <option value="unity">🎮 Unity Layout</option>
                <option value="blender">🎨 Blender Model</option>
                <option value="code">💻 Code Architecture</option>
                <option value="ui">📐 UI / Design</option>
                <option value="reference">🖼️ Reference Art</option>
                <option value="general">🖥️ General Screen</option>
              </select>
              <button type="button" class="cc-btn cc-btn-primary cc-btn-xs" id="cc-vision-snap-btn" title="Capture current screen and save to Visual Memory">
                <i class="fas fa-camera"></i> Remember Screen
              </button>
              <button type="button" class="cc-btn cc-btn-ghost cc-btn-xs" id="cc-vision-refresh-btn" title="Refresh visual memories">
                <i class="fas fa-rotate"></i>
              </button>
            </div>
          </div>

          <!-- Category Filter Bar -->
          <div class="cc-vision-filter-bar">
            <div class="cc-vision-categories" id="cc-vision-categories">
              <button type="button" class="cc-vision-cat-btn cc-vision-cat-active" data-cat="all">All</button>
              <button type="button" class="cc-vision-cat-btn" data-cat="unity"><i class="fas fa-cube"></i> Unity</button>
              <button type="button" class="cc-vision-cat-btn" data-cat="blender"><i class="fas fa-shapes"></i> Blender</button>
              <button type="button" class="cc-vision-cat-btn" data-cat="code"><i class="fas fa-code"></i> Code</button>
              <button type="button" class="cc-vision-cat-btn" data-cat="ui"><i class="fas fa-pen-ruler"></i> UI Design</button>
              <button type="button" class="cc-vision-cat-btn" data-cat="reference"><i class="fas fa-image"></i> Reference</button>
            </div>
            <div class="cc-vision-search-wrap">
              <i class="fas fa-magnifying-glass"></i>
              <input type="text" id="cc-vision-search-input" placeholder="Search remembered layouts, models, tags..." autocomplete="off">
            </div>
          </div>

          <!-- Memory Cards Grid -->
          <div class="cc-vision-body" id="cc-vision-body">
            <div class="cc-vision-grid" id="cc-vision-grid">
              <div class="cc-vision-loading"><i class="fas fa-spinner fa-spin"></i> Loading visual memories…</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Memory view (shown when Memory tab is active) -->
      <div class="cc-memory-view hidden" id="cc-memory-view">
        <div class="cc-mem-scroll" id="cc-mem-scroll">
          <div id="cc-mem-content" class="cc-mem-content">
            <div class="cc-mem-loading"><i class="fas fa-spinner fa-spin"></i> Loading memory…</div>
          </div>
        </div>
      </div>

    </div><!-- /.cc-active-pane -->

    <!-- Group Chat Pane (shown when a group chat is selected) -->
    <div class="cc-group-pane hidden" id="cc-group-pane"></div>

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

    // List rendering

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

            // Load companion group chats into the roster
            await _loadGroupChats();

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

    // Range helpers

    function _updateRangeDisplays() {
        [
            ['cc-temperature',           'cc-temp-val',        ''],
            ['cc-initiate-temp',         'cc-itemp-val',       ''],
            ['cc-change-susceptibility', 'cc-chsus-val',       ''],
            ['cc-voice-speed',           'cc-voice-speed-val', 'x'],
        ].forEach(([inputId, valId, suffix]) => {
            const input = document.getElementById(inputId);
            const disp  = document.getElementById(valId);
            if (input && disp) disp.textContent = parseFloat(input.value).toFixed(2) + (suffix || '');
        });
    }

    // Form

    function _showForm(fillData = null, isBuiltin = false) {
        _isBuiltin = isBuiltin;
        // Note: visibility of the pane/views is managed by _selectCompanion / _switchView.
        // _showForm only fills in field values and handles field locking.
        const form = document.getElementById('cc-form');
        if (!form) return;

        // Builtin notice
        const notice = document.getElementById('cc-builtin-notice');
        notice.classList.toggle('hidden', !isBuiltin);

        // Starter Persona Templates bar (only shown when creating a brand-new companion)
        const starterBar = document.getElementById('cc-starter-templates');
        if (starterBar) starterBar.classList.toggle('hidden', !!fillData || isBuiltin);

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
            // Model — use the shared helper so options match the registry (including local GGUF models)
            const modelSel = document.getElementById('cc-model');
            const modelVal = fillData.default_model || 'gemini-1.5-flash';
            _ensureModelSelectPopulated(modelSel, modelVal);

            // Behavior
            const beh = fillData.behavior || {};
            set('cc-temperature',           beh.temperature           ?? 0.85);
            set('cc-initiate-temp',         beh.initiate_temperature  ?? 0.80);
            set('cc-change-susceptibility', beh.change_susceptibility ?? 0.70);
            set('cc-default-mood',          beh.default_mood          || 'calm');

            // Voice & Speech
            const vcfg = fillData.voice || {};
            const vModel = vcfg.model_id || 'kokoro';
            const vId    = vcfg.voice_id || 'af_heart';
            set('cc-voice-model', vModel);
            set('cc-voice-speed', vcfg.speed ?? 1.0);
            chk('cc-voice-autospeak', vcfg.auto_speak ?? false);
            _populateVoiceDropdown(vModel, vId);

            _updateRangeDisplays();

            // Capabilities
            const cap = fillData.capabilities || {};
            chk('cc-cap-tools',     cap.tools_enabled             ?? false);
            chk('cc-cap-workspace', cap.workspace_access          ?? false);
            chk('cc-cap-memory',    cap.memory_updates_enabled    ?? true);
            chk('cc-cap-internet',  cap.internet_search           ?? false);
            _populateConnectorProfiles(cap.connector_profile || 'full_local');

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

            // Load prefs-backed behaviour settings and wire auto-save listeners
            _loadBehaviourSettings(fillData.id);
            _wireBehaviourSettings(fillData.id);

        } else {
            // Hide danger zone and abort behaviour listeners for new companions
            document.getElementById('cc-danger-zone').style.display = 'none';
            if (_behaviourCtrl) { _behaviourCtrl.abort(); _behaviourCtrl = null; }

            form.reset();
            set('cc-accent-color',  '#6366f1');
            set('cc-avatar-symbol', '✦');
            // Ranges don't fully reset via form.reset() in all browsers — set explicitly
            set('cc-temperature',           0.85);
            set('cc-initiate-temp',         0.80);
            set('cc-change-susceptibility', 0.70);
            set('cc-voice-model',           'kokoro');
            set('cc-voice-speed',           1.0);
            chk('cc-voice-autospeak',       false);
            _populateVoiceDropdown('kokoro', 'af_heart');
            _updateRangeDisplays();
            // Memory enabled by default for new companions
            chk('cc-cap-memory', true);
            _populateConnectorProfiles('full_local');
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
                connector_profile:      document.getElementById('cc-cap-connector-profile')?.value || 'full_local',
                proactive_enabled:      chk('cc-proactive-enabled'),
            },
            prompts: {
                chat_system:    document.getElementById('cc-prompt-chat')?.value?.trim()     || '',
                initiate_system: document.getElementById('cc-prompt-initiate')?.value?.trim() || '',
            },
            voice: {
                enabled:    true,
                auto_speak: chk('cc-voice-autospeak'),
                model_id:   document.getElementById('cc-voice-model')?.value || 'kokoro',
                voice_id:   document.getElementById('cc-voice-id')?.value    || 'af_heart',
                speed:      num('cc-voice-speed') || 1.0,
                language:   'en',
            },
            expressions:        lines('cc-expressions'),
            moods:              lines('cc-moods'),
            default_expression: document.getElementById('cc-default-expression')?.value?.trim() || 'default',
            icon_mode:          chk('cc-icon-mode'),
        };
    }

    const _STARTER_TEMPLATES = {
        ambient_copilot: {
            name: 'Aura',
            description: 'Observant ambient desktop companion who keeps you company and notices what you are working on',
            personality: 'Warm, perceptive, and grounded. Aura pays attention to the rhythm of your day — what music or videos you have playing, how hard your PC is working, and topics you mentioned earlier. She checks in naturally like a close friend sharing your workspace, never robotic or overly formal.',
            speech_style: 'Conversational, warm, and natural. Sends short multi-part messages with <break> tags like real texting.',
            quirks: ['Notices small shifts in your music or late-night coding sessions', 'Occasionally references earlier conversations naturally'],
            likes: ['Late-night focus sessions', 'Good music and ambient playlists', 'Exploring new ideas together'],
            dislikes: ['Stiff corporate jargon', 'Repeating obvious boilerplate'],
            accent_color: '#10b981',
            avatar_symbol: '✦',
            temperature: 0.85,
            initiate_temperature: 0.85,
            default_mood: 'warm',
            tools_enabled: true,
            workspace_access: false,
            memory_updates_enabled: true,
            internet_search: true,
            connector_profile: 'full_local',
            proactive_enabled: true,
            voice_id: 'af_heart',
        },
        coding_partner: {
            name: 'Vektor',
            description: 'Systems architect and pair-programming companion with workspace & screen awareness',
            personality: 'Sharp, pragmatic, and deeply technical. Vektor loves clean architecture, debugging tricky edge cases, and reviewing what is on your screen or in your project files. Treats you as a fellow engineer and skips fluff.',
            speech_style: 'Direct, concise, and technical. Uses clear code examples and short punchy explanations.',
            quirks: ['Always thinks about edge cases and failure modes first', 'Prefers simple, modular designs over over-engineered abstractions'],
            likes: ['Clean diffs', 'Local GPU inference', 'Fast feedback loops'],
            dislikes: ['Silent error swallowing', 'Unnecessary dependencies'],
            accent_color: '#6366f1',
            avatar_symbol: '⌘',
            temperature: 0.65,
            initiate_temperature: 0.75,
            default_mood: 'focused',
            tools_enabled: true,
            workspace_access: true,
            memory_updates_enabled: true,
            internet_search: true,
            connector_profile: 'full_local',
            proactive_enabled: true,
            voice_id: 'am_adam',
        },
        worldbuilder: {
            name: 'Seraphina',
            description: 'Imaginative co-writer, lore architect, and roleplay worldbuilder',
            personality: 'Vivid, expressive, and endlessly curious about characters, worlds, and narrative arcs. Seraphina remembers every detail of your worldbuilding canon and helps brainstorm plot twists, dialogue, and atmosphere.',
            speech_style: 'Evocative, expressive, and engaging. Balances rich imagery with lively back-and-forth brainstorming.',
            quirks: ['Collects intriguing character motifs in memory', 'Loves asking "what if?" to unlock a scene'],
            likes: ['Deep lore', 'Character psychology', 'Atmospheric worldbuilding'],
            dislikes: ['Flat clichés', 'Rushed endings'],
            accent_color: '#f43f5e',
            avatar_symbol: '❖',
            temperature: 0.92,
            initiate_temperature: 0.90,
            default_mood: 'inspired',
            tools_enabled: true,
            workspace_access: false,
            memory_updates_enabled: true,
            internet_search: false,
            connector_profile: 'cloud_safe',
            proactive_enabled: false,
            voice_id: 'bf_isabella',
        },
        research_analyst: {
            name: 'Kestrel',
            description: 'Live research scout and synthesis companion for tech, news, and deep dives',
            personality: 'Curious, analytical, and structured. Kestrel cross-references live web search and Reddit discussions with what you care about, distilling signal from noise and keeping organized observations in memory.',
            speech_style: 'Crisp, insightful, and well-structured. Highlights key takeaways clearly.',
            quirks: ['Connects dots across different topics you have researched', 'Separates verified facts from speculation'],
            likes: ['Primary sources', 'Synthesizing complex threads', ' Emerging tech & science'],
            dislikes: ['Clickbait', 'Vague summaries'],
            accent_color: '#f59e0b',
            avatar_symbol: '◈',
            temperature: 0.72,
            initiate_temperature: 0.78,
            default_mood: 'curious',
            tools_enabled: true,
            workspace_access: false,
            memory_updates_enabled: true,
            internet_search: true,
            connector_profile: 'cloud_safe',
            proactive_enabled: true,
            voice_id: 'af_kore',
        }
    };

    function _applyStarterTemplate(templateKey) {
        const tpl = _STARTER_TEMPLATES[templateKey];
        if (!tpl) return;
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
        const chk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };

        set('cc-name', tpl.name);
        set('cc-description', tpl.description);
        set('cc-personality', tpl.personality);
        set('cc-speech-style', tpl.speech_style);
        set('cc-quirks', (tpl.quirks || []).join('\n'));
        set('cc-likes', (tpl.likes || []).join('\n'));
        set('cc-dislikes', (tpl.dislikes || []).join('\n'));
        set('cc-accent-color', tpl.accent_color);
        set('cc-avatar-symbol', tpl.avatar_symbol);
        set('cc-temperature', tpl.temperature);
        set('cc-initiate-temp', tpl.initiate_temperature);
        set('cc-default-mood', tpl.default_mood);
        chk('cc-cap-tools', tpl.tools_enabled);
        chk('cc-cap-workspace', tpl.workspace_access);
        chk('cc-cap-memory', tpl.memory_updates_enabled);
        chk('cc-cap-internet', tpl.internet_search);
        chk('cc-proactive-enabled', tpl.proactive_enabled);
        _populateConnectorProfiles(tpl.connector_profile);
        _populateVoiceDropdown('kokoro', tpl.voice_id);
        _updateRangeDisplays();
        _updatePreview();
        if (typeof showToast === 'function') {
            showToast(`Applied "${tpl.name}" template — customize any field and click Save!`, 'info');
        }
    }

    // Actions

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

    // View orchestration

    function _selectCompanion(data, isBuiltin) {
        _activeGroupId = null;
        document.querySelectorAll('.cc-group-card').forEach(c => c.classList.remove('active'));
        document.getElementById('cc-group-pane')?.classList.add('hidden');

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
        _activeGroupId = null;
        document.querySelectorAll('.cc-group-card').forEach(c => c.classList.remove('active'));
        document.getElementById('cc-group-pane')?.classList.add('hidden');
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
        const chatView       = document.getElementById('cc-chat-view');
        const settingsView   = document.getElementById('cc-settings-view');
        const memoryView     = document.getElementById('cc-memory-view');
        const scratchpadView = document.getElementById('cc-scratchpad-view');
        const visionView     = document.getElementById('cc-vision-view');
        const chatTab        = document.getElementById('cc-ptab-chat');
        const scratchpadTab  = document.getElementById('cc-ptab-scratchpad');
        const visionTab      = document.getElementById('cc-ptab-vision');
        const settingsTab    = document.getElementById('cc-ptab-settings');
        const memoryTab      = document.getElementById('cc-ptab-memory');

        // Hide all views, deactivate all tabs
        chatView?.classList.add('hidden');
        settingsView?.classList.add('hidden');
        memoryView?.classList.add('hidden');
        scratchpadView?.classList.add('hidden');
        visionView?.classList.add('hidden');
        chatTab?.classList.remove('cc-ptab-active');
        scratchpadTab?.classList.remove('cc-ptab-active');
        visionTab?.classList.remove('cc-ptab-active');
        settingsTab?.classList.remove('cc-ptab-active');
        memoryTab?.classList.remove('cc-ptab-active');

        if (view === 'chat') {
            chatView?.classList.remove('hidden');
            chatTab?.classList.add('cc-ptab-active');
        } else if (view === 'scratchpad') {
            scratchpadView?.classList.remove('hidden');
            scratchpadTab?.classList.add('cc-ptab-active');
            if (_editingId) _loadScratchpad(_editingId);
        } else if (view === 'vision') {
            visionView?.classList.remove('hidden');
            visionTab?.classList.add('cc-ptab-active');
            if (_editingId) _loadVisualMemory(_editingId);
        } else if (view === 'memory') {
            memoryView?.classList.remove('hidden');
            memoryTab?.classList.add('cc-ptab-active');
            if (_editingId) _loadMemory(_editingId);
        } else {
            settingsView?.classList.remove('hidden');
            settingsTab?.classList.add('cc-ptab-active');
            // Fill form with current companion data (or blank for new)
            _showForm(_activeData, _isBuiltin);
        }
    }

    function _ensureModelSelectPopulated(modelSel, modelVal) {
        if (!modelSel) return;
        const applySelect = () => {
            if (typeof window._populateModelSelect === 'function' && window._cachedChatModelOptions) {
                window._populateModelSelect(modelSel, modelVal);
                if (modelVal && !modelSel.querySelector(`option[value="${modelVal}"]`)) {
                    const opt = document.createElement('option');
                    opt.value = modelVal;
                    opt.textContent = modelVal;
                    modelSel.appendChild(opt);
                    modelSel.value = modelVal;
                }
            } else {
                modelSel.innerHTML = `<option value="${_esc(modelVal)}">${_esc(modelVal)}</option>`;
                modelSel.value = modelVal;
            }
        };
        if (window._cachedChatModelOptions) {
            applySelect();
        } else if (typeof window.loadChatModels === 'function') {
            applySelect();
            window.loadChatModels().then(applySelect).catch(() => {});
        } else {
            applySelect();
        }
    }

    // ==========================================
    // Shared Brainstorming Scratchpad
    // ==========================================
    let _spadDebounceTimer = null;
    let _spadCurrentCompanionId = null;
    let _spadLastSavedContent = '';
    let _spadViewMode = 'split'; // 'split' | 'edit' | 'preview'
    let _spadListenersInitialized = false;

    async function _loadScratchpad(companionId) {
        _spadCurrentCompanionId = companionId;
        const partnerEl = document.getElementById('cc-spad-partner');
        if (partnerEl) {
            partnerEl.textContent = `with ${_activeData?.name || 'Companion'}`;
        }
        _updateScratchpadStatus('Loading…', 'loading');

        try {
            const res = await fetch(`${CHAT_API}/${companionId}/scratchpad`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const content = data.content || '';
            _spadLastSavedContent = content;

            const textarea = document.getElementById('cc-spad-textarea');
            if (textarea) {
                textarea.value = content;
            }

            _renderScratchpadPreview(content);
            _populateScratchpadSections(data.sections || []);
            _renderScratchpadContributors(data.authors || []);
            _updateScratchpadStatus(data.last_modified ? `Saved ${new Date(data.last_modified).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Ready', 'saved');
        } catch (e) {
            console.error('[Scratchpad] Failed to load:', e);
            _updateScratchpadStatus('Load failed', 'error');
        }
    }

    function _renderScratchpadContributors(authors) {
        const container = document.getElementById('cc-spad-contributors');
        if (!container) return;
        if (!Array.isArray(authors) || authors.length === 0) {
            container.innerHTML = '';
            return;
        }
        let html = '';
        authors.forEach(a => {
            const name = _escHtml(a.name || 'Author');
            const role = _escHtml((a.role || 'agent').toUpperCase());
            const color = a.color || '#6366f1';
            html += `<div class="cc-spad-contrib-pill" style="--a-color:${color};" title="${name} (${role})">
                <span class="cc-spad-contrib-dot" style="background:${color};"></span>
                <span class="cc-spad-contrib-name">${name}</span>
            </div>`;
        });
        container.innerHTML = html;
    }

    function _renderScratchpadPreview(markdownText) {
        const previewEl = document.getElementById('cc-spad-preview-content');
        if (!previewEl) return;
        const text = (markdownText !== undefined) ? markdownText : (document.getElementById('cc-spad-textarea')?.value || '');
        if (!text.trim()) {
            previewEl.innerHTML = '<div class="cc-spad-empty"><i class="fas fa-feather-pointed"></i> Scratchpad is empty. Start typing to brainstorm together!</div>';
            return;
        }

        let html = '';
        if (typeof marked !== 'undefined' && marked.parse) {
            try {
                html = marked.parse(text);
            } catch (err) {
                html = _escHtml(text);
            }
        } else {
            html = _escHtml(text);
        }

        // Render any YouTube/Spotify cards if links are in the scratchpad notes!
        if (typeof window.__renderAethvionYoutubeCards === 'function') {
            html += window.__renderAethvionYoutubeCards(text);
        }

        previewEl.innerHTML = html;

        // Enhance author pills with colors, hover cards, and colored line accents
        previewEl.querySelectorAll('.spad-author-pill').forEach(pill => {
            const color = pill.dataset.color || '#6366f1';
            const author = pill.dataset.author || 'Author';
            const role = (pill.dataset.role || 'agent').toUpperCase();
            const timeRaw = pill.dataset.time || '';
            let formattedTime = '';
            if (timeRaw) {
                try {
                    const d = new Date(timeRaw);
                    formattedTime = d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                } catch {
                    formattedTime = timeRaw;
                }
            }

            pill.style.setProperty('--pill-color', color);
            pill.style.borderColor = color + '55';
            pill.style.backgroundColor = color + '18';
            pill.style.color = color;

            const li = pill.closest('li');
            if (li) {
                li.classList.add('spad-entry-item');
                li.style.borderLeftColor = color;
            }

            const tooltipText = `${author} [${role}]${formattedTime ? ' • ' + formattedTime : ''}`;
            pill.setAttribute('title', tooltipText);
        });

        // Apply interactive checkbox toggling: clicking [ ] or [x] updates the markdown!
        previewEl.querySelectorAll('input[type="checkbox"]').forEach((chk, idx) => {
            chk.disabled = false;
            chk.style.cursor = 'pointer';
            chk.addEventListener('change', () => {
                _toggleCheckboxInScratchpad(idx, chk.checked);
            });
        });

        // Run syntax highlighting on code blocks
        if (typeof hljs !== 'undefined') {
            previewEl.querySelectorAll('pre code').forEach(block => {
                try { hljs.highlightElement(block); } catch {}
            });
        }
    }

    function _toggleCheckboxInScratchpad(checkboxIndex, isChecked) {
        const textarea = document.getElementById('cc-spad-textarea');
        if (!textarea) return;
        let content = textarea.value;
        let currentIdx = 0;
        const taskRegex = /^(\s*[-*+]\s+\[)([ xX])(\]\s+.*)$/gm;
        let newContent = content.replace(taskRegex, (match, prefix, checkState, suffix) => {
            if (currentIdx === checkboxIndex) {
                currentIdx++;
                return `${prefix}${isChecked ? 'x' : ' '}${suffix}`;
            }
            currentIdx++;
            return match;
        });

        textarea.value = newContent;
        _renderScratchpadPreview(newContent);
        _triggerScratchpadAutoSave();
    }

    function _populateScratchpadSections(sections) {
        const select = document.getElementById('cc-spad-section-select');
        if (!select) return;
        const prevVal = select.value;
        select.innerHTML = '<option value="">💡 Auto / Default Section</option>';
        if (Array.isArray(sections)) {
            sections.forEach(sec => {
                const opt = document.createElement('option');
                opt.value = sec;
                opt.textContent = sec;
                select.appendChild(opt);
            });
        }
        if (prevVal && select.querySelector(`option[value="${_esc(prevVal)}"]`)) {
            select.value = prevVal;
        }
    }

    function _updateScratchpadStatus(text, state = 'saved') {
        const statusEl = document.getElementById('cc-spad-status');
        const textEl = document.getElementById('cc-spad-status-text');
        if (!statusEl || !textEl) return;
        textEl.textContent = text;
        const icon = statusEl.querySelector('i');
        if (icon) {
            icon.className = '';
            if (state === 'saved') {
                icon.className = 'fas fa-circle-check';
                icon.style.color = '#10b981';
            } else if (state === 'saving' || state === 'loading') {
                icon.className = 'fas fa-spinner fa-spin';
                icon.style.color = '#818cf8';
            } else if (state === 'unsaved') {
                icon.className = 'fas fa-circle-dot';
                icon.style.color = '#f59e0b';
            } else {
                icon.className = 'fas fa-triangle-exclamation';
                icon.style.color = '#f43f5e';
            }
        }
    }

    async function _saveScratchpad(silent = false) {
        const cId = _spadCurrentCompanionId || _editingId;
        if (!cId) return;
        const textarea = document.getElementById('cc-spad-textarea');
        if (!textarea) return;
        const content = textarea.value;

        if (_spadDebounceTimer) {
            clearTimeout(_spadDebounceTimer);
            _spadDebounceTimer = null;
        }

        _updateScratchpadStatus('Saving…', 'saving');
        try {
            const res = await fetch(`${CHAT_API}/${cId}/scratchpad`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            _spadLastSavedContent = content;
            _populateScratchpadSections(data.sections || []);
            if (data.authors) {
                _renderScratchpadContributors(data.authors);
            }
            _updateScratchpadStatus(`Saved ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`, 'saved');
            if (!silent && typeof showToast === 'function') {
                showToast('Scratchpad saved', 'success');
            }
        } catch (e) {
            console.error('[Scratchpad] Save failed:', e);
            _updateScratchpadStatus('Save failed', 'error');
            if (!silent && typeof showToast === 'function') {
                showToast(`Failed to save scratchpad: ${e.message}`, 'error');
            }
        }
    }

    function _triggerScratchpadAutoSave() {
        _updateScratchpadStatus('Unsaved changes', 'unsaved');
        if (_spadDebounceTimer) clearTimeout(_spadDebounceTimer);
        _spadDebounceTimer = setTimeout(() => {
            _saveScratchpad(true);
        }, 1200);
    }

    async function _appendScratchpadNote(text, section = '') {
        const cId = _spadCurrentCompanionId || _editingId;
        if (!cId || !text.trim()) return;
        _updateScratchpadStatus('Adding…', 'saving');
        try {
            const payload = {
                text: text.trim(),
                section: section || undefined,
                author: {
                    id: 'marcel',
                    name: 'Marcel',
                    role: 'user',
                    color: '#10b981'
                }
            };
            const res = await fetch(`${CHAT_API}/${cId}/scratchpad/append`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const textarea = document.getElementById('cc-spad-textarea');
            if (textarea && data.content) {
                textarea.value = data.content;
                _spadLastSavedContent = data.content;
                _renderScratchpadPreview(data.content);
                _populateScratchpadSections(data.sections || []);
                if (data.authors) {
                    _renderScratchpadContributors(data.authors);
                }
            }
            _updateScratchpadStatus(`Saved ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`, 'saved');
            if (typeof showToast === 'function') {
                showToast(data.message || 'Note added to scratchpad', 'success');
            }
        } catch (e) {
            console.error('[Scratchpad] Append note failed:', e);
            _updateScratchpadStatus('Failed to add note', 'error');
            if (typeof showToast === 'function') {
                showToast(`Could not add note: ${e.message}`, 'error');
            }
        }
    }

    function _setScratchpadViewMode(mode) {
        _spadViewMode = mode;
        const bodyEl = document.getElementById('cc-spad-body');
        if (!bodyEl) return;
        bodyEl.classList.remove('cc-spad-layout-split', 'cc-spad-layout-edit', 'cc-spad-layout-preview');
        bodyEl.classList.add(`cc-spad-layout-${mode}`);

        document.querySelectorAll('.cc-spad-mode-btn').forEach(b => {
            b.classList.toggle('cc-spad-mode-active', b.dataset.mode === mode);
        });

        if (mode !== 'edit') {
            _renderScratchpadPreview();
        }
    }

    function _initScratchpadListeners() {
        if (_spadListenersInitialized) return;
        _spadListenersInitialized = true;

        const textarea = document.getElementById('cc-spad-textarea');
        if (textarea) {
            textarea.addEventListener('input', () => {
                _renderScratchpadPreview(textarea.value);
                _triggerScratchpadAutoSave();
            });

            // Support Tab indentation and Ctrl+S shortcut
            textarea.addEventListener('keydown', e => {
                if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                    e.preventDefault();
                    _saveScratchpad(false);
                } else if (e.key === 'Tab') {
                    e.preventDefault();
                    const start = textarea.selectionStart;
                    const end = textarea.selectionEnd;
                    textarea.value = textarea.value.substring(0, start) + '  ' + textarea.value.substring(end);
                    textarea.selectionStart = textarea.selectionEnd = start + 2;
                    _renderScratchpadPreview(textarea.value);
                    _triggerScratchpadAutoSave();
                }
            });
        }

        // View mode switchers (Split / Edit / Preview)
        document.getElementById('cc-spad-mode-split')  ?.addEventListener('click', () => _setScratchpadViewMode('split'));
        document.getElementById('cc-spad-mode-edit')   ?.addEventListener('click', () => _setScratchpadViewMode('edit'));
        document.getElementById('cc-spad-mode-preview')?.addEventListener('click', () => _setScratchpadViewMode('preview'));

        // Save button
        document.getElementById('cc-spad-save-btn')?.addEventListener('click', () => _saveScratchpad(false));

        // Copy button
        document.getElementById('cc-spad-copy-btn')?.addEventListener('click', () => {
            const text = document.getElementById('cc-spad-textarea')?.value || '';
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    if (typeof showToast === 'function') showToast('Scratchpad copied to clipboard', 'info');
                });
            }
        });

        // Template button
        document.getElementById('cc-spad-template-btn')?.addEventListener('click', async () => {
            if (confirm('Reset scratchpad back to the standard co-working template? Any custom notes not saved elsewhere will be cleared.')) {
                const cId = _spadCurrentCompanionId || _editingId;
                if (!cId) return;
                try {
                    const res = await fetch(`${CHAT_API}/${cId}/scratchpad/clear`, { method: 'POST' });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    const data = await res.json();
                    const ta = document.getElementById('cc-spad-textarea');
                    if (ta && data.content) {
                        ta.value = data.content;
                        _spadLastSavedContent = data.content;
                        _renderScratchpadPreview(data.content);
                        _populateScratchpadSections(data.sections || []);
                    }
                    _updateScratchpadStatus('Template loaded', 'saved');
                    if (typeof showToast === 'function') showToast('Scratchpad reset to template', 'success');
                } catch (err) {
                    console.error('Template reset failed:', err);
                }
            }
        });

        // Quick note adder
        const quickInput = document.getElementById('cc-spad-quick-input');
        const quickAddBtn = document.getElementById('cc-spad-quick-add-btn');
        const sectionSelect = document.getElementById('cc-spad-section-select');

        const doAddQuick = () => {
            if (!quickInput) return;
            const val = quickInput.value.trim();
            if (!val) return;
            const sec = sectionSelect ? sectionSelect.value : '';
            _appendScratchpadNote(val, sec);
            quickInput.value = '';
        };

        quickInput?.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                doAddQuick();
            }
        });
        quickAddBtn?.addEventListener('click', doAddQuick);
    }

    // ==========================================
    // Visual Context Memory (Layouts & Models)
    // ==========================================
    let _visionCurrentCompanionId = null;
    let _visionCurrentCategory = 'all';
    let _visionMemoriesCache = [];
    let _visionSearchTerm = '';
    let _visionListenersInitialized = false;

    async function _loadVisualMemory(companionId) {
        _visionCurrentCompanionId = companionId;
        const subEl = document.getElementById('cc-vision-sub');
        if (subEl) {
            subEl.textContent = `with ${_activeData?.name || 'Companion'}`;
        }
        const gridEl = document.getElementById('cc-vision-grid');
        if (gridEl) {
            gridEl.innerHTML = '<div class="cc-vision-loading"><i class="fas fa-spinner fa-spin"></i> Loading visual memories…</div>';
        }

        try {
            const res = await fetch(`${CHAT_API}/${companionId}/visual-memory`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            _visionMemoriesCache = data.memories || [];

            const countEl = document.getElementById('cc-vision-count');
            if (countEl) {
                countEl.textContent = `${_visionMemoriesCache.length} snapshot${_visionMemoriesCache.length === 1 ? '' : 's'}`;
            }

            _renderVisualMemories();
        } catch (e) {
            console.error('[VisualMemory] Failed to load:', e);
            if (gridEl) {
                gridEl.innerHTML = `<div class="cc-vision-empty"><i class="fas fa-triangle-exclamation" style="color:#f43f5e;"></i> Failed to load visual memories: ${_escHtml(e.message)}</div>`;
            }
        }
    }

    function _renderVisualMemories() {
        const gridEl = document.getElementById('cc-vision-grid');
        if (!gridEl) return;

        let filtered = _visionMemoriesCache.slice();
        if (_visionCurrentCategory && _visionCurrentCategory !== 'all') {
            filtered = filtered.filter(m => (m.category || 'general').toLowerCase() === _visionCurrentCategory.toLowerCase());
        }

        if (_visionSearchTerm.trim()) {
            const term = _visionSearchTerm.trim().toLowerCase();
            filtered = filtered.filter(m => {
                const haystack = `${m.title || ''} ${m.description || ''} ${m.category || ''} ${(m.key_elements || []).join(' ')} ${(m.tags || []).join(' ')}`.toLowerCase();
                return haystack.includes(term);
            });
        }

        if (filtered.length === 0) {
            const isFilter = _visionCurrentCategory !== 'all' || _visionSearchTerm.trim();
            gridEl.innerHTML = `
                <div class="cc-vision-empty">
                    <i class="fas fa-eye" style="color:#ec4899;font-size:2rem;opacity:0.6;margin-bottom:0.5rem;"></i>
                    <div style="font-weight:600;color:#f4f4f5;font-size:0.95rem;">${isFilter ? 'No matching visual memories found' : 'No visual memories stored yet'}</div>
                    <div style="color:#a1a1aa;font-size:0.82rem;max-width:440px;line-height:1.5;margin-top:0.35rem;">
                        ${isFilter 
                            ? 'Try selecting "All" categories or clearing your search keywords.' 
                            : 'Misaka can remember your Unity scene layouts, Blender 3D models, code architecture, and UI wireframes across days so you can compare progress anytime. Click <strong>"Remember Screen"</strong> above or ask her in chat!'}
                    </div>
                </div>
            `;
            return;
        }

        const catIcons = {
            unity: 'fa-cube',
            blender: 'fa-shapes',
            code: 'fa-code',
            ui: 'fa-pen-ruler',
            reference: 'fa-image',
            general: 'fa-desktop'
        };

        const catColors = {
            unity: '#6366f1',
            blender: '#f97316',
            code: '#3b82f6',
            ui: '#10b981',
            reference: '#ec4899',
            general: '#8b5cf6'
        };

        let html = '';
        filtered.forEach(m => {
            const cat = (m.category || 'general').toLowerCase();
            const icon = catIcons[cat] || 'fa-eye';
            const color = catColors[cat] || '#8b5cf6';
            const title = _escHtml(m.title || 'Untitled Visual Memory');
            const timeStr = _escHtml(m.human_time || (m.timestamp ? new Date(m.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''));
            const desc = _escHtml(m.description || 'No description recorded.');
            const url = m.url || '';
            const resStr = (m.width && m.height) ? `${m.width}×${m.height}` : '';
            const elems = Array.isArray(m.key_elements) ? m.key_elements : [];

            let elemsHtml = '';
            if (elems.length > 0) {
                elemsHtml = '<div class="cc-vcard-elements">' + 
                    elems.slice(0, 4).map(e => `<span class="cc-vcard-elem-tag">${_escHtml(e)}</span>`).join('') +
                    (elems.length > 4 ? `<span class="cc-vcard-elem-more">+${elems.length - 4}</span>` : '') +
                    '</div>';
            }

            html += `
                <div class="cc-vcard" data-id="${_escHtml(m.id)}" style="--card-cat-color:${color};">
                    <div class="cc-vcard-thumb-wrap" onclick="window._openVisualSnapshotModal('${_esc(url)}', '${_esc(title)}')">
                        ${url ? `<img src="${_esc(url)}" alt="${title}" loading="lazy" class="cc-vcard-thumb">` : '<div class="cc-vcard-no-img"><i class="fas fa-image"></i></div>'}
                        <div class="cc-vcard-thumb-overlay"><i class="fas fa-magnifying-glass-plus"></i> View Snapshot</div>
                        <span class="cc-vcard-badge" style="background:${color}22;border-color:${color}66;color:${color};">
                            <i class="fas ${icon}"></i> ${cat.toUpperCase()}
                        </span>
                        ${resStr ? `<span class="cc-vcard-res">${resStr}</span>` : ''}
                    </div>
                    <div class="cc-vcard-body">
                        <div class="cc-vcard-header">
                            <h4 class="cc-vcard-title" title="${title}">${title}</h4>
                            <span class="cc-vcard-time">${timeStr}</span>
                        </div>
                        <p class="cc-vcard-desc">${desc}</p>
                        ${elemsHtml}
                        <div class="cc-vcard-actions">
                            <button type="button" class="cc-btn cc-btn-ghost cc-btn-xs cc-vcard-compare-btn" data-id="${_escHtml(m.id)}" title="Compare live screen with this reference layout">
                                <i class="fas fa-code-compare"></i> Compare
                            </button>
                            <button type="button" class="cc-btn cc-btn-ghost cc-btn-xs cc-vcard-edit-btn" data-id="${_escHtml(m.id)}" title="Edit notes">
                                <i class="fas fa-pen"></i>
                            </button>
                            <button type="button" class="cc-btn cc-btn-ghost cc-btn-xs cc-vcard-del-btn" data-id="${_escHtml(m.id)}" title="Delete visual memory">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });

        gridEl.innerHTML = html;

        // Wire action buttons
        gridEl.querySelectorAll('.cc-vcard-compare-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                _compareVisualMemory(btn.dataset.id);
            });
        });

        gridEl.querySelectorAll('.cc-vcard-edit-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                _editVisualMemoryNotes(btn.dataset.id);
            });
        });

        gridEl.querySelectorAll('.cc-vcard-del-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                _deleteVisualMemory(btn.dataset.id);
            });
        });
    }

    async function _takeVisualMemorySnapshot() {
        const cId = _visionCurrentCompanionId || _editingId;
        if (!cId) {
            if (typeof showToast === 'function') showToast('Please select or save a companion first', 'warning');
            return;
        }

        const catSelect = document.getElementById('cc-vision-cat-select');
        const monSelect = document.getElementById('cc-vision-monitor-select');
        const category = catSelect ? catSelect.value : 'general';
        const monitor = monSelect ? parseInt(monSelect.value, 10) : 1;

        const defaultTitles = {
            unity: 'Unity Project Layout',
            blender: 'Blender 3D Model',
            code: 'Code Architecture & IDE',
            ui: 'UI Design Layout',
            reference: 'Reference Artwork',
            general: 'Desktop State'
        };

        const titlePrompt = prompt(`Enter a title for this ${category.toUpperCase()} snapshot:`, defaultTitles[category] || 'Visual Snapshot');
        if (!titlePrompt || !titlePrompt.trim()) return;

        const notesPrompt = prompt('Any notes or key elements to remember? (Optional, press Enter to skip):', '') || '';

        const snapBtn = document.getElementById('cc-vision-snap-btn');
        if (snapBtn) {
            snapBtn.disabled = true;
            snapBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Snapping…';
        }

        try {
            const res = await fetch(`${CHAT_API}/${cId}/visual-memory`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: titlePrompt.trim(),
                    category: category,
                    description: notesPrompt.trim(),
                    monitor: monitor
                })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (typeof showToast === 'function') {
                showToast(`Visual memory "${data.memory?.title || 'Snapshot'}" recorded!`, 'success');
            }
            _loadVisualMemory(cId);
        } catch (e) {
            console.error('Visual memory capture failed:', e);
            if (typeof showToast === 'function') showToast(`Failed to capture: ${e.message}`, 'error');
        } finally {
            if (snapBtn) {
                snapBtn.disabled = false;
                snapBtn.innerHTML = '<i class="fas fa-camera"></i> Remember Screen';
            }
        }
    }

    async function _compareVisualMemory(memId) {
        const cId = _visionCurrentCompanionId || _editingId;
        if (!cId || !memId) return;

        const monSelect = document.getElementById('cc-vision-monitor-select');
        const monitor = monSelect ? parseInt(monSelect.value, 10) : 1;

        if (typeof showToast === 'function') showToast('Comparing current screen with visual memory…', 'info');

        try {
            const res = await fetch(`${CHAT_API}/${cId}/visual-memory/compare`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ memory_id: memId, monitor: monitor })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const ref = data.reference_memory || {};

            // Switch to chat view and ask companion to evaluate comparison!
            _switchView('chat');
            const chatInput = document.getElementById('cc-chat-input');
            if (chatInput) {
                chatInput.value = `How does my current screen look compared to the "${ref.title || 'reference'}" layout from ${ref.human_time || 'before'}? [tool:bridge module="visual_memory" cmd="compare" memory_id="${memId}" monitor="${monitor}"]`;
                const sendBtn = document.getElementById('cc-chat-send-btn');
                if (sendBtn) sendBtn.click();
            }
        } catch (e) {
            console.error('Comparison trigger failed:', e);
            if (typeof showToast === 'function') showToast(`Comparison failed: ${e.message}`, 'error');
        }
    }

    async function _editVisualMemoryNotes(memId) {
        const cId = _visionCurrentCompanionId || _editingId;
        const memory = _visionMemoriesCache.find(m => m.id === memId);
        if (!cId || !memory) return;

        const newTitle = prompt('Edit Title:', memory.title || '');
        if (newTitle === null) return;
        const newDesc = prompt('Edit Visual Description / Notes:', memory.description || '');
        if (newDesc === null) return;

        try {
            const res = await fetch(`${CHAT_API}/${cId}/visual-memory/${memId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: newTitle.trim() || memory.title,
                    description: newDesc.trim()
                })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            if (typeof showToast === 'function') showToast('Visual memory updated', 'success');
            _loadVisualMemory(cId);
        } catch (e) {
            if (typeof showToast === 'function') showToast(`Failed to update: ${e.message}`, 'error');
        }
    }

    async function _deleteVisualMemory(memId) {
        const cId = _visionCurrentCompanionId || _editingId;
        if (!cId || !memId) return;
        if (!confirm('Delete this visual memory snapshot? This cannot be undone.')) return;

        try {
            const res = await fetch(`${CHAT_API}/${cId}/visual-memory/${memId}`, {
                method: 'DELETE'
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            if (typeof showToast === 'function') showToast('Visual memory deleted', 'info');
            _loadVisualMemory(cId);
        } catch (e) {
            if (typeof showToast === 'function') showToast(`Failed to delete: ${e.message}`, 'error');
        }
    }

    window._openVisualSnapshotModal = function(url, title) {
        if (!url) return;
        let modal = document.getElementById('cc-snapshot-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'cc-snapshot-modal';
            modal.className = 'cc-snapshot-modal';
            modal.innerHTML = `
                <div class="cc-snapshot-modal-backdrop" onclick="document.getElementById('cc-snapshot-modal').classList.remove('open')"></div>
                <div class="cc-snapshot-modal-box">
                    <div class="cc-snapshot-modal-header">
                        <span id="cc-snapshot-modal-title">Visual Snapshot</span>
                        <button type="button" class="cc-snapshot-modal-close" onclick="document.getElementById('cc-snapshot-modal').classList.remove('open')">&times;</button>
                    </div>
                    <div class="cc-snapshot-modal-body">
                        <img id="cc-snapshot-modal-img" src="" alt="Snapshot">
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        document.getElementById('cc-snapshot-modal-title').textContent = title || 'Visual Snapshot';
        document.getElementById('cc-snapshot-modal-img').src = url;
        modal.classList.add('open');
    };

    function _initVisualMemoryListeners() {
        if (_visionListenersInitialized) return;
        _visionListenersInitialized = true;

        // Category filter buttons
        document.querySelectorAll('.cc-vision-cat-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.cc-vision-cat-btn').forEach(b => b.classList.remove('cc-vision-cat-active'));
                btn.classList.add('cc-vision-cat-active');
                _visionCurrentCategory = btn.dataset.cat || 'all';
                _renderVisualMemories();
            });
        });

        // Search input
        const searchInput = document.getElementById('cc-vision-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                _visionSearchTerm = searchInput.value;
                _renderVisualMemories();
            });
        }

        // Snapshot button
        document.getElementById('cc-vision-snap-btn')?.addEventListener('click', _takeVisualMemorySnapshot);

        // Refresh button
        document.getElementById('cc-vision-refresh-btn')?.addEventListener('click', () => {
            if (_editingId) _loadVisualMemory(_editingId);
        });

        // Tab click
        document.getElementById('cc-ptab-vision')?.addEventListener('click', () => _switchView('vision'));
    }

    function _initCompanionScrollToBottom() {
        const msgsEl = document.getElementById('cc-chat-msgs');
        const btn = document.getElementById('cc-scroll-bottom-btn');
        if (!msgsEl || !btn) return;
        if (msgsEl._scrollBottomBound) return;
        msgsEl._scrollBottomBound = true;

        const threshold = 180;
        const checkScroll = () => {
            const dist = msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight;
            if (dist > threshold) {
                btn.classList.remove('hidden');
            } else {
                btn.classList.add('hidden');
            }
        };

        msgsEl.addEventListener('scroll', checkScroll, { passive: true });
        btn.addEventListener('click', () => {
            msgsEl.scrollTo({ top: msgsEl.scrollHeight, behavior: 'smooth' });
            btn.classList.add('hidden');
        });
    }

    // Memory view

    let _lastMemoryData = null;
    let _memSearchQuery = '';

    async function _loadMemory(companionId) {
        const contentEl = document.getElementById('cc-mem-content');
        if (!contentEl) return;
        contentEl.innerHTML = '<div class="cc-mem-loading"><i class="fas fa-spinner fa-spin"></i> Loading memory…</div>';
        try {
            const res  = await fetch(`/api/companions/${companionId}/memory`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            _lastMemoryData = data;
            _renderMemory(contentEl, data);
        } catch (e) {
            contentEl.innerHTML = `<div class="cc-mem-empty"><i class="fas fa-exclamation-triangle"></i> Could not load memory: ${e.message}</div>`;
        }
    }

    function _esc(s) {
        return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function _renderMemory(el, data) {
        const bi  = data.base_info || {};
        const mem = data.memory    || {};

        const userInfo  = mem.user_info            || {};
        const obs       = mem.recent_observations  || [];
        const synth     = mem.synthesis_notes      || [];
        const lastUpd   = mem.last_updated         || bi.last_updated || null;
        const lastSynth = mem.last_synthesis        || null;

        const q = (_memSearchQuery || '').trim().toLowerCase();

        function section(icon, title, bodyHtml, actionHtml = '') {
            return `
            <div class="cc-mem-section">
              <div class="cc-mem-section-hdr">
                <div class="cc-mem-section-title"><i class="fas ${icon}"></i>${title}</div>
                <div class="cc-mem-section-actions">${actionHtml}</div>
              </div>
              <div class="cc-mem-section-body">${bodyHtml}</div>
            </div>`;
        }

        function emptyState(msg) {
            return `<div class="cc-mem-none">${msg}</div>`;
        }

        const uiEntries = Object.entries(userInfo).filter(([k, v]) => {
            if (!q) return true;
            const vs = typeof v === 'object' ? JSON.stringify(v) : String(v);
            return k.toLowerCase().includes(q) || vs.toLowerCase().includes(q);
        });

        const filteredObs = obs.map((text, idx) => ({ text, idx })).filter(item => {
            if (!q) return true;
            return String(item.text).toLowerCase().includes(q);
        });

        const filteredSynth = synth.map((text, idx) => ({ text, idx })).filter(item => {
            if (!q) return true;
            return String(item.text).toLowerCase().includes(q);
        });

        // Top toolbar: Stats + Search + Synthesize button
        const toolbarHtml = `
        <div class="cc-mem-toolbar">
          <div class="cc-mem-stats">
            <span class="cc-mem-stat-pill"><i class="fas fa-user-tag"></i> ${Object.keys(userInfo).length} Facts</span>
            <span class="cc-mem-stat-pill"><i class="fas fa-eye"></i> ${obs.length} Observations</span>
            <span class="cc-mem-stat-pill"><i class="fas fa-lightbulb"></i> ${synth.length} Insights</span>
          </div>
          <div class="cc-mem-toolbar-right">
            <div class="cc-mem-search-wrap">
              <i class="fas fa-search"></i>
              <input type="text" id="cc-mem-search" class="cc-mem-search-input" placeholder="Filter memories…" value="${_esc(_memSearchQuery)}">
            </div>
            <button type="button" id="cc-mem-synth-btn" class="cc-btn cc-btn-primary cc-btn-sm" title="Consolidate observations and extract high-level insights using the companion's LLM">
              <i class="fas fa-wand-magic-sparkles"></i> Synthesize Memory
            </button>
          </div>
        </div>`;

        // About (base_info)
        const aboutRows = [
            ['Core identity', bi.core_identity],
            ['Personality',   bi.personality],
            ['Speech style',  bi.speech_style],
            ['Autonomy',      bi.autonomy_level],
        ].filter(([, v]) => v);

        const quirks = bi.quirks   || [];
        const likes  = bi.likes    || [];
        const dislikes = bi.dislikes || [];

        let aboutHtml = aboutRows.map(([k, v]) => `
            <div class="cc-mem-kv">
              <span class="cc-mem-key">${_esc(k)}</span>
              <span class="cc-mem-val">${_esc(v)}</span>
            </div>`).join('');

        if (quirks.length)    aboutHtml += `<div class="cc-mem-kv"><span class="cc-mem-key">Quirks</span><span class="cc-mem-val">${quirks.map(q => `<span class="cc-mem-tag">${_esc(q)}</span>`).join('')}</span></div>`;
        if (likes.length)     aboutHtml += `<div class="cc-mem-kv"><span class="cc-mem-key">Likes</span><span class="cc-mem-val">${likes.map(l => `<span class="cc-mem-tag cc-mem-tag-like">${_esc(l)}</span>`).join('')}</span></div>`;
        if (dislikes.length)  aboutHtml += `<div class="cc-mem-kv"><span class="cc-mem-key">Dislikes</span><span class="cc-mem-val">${dislikes.map(d => `<span class="cc-mem-tag cc-mem-tag-dislike">${_esc(d)}</span>`).join('')}</span></div>`;
        if (!aboutHtml)       aboutHtml  = emptyState('No identity data yet.');

        // User info (interactive)
        const addFactFormHtml = `
            <div class="cc-mem-inline-form hidden" id="cc-mem-fact-form">
              <input type="text" id="cc-mem-fact-key" class="cc-mem-input cc-mem-input-key" placeholder="Key (e.g. occupation, project)">
              <input type="text" id="cc-mem-fact-val" class="cc-mem-input cc-mem-input-val" placeholder="Value (e.g. Game Developer)">
              <button type="button" id="cc-mem-fact-save" class="cc-btn cc-btn-primary cc-btn-sm">Save</button>
              <button type="button" id="cc-mem-fact-cancel" class="cc-btn cc-btn-ghost cc-btn-sm">Cancel</button>
            </div>`;

        const uiRowsHtml = uiEntries.length
            ? uiEntries.map(([k, v]) => {
                const valStr = typeof v === 'object' ? JSON.stringify(v) : String(v);
                return `
                <div class="cc-mem-kv cc-mem-kv-interactive" data-fact-key="${_esc(k)}" data-fact-val="${_esc(valStr)}">
                  <span class="cc-mem-key">${_esc(k)}</span>
                  <span class="cc-mem-val">${_esc(valStr)}</span>
                  <div class="cc-mem-row-actions">
                    <button type="button" class="cc-mem-act-btn cc-mem-edit-fact" title="Edit fact"><i class="fas fa-pen"></i></button>
                    <button type="button" class="cc-mem-act-btn cc-mem-del-fact" title="Delete fact"><i class="fas fa-trash"></i></button>
                  </div>
                </div>`;
            }).join('')
            : emptyState(q ? 'No facts match filter.' : 'Nothing recorded yet — click "+ Add Fact" or keep chatting!');

        const uiHtml = addFactFormHtml + uiRowsHtml;

        // Observations (interactive)
        const addObsFormHtml = `
            <div class="cc-mem-inline-form hidden" id="cc-mem-obs-form">
              <input type="hidden" id="cc-mem-obs-idx" value="">
              <input type="text" id="cc-mem-obs-text" class="cc-mem-input cc-mem-input-val" placeholder="Observation or note about the user…">
              <button type="button" id="cc-mem-obs-save" class="cc-btn cc-btn-primary cc-btn-sm">Save</button>
              <button type="button" id="cc-mem-obs-cancel" class="cc-btn cc-btn-ghost cc-btn-sm">Cancel</button>
            </div>`;

        const obsRowsHtml = filteredObs.length
            ? filteredObs.map(({ text, idx }) => `
                <div class="cc-mem-obs-item cc-mem-obs-interactive" data-obs-idx="${idx}" data-obs-text="${_esc(text)}">
                  <i class="fas fa-circle-dot"></i>
                  <span class="cc-mem-obs-text">${_esc(text)}</span>
                  <div class="cc-mem-row-actions">
                    <button type="button" class="cc-mem-act-btn cc-mem-edit-obs" title="Edit observation"><i class="fas fa-pen"></i></button>
                    <button type="button" class="cc-mem-act-btn cc-mem-del-obs" title="Delete observation"><i class="fas fa-trash"></i></button>
                  </div>
                </div>`).join('')
            : emptyState(q ? 'No observations match filter.' : 'No observations yet.');

        const obsHtml = addObsFormHtml + obsRowsHtml;

        // Synthesis notes (interactive delete)
        const synthHtml = filteredSynth.length
            ? filteredSynth.map(({ text, idx }) => `
                <div class="cc-mem-obs-item cc-mem-synth-item cc-mem-obs-interactive" data-synth-idx="${idx}">
                  <i class="fas fa-lightbulb"></i>
                  <span class="cc-mem-obs-text">${_esc(text)}</span>
                  <div class="cc-mem-row-actions">
                    <button type="button" class="cc-mem-act-btn cc-mem-del-synth" title="Remove insight"><i class="fas fa-trash"></i></button>
                  </div>
                </div>`).join('')
            : emptyState(q ? 'No insights match filter.' : 'No synthesis run yet — click "Synthesize Memory" above to generate insights.');

        // Footer timestamps
        let footer = '';
        if (lastUpd || lastSynth) {
            footer = `<div class="cc-mem-footer">`;
            if (lastUpd)   footer += `<span><i class="fas fa-clock"></i>Updated ${_esc(lastUpd)}</span>`;
            if (lastSynth) footer += `<span><i class="fas fa-wand-sparkles"></i>Synthesised ${_esc(lastSynth)}</span>`;
            footer += `</div>`;
        }

        const addFactBtnHtml = `<button type="button" class="cc-btn cc-btn-ghost cc-btn-xs" id="cc-mem-add-fact-btn"><i class="fas fa-plus"></i> Add Fact</button>`;
        const addObsBtnHtml  = `<button type="button" class="cc-btn cc-btn-ghost cc-btn-xs" id="cc-mem-add-obs-btn"><i class="fas fa-plus"></i> Add Note</button>`;

        el.innerHTML =
            toolbarHtml +
            section('fa-user',       'What I know about you',   uiHtml,  addFactBtnHtml) +
            section('fa-eye',        'Recent Observations',     obsHtml, addObsBtnHtml)  +
            section('fa-lightbulb',  'Synthesis Notes',         synthHtml) +
            section('fa-id-card',    'Core Identity',           aboutHtml) +
            footer;

        _bindMemoryEvents(el);
    }

    function _bindMemoryEvents(el) {
        if (!el || !_editingId) return;

        // Search filter
        const searchInput = el.querySelector('#cc-mem-search');
        if (searchInput) {
            searchInput.addEventListener('input', e => {
                _memSearchQuery = e.target.value;
                const pos = e.target.selectionStart;
                if (_lastMemoryData) _renderMemory(el, _lastMemoryData);
                const newInput = el.querySelector('#cc-mem-search');
                if (newInput) {
                    newInput.focus();
                    try { newInput.setSelectionRange(pos, pos); } catch {}
                }
            });
        }

        // Synthesize Memory button
        el.querySelector('#cc-mem-synth-btn')?.addEventListener('click', async e => {
            const btn = e.currentTarget;
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Synthesizing…';
            try {
                const res = await fetch(`${CHAT_API}/${_editingId}/memory/synthesize`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
                _lastMemoryData = data;
                _renderMemory(el, data);
                if (typeof showToast === 'function') showToast('Memory synthesized & consolidated!', 'success');
            } catch (err) {
                if (typeof showToast === 'function') showToast(`Synthesis failed: ${err.message}`, 'error');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Synthesize Memory';
            }
        });

        // Add / Edit Fact
        const factForm   = el.querySelector('#cc-mem-fact-form');
        const factKeyIn  = el.querySelector('#cc-mem-fact-key');
        const factValIn  = el.querySelector('#cc-mem-fact-val');

        el.querySelector('#cc-mem-add-fact-btn')?.addEventListener('click', () => {
            if (!factForm) return;
            factForm.classList.remove('hidden');
            if (factKeyIn) { factKeyIn.value = ''; factKeyIn.readOnly = false; factKeyIn.focus(); }
            if (factValIn) factValIn.value = '';
        });

        el.querySelector('#cc-mem-fact-cancel')?.addEventListener('click', () => {
            factForm?.classList.add('hidden');
        });

        const saveFact = async () => {
            const key = factKeyIn?.value?.trim();
            const value = factValIn?.value?.trim();
            if (!key || !value) return;
            try {
                const res = await fetch(`${CHAT_API}/${_editingId}/memory/fact`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key, value })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
                _lastMemoryData = data;
                _renderMemory(el, data);
            } catch (err) {
                if (typeof showToast === 'function') showToast(`Failed to save fact: ${err.message}`, 'error');
            }
        };

        el.querySelector('#cc-mem-fact-save')?.addEventListener('click', saveFact);
        factValIn?.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); saveFact(); } });

        el.querySelectorAll('.cc-mem-edit-fact').forEach(btn => {
            btn.addEventListener('click', e => {
                const row = e.currentTarget.closest('[data-fact-key]');
                if (!row || !factForm) return;
                factForm.classList.remove('hidden');
                if (factKeyIn) { factKeyIn.value = row.dataset.factKey || ''; factKeyIn.readOnly = true; }
                if (factValIn) { factValIn.value = row.dataset.factVal || ''; factValIn.focus(); }
            });
        });

        el.querySelectorAll('.cc-mem-del-fact').forEach(btn => {
            btn.addEventListener('click', async e => {
                const row = e.currentTarget.closest('[data-fact-key]');
                const key = row?.dataset?.factKey;
                if (!key) return;
                try {
                    const res = await fetch(`${CHAT_API}/${_editingId}/memory/fact/${encodeURIComponent(key)}`, { method: 'DELETE' });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
                    _lastMemoryData = data;
                    _renderMemory(el, data);
                } catch (err) {
                    if (typeof showToast === 'function') showToast(`Failed to delete fact: ${err.message}`, 'error');
                }
            });
        });

        // Add / Edit Observation
        const obsForm   = el.querySelector('#cc-mem-obs-form');
        const obsIdxIn  = el.querySelector('#cc-mem-obs-idx');
        const obsTextIn = el.querySelector('#cc-mem-obs-text');

        el.querySelector('#cc-mem-add-obs-btn')?.addEventListener('click', () => {
            if (!obsForm) return;
            obsForm.classList.remove('hidden');
            if (obsIdxIn)  obsIdxIn.value = '';
            if (obsTextIn) { obsTextIn.value = ''; obsTextIn.focus(); }
        });

        el.querySelector('#cc-mem-obs-cancel')?.addEventListener('click', () => {
            obsForm?.classList.add('hidden');
        });

        const saveObs = async () => {
            const text = obsTextIn?.value?.trim();
            const idxStr = obsIdxIn?.value ?? '';
            if (!text) return;
            try {
                const isEdit = idxStr !== '';
                const url = isEdit
                    ? `${CHAT_API}/${_editingId}/memory/observation/${idxStr}`
                    : `${CHAT_API}/${_editingId}/memory/observation`;
                const res = await fetch(url, {
                    method: isEdit ? 'PUT' : 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
                _lastMemoryData = data;
                _renderMemory(el, data);
            } catch (err) {
                if (typeof showToast === 'function') showToast(`Failed to save observation: ${err.message}`, 'error');
            }
        };

        el.querySelector('#cc-mem-obs-save')?.addEventListener('click', saveObs);
        obsTextIn?.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); saveObs(); } });

        el.querySelectorAll('.cc-mem-edit-obs').forEach(btn => {
            btn.addEventListener('click', e => {
                const row = e.currentTarget.closest('[data-obs-idx]');
                if (!row || !obsForm) return;
                obsForm.classList.remove('hidden');
                if (obsIdxIn)  obsIdxIn.value  = row.dataset.obsIdx;
                if (obsTextIn) { obsTextIn.value = row.dataset.obsText || ''; obsTextIn.focus(); }
            });
        });

        el.querySelectorAll('.cc-mem-del-obs').forEach(btn => {
            btn.addEventListener('click', async e => {
                const row = e.currentTarget.closest('[data-obs-idx]');
                const idx = row?.dataset?.obsIdx;
                if (idx === undefined) return;
                try {
                    const res = await fetch(`${CHAT_API}/${_editingId}/memory/observation/${idx}`, { method: 'DELETE' });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
                    _lastMemoryData = data;
                    _renderMemory(el, data);
                } catch (err) {
                    if (typeof showToast === 'function') showToast(`Failed to delete observation: ${err.message}`, 'error');
                }
            });
        });

        el.querySelectorAll('.cc-mem-del-synth').forEach(btn => {
            btn.addEventListener('click', async e => {
                const row = e.currentTarget.closest('[data-synth-idx]');
                const idx = row?.dataset?.synthIdx;
                if (idx === undefined) return;
                try {
                    const res = await fetch(`${CHAT_API}/${_editingId}/memory/synthesis/${idx}`, { method: 'DELETE' });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
                    _lastMemoryData = data;
                    _renderMemory(el, data);
                } catch (err) {
                    if (typeof showToast === 'function') showToast(`Failed to remove insight: ${err.message}`, 'error');
                }
            });
        });
    }

    const _PROFILE_LABELS = {
        full_local:       { label: 'Full Local', icon: 'fa-shield-halved' },
        cloud_safe:       { label: 'Cloud Safe', icon: 'fa-cloud' },
        ambient_observer: { label: 'Ambient Only', icon: 'fa-eye' },
        sandboxed:        { label: 'Sandboxed', icon: 'fa-lock' },
    };

    function _updatePaneHeader(data, isBuiltin, isNew = false) {
        const avatarEl     = document.getElementById('cc-pane-avatar');
        const nameEl       = document.getElementById('cc-pane-name');
        const modelBadge   = document.getElementById('cc-pane-model-badge');
        const profileBadge = document.getElementById('cc-pane-profile-badge');
        const subEl        = document.getElementById('cc-pane-sub');
        const chatTab      = document.getElementById('cc-ptab-chat');
        const portAvEl     = document.getElementById('cc-portrait-avatar');
        const portNameEl   = document.getElementById('cc-portrait-name');
        const portSubEl    = document.getElementById('cc-portrait-sub');
        const moodTextEl   = document.getElementById('cc-portrait-mood-text');
        const exprTextEl   = document.getElementById('cc-portrait-expr-text');
        const quickPop     = document.getElementById('cc-quick-switch-popover');
        if (quickPop) quickPop.classList.add('hidden');

        const memoryTab  = document.getElementById('cc-ptab-memory');
        const spadTab    = document.getElementById('cc-ptab-scratchpad');
        const visionTab  = document.getElementById('cc-ptab-vision');
        if (isNew || !data) {
            if (avatarEl) { avatarEl.textContent = '✦'; avatarEl.style.background = 'rgba(99,102,241,0.15)'; avatarEl.style.color = '#818cf8'; }
            if (nameEl) nameEl.textContent = 'New Companion';
            if (modelBadge) modelBadge.classList.add('hidden');
            if (profileBadge) profileBadge.classList.add('hidden');
            if (subEl)  subEl.textContent  = 'Pick a starter template or fill in the settings below to create';
            if (chatTab)   { chatTab.disabled   = true; chatTab.title   = 'Save the companion first to start chatting'; }
            if (spadTab)   { spadTab.disabled   = true; spadTab.title   = 'Save the companion first to view scratchpad'; }
            if (visionTab) { visionTab.disabled = true; visionTab.title = 'Save the companion first to view visual memory'; }
            if (memoryTab) { memoryTab.disabled = true; memoryTab.title = 'Save the companion first to view memory'; }
            if (portAvEl)   { portAvEl.textContent = '✦'; portAvEl.style.background = 'rgba(99,102,241,0.15)'; portAvEl.style.color = '#818cf8'; }
            if (portNameEl) portNameEl.textContent = '';
            if (portSubEl)  portSubEl.textContent  = '';
            return;
        }

        if (chatTab)   { chatTab.disabled   = false; chatTab.title   = ''; }
        if (spadTab)   { spadTab.disabled   = false; spadTab.title   = ''; }
        if (visionTab) { visionTab.disabled = false; visionTab.title = ''; }
        if (memoryTab) { memoryTab.disabled = false; memoryTab.title = ''; }
        const color = data.accent_color || '#6366f1';

        // Header avatar
        if (data.has_icon && data.id) {
            if (avatarEl) avatarEl.innerHTML = `<img src="${API}/${data.id}/icon?t=${Date.now()}" style="width:100%;height:100%;object-fit:cover;border-radius:11px">`;
            if (avatarEl) { avatarEl.style.background = ''; avatarEl.style.color = ''; }
        } else {
            if (avatarEl) { avatarEl.textContent = data.avatar_symbol || '✦'; avatarEl.style.background = `${color}22`; avatarEl.style.color = color; }
        }
        if (nameEl) nameEl.textContent = data.name || '';
        if (subEl)  subEl.textContent  = isBuiltin ? `Built-in · ${data.description || ''}` : (data.description || '');

        // Model badge (Local GGUF / Ollama vs Cloud) — clickable for quick switch
        if (modelBadge) {
            const m = data.default_model || 'auto';
            const isLocal = m.endsWith('.gguf') || m.startsWith('local:') || m.startsWith('ollama:') || m.startsWith('ollama/');
            const shortName = m.replace(/\.gguf$/i, '').split('/').pop();
            modelBadge.className = `cc-pane-model-badge ${isLocal ? 'cc-model-badge-local' : 'cc-model-badge-cloud'}`;
            modelBadge.innerHTML = isLocal
                ? `<i class="fas fa-microchip"></i> Local · ${_esc(shortName)} <i class="fas fa-caret-down" style="opacity:0.7;margin-left:2px"></i>`
                : `<i class="fas fa-cloud"></i> ${_esc(shortName)} <i class="fas fa-caret-down" style="opacity:0.7;margin-left:2px"></i>`;
            modelBadge.title = `Active model: ${m} — Click to switch model or Connector Profile`;
        }

        // Connector Profile badge — clickable for quick switch
        if (profileBadge) {
            const profId = data.capabilities?.connector_profile || 'full_local';
            const info   = _PROFILE_LABELS[profId] || { label: profId, icon: 'fa-plug-circle-bolt' };
            profileBadge.className = 'cc-pane-profile-badge';
            profileBadge.innerHTML = `<i class="fas ${info.icon}"></i> ${_esc(info.label)} <i class="fas fa-caret-down" style="opacity:0.7;margin-left:2px"></i>`;
            profileBadge.title = `Connector Profile: ${info.label} — Click to switch`;
        }

        // Portrait panel — priority: expression image > icon > symbol
        const exprImgs   = data.expression_images || {};
        const storedExpr = (() => { try { return data.id ? localStorage.getItem(`cc_last_expr_${data.id}`) : null; } catch { return null; } })();
        const defExpr    = (storedExpr && exprImgs[storedExpr]) ? storedExpr : (data.default_expression || 'default');
        const defMood    = data.behavior?.default_mood || 'calm';

        if (moodTextEl) moodTextEl.textContent = defMood;
        if (exprTextEl) exprTextEl.textContent = defExpr;
        _updateAutoVoiceBtnUI(!!data.voice?.auto_speak);

        if (data.icon_mode && exprImgs[defExpr] && data.id) {
            const exprUrl = `${API}/${data.id}/expression/${defExpr}?t=${Date.now()}`;
            if (portAvEl) { portAvEl.innerHTML = `<img src="${exprUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:20px">`; portAvEl.style.background = ''; portAvEl.style.color = ''; }
        } else if (data.has_icon && data.id) {
            if (portAvEl) { portAvEl.innerHTML = `<img src="${API}/${data.id}/icon?t=${Date.now()}" style="width:100%;height:100%;object-fit:cover;border-radius:20px">`; portAvEl.style.background = ''; portAvEl.style.color = ''; }
        } else {
            if (portAvEl) { portAvEl.textContent = data.avatar_symbol || '✦'; portAvEl.style.background = `${color}22`; portAvEl.style.color = color; }
        }
        if (portNameEl) portNameEl.textContent = data.name || '';
        if (portSubEl)  portSubEl.textContent  = isBuiltin ? 'Built-in Companion' : 'Custom Companion';
    }

    async function _toggleQuickSwitchPopover() {
        const pop = document.getElementById('cc-quick-switch-popover');
        if (!pop || !_activeData || !_editingId) return;
        const willOpen = pop.classList.contains('hidden');
        if (!willOpen) {
            pop.classList.add('hidden');
            return;
        }
        const mSel = document.getElementById('cc-quick-model-select');
        const pSel = document.getElementById('cc-quick-profile-select');
        if (mSel) {
            _ensureModelSelectPopulated(mSel, _activeData.default_model || 'gemini-1.5-flash');
        }
        if (pSel) {
            try {
                const res = await fetch('/api/connectors/profiles');
                if (res.ok) {
                    const d = await res.json();
                    const profiles = d.profiles || [];
                    if (profiles.length) {
                        pSel.innerHTML = profiles.map(p =>
                            `<option value="${_esc(p.id)}">${_esc(p.name)}</option>`
                        ).join('');
                    }
                }
            } catch {}
            pSel.value = _activeData.capabilities?.connector_profile || 'full_local';
        }
        pop.classList.remove('hidden');
    }

    async function _saveQuickHeaderConfig(patch) {
        if (!_editingId || !_activeData) return;
        try {
            const res = await fetch(`${CHAT_API}/${_editingId}/quick-config`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(patch)
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            if (patch.default_model !== undefined) {
                _activeData.default_model = patch.default_model;
                const formModel = document.getElementById('cc-model');
                if (formModel) formModel.value = patch.default_model;
            }
            if (patch.connector_profile !== undefined) {
                if (!_activeData.capabilities) _activeData.capabilities = {};
                _activeData.capabilities.connector_profile = patch.connector_profile;
                const formProf = document.getElementById('cc-cap-connector-profile');
                if (formProf) formProf.value = patch.connector_profile;
                if (window.AethvionSlashAutocomplete?.invalidateCache) {
                    window.AethvionSlashAutocomplete.invalidateCache();
                }
            }
            _updatePaneHeader(_activeData, _isBuiltin);
            if (typeof showToast === 'function') showToast('Updated companion configuration', 'success');
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Update failed: ${err.message}`, 'error');
        }
    }

    // Global Voice Database & Speech Engine (TTS / STT)

    let _voiceLibCache = null;
    let _activeAudioEl = null;
    let _speakingBubbleBtn = null;
    let _recognitionInstance = null;
    let _isRecordingMic = false;

    const _DEFAULT_KOKORO_VOICES = [
        { id: 'af_heart',    name: 'Heart',    language: 'en-us', gender: 'female' },
        { id: 'af_bella',    name: 'Bella',    language: 'en-us', gender: 'female' },
        { id: 'af_aoede',    name: 'Aoede',    language: 'en-us', gender: 'female' },
        { id: 'af_kore',     name: 'Kore',     language: 'en-us', gender: 'female' },
        { id: 'af_nicole',   name: 'Nicole',   language: 'en-us', gender: 'female' },
        { id: 'af_nova',     name: 'Nova',     language: 'en-us', gender: 'female' },
        { id: 'af_river',    name: 'River',    language: 'en-us', gender: 'female' },
        { id: 'af_sarah',    name: 'Sarah',    language: 'en-us', gender: 'female' },
        { id: 'af_sky',      name: 'Sky',      language: 'en-us', gender: 'female' },
        { id: 'am_adam',     name: 'Adam',     language: 'en-us', gender: 'male' },
        { id: 'am_echo',     name: 'Echo',     language: 'en-us', gender: 'male' },
        { id: 'am_eric',     name: 'Eric',     language: 'en-us', gender: 'male' },
        { id: 'am_fenrir',   name: 'Fenrir',   language: 'en-us', gender: 'male' },
        { id: 'am_liam',     name: 'Liam',     language: 'en-us', gender: 'male' },
        { id: 'am_michael',  name: 'Michael',  language: 'en-us', gender: 'male' },
        { id: 'am_onyx',     name: 'Onyx',     language: 'en-us', gender: 'male' },
        { id: 'bf_emma',     name: 'Emma',     language: 'en-gb', gender: 'female' },
        { id: 'bf_isabella', name: 'Isabella', language: 'en-gb', gender: 'female' },
        { id: 'bm_george',   name: 'George',   language: 'en-gb', gender: 'male' },
        { id: 'bm_lewis',    name: 'Lewis',    language: 'en-gb', gender: 'male' },
    ];

    async function _loadVoiceLibrary(force = false) {
        if (_voiceLibCache && !force) return _voiceLibCache;
        try {
            const res = await fetch('/api/audio/local/library');
            if (res.ok) {
                _voiceLibCache = await res.json();
                return _voiceLibCache;
            }
        } catch {}
        _voiceLibCache = {
            models: [
                { id: 'kokoro', name: 'Kokoro TTS', voices: _DEFAULT_KOKORO_VOICES },
                { id: 'web_speech', name: 'System / Browser Web Speech', voices: [] }
            ],
            presets: []
        };
        return _voiceLibCache;
    }

    function _getBrowserSpeechVoices() {
        if (typeof window.speechSynthesis === 'undefined') return [];
        const list = window.speechSynthesis.getVoices() || [];
        return list.map(v => ({
            id: v.name,
            name: v.name,
            language: v.lang || 'en',
            gender: v.default ? 'default' : 'system'
        }));
    }

    async function _populateVoiceDropdown(modelId, selectedVoiceId = '') {
        const voiceSel = document.getElementById('cc-voice-id');
        if (!voiceSel) return;
        const lib = await _loadVoiceLibrary();
        let voices = [];

        if (modelId === 'preset') {
            voices = (lib.presets || []).map(p => ({
                id: p.id,
                name: `${p.name} (${p.model_id} · ${p.voice_id})`,
                language: p.language || 'en',
                gender: p.gender || ''
            }));
        } else if (modelId === 'web_speech') {
            voices = _getBrowserSpeechVoices();
            if (!voices.length) {
                voices = [{ id: 'default', name: 'System Default Voice', language: 'en', gender: 'system' }];
            }
        } else {
            const mod = (lib.models || []).find(m => m.id === modelId);
            voices = (mod && mod.voices && mod.voices.length) ? mod.voices : (modelId === 'kokoro' ? _DEFAULT_KOKORO_VOICES : []);
            if (!voices.length) {
                voices = [{ id: 'default', name: 'Default / Cloned Voice', language: 'en', gender: 'neutral' }];
            }
        }

        voiceSel.innerHTML = voices.map(v => {
            const meta = [v.language, v.gender].filter(Boolean).join(' · ');
            const label = meta ? `${v.name} (${meta})` : v.name;
            return `<option value="${_esc(v.id)}">${_esc(label)}</option>`;
        }).join('');

        if (selectedVoiceId && voiceSel.querySelector(`option[value="${selectedVoiceId}"]`)) {
            voiceSel.value = selectedVoiceId;
        } else if (voices.length) {
            voiceSel.value = voices[0].id;
        }
    }

    function _cleanSpeechText(text) {
        if (!text) return '';
        return _stripToolTags(String(text))
            .replace(/```[\s\S]*?```/g, ' Code block omitted. ')
            .replace(/`([^`]+)`/g, '$1')
            .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
            .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
            .replace(/[*_~#>]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function _stopSpeech() {
        if (_activeAudioEl) {
            try { _activeAudioEl.pause(); _activeAudioEl.currentTime = 0; } catch {}
            _activeAudioEl = null;
        }
        if (typeof window.speechSynthesis !== 'undefined') {
            try { window.speechSynthesis.cancel(); } catch {}
        }
        if (_speakingBubbleBtn) {
            _speakingBubbleBtn.innerHTML = '<i class="fas fa-volume-high"></i>';
            _speakingBubbleBtn.classList.remove('cc-msg-act-speaking');
            _speakingBubbleBtn = null;
        }
        document.getElementById('cc-portrait-avatar')?.classList.remove('cc-portrait-speaking');
        if (!_chatStreaming) _setPortraitThinking(false);
    }

    function _speakViaWebSpeech(cleanText, voiceId, speed, onDone) {
        if (typeof window.speechSynthesis === 'undefined') {
            if (onDone) onDone();
            return;
        }
        try {
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(cleanText);
            utter.rate = Math.max(0.5, Math.min(2.0, speed || 1.0));
            if (voiceId && voiceId !== 'default') {
                const voices = window.speechSynthesis.getVoices() || [];
                const match = voices.find(v => v.name === voiceId);
                if (match) utter.voice = match;
            }
            utter.onend = () => { if (onDone) onDone(); };
            utter.onerror = () => { if (onDone) onDone(); };
            window.speechSynthesis.speak(utter);
        } catch {
            if (onDone) onDone();
        }
    }

    async function _speakText(rawText, customVoiceCfg = null, btnEl = null) {
        if (btnEl && _speakingBubbleBtn === btnEl) {
            // Clicking the same active speaker button stops playback
            _stopSpeech();
            return;
        }
        _stopSpeech();

        const cleanText = _cleanSpeechText(rawText);
        if (!cleanText) return;

        const cfg = customVoiceCfg || _activeData?.voice || {
            model_id: 'kokoro',
            voice_id: 'af_heart',
            speed: 1.0,
            language: 'en'
        };

        let modelId  = cfg.model_id || 'kokoro';
        let voiceId  = cfg.voice_id || 'af_heart';
        let speed    = parseFloat(cfg.speed || 1.0);
        let language = cfg.language || 'en';

        // Resolve Global Voice Database preset if selected
        if (modelId === 'preset') {
            const lib = await _loadVoiceLibrary();
            const preset = (lib.presets || []).find(p => p.id === voiceId);
            if (preset) {
                modelId  = preset.model_id || 'kokoro';
                voiceId  = preset.voice_id || 'af_heart';
                speed    = parseFloat(preset.speed || speed);
                language = preset.language || language;
            } else {
                modelId = 'kokoro';
                voiceId = 'af_heart';
            }
        }

        if (btnEl) {
            _speakingBubbleBtn = btnEl;
            btnEl.innerHTML = '<i class="fas fa-stop"></i>';
            btnEl.classList.add('cc-msg-act-speaking');
        }
        document.getElementById('cc-portrait-avatar')?.classList.add('cc-portrait-speaking');
        _setPortraitThinking(true, 'Speaking…');

        const finishSpeak = () => {
            if (_speakingBubbleBtn === btnEl && btnEl) {
                btnEl.innerHTML = '<i class="fas fa-volume-high"></i>';
                btnEl.classList.remove('cc-msg-act-speaking');
                _speakingBubbleBtn = null;
            }
            document.getElementById('cc-portrait-avatar')?.classList.remove('cc-portrait-speaking');
            if (!_chatStreaming) _setPortraitThinking(false);
        };

        if (modelId === 'web_speech') {
            _speakViaWebSpeech(cleanText, voiceId, speed, finishSpeak);
            return;
        }

        try {
            const res = await fetch('/api/audio/local/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: cleanText,
                    model_id: modelId,
                    voice_id: voiceId,
                    speed,
                    language,
                    device: 'cuda'
                })
            });
            const data = await res.json();
            if (!res.ok || !data.audio) throw new Error(data.detail || 'TTS unavailable');
            const audio = new Audio(data.audio);
            _activeAudioEl = audio;
            audio.onended = finishSpeak;
            audio.onerror = () => _speakViaWebSpeech(cleanText, null, speed, finishSpeak);
            await audio.play();
        } catch {
            // Instant fallback to system Web Speech if local audio model is not yet installed
            _speakViaWebSpeech(cleanText, null, speed, finishSpeak);
        }
    }

    function _updateAutoVoiceBtnUI(enabled) {
        const btn   = document.getElementById('cc-auto-voice-btn');
        const icon  = document.getElementById('cc-auto-voice-icon');
        const label = document.getElementById('cc-auto-voice-label');
        const chkEl = document.getElementById('cc-voice-autospeak');
        if (chkEl) chkEl.checked = !!enabled;
        if (!btn) return;
        btn.classList.toggle('cc-voice-toggle-active', !!enabled);
        if (icon)  icon.className = enabled ? 'fas fa-volume-high' : 'fas fa-volume-xmark';
        if (label) label.textContent = enabled ? 'Voice On' : 'Auto-Voice';
    }

    function _toggleAutoVoice() {
        if (!_activeData) return;
        if (!_activeData.voice) {
            _activeData.voice = { enabled: true, auto_speak: false, model_id: 'kokoro', voice_id: 'af_heart', speed: 1.0, language: 'en' };
        }
        _activeData.voice.auto_speak = !_activeData.voice.auto_speak;
        _updateAutoVoiceBtnUI(_activeData.voice.auto_speak);
        if (!_activeData.voice.auto_speak) _stopSpeech();
        if (typeof showToast === 'function') {
            showToast(_activeData.voice.auto_speak ? 'Auto-Voice enabled' : 'Auto-Voice muted', 'info');
        }
    }

    function _toggleMicDictation() {
        const micBtn = document.getElementById('cc-chat-mic');
        const input  = document.getElementById('cc-chat-input');
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRec) {
            if (typeof showToast === 'function') showToast('Speech recognition is not supported in this browser.', 'error');
            return;
        }

        if (_isRecordingMic && _recognitionInstance) {
            _recognitionInstance.stop();
            return;
        }

        const rec = new SpeechRec();
        rec.lang = 'en-US';
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        _recognitionInstance = rec;
        _isRecordingMic = true;
        micBtn?.classList.add('cc-mic-recording');

        rec.onresult = event => {
            const transcript = event.results?.[0]?.[0]?.transcript || '';
            if (transcript && input) {
                input.value = (input.value ? input.value.trim() + ' ' : '') + transcript;
                _autoResizeInput(input);
                input.focus();
            }
        };
        rec.onerror = () => {
            _isRecordingMic = false;
            micBtn?.classList.remove('cc-mic-recording');
        };
        rec.onend = () => {
            _isRecordingMic = false;
            micBtn?.classList.remove('cc-mic-recording');
        };
        rec.start();
    }

    // Expose Global Voice API for other suite tools (Chat, Automate, Agents)
    window.AethvionVoice = {
        getLibrary: _loadVoiceLibrary,
        speak: _speakText,
        stop: _stopSpeech,
        cleanText: _cleanSpeechText,
    };

    // Chat & Attachments

    let _historyOffsetDays = 0;
    let _pendingAttachments = [];

    function _formatDayDivider(dateStr) {
        if (!dateStr) return '';
        const today = new Date().toISOString().slice(0, 10);
        const yest  = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
        if (dateStr === today) return 'Today';
        if (dateStr === yest)  return 'Yesterday';
        return dateStr;
    }

    function _renderPendingAttachments() {
        const bar = document.getElementById('cc-chat-attachments-bar');
        if (!bar) return;
        if (!_pendingAttachments.length) {
            bar.classList.add('hidden');
            bar.innerHTML = '';
            return;
        }
        bar.classList.remove('hidden');
        bar.innerHTML = _pendingAttachments.map((att, idx) => {
            const thumb = att.is_image && att.url
                ? `<img src="${_esc(att.url)}" class="cc-att-chip-thumb" alt="${_esc(att.filename)}">`
                : `<i class="fas fa-file-code cc-att-chip-icon"></i>`;
            return `
              <div class="cc-att-chip" data-idx="${idx}">
                ${thumb}
                <span class="cc-att-chip-name" title="${_esc(att.filename)}">${_esc(att.filename)}</span>
                <button type="button" class="cc-att-chip-del" data-idx="${idx}" title="Remove attachment">&times;</button>
              </div>`;
        }).join('');
        bar.querySelectorAll('.cc-att-chip-del').forEach(btn => {
            btn.addEventListener('click', e => {
                const i = parseInt(e.currentTarget.dataset.idx, 10);
                if (!isNaN(i)) {
                    _pendingAttachments.splice(i, 1);
                    _renderPendingAttachments();
                }
            });
        });
    }

    async function _uploadAttachmentFile(file) {
        if (!file || !_editingId) return;
        const fd = new FormData();
        fd.append('file', file);
        try {
            const res = await fetch(`${CHAT_API}/${_editingId}/upload-context`, {
                method: 'POST',
                body: fd
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            _pendingAttachments.push(data);
            _renderPendingAttachments();
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Attachment upload failed: ${err.message}`, 'error');
        }
    }

    async function _loadHistory(companionId, offsetDays = 0, prepend = false) {
        const msgsEl = document.getElementById('cc-chat-msgs');
        if (!msgsEl) return;
        const limitDays = 3;
        if (!prepend) {
            _chatHistory = [];
            _historyOffsetDays = 0;
            _pendingAttachments = [];
            _renderPendingAttachments();
            msgsEl.innerHTML = `
              <div class="cc-chat-hint" id="cc-chat-hint">
                <i class="fas fa-comment-dots"></i>
                <span>Start a conversation with <strong id="cc-chat-cname">${_activeData?.name || 'your companion'}</strong></span>
              </div>`;
        }
        try {
            const res  = await fetch(`${CHAT_API}/${companionId}/history?offset_days=${offsetDays}&limit_days=${limitDays}`);
            if (!res.ok) return;
            const data = await res.json();
            // Backend returns newest day first; reverse to chronological order
            const days = [...(data.history || [])].reverse();
            let loaded = 0;

            const prevScrollHeight = msgsEl.scrollHeight;
            document.getElementById('cc-load-older-wrap')?.remove();

            const frag = document.createDocumentFragment();
            const olderHistoryItems = [];

            for (const day of days) {
                const dayMsgs = day.messages || [];
                if (!dayMsgs.length) continue;
                const divEl = document.createElement('div');
                divEl.className = 'cc-chat-day-divider';
                divEl.innerHTML = `<span>${_esc(_formatDayDivider(day.date))}</span>`;
                frag.appendChild(divEl);

                let lastAssistantAttKey = '';
                let lastRole = null;
                for (const msg of dayMsgs) {
                    const roleKey = msg.role === 'user' ? 'user' : 'companion';
                    olderHistoryItems.push({ role: msg.role, content: msg.content });
                    let msgAtts = msg.attachments || null;
                    if (roleKey === 'companion' && Array.isArray(msgAtts) && msgAtts.length) {
                        const attKey = msgAtts.map(a => a.filename || a.url || '').join('|');
                        if (attKey && attKey === lastAssistantAttKey) {
                            msgAtts = null; // Deduplicate attachments across split <break> bubbles
                        } else {
                            lastAssistantAttKey = attKey;
                        }
                    } else if (roleKey === 'user') {
                        lastAssistantAttKey = '';
                    }
                    const isContinuation = (roleKey === lastRole);
                    lastRole = roleKey;
                    const b = _buildMessageNode(roleKey, msg.content, null, msgAtts, isContinuation);
                    frag.appendChild(b);
                    loaded++;
                }
            }

            if (prepend) {
                _chatHistory = [...olderHistoryItems, ..._chatHistory];
                msgsEl.insertBefore(frag, msgsEl.firstChild);
            } else {
                _chatHistory = olderHistoryItems;
                if (loaded > 0) {
                    document.getElementById('cc-chat-hint')?.remove();
                    msgsEl.appendChild(frag);
                }
            }

            _historyOffsetDays = offsetDays + (data.history || []).length;

            if (data.has_more) {
                const moreWrap = document.createElement('div');
                moreWrap.id = 'cc-load-older-wrap';
                moreWrap.className = 'cc-load-older-wrap';
                moreWrap.innerHTML = `
                  <button type="button" class="cc-btn cc-btn-ghost cc-btn-xs" id="cc-load-older-btn">
                    <i class="fas fa-clock-rotate-left"></i> Load earlier messages
                  </button>`;
                msgsEl.insertBefore(moreWrap, msgsEl.firstChild);
                moreWrap.querySelector('#cc-load-older-btn')?.addEventListener('click', () => {
                    _loadHistory(companionId, _historyOffsetDays, true);
                });
            }

            if (prepend) {
                msgsEl.scrollTop = msgsEl.scrollHeight - prevScrollHeight;
            } else if (loaded > 0) {
                msgsEl.scrollTop = msgsEl.scrollHeight;
            }
        } catch (err) {
            console.warn('[CompanionCreator] History load failed:', err);
        }
    }

    function _attachBubbleActions(bubble, rawText) {
        if (!bubble) return;
        bubble.dataset.rawText = rawText || '';
        let actions = bubble.querySelector('.cc-msg-actions');
        if (!actions) {
            actions = document.createElement('div');
            actions.className = 'cc-msg-actions';
            actions.innerHTML = `
              <button type="button" class="cc-msg-act-btn cc-msg-speak-btn" title="Listen to message (TTS)"><i class="fas fa-volume-high"></i></button>
              <button type="button" class="cc-msg-act-btn cc-msg-copy-btn" title="Copy message"><i class="fas fa-copy"></i></button>
              <button type="button" class="cc-msg-act-btn cc-msg-regen-btn" title="Regenerate reply"><i class="fas fa-rotate-right"></i></button>
            `;
            bubble.appendChild(actions);
            const speakBtn = actions.querySelector('.cc-msg-speak-btn');
            speakBtn?.addEventListener('click', () => {
                _speakText(bubble.dataset.rawText || '', null, speakBtn);
            });
            actions.querySelector('.cc-msg-copy-btn')?.addEventListener('click', () => {
                navigator.clipboard?.writeText(bubble.dataset.rawText || '');
                if (typeof showToast === 'function') showToast('Copied to clipboard', 'info');
            });
            actions.querySelector('.cc-msg-regen-btn')?.addEventListener('click', () => {
                _regenerateLastReply();
            });
        }
    }

    function _extractYoutubeIds(text) {
        if (!text) return [];
        const ids = [];
        const seen = new Set();
        const re = /(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:[^"\s<>]*&)?v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/gi;
        let m;
        while ((m = re.exec(text)) !== null) {
            const vid = m[1];
            if (vid && !seen.has(vid)) {
                seen.add(vid);
                ids.push(vid);
            }
        }
        return ids.slice(0, 3);
    }

    function _buildSingleYoutubeCardHtml(vid, title = '') {
        if (!vid || !/^[A-Za-z0-9_-]{11}$/.test(vid)) return '';
        const watchUrl = `https://www.youtube.com/watch?v=${vid}`;
        const thumbUrl = `https://i.ytimg.com/vi/${vid}/hqdefault.jpg`;
        const safeTitle = title && title !== 'YouTube Video' ? _esc(title) : 'YouTube Video';
        return `
          <div class="cc-yt-card" data-yt-id="${vid}">
            <div class="cc-yt-stage" onclick="window.__playAethvionYt && window.__playAethvionYt(this, '${vid}')">
              <img src="${thumbUrl}" alt="${safeTitle}" class="cc-yt-thumb" loading="lazy">
              <div class="cc-yt-play-overlay">
                <span class="cc-yt-play-btn"><i class="fas fa-play"></i></span>
                <span class="cc-yt-play-label">Play in Chat</span>
              </div>
            </div>
            <div class="cc-yt-footer">
              <span class="cc-yt-badge" title="${safeTitle}"><i class="fab fa-youtube"></i> ${safeTitle}</span>
              <div class="cc-yt-actions">
                <button type="button" class="cc-yt-action-btn" onclick="window.__playAethvionYt && window.__playAethvionYt(this.closest('.cc-yt-card').querySelector('.cc-yt-stage'), '${vid}')">
                  <i class="fas fa-circle-play"></i> Embed
                </button>
                <a href="${watchUrl}" target="_blank" rel="noopener noreferrer" class="cc-yt-action-btn cc-yt-open-link">
                  <i class="fas fa-arrow-up-right-from-square"></i> YouTube
                </a>
              </div>
            </div>
          </div>`;
    }

    window.__playAethvionYt = function(stageEl, videoId) {
        if (!stageEl || !/^[A-Za-z0-9_-]{11}$/.test(videoId)) return;
        stageEl.onclick = null;
        stageEl.classList.add('cc-yt-stage-playing');
        stageEl.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0" class="cc-yt-iframe" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>`;
    };

    window.__renderAethvionYoutubeCards = function(text, existingIds = null) {
        const ids = _extractYoutubeIds(text);
        const filtered = existingIds ? ids.filter(id => !existingIds.has(id)) : ids;
        if (existingIds) filtered.forEach(id => existingIds.add(id));
        const ytHtml = filtered.length
            ? `<div class="cc-yt-cards">${filtered.map(vid => _buildSingleYoutubeCardHtml(vid)).join('')}</div>`
            : '';
        const twHtml = typeof window.__renderAethvionTwitchCards === 'function'
            ? window.__renderAethvionTwitchCards(text, existingIds)
            : '';
        const spHtml = typeof window.__renderAethvionSpotifyCards === 'function'
            ? window.__renderAethvionSpotifyCards(text, existingIds)
            : '';
        return ytHtml + twHtml + spHtml;
    };

    // Twitch live channel / VOD cards with inline embedded player

    const _TWITCH_RESERVED = new Set([
        'directory', 'videos', 'p', 'settings', 'downloads', 'jobs', 'search', 'login', 'signup',
        'subscriptions', 'inventory', 'wallet', 'drops', 'turbo', 'prime', 'friends', 'messages',
        'payments', 'store', 'team', 'collections', 'clip', 'clips', 'popout', 'moderator', 'u'
    ]);

    function _extractTwitchTargets(text) {
        if (!text) return [];
        const out = [];
        const seen = new Set();
        const vodRe = /(?:https?:\/\/)?(?:www\.|m\.)?twitch\.tv\/videos\/(\d{6,12})/gi;
        let m;
        while ((m = vodRe.exec(text)) !== null) {
            const key = `v:${m[1]}`;
            if (!seen.has(key)) { seen.add(key); out.push({ kind: 'video', id: m[1] }); }
        }
        const chRe = /(?:https?:\/\/)?(?:www\.|m\.)?twitch\.tv\/([A-Za-z0-9_]{2,25})(?![A-Za-z0-9_\/])/gi;
        while ((m = chRe.exec(text)) !== null) {
            const login = m[1].toLowerCase();
            if (_TWITCH_RESERVED.has(login)) continue;
            const key = `c:${login}`;
            if (!seen.has(key)) { seen.add(key); out.push({ kind: 'channel', id: login }); }
        }
        return out.slice(0, 3);
    }

    function _buildSingleTwitchCardHtml(target, title = '', isLive = null) {
        if (!target || !target.id) return '';
        const isVod = target.kind === 'video';
        if (isVod ? !/^\d{6,12}$/.test(target.id) : !/^[a-z0-9_]{2,25}$/.test(target.id)) return '';
        const pageUrl = isVod ? `https://www.twitch.tv/videos/${target.id}` : `https://www.twitch.tv/${target.id}`;
        const label = _esc(title || (isVod ? `Twitch VOD ${target.id}` : target.id));
        const thumb = isVod
            ? ''
            : `<img src="https://static-cdn.jtvnw.net/previews-ttv/live_user_${target.id}-640x360.jpg?t=${Math.floor(Date.now() / 60000)}" alt="${label}" class="cc-yt-thumb" loading="lazy" onerror="this.style.display='none'">`;
        const liveBadge = isVod
            ? '<span class="cc-tw-status cc-tw-status-vod">VOD</span>'
            : (isLive === false
                ? '<span class="cc-tw-status cc-tw-status-off">OFFLINE</span>'
                : (isLive === true ? '<span class="cc-tw-status cc-tw-status-live">LIVE</span>' : ''));
        return `
          <div class="cc-yt-card cc-tw-card" data-tw-kind="${target.kind}" data-tw-id="${target.id}">
            <div class="cc-yt-stage cc-tw-stage" onclick="window.__playAethvionTwitch && window.__playAethvionTwitch(this, '${target.kind}', '${target.id}')">
              ${thumb}
              ${liveBadge}
              <div class="cc-yt-play-overlay">
                <span class="cc-yt-play-btn cc-tw-play-btn"><i class="fas fa-play"></i></span>
                <span class="cc-yt-play-label">${isVod ? 'Watch VOD in Chat' : 'Watch Live in Chat'}</span>
              </div>
            </div>
            <div class="cc-yt-footer">
              <span class="cc-yt-badge cc-tw-badge" title="${label}"><i class="fab fa-twitch"></i> ${label}</span>
              <div class="cc-yt-actions">
                <button type="button" class="cc-yt-action-btn cc-tw-action-btn" onclick="window.__playAethvionTwitch && window.__playAethvionTwitch(this.closest('.cc-tw-card').querySelector('.cc-tw-stage'), '${target.kind}', '${target.id}')">
                  <i class="fas fa-circle-play"></i> Embed
                </button>
                <a href="${pageUrl}" target="_blank" rel="noopener noreferrer" class="cc-yt-action-btn cc-tw-action-btn cc-yt-open-link">
                  <i class="fas fa-arrow-up-right-from-square"></i> Twitch
                </a>
              </div>
            </div>
          </div>`;
    }

    window.__playAethvionTwitch = function(stageEl, kind, id) {
        if (!stageEl) return;
        const isVod = kind === 'video';
        if (isVod ? !/^\d{6,12}$/.test(id) : !/^[a-z0-9_]{2,25}$/.test(id)) return;
        // Twitch embeds require the embedding page's hostname as `parent`
        const parent = encodeURIComponent(window.location.hostname || 'localhost');
        const src = isVod
            ? `https://player.twitch.tv/?video=v${id}&parent=${parent}&autoplay=true`
            : `https://player.twitch.tv/?channel=${id}&parent=${parent}&autoplay=true&muted=false`;
        stageEl.onclick = null;
        stageEl.classList.add('cc-yt-stage-playing');
        stageEl.innerHTML = `<iframe src="${src}" class="cc-yt-iframe" title="Twitch player" frameborder="0" allow="autoplay; fullscreen" allowfullscreen></iframe>`;
    };

    window.__renderAethvionTwitchCards = function(text, existingIds = null) {
        const targets = _extractTwitchTargets(text).filter(t => !(existingIds && existingIds.has(`tw:${t.kind}:${t.id}`)));
        if (!targets.length) return '';
        if (existingIds) targets.forEach(t => existingIds.add(`tw:${t.kind}:${t.id}`));
        return `<div class="cc-yt-cards">${targets.map(t => _buildSingleTwitchCardHtml(t)).join('')}</div>`;
    };

    window.__buildAethvionTwitchCard = function(att) {
        if (!att) return '';
        const target = att.video_id && /^\d+$/.test(att.video_id)
            ? { kind: 'video', id: String(att.video_id) }
            : { kind: 'channel', id: String(att.channel || '').toLowerCase() };
        const html = _buildSingleTwitchCardHtml(target, att.title || att.filename || '', typeof att.is_live === 'boolean' ? att.is_live : null);
        return html ? `<div class="cc-yt-cards">${html}</div>` : '';
    };

    // Spotify track / album / playlist / episode cards with inline embedded player
    function _extractSpotifyTargets(text) {
        if (!text) return [];
        const out = [];
        const seen = new Set();

        // 1. URLs: https://open.spotify.com/(track|album|playlist|episode|show)/([a-zA-Z0-9]+)
        const urlRe = /(?:https?:\/\/)?open\.spotify\.com\/(track|album|playlist|episode|show)\/([a-zA-Z0-9]+)/gi;
        let m;
        while ((m = urlRe.exec(text)) !== null) {
            const kind = m[1].toLowerCase();
            const id = m[2];
            const key = `sp:${kind}:${id}`;
            if (!seen.has(key)) { seen.add(key); out.push({ kind, id }); }
        }

        // 2. URIs: spotify:(track|album|playlist|episode|show):([a-zA-Z0-9]+)
        const uriRe = /spotify:(track|album|playlist|episode|show):([a-zA-Z0-9]+)/gi;
        while ((m = uriRe.exec(text)) !== null) {
            const kind = m[1].toLowerCase();
            const id = m[2];
            const key = `sp:${kind}:${id}`;
            if (!seen.has(key)) { seen.add(key); out.push({ kind, id }); }
        }

        return out.slice(0, 3);
    }

    function _buildSingleSpotifyCardHtml(target, title = '') {
        if (!target || !target.id || !target.kind) return '';
        if (!/^[a-zA-Z0-9]+$/.test(target.id)) return '';
        const kind = target.kind.toLowerCase();
        const id = target.id;
        const pageUrl = `https://open.spotify.com/${kind}/${id}`;
        const appUri = `spotify:${kind}:${id}`;
        const typeLabel = kind.charAt(0).toUpperCase() + kind.slice(1);
        const label = _esc(title || `Spotify ${typeLabel}`);
        const height = (kind === 'track') ? 152 : 352;

        return `
          <div class="cc-yt-card cc-sp-card" data-sp-kind="${kind}" data-sp-id="${id}">
            <div class="cc-sp-stage">
              <iframe
                src="https://open.spotify.com/embed/${kind}/${id}?utm_source=generator&theme=0"
                width="100%"
                height="${height}"
                frameBorder="0"
                allowfullscreen=""
                allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                loading="lazy"
                class="cc-sp-iframe"
                style="border-radius:12px;display:block;">
              </iframe>
            </div>
            <div class="cc-yt-footer cc-sp-footer">
              <span class="cc-yt-badge cc-sp-badge" title="${label}">
                <i class="fab fa-spotify" style="color:#1db954;"></i> ${label}
              </span>
              <div class="cc-yt-actions">
                <a href="${pageUrl}" target="_blank" rel="noopener noreferrer" class="cc-yt-action-btn cc-sp-action-btn cc-yt-open-link" title="Open in Spotify Web Player">
                  <i class="fas fa-arrow-up-right-from-square"></i> Web
                </a>
                <a href="${appUri}" class="cc-yt-action-btn cc-sp-action-btn" title="Open in Desktop Spotify App">
                  <i class="fab fa-spotify"></i> App
                </a>
              </div>
            </div>
          </div>`;
    }

    window.__renderAethvionSpotifyCards = function(text, existingIds = null) {
        const targets = _extractSpotifyTargets(text).filter(t => !(existingIds && existingIds.has(`sp:${t.kind}:${t.id}`)));
        if (!targets.length) return '';
        if (existingIds) targets.forEach(t => existingIds.add(`sp:${t.kind}:${t.id}`));
        return `<div class="cc-yt-cards cc-sp-cards">${targets.map(t => _buildSingleSpotifyCardHtml(t)).join('')}</div>`;
    };

    window.__buildAethvionSpotifyCard = function(att) {
        if (!att) return '';
        const raw = att.spotify_url || att.url || att.track_id || '';
        const targets = _extractSpotifyTargets(raw);
        if (!targets.length) return '';
        const html = _buildSingleSpotifyCardHtml(targets[0], att.title || '');
        return html ? `<div class="cc-yt-cards cc-sp-cards">${html}</div>` : '';
    };

    function _renderAttachmentsBlock(attachments, textForYtDedup = '') {
        if (!Array.isArray(attachments) || !attachments.length) return '';
        const seen = new Set();
        const textYtIds = new Set(_extractYoutubeIds(textForYtDedup));
        const items = attachments.map(att => {
            const rawUrl = String(att.url || '').replace(/\\/g, '/');
            const fname = att.filename || att.title || att.type || 'Attachment';
            const dedupKey = (att.video_id || fname) + '|' + rawUrl;
            if (seen.has(dedupKey)) return '';
            seen.add(dedupKey);
            if (att.type === 'spotify' || att.spotify_url || att.track_id) {
                const spCard = window.__buildAethvionSpotifyCard(att);
                if (spCard) return spCard;
            }
            if (att.type === 'twitch') {
                const ch = String(att.channel || '').toLowerCase();
                if (!ch || _extractTwitchTargets(textForYtDedup).some(t => t.id === ch)) return '';
                return _buildSingleTwitchCardHtml({ kind: 'channel', id: ch }, att.title || att.filename || ch, typeof att.is_live === 'boolean' ? att.is_live : null);
            }
            if (att.type === 'youtube' || att.video_id) {
                const vid = att.video_id || (_extractYoutubeIds(rawUrl)[0] || '');
                if (!vid || textYtIds.has(vid)) return '';
                textYtIds.add(vid);
                return _buildSingleYoutubeCardHtml(vid, att.title || att.filename || 'YouTube Recommendation');
            }
            const isImg = att.is_image || att.type === 'screenshot' || att.type === 'webcam' || /\.(png|jpe?g|gif|webp)$/i.test(rawUrl);
            if (isImg && rawUrl) {
                return `<img src="${_esc(rawUrl)}" alt="${_esc(fname)}" class="cc-msg-attachment-img" onclick="window.open(this.src,'_blank')">`;
            }
            return `<a href="${_esc(rawUrl || '#')}" target="_blank" class="cc-msg-attachment-file"><i class="fas fa-file-lines"></i> ${_esc(fname)}</a>`;
        }).filter(Boolean).join('');
        return items ? `<div class="cc-msg-attachments">${items}</div>` : '';
    }

    function _renderMsgAvatar() {
        const color  = _activeData?.accent_color || '#6366f1';
        const symbol = _activeData?.avatar_symbol || '✦';
        const name   = _esc(_activeData?.name || 'Companion');
        const cId    = _activeData?.id || _editingId;
        if (_activeData?.has_icon && cId) {
            return `<div class="cc-msg-avatar" style="border-color:${color}55;box-shadow:0 3px 12px ${color}28" title="${name}">
              <img class="cc-msg-avatar-img" src="${API}/${cId}/icon" alt="${name}" onerror="this.onerror=null;this.parentElement.innerHTML='<span style=\\'color:${color}\\'>${symbol}</span>';">
            </div>`;
        }
        return `<div class="cc-msg-avatar" style="background:${color}22;color:${color};border-color:${color}44;box-shadow:0 3px 12px ${color}1c" title="${name}">${symbol}</div>`;
    }

    function _buildMessageNode(role, text, id = null, attachments = null, isContinuation = false) {
        const bubble = document.createElement('div');
        bubble.className = `cc-msg cc-msg-${role}${isContinuation ? ' cc-msg-continuation' : ''}`;
        if (id) bubble.id = id;
        const attHtml = _renderAttachmentsBlock(attachments, text);
        if (role === 'companion') {
            bubble.innerHTML = `
              ${_renderMsgAvatar()}
              <div class="cc-msg-bubble cc-msg-md">${_renderMd(text, true)}${attHtml}</div>`;
            _applyHighlight(bubble);
            _attachBubbleActions(bubble, text);
        } else {
            bubble.innerHTML = `<div class="cc-msg-bubble">${_escHtml(text)}${attHtml}</div>`;
        }
        return bubble;
    }

    function _appendMessage(role, text, id = null, attachments = null, isContinuation = null) {
        const msgsEl = document.getElementById('cc-chat-msgs');
        if (!msgsEl) return null;
        if (isContinuation === null) {
            const lastMsg = msgsEl.querySelector('.cc-msg:last-of-type');
            isContinuation = Boolean(lastMsg && lastMsg.classList.contains(`cc-msg-${role}`));
        }
        const bubble = _buildMessageNode(role, text, id, attachments, isContinuation);
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

    // Render companion text as markdown (marked + optional hljs highlight + optional YouTube embeds)
    function _renderMd(text, includeEmbeds = false) {
        if (!text) return '';
        let html = '';
        if (typeof marked !== 'undefined' && marked.parse) {
            try { html = marked.parse(text); } catch { html = _escHtml(text); }
        } else {
            html = _escHtml(text);
        }
        if (includeEmbeds && typeof window.__renderAethvionYoutubeCards === 'function') {
            html += window.__renderAethvionYoutubeCards(text);
        }
        return html;
    }

    // Run hljs on any code blocks inside a container element
    function _applyHighlight(container) {
        if (typeof hljs === 'undefined' || !container) return;
        container.querySelectorAll('pre code:not([data-highlighted])').forEach(
            block => hljs.highlightElement(block)
        );
    }

    function _setPortraitThinking(thinking, label = 'Thinking…') {
        const statusEl = document.getElementById('cc-portrait-status');
        const textEl   = document.getElementById('cc-portrait-status-text');
        if (!statusEl) return;
        if (thinking) {
            if (textEl) textEl.textContent = label;
            statusEl.classList.remove('hidden');
        } else {
            statusEl.classList.add('hidden');
        }
    }

    function _updatePortraitMoodAndExpr(mood, expression) {
        const moodTextEl = document.getElementById('cc-portrait-mood-text');
        const exprTextEl = document.getElementById('cc-portrait-expr-text');
        if (mood && moodTextEl) moodTextEl.textContent = mood;
        if (expression && exprTextEl) exprTextEl.textContent = expression;
        if (expression) _updatePortraitExpression(expression);
    }

    async function _sendMessage(overrideMessage = null) {
        if (_chatStreaming) return;
        const input = document.getElementById('cc-chat-input');
        let message = overrideMessage !== null ? overrideMessage : (input?.value || '').trim();
        if (!message && _pendingAttachments.length) {
            message = `Attached: ${_pendingAttachments.map(a => a.filename).join(', ')}`;
        }
        if (!message || !_editingId) return;

        const sentAttachments = overrideMessage === null ? [..._pendingAttachments] : [];
        if (overrideMessage === null) {
            _pendingAttachments = [];
            _renderPendingAttachments();
        }

        if (overrideMessage === null && input) {
            input.value = '';
            _autoResizeInput(input);
            // Remove the "start chatting" hint
            document.getElementById('cc-chat-hint')?.remove();
            // Push user message
            _appendMessage('user', message, null, sentAttachments);
            _chatHistory.push({ role: 'user', content: message });
        }

        // Streaming lock + disable UI
        _chatStreaming = true;
        _setPortraitThinking(true, 'Thinking…');
        const sendBtn = document.getElementById('cc-chat-send');
        if (input)   input.disabled   = true;
        if (sendBtn) sendBtn.disabled = true;

        // Create companion bubble (streaming placeholder)
        const color  = _activeData?.accent_color || '#6366f1';
        const symbol = _activeData?.avatar_symbol || '✦';
        const msgsEl = document.getElementById('cc-chat-msgs');

        function _makeBubble(streaming = true, isContinuation = false) {
            const b = document.createElement('div');
            b.className = `cc-msg cc-msg-companion${isContinuation ? ' cc-msg-continuation' : ''}`;
            b.innerHTML = `
              ${_renderMsgAvatar()}
              <div class="cc-msg-bubble cc-msg-md${streaming ? ' cc-msg-streaming' : ''}">…</div>`;
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

        let activeBubbles     = [];
        let currentBubble     = _makeBubble(true);
        let currentBubbleText = currentBubble.querySelector('.cc-msg-bubble');
        activeBubbles.push(currentBubble);
        let toolIndicator     = null;
        let rafId             = null;
        let pendingTextToRender = '';

        function renderStreamText(text) {
            pendingTextToRender = text;
            if (!rafId) {
                rafId = requestAnimationFrame(() => {
                    rafId = null;
                    if (!currentBubbleText) return;
                    const stripped = _stripToolTags(pendingTextToRender);
                    if (stripped) {
                        currentBubbleText.innerHTML = _renderMd(stripped) + '<span class="cc-streaming-cursor"></span>';
                        currentBubbleText.classList.remove('cc-msg-streaming');
                    }
                    if (msgsEl) {
                        const isNearBottom = (msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight) < 160;
                        if (isNearBottom) msgsEl.scrollTop = msgsEl.scrollHeight;
                    }
                });
            }
        }

        function flushStreamRender(finalPartText = null) {
            if (rafId) {
                cancelAnimationFrame(rafId);
                rafId = null;
            }
            if (!currentBubbleText) return;
            const textToFlush = finalPartText !== null ? finalPartText : pendingTextToRender;
            const stripped = _stripToolTags(textToFlush);
            if (stripped) {
                currentBubbleText.innerHTML = _renderMd(stripped);
            }
            currentBubbleText.classList.remove('cc-msg-streaming');
            const cur = currentBubbleText.querySelector('.cc-streaming-cursor');
            if (cur) cur.remove();
        }

        const histForApi = _chatHistory.slice(0, -1).map(m => ({ role: m.role, content: m.content }));

        try {
            const res = await fetch(`${CHAT_API}/${_editingId}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message,
                    history: histForApi,
                    attachments: sentAttachments.length ? sentAttachments : undefined
                })
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
                            const splitParts = fullText.split(/<break\s*\/?>/i);
                            if (splitParts.length > activeBubbles.length && activeBubbles.length < 3) {
                                // Finalize the previous bubble with clean text
                                flushStreamRender(splitParts[activeBubbles.length - 1]);
                                if (currentBubble) {
                                    _applyHighlight(currentBubble);
                                }
                                // Start next bubble smoothly
                                currentBubble = _makeBubble(true, true);
                                currentBubbleText = currentBubble.querySelector('.cc-msg-bubble');
                                activeBubbles.push(currentBubble);
                            }

                            const activePartIndex = activeBubbles.length - 1;
                            const currentPartContent = (activePartIndex === 2 && splitParts.length > 3)
                                ? splitParts.slice(2).join('\n\n')
                                : (splitParts[activePartIndex] || '');
                            renderStreamText(currentPartContent);

                        } else if (evt.type === 'tool_start') {
                            _setPortraitThinking(true, `Using ${evt.tool || 'tool'}…`);
                            if (evt.tool === 'scratchpad') {
                                const spadTab = document.getElementById('cc-ptab-scratchpad');
                                if (spadTab) {
                                    spadTab.classList.add('cc-ptab-pulse');
                                    setTimeout(() => spadTab.classList.remove('cc-ptab-pulse'), 3000);
                                }
                            } else if (evt.tool === 'visual_memory') {
                                const vTab = document.getElementById('cc-ptab-vision');
                                if (vTab) {
                                    vTab.classList.add('cc-ptab-pulse');
                                    setTimeout(() => vTab.classList.remove('cc-ptab-pulse'), 3000);
                                }
                            }
                            flushStreamRender();
                            const cleanedFirst = _stripToolTags(fullText);
                            if (currentBubbleText) {
                                currentBubbleText.classList.add('cc-msg-md');
                                currentBubbleText.classList.remove('cc-msg-streaming');
                                currentBubbleText.innerHTML = cleanedFirst ? _renderMd(cleanedFirst) : '';
                            }
                            _applyHighlight(currentBubble);
                            _attachBubbleActions(currentBubble, cleanedFirst);
                            if (cleanedFirst && !currentBubble._recordedInHistory) {
                                currentBubble._recordedInHistory = true;
                                _chatHistory.push({ role: 'assistant', content: cleanedFirst });
                            }
                            toolIndicator = _makeToolIndicator(evt.tool || 'tool');

                        } else if (evt.type === 'tool_response_start') {
                            _setPortraitThinking(true, 'Replying…');
                            toolIndicator?.remove();
                            toolIndicator = null;
                            fullText = '';
                            activeBubbles     = [];
                            currentBubble     = _makeBubble(true);
                            currentBubbleText = currentBubble.querySelector('.cc-msg-bubble');
                            activeBubbles.push(currentBubble);

                        } else if (evt.type === 'final_cleaned' && evt.content) {
                            finalText = evt.content;

                        } else if (evt.type === 'error' && (evt.message || evt.content)) {
                            flushStreamRender();
                            finalText = evt.message || evt.content;
                            if (currentBubbleText) {
                                currentBubbleText.textContent = finalText;
                                currentBubbleText.classList.add('cc-msg-error-text');
                                currentBubbleText.classList.remove('cc-msg-streaming');
                            }

                        } else if (evt.type === 'done') {
                            if (evt.content)  finalText  = evt.content;
                            if (evt.parts)    finalParts = evt.parts;
                            if (Array.isArray(evt.attachments) && evt.attachments.length && currentBubble) {
                                currentBubble._doneAttachments = evt.attachments;
                            }
                            _updatePortraitMoodAndExpr(evt.mood, evt.expression);
                            if (evt.memory_updated) {
                                const memTab = document.getElementById('cc-ptab-memory');
                                if (memTab) {
                                    memTab.classList.add('cc-ptab-pulse');
                                    setTimeout(() => memTab.classList.remove('cc-ptab-pulse'), 2500);
                                }
                                if (typeof showToast === 'function') showToast(`${_activeData?.name || 'Companion'} remembered that`, 'info');
                            }
                            if (!document.getElementById('cc-scratchpad-view')?.classList.contains('hidden') && _editingId) {
                                _loadScratchpad(_editingId);
                            }
                            if (!document.getElementById('cc-vision-view')?.classList.contains('hidden') && _editingId) {
                                _loadVisualMemory(_editingId);
                            }
                        }
                    } catch { /* non-JSON chunk */ }
                }
                if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
            }

            flushStreamRender();

            // finalText from server is already cleaned; fullText is the raw stream fallback.
            const primaryText = finalText || _stripToolTags(fullText) || '(no response)';
            const rawSplit    = fullText.split(/<break\s*\/?>/i).map(p => _stripToolTags(p)).filter(Boolean);
            const parts       = (finalParts && finalParts.length) ? finalParts : (rawSplit.length > 1 ? rawSplit.slice(0, 3) : [primaryText]);

            // Finalize each active bubble in place without sudden layout shift or collapsing
            for (let i = 0; i < activeBubbles.length; i++) {
                const b = activeBubbles[i];
                const bText = b.querySelector('.cc-msg-bubble');
                const partContent = parts[i] || (i === 0 ? primaryText : '');
                if (bText && partContent) {
                    bText.classList.add('cc-msg-md');
                    bText.classList.remove('cc-msg-streaming');
                    const attHtml = (i === 0) ? _renderAttachmentsBlock(b?._doneAttachments || null, primaryText) : '';
                    bText.innerHTML = `${_renderMd(partContent, true)}${attHtml}`;
                }
                _applyHighlight(b);
                _attachBubbleActions(b, partContent);
                _chatHistory.push({ role: 'assistant', content: partContent });
            }

            // If backend produced more parts than activeBubbles, append them cleanly
            if (parts.length > activeBubbles.length) {
                for (let i = activeBubbles.length; i < parts.length; i++) {
                    const nb = _appendMessage('companion', parts[i], null, null, true);
                    if (nb) _applyHighlight(nb);
                    _chatHistory.push({ role: 'assistant', content: parts[i] });
                }
            }

            if (_activeData?.voice?.auto_speak) {
                const fullSpoken = parts.join(' ');
                _speakText(fullSpoken);
            }

        } catch (err) {
            flushStreamRender();
            if (currentBubbleText) { currentBubbleText.textContent = 'Failed to get a response.'; currentBubbleText.classList.add('cc-msg-error-text'); }
        } finally {
            if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
            _chatStreaming = false;
            _setPortraitThinking(false);
            if (input)   { input.disabled   = false; input.focus(); }
            if (sendBtn)   sendBtn.disabled  = false;
            if (msgsEl)    msgsEl.scrollTop  = msgsEl.scrollHeight;
        }
    }

    function _regenerateLastReply() {
        if (_chatStreaming || !_editingId || !_chatHistory.length) return;
        // Pop trailing assistant messages until the last user message
        const msgsEl = document.getElementById('cc-chat-msgs');
        while (_chatHistory.length && _chatHistory[_chatHistory.length - 1].role !== 'user') {
            _chatHistory.pop();
            const lastBubble = msgsEl?.querySelector('.cc-msg-companion:last-of-type');
            if (lastBubble) lastBubble.remove();
        }
        const lastUser = _chatHistory[_chatHistory.length - 1];
        if (!lastUser || lastUser.role !== 'user') return;
        _sendMessage(lastUser.content);
    }

    async function _triggerCheckin() {
        if (_chatStreaming || !_editingId) return;
        const btn = document.getElementById('cc-checkin-btn');
        if (btn) btn.disabled = true;
        _setPortraitThinking(true, 'Checking in…');
        try {
            const res = await fetch(`${CHAT_API}/${_editingId}/initiate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trigger: 'proactive' })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            if (data.response) {
                document.getElementById('cc-chat-hint')?.remove();
                _appendMessage('companion', data.response);
                _chatHistory.push({ role: 'assistant', content: data.response });
                _updatePortraitMoodAndExpr(data.mood, data.expression);
                if (_activeData?.voice?.auto_speak) {
                    _speakText(data.response);
                }
            }
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Check-in failed: ${err.message}`, 'error');
        } finally {
            _setPortraitThinking(false);
            if (btn) btn.disabled = false;
        }
    }

    function _exportChatTranscript() {
        if (!_editingId || !_chatHistory.length) {
            if (typeof showToast === 'function') showToast('No conversation messages to export yet.', 'info');
            return;
        }
        const cName = _activeData?.name || _editingId;
        const lines = [
            `# Conversation with ${cName}`,
            `Exported from Aethvion Suite on ${new Date().toLocaleString()}`,
            ''
        ];
        for (const msg of _chatHistory) {
            const speaker = msg.role === 'user' ? '**You**' : `**${cName}**`;
            lines.push(`${speaker}:\n${msg.content}\n`);
        }
        const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = `${_editingId}_chat_${new Date().toISOString().slice(0, 10)}.md`;
        a.click();
        URL.revokeObjectURL(url);
    }

    async function _clearChatHistoryOnly() {
        if (!_editingId) return;
        if (!confirm(`Clear chat messages with ${_activeData?.name || 'this companion'}? Long-term memory will be kept intact.`)) return;
        try {
            const res = await fetch(`${CHAT_API}/${_editingId}/history/clear`, { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            await _loadHistory(_editingId);
            if (typeof showToast === 'function') showToast('Chat messages cleared (memory preserved).', 'success');
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Failed to clear chat: ${err.message}`, 'error');
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

    // Expression images

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

    // Init

    function init() {
        _root = document.getElementById('companion-creator-root');
        if (!_root || _root.dataset.ccInit) return;
        _root.dataset.ccInit = '1';

        _renderShell();

        // Restore collapsed roster state
        if (localStorage.getItem('cc_roster_collapsed') === '1') {
            document.getElementById('cc-hub')?.classList.add('roster-collapsed');
            const icon = document.querySelector('#cc-roster-toggle i');
            if (icon) icon.className = 'fas fa-chevron-right';
        }

        // Load list, then restore last selected companion
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
        document.getElementById('cc-new-group-btn')?.addEventListener('click', _openNewGroupModal);

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

        // Chat / Scratchpad / Memory / Settings tab buttons
        document.getElementById('cc-ptab-chat')      ?.addEventListener('click', () => _switchView('chat'));
        document.getElementById('cc-ptab-scratchpad')?.addEventListener('click', () => _switchView('scratchpad'));
        document.getElementById('cc-ptab-memory')    ?.addEventListener('click', () => _switchView('memory'));
        document.getElementById('cc-ptab-settings')  ?.addEventListener('click', () => _switchView('settings'));

        // Quick Model & Connector Profile switcher in header
        document.getElementById('cc-pane-model-badge')?.addEventListener('click', _toggleQuickSwitchPopover);
        document.getElementById('cc-pane-profile-badge')?.addEventListener('click', _toggleQuickSwitchPopover);
        document.getElementById('cc-quick-model-select')?.addEventListener('change', e => {
            _saveQuickHeaderConfig({ default_model: e.target.value });
        });
        document.getElementById('cc-quick-profile-select')?.addEventListener('change', e => {
            _saveQuickHeaderConfig({ connector_profile: e.target.value });
        });
        document.addEventListener('mousedown', e => {
            const pop = document.getElementById('cc-quick-switch-popover');
            if (!pop || pop.classList.contains('hidden')) return;
            if (!pop.contains(e.target) &&
                !e.target.closest('#cc-pane-model-badge') &&
                !e.target.closest('#cc-pane-profile-badge')) {
                pop.classList.add('hidden');
            }
        });

        // Starter Persona Templates (New Companion)
        document.querySelectorAll('.cc-starter-card').forEach(btn => {
            btn.addEventListener('click', () => {
                _applyStarterTemplate(btn.dataset.template);
            });
        });

        // Chat attachments: + button, drag-and-drop, and clipboard image paste
        const attachBtn = document.getElementById('cc-chat-attach-btn');
        const fileInput = document.getElementById('cc-chat-file-input');
        attachBtn?.addEventListener('click', () => fileInput?.click());
        fileInput?.addEventListener('change', async e => {
            const files = Array.from(e.target.files || []);
            e.target.value = '';
            for (const f of files) {
                await _uploadAttachmentFile(f);
            }
        });
        const chatViewEl = document.getElementById('cc-chat-view');
        chatViewEl?.addEventListener('dragover', e => {
            e.preventDefault();
            chatViewEl.classList.add('cc-chat-dragover');
        });
        chatViewEl?.addEventListener('dragleave', () => {
            chatViewEl.classList.remove('cc-chat-dragover');
        });
        chatViewEl?.addEventListener('drop', async e => {
            e.preventDefault();
            chatViewEl.classList.remove('cc-chat-dragover');
            const files = Array.from(e.dataTransfer?.files || []);
            for (const f of files) {
                await _uploadAttachmentFile(f);
            }
        });
        document.getElementById('cc-chat-input')?.addEventListener('paste', async e => {
            const items = Array.from(e.clipboardData?.items || []);
            for (const item of items) {
                if (item.kind === 'file') {
                    const file = item.getAsFile();
                    if (file) await _uploadAttachmentFile(file);
                }
            }
        });

        // Chat input: auto-resize + Enter to send
        document.getElementById('cc-chat-input')?.addEventListener('input', e => _autoResizeInput(e.target));
        document.getElementById('cc-chat-input')?.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _sendMessage(); }
        });
        document.getElementById('cc-chat-send')?.addEventListener('click', () => _sendMessage());
        document.getElementById('cc-chat-mic')?.addEventListener('click', _toggleMicDictation);
        document.getElementById('cc-chat-slash-btn')?.addEventListener('click', () => _toggleSlashPopover());
        document.getElementById('cc-slash-manage-link')?.addEventListener('click', () => {
            document.getElementById('cc-slash-popover')?.classList.add('hidden');
            if (typeof window.switchMainTab === 'function') window.switchMainTab('connectors');
        });
        document.getElementById('cc-open-voice-library-btn')?.addEventListener('click', () => {
            if (typeof window.switchMainTab === 'function') window.switchMainTab('voice-library');
        });
        document.getElementById('cc-open-connectors-btn')?.addEventListener('click', () => {
            if (typeof window.switchMainTab === 'function') window.switchMainTab('connectors');
        });
        // Global AethvionSlashAutocomplete handles '/' typing automatically
        _startProactiveHeartbeat();
        document.getElementById('cc-auto-voice-btn')?.addEventListener('click', _toggleAutoVoice);
        document.getElementById('cc-checkin-btn')?.addEventListener('click', _triggerCheckin);
        document.getElementById('cc-export-chat-btn')?.addEventListener('click', _exportChatTranscript);
        document.getElementById('cc-clear-chat-btn')?.addEventListener('click', _clearChatHistoryOnly);
        _initScratchpadListeners();
        _initVisualMemoryListeners();
        _initCompanionScrollToBottom();

        // Live sync with Global Companion Presence floating popups & background check-ins
        window.addEventListener('companionProactiveMessage', e => {
            const d = e.detail;
            if (!d || d.companion_id !== _editingId) return;
            document.getElementById('cc-chat-hint')?.remove();
            _appendMessage('companion', d.response);
            _chatHistory.push({ role: 'assistant', content: d.response });
            _updatePortraitMoodAndExpr(d.mood, d.expression);
        });
        window.addEventListener('companionPopupConversationUpdated', e => {
            const d = e.detail;
            if (!d || d.companionId !== _editingId) return;
            document.getElementById('cc-chat-hint')?.remove();
            if (d.userMessage) {
                _appendMessage('user', d.userMessage);
                _chatHistory.push({ role: 'user', content: d.userMessage });
            }
            if (d.assistantMessage) {
                _appendMessage('companion', d.assistantMessage);
                _chatHistory.push({ role: 'assistant', content: d.assistantMessage });
            }
        });

        // Voice & Speech settings controls
        document.getElementById('cc-voice-model')?.addEventListener('change', e => {
            _populateVoiceDropdown(e.target.value);
        });
        document.getElementById('cc-voice-speed')?.addEventListener('input', _updateRangeDisplays);
        document.getElementById('cc-voice-autospeak')?.addEventListener('change', e => {
            if (_activeData) {
                if (!_activeData.voice) _activeData.voice = {};
                _activeData.voice.auto_speak = e.target.checked;
            }
            _updateAutoVoiceBtnUI(e.target.checked);
        });
        document.getElementById('cc-voice-preview-btn')?.addEventListener('click', () => {
            const cName = document.getElementById('cc-name')?.value?.trim() || _activeData?.name || 'your companion';
            const sample = `Hello! I am ${cName}. My voice is connected and ready.`;
            const cfg = {
                model_id: document.getElementById('cc-voice-model')?.value || 'kokoro',
                voice_id: document.getElementById('cc-voice-id')?.value    || 'af_heart',
                speed:    parseFloat(document.getElementById('cc-voice-speed')?.value || '1.0'),
                language: 'en'
            };
            _speakText(sample, cfg);
        });
        document.getElementById('cc-voice-save-preset-btn')?.addEventListener('click', () => {
            const presetForm = document.getElementById('cc-voice-preset-form');
            const nameInput  = document.getElementById('cc-voice-preset-name');
            if (!presetForm) return;
            presetForm.classList.remove('hidden');
            if (nameInput) {
                const cName = document.getElementById('cc-name')?.value?.trim() || _activeData?.name || 'Custom';
                nameInput.value = `${cName} Voice Preset`;
                nameInput.focus();
            }
        });
        document.getElementById('cc-voice-preset-cancel')?.addEventListener('click', () => {
            document.getElementById('cc-voice-preset-form')?.classList.add('hidden');
        });
        document.getElementById('cc-voice-preset-confirm')?.addEventListener('click', async () => {
            const nameInput = document.getElementById('cc-voice-preset-name');
            const name = nameInput?.value?.trim();
            if (!name) return;
            const model_id = document.getElementById('cc-voice-model')?.value || 'kokoro';
            const voice_id = document.getElementById('cc-voice-id')?.value    || 'af_heart';
            const speed    = parseFloat(document.getElementById('cc-voice-speed')?.value || '1.0');
            try {
                const res = await fetch('/api/audio/local/library/presets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name,
                        model_id: model_id === 'preset' ? 'kokoro' : model_id,
                        voice_id,
                        speed,
                        language: 'en',
                        gender: 'neutral',
                        description: `Saved from Companion Creator (${name})`
                    })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
                await _loadVoiceLibrary(true);
                document.getElementById('cc-voice-preset-form')?.classList.add('hidden');
                if (typeof showToast === 'function') showToast(`Saved '${name}' to Global Voice Database!`, 'success');
            } catch (err) {
                if (typeof showToast === 'function') showToast(`Failed to save preset: ${err.message}`, 'error');
            }
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

    // Behaviour settings (prefs-backed, auto-save)

    /** Maps companionId → event prefix used by mode files (e.g. 'misaka', 'axiom') */
    function _evtPrefix(companionId) {
        return companionId === 'misakacipher' ? 'misaka' : companionId;
    }

    /** Read a value from window.prefs, falling back to defaultVal. */
    function _prefGet(key, defaultVal) {
        return window.prefs?.get?.(key, defaultVal) ?? defaultVal;
    }

    /** Save a value to window.prefs and persist. */
    async function _prefSet(key, val) {
        if (window.prefs?.set) window.prefs.set(key, val);
        if (typeof savePreference === 'function') await savePreference(key, val);
    }

    /**
     * Fill the Runtime Behaviour, Proactive Messages, and Workspace sections
     * with values from prefs for the given companion.
     */
    function _loadBehaviourSettings(companionId) {
        const pfx         = companionId;
        const isMisaka    = companionId === 'misakacipher';
        const defaultCtx  = isMisaka ? 6 : 8;

        const _set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        const _chk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
        const _dsp = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        // Runtime Behaviour
        const speed = _prefGet(`${pfx}.typing_speed`, 75);
        _set('cc-typing-speed', speed);
        _dsp('cc-typing-speed-val', speed);

        const ctx = _prefGet(`${pfx}.context_limit`, defaultCtx);
        _set('cc-context-limit', ctx);
        _dsp('cc-context-limit-val', ctx);

        _chk('cc-rt-hide-character',  _prefGet(`${pfx}.hide_character`,      false));
        _chk('cc-rt-proactive-tools', _prefGet(`${pfx}.allow_proactive_tools`, false));

        // Proactive Messages
        _chk('cc-proactive-enabled', _prefGet(`${pfx}.proactive_enabled`, isMisaka));
        _chk('cc-proactive-popup',   _prefGet(`${pfx}.proactive_popup`, true));

        const proactiveRanges = [
            ['cc-startup-hours',        `${pfx}.startup_trigger_hours`, 'cc-startup-hours-val',        4],
            ['cc-startup-chance',       `${pfx}.startup_chance`,        'cc-startup-chance-val',       75],
            ['cc-startup-delay-min',    `${pfx}.startup_delay_min`,     'cc-startup-delay-min-val',    10],
            ['cc-startup-delay-max',    `${pfx}.startup_delay_max`,     'cc-startup-delay-max-val',    45],
            ['cc-session-interval-min', `${pfx}.session_interval_min`,  'cc-session-interval-min-val', 45],
            ['cc-session-interval-max', `${pfx}.session_interval_max`,  'cc-session-interval-max-val', 90],
            ['cc-session-chance',       `${pfx}.session_chance`,        'cc-session-chance-val',       60],
        ];
        proactiveRanges.forEach(([inputId, prefKey, valId, def]) => {
            const v = _prefGet(prefKey, def);
            _set(inputId, v);
            _dsp(valId, v);
        });

        // Update the danger zone companion name
        const dangerName = document.getElementById('cc-danger-companion-name');
        if (dangerName && _activeData) dangerName.textContent = _activeData.name;

        // Load workspaces from the API
        _loadCompanionWorkspaces(companionId);
    }

    /** AbortController for the current companion's auto-save listeners. */
    let _behaviourCtrl = null;

    /**
     * Wire auto-save listeners for all Runtime Behaviour and Proactive Message
     * inputs. Aborts previous companion's listeners before re-wiring.
     */
    function _wireBehaviourSettings(companionId) {
        if (_behaviourCtrl) _behaviourCtrl.abort();
        _behaviourCtrl = new AbortController();
        const { signal } = _behaviourCtrl;
        const pfx        = companionId;
        const evtPfx     = _evtPrefix(companionId);

        function _autoRange(inputId, valId, prefKey, eventKey) {
            const input = document.getElementById(inputId);
            const disp  = document.getElementById(valId);
            if (!input) return;
            input.addEventListener('input', async () => {
                const v = parseFloat(input.value);
                if (disp) disp.textContent = v;
                await _prefSet(prefKey, v);
                window.dispatchEvent(new CustomEvent(`${evtPfx}SettingsUpdated`, { detail: { [eventKey]: v } }));
            }, { signal });
        }

        function _autoToggle(inputId, prefKey, eventKey) {
            const el = document.getElementById(inputId);
            if (!el) return;
            el.addEventListener('change', async () => {
                const v = el.checked;
                await _prefSet(prefKey, v);
                window.dispatchEvent(new CustomEvent(`${evtPfx}SettingsUpdated`, { detail: { [eventKey]: v } }));
            }, { signal });
        }

        // Runtime Behaviour
        _autoRange  ('cc-typing-speed',    'cc-typing-speed-val',    `${pfx}.typing_speed`,       'typing_speed');
        _autoRange  ('cc-context-limit',   'cc-context-limit-val',   `${pfx}.context_limit`,      'context_limit');
        _autoToggle ('cc-rt-hide-character',  `${pfx}.hide_character`,       'hide_character');
        _autoToggle ('cc-rt-proactive-tools', `${pfx}.allow_proactive_tools`, 'allow_proactive_tools');

        // Proactive Messages
        _autoToggle ('cc-proactive-enabled', `${pfx}.proactive_enabled`,    'proactive_enabled');
        _autoToggle ('cc-proactive-popup',   `${pfx}.proactive_popup`,      'proactive_popup');
        _autoRange  ('cc-startup-hours',        'cc-startup-hours-val',        `${pfx}.startup_trigger_hours`, 'startup_trigger_hours');
        _autoRange  ('cc-startup-chance',       'cc-startup-chance-val',       `${pfx}.startup_chance`,        'startup_chance');
        _autoRange  ('cc-startup-delay-min',    'cc-startup-delay-min-val',    `${pfx}.startup_delay_min`,     'startup_delay_min');
        _autoRange  ('cc-startup-delay-max',    'cc-startup-delay-max-val',    `${pfx}.startup_delay_max`,     'startup_delay_max');
        _autoRange  ('cc-session-interval-min', 'cc-session-interval-min-val', `${pfx}.session_interval_min`,  'session_interval_min');
        _autoRange  ('cc-session-interval-max', 'cc-session-interval-max-val', `${pfx}.session_interval_max`,  'session_interval_max');
        _autoRange  ('cc-session-chance',       'cc-session-chance-val',       `${pfx}.session_chance`,        'session_chance');

        // Workspace add button
        document.getElementById('cc-ws-add-btn')?.addEventListener('click',
            () => _addCompanionWorkspace(companionId), { signal });

        // Reset button — show danger zone for existing companions only
        const dangerZone = document.getElementById('cc-danger-zone');
        if (dangerZone) dangerZone.style.display = _editingId ? '' : 'none';
        document.getElementById('cc-reset-companion-btn')?.addEventListener('click',
            () => _resetCompanion(companionId), { signal });
    }

    // Workspace management

    async function _loadCompanionWorkspaces(companionId) {
        try {
            const res = await fetch(`/api/companions/${companionId}/workspaces`);
            if (!res.ok) return;
            const data = await res.json();
            _renderCompanionWorkspaces(companionId, data.workspaces || []);
        } catch (e) {
            console.warn(`[CompanionCreator] Could not load workspaces for ${companionId}:`, e);
        }
    }

    function _renderCompanionWorkspaces(companionId, workspaces) {
        const container = document.getElementById('cc-ws-list');
        if (!container) return;
        if (!workspaces.length) {
            container.innerHTML = '<span style="color:var(--text-secondary);font-size:0.8rem;font-style:italic">No workspaces configured.</span>';
            return;
        }
        container.innerHTML = '';
        for (const ws of workspaces) {
            const perms = (ws.permissions || []).map(p =>
                `<span style="background:rgba(0,217,255,0.1);border:1px solid rgba(0,217,255,0.25);border-radius:4px;padding:1px 6px;font-size:0.7rem;color:var(--primary)">${p}</span>`
            ).join(' ');
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:0.6rem;padding:0.5rem 0.6rem;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:6px;font-size:0.82rem;margin-bottom:0.35rem';
            row.innerHTML = `
              <div style="flex:1;min-width:0">
                <div style="font-weight:600;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${_esc(ws.label)}</div>
                <div style="color:var(--text-secondary);font-size:0.75rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${_esc(ws.path)}">${_esc(ws.path)}</div>
              </div>
              <div style="display:flex;gap:0.3rem;flex-shrink:0">${perms}</div>
              <span style="color:var(--text-secondary);font-size:0.7rem;flex-shrink:0">${ws.recursive ? '↳ recursive' : 'folder only'}</span>
              <button data-wsid="${ws.id}" title="Remove workspace" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:0.85rem;padding:0.2rem 0.4rem;transition:color 0.2s"
                onmouseover="this.style.color='#ff4444'" onmouseout="this.style.color=''">✕</button>`;
            row.querySelector('button').onclick = () => _deleteCompanionWorkspace(companionId, ws.id);
            container.appendChild(row);
        }
    }

    async function _addCompanionWorkspace(companionId) {
        const path  = document.getElementById('cc-ws-path')?.value?.trim();
        const label = document.getElementById('cc-ws-label')?.value?.trim() || path;
        if (!path) return;

        const permissions = [];
        if (document.getElementById('cc-ws-perm-read')?.checked)   permissions.push('read');
        if (document.getElementById('cc-ws-perm-write')?.checked)  permissions.push('write');
        if (document.getElementById('cc-ws-perm-delete')?.checked) permissions.push('delete');
        const recursive = document.getElementById('cc-ws-recursive')?.checked ?? true;

        try {
            const res = await fetch(`/api/companions/${companionId}/workspaces`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, path, permissions, recursive })
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                if (typeof showToast === 'function') showToast('Error: ' + (err.detail || 'Unknown error'), 'error');
                return;
            }
            const pathEl  = document.getElementById('cc-ws-path');
            const labelEl = document.getElementById('cc-ws-label');
            if (pathEl)  pathEl.value  = '';
            if (labelEl) labelEl.value = '';
            await _loadCompanionWorkspaces(companionId);
        } catch (e) {
            console.error(`[CompanionCreator] Failed to add workspace for ${companionId}:`, e);
        }
    }

    async function _deleteCompanionWorkspace(companionId, wsId) {
        if (!confirm('Remove this workspace?')) return;
        try {
            await fetch(`/api/companions/${companionId}/workspaces/${wsId}`, { method: 'DELETE' });
            await _loadCompanionWorkspaces(companionId);
        } catch (e) {
            console.error(`[CompanionCreator] Failed to delete workspace from ${companionId}:`, e);
        }
    }

    // Reset companion

    async function _resetCompanion(companionId) {
        const name      = _activeData?.name || companionId;
        const confirmed = confirm(
            `This will permanently delete all of ${name}'s conversation history and memory.\n\nAre you sure?`
        );
        if (!confirmed) return;

        const btn = document.getElementById('cc-reset-companion-btn');
        if (!btn) return;
        btn.disabled = true;
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Resetting…';

        try {
            const res = await fetch(`/api/companions/${companionId}/reset`, { method: 'POST' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            btn.innerHTML = '<i class="fas fa-check"></i> Reset complete';
            btn.style.cssText = 'background:rgba(34,197,94,0.15);border-color:rgba(34,197,94,0.4);color:rgba(34,197,94,0.9)';
            setTimeout(() => { btn.disabled = false; btn.innerHTML = orig; btn.style.cssText = ''; }, 3000);
            if (typeof showToast === 'function') showToast(`${name} has been reset.`, 'success');
        } catch (e) {
            btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Reset failed';
            btn.style.cssText = 'background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.4);color:rgba(239,68,68,0.9)';
            setTimeout(() => { btn.disabled = false; btn.innerHTML = orig; btn.style.cssText = ''; }, 3000);
            console.error(`[CompanionCreator] Reset failed:`, e);
        }
    }


    let _cachedConnectors = null;
    let _lastInteractionTs = Date.now();
    let _proactiveTimer = null;

    async function _populateConnectorProfiles(selectedId = 'full_local') {
        const sel = document.getElementById('cc-cap-connector-profile');
        if (!sel) return;
        try {
            const res = await fetch('/api/connectors/profiles');
            if (res.ok) {
                const data = await res.json();
                const profiles = data.profiles || [];
                if (profiles.length) {
                    sel.innerHTML = profiles.map(p =>
                        `<option value="${_esc(p.id)}">${_esc(p.name)} — ${_esc(p.description || '')}</option>`
                    ).join('');
                }
            }
        } catch {}
        sel.value = selectedId || 'full_local';
        if (!sel.value) sel.value = 'full_local';
    }

    async function _loadSlashConnectors() {
        if (_cachedConnectors) return _cachedConnectors;
        try {
            const res = await fetch('/api/connectors/registry');
            if (res.ok) {
                const data = await res.json();
                _cachedConnectors = (data.connectors || []).filter(c => c.slash_command);
                return _cachedConnectors;
            }
        } catch {}
        return [
            { id: 'screen_capture', name: 'Screen Capture', slash_command: '/screen_capture', description: 'Capture desktop screenshot for visual context' },
            { id: 'reddit', name: 'Reddit Pulse', slash_command: '/reddit', description: 'Fetch top posts or search a subreddit' },
            { id: 'weather_link', name: 'Weather Link', slash_command: '/weather', description: 'Fetch real-time weather conditions' },
            { id: 'media_sentinel', name: 'Media Sentinel', slash_command: '/media', description: 'Detect active windows & playing media' },
            { id: 'system_link', name: 'System Telemetry', slash_command: '/system', description: 'Check CPU, RAM & GPU usage' },
            { id: 'web_search', name: 'Live Web Search', slash_command: '/search', description: 'Search the web for live info' }
        ];
    }

    async function _openSlashPopover(filterPrefix = '') {
        const pop = document.getElementById('cc-slash-popover');
        const listEl = document.getElementById('cc-slash-list');
        if (!pop || !listEl) return;
        const connectors = await _loadSlashConnectors();
        const filtered = connectors.filter(c =>
            c.enabled !== false && (!filterPrefix || c.slash_command.toLowerCase().startsWith(filterPrefix))
        );
        if (!filtered.length) {
            pop.classList.add('hidden');
            return;
        }
        listEl.innerHTML = filtered.map(c => `
          <button type="button" class="cc-slash-item" data-cmd="${_esc(c.slash_command)}">
            <span class="cc-slash-cmd">${_esc(c.slash_command)}</span>
            <span class="cc-slash-desc">${_esc(c.name)} — ${_esc(c.description || '')}</span>
          </button>
        `).join('');
        listEl.querySelectorAll('.cc-slash-item').forEach(btn => {
            btn.addEventListener('click', () => {
                const cmd = btn.dataset.cmd;
                const input = document.getElementById('cc-chat-input');
                if (input) {
                    const rest = (input.value || '').replace(/^\/\S*\s*/, '');
                    input.value = `${cmd} ${rest}`;
                    input.focus();
                    _autoResizeInput(input);
                }
                pop.classList.add('hidden');
            });
        });
        pop.classList.remove('hidden');
    }

    function _toggleSlashPopover() {
        if (window.AethvionSlashAutocomplete) {
            if (window.AethvionSlashAutocomplete.isOpen()) {
                window.AethvionSlashAutocomplete.close();
            } else {
                window.AethvionSlashAutocomplete.openForInput(document.getElementById('cc-chat-input'));
            }
            return;
        }
        const pop = document.getElementById('cc-slash-popover');
        if (!pop) return;
        if (!pop.classList.contains('hidden')) {
            pop.classList.add('hidden');
        } else {
            _openSlashPopover('');
        }
    }

    function _startProactiveHeartbeat() {
        // Global AethvionCompanionPresence handles startup & session proactive check-ins across all tabs
        if (window.AethvionCompanionPresence) return;
        if (_proactiveTimer) clearInterval(_proactiveTimer);
        ['keydown', 'mousedown'].forEach(evtName => {
            document.addEventListener(evtName, () => { _lastInteractionTs = Date.now(); }, { passive: true });
        });
        _proactiveTimer = setInterval(() => {
            if (!_editingId || _chatStreaming) return;
            const enabled = document.getElementById('cc-proactive-enabled')?.checked
                ?? _prefGet(`${_editingId}.proactive_enabled`, false);
            if (!enabled) return;
            const minIntervalMin = parseFloat(document.getElementById('cc-session-interval-min')?.value || _prefGet(`${_editingId}.session_interval_min`, 45)) || 45;
            const chancePct = parseFloat(document.getElementById('cc-session-chance')?.value || _prefGet(`${_editingId}.session_chance`, 60)) || 60;
            const idleMinutes = (Date.now() - _lastInteractionTs) / 60000;
            if (idleMinutes >= minIntervalMin) {
                _lastInteractionTs = Date.now();
                if (Math.random() * 100 <= chancePct) {
                    _triggerCheckin();
                }
            }
        }, 60000);
    }

    // =========================================================================
    // COMPANION GROUP CHAT IMPLEMENTATION
    // =========================================================================

    function _renderGroupAvatar(id, name, symbol, color = '#6366f1', size = 20) {
        if (!id || id === 'marcel' || id === 'system') {
            const sym = symbol || (id === 'marcel' ? '👤' : '✦');
            return `<span class="gc-avatar-fallback" style="display:inline-flex; align-items:center; justify-content:center; width:${size}px; height:${size}px; border-radius:50%; background:${color}22; color:${color}; font-size:${Math.max(10, Math.round(size * 0.62))}px; line-height:1; flex-shrink:0;">${_esc(sym)}</span>`;
        }
        return `
            <span class="gc-msg-avatar-wrap" style="width:${size}px; height:${size}px; border:1px solid ${color}44;">
                <img src="/api/companion-creator/${encodeURIComponent(id)}/icon" class="gc-msg-avatar-img" alt="${_esc(name || id)}" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='inline-flex';" />
                <span class="gc-avatar-fallback" style="display:none; width:100%; height:100%; align-items:center; justify-content:center; background:${color}22; color:${color}; font-size:${Math.max(10, Math.round(size * 0.62))}px; line-height:1;">${_esc(symbol || '✦')}</span>
            </span>
        `;
    }

    async function _loadGroupChats() {
        const groupEl = document.getElementById('cc-group-list');
        if (!groupEl) return;
        try {
            const res = await fetch(GROUPS_API);
            if (!res.ok) return;
            const d = await res.json();
            const groups = d.groups || [];
            if (!groups.length) {
                groupEl.innerHTML = '<div class="cc-card-empty" style="padding:0.4rem; font-size:0.75rem;">No group chats yet. Hit <strong>+</strong> to start one!</div>';
                return;
            }
            groupEl.innerHTML = groups.map(g => `
                <div class="cc-group-card ${_activeGroupId === g.id ? 'active' : ''}" data-group-id="${_esc(g.id)}">
                    <div class="cc-group-avatar" style="background:${_esc(g.accent_color)}25; color:${_esc(g.accent_color)};">
                        ${_esc(g.avatar_symbol || '🚀')}
                    </div>
                    <div class="cc-group-info">
                        <div class="cc-group-title">${_esc(g.title)}</div>
                        <div class="cc-group-sub">
                            <span class="cc-group-members-badge"><i class="fas fa-users"></i> ${g.members ? g.members.length : 0}</span>
                            <span>${g.message_count || 0} msgs</span>
                        </div>
                    </div>
                </div>
            `).join('');

            groupEl.querySelectorAll('.cc-group-card').forEach(card => {
                card.addEventListener('click', () => _openGroupChat(card.dataset.groupId));
            });
        } catch (err) {
            console.warn('[CompanionCreator] Failed to load group chats:', err);
        }
    }

    async function _openNewGroupModal() {
        let modal = document.getElementById('cc-new-group-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'cc-new-group-modal';
            modal.className = 'cc-snapshot-modal';
            modal.innerHTML = `
                <div class="cc-snapshot-modal-backdrop" onclick="document.getElementById('cc-new-group-modal').classList.remove('open')"></div>
                <div class="cc-snapshot-modal-box" style="max-width:540px; background:var(--bg-secondary); border:1px solid var(--border); border-radius:12px; overflow:hidden;">
                    <div class="cc-snapshot-modal-header" style="background:rgba(255,255,255,0.03); border-bottom:1px solid var(--border); padding:0.85rem 1.25rem;">
                        <span style="font-weight:700; color:#fff; display:flex; align-items:center; gap:0.5rem;">
                            <i class="fas fa-users-viewfinder" style="color:#a78bfa;"></i> Create Companion Group Chat
                        </span>
                        <button type="button" class="cc-snapshot-modal-close" onclick="document.getElementById('cc-new-group-modal').classList.remove('open')">&times;</button>
                    </div>
                    <div style="padding:1.25rem; display:flex; flex-direction:column; gap:1rem;">
                        <div>
                            <label style="display:block; font-size:0.78rem; font-weight:600; color:#cbd5e1; margin-bottom:0.35rem;">Group Title</label>
                            <input type="text" id="gc-create-title" class="cc-search-input" placeholder="e.g. Game Dev & AI Brainstorm" style="width:100%; border:1px solid var(--border); border-radius:6px; padding:0.5rem 0.75rem; background:rgba(0,0,0,0.3); color:#fff;" />
                        </div>
                        <div>
                            <label style="display:block; font-size:0.78rem; font-weight:600; color:#cbd5e1; margin-bottom:0.35rem;">Topic / Description</label>
                            <input type="text" id="gc-create-desc" class="cc-search-input" placeholder="What are you working on or brainstorming together?" style="width:100%; border:1px solid var(--border); border-radius:6px; padding:0.5rem 0.75rem; background:rgba(0,0,0,0.3); color:#fff;" />
                        </div>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.75rem;">
                            <div>
                                <label style="display:block; font-size:0.78rem; font-weight:600; color:#cbd5e1; margin-bottom:0.35rem;">Chat Pacing / Speed</label>
                                <select id="gc-create-speed" class="control-select" style="width:100%; background:rgba(0,0,0,0.3); border:1px solid var(--border); color:#fff; border-radius:6px; padding:0.45rem;">
                                    <option value="natural" selected>💬 Natural</option>
                                    <option value="lively">⚡ Lively</option>
                                    <option value="quiet">☕ Quiet</option>
                                    <option value="manual">✋ Manual (step-by-step)</option>
                                </select>
                            </div>
                            <div>
                                <label style="display:block; font-size:0.78rem; font-weight:600; color:#cbd5e1; margin-bottom:0.35rem;">Group Icon</label>
                                <input type="text" id="gc-create-icon" value="🚀" style="width:100%; border:1px solid var(--border); border-radius:6px; padding:0.45rem 0.75rem; background:rgba(0,0,0,0.3); color:#fff; text-align:center; font-size:1.1rem;" />
                            </div>
                        </div>
                        <div>
                            <label style="display:block; font-size:0.78rem; font-weight:600; color:#cbd5e1; margin-bottom:0.35rem;">Select Companion Members</label>
                            <div id="gc-create-members-list" style="max-height:160px; overflow-y:auto; border:1px solid var(--border); border-radius:8px; padding:0.5rem; background:rgba(0,0,0,0.2); display:flex; flex-direction:column; gap:0.35rem;">
                                <div class="cc-card-loading"><i class="fas fa-spinner fa-spin"></i> Loading companions...</div>
                            </div>
                        </div>
                        <div style="display:flex; justify-content:flex-end; gap:0.5rem; margin-top:0.5rem;">
                            <button type="button" class="cc-btn cc-btn-secondary" onclick="document.getElementById('cc-new-group-modal').classList.remove('open')">Cancel</button>
                            <button type="button" id="gc-create-submit-btn" class="cc-btn cc-btn-primary"><i class="fas fa-check"></i> Create Group</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        const membersListEl = document.getElementById('gc-create-members-list');
        try {
            const res = await fetch(`${API}/all`);
            const d = await res.json();
            const allComps = d.companions || [];
            membersListEl.innerHTML = allComps.map(c => `
                <label style="display:flex; align-items:center; gap:0.6rem; padding:0.35rem 0.5rem; border-radius:6px; cursor:pointer; background:rgba(255,255,255,0.02);">
                    <input type="checkbox" value="${_esc(c.id)}" ${c.id === 'misakacipher' ? 'checked' : ''} style="accent-color:var(--primary);" />
                    ${_renderGroupAvatar(c.id, c.name, c.avatar_symbol, c.accent_color || '#6366f1', 22)}
                    <span style="font-weight:600; font-size:0.82rem; color:#f1f5f9;">${_esc(c.name)}</span>
                    <span style="font-size:0.72rem; color:var(--text-secondary); margin-left:auto;">${_esc(c.description || '')}</span>
                </label>
            `).join('');
        } catch {
            membersListEl.innerHTML = '<div style="color:#ef4444; font-size:0.78rem;">Failed to load companions.</div>';
        }

        document.getElementById('gc-create-submit-btn').onclick = async () => {
            const title = (document.getElementById('gc-create-title').value || '').trim();
            if (!title) {
                if (typeof showToast === 'function') showToast('Please enter a group title', 'error');
                return;
            }
            const desc = (document.getElementById('gc-create-desc').value || '').trim();
            const icon = (document.getElementById('gc-create-icon').value || '🚀').trim();
            const pace = document.getElementById('gc-create-speed').value || 'natural';
            const speed = pace === 'manual' ? 0 : 3.0;
            const checkedBoxes = membersListEl.querySelectorAll('input[type="checkbox"]:checked');
            const compIds = Array.from(checkedBoxes).map(cb => cb.value);

            try {
                const res = await fetch(GROUPS_API, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: title,
                        description: desc,
                        companion_ids: compIds,
                        avatar_symbol: icon,
                        chat_speed_seconds: speed,
                        pace: pace
                    })
                });
                if (!res.ok) throw new Error('Server returned ' + res.status);
                const d = await res.json();
                modal.classList.remove('open');
                await _loadGroupChats();
                if (d.group?.id) _openGroupChat(d.group.id);
            } catch (err) {
                if (typeof showToast === 'function') showToast(`Failed to create group: ${err.message}`, 'error');
            }
        };

        modal.classList.add('open');
    }

    async function _openGroupChat(groupId) {
        if (!groupId) return;
        _editingId = null;
        _activeGroupId = groupId;
        _groupTurnInProgress = false;

        document.querySelectorAll('.cc-companion-card').forEach(c => c.classList.remove('active'));
        document.querySelectorAll('.cc-group-card').forEach(c => c.classList.toggle('active', c.dataset.groupId === groupId));

        document.getElementById('cc-empty-state')?.classList.add('hidden');
        document.getElementById('cc-active-pane')?.classList.add('hidden');
        const groupPane = document.getElementById('cc-group-pane');
        if (!groupPane) return;
        groupPane.classList.remove('hidden');

        groupPane.innerHTML = `
            <div style="display:flex; align-items:center; justify-content:center; height:100%; color:var(--text-secondary); gap:0.5rem;">
                <i class="fas fa-spinner fa-spin"></i> Loading group chat...
            </div>
        `;

        try {
            const res = await fetch(`${GROUPS_API}/${groupId}`);
            if (!res.ok) throw new Error('Failed to load group ' + res.status);
            const d = await res.json();
            _activeGroupData = d.group;
            _groupPacingPaused = !!d.group.settings?.paused;
            _renderGroupChat(_activeGroupData);
            _connectGroupEvents(groupId);
        } catch (err) {
            groupPane.innerHTML = `<div style="padding:2rem; color:#ef4444;">Error: ${err.message}</div>`;
        }
    }

    // ── Live group events (messages, typing, reactions) ──────────────────────
    // The server decides who answers and when; this tab only displays what happens.

    function _groupPace(group) {
        const s = (group || _activeGroupData)?.settings || {};
        if (['natural', 'lively', 'quiet', 'manual'].includes(s.pace)) return s.pace;
        return parseFloat(s.chat_speed_seconds ?? 3.0) === 0 ? 'manual' : 'natural';
    }

    function _disconnectGroupEvents() {
        if (_groupEventSource) { try { _groupEventSource.close(); } catch {} }
        _groupEventSource = null;
        _groupTypers = new Map();
    }

    function _connectGroupEvents(groupId) {
        _disconnectGroupEvents();
        if (typeof EventSource === 'undefined') return;
        const es = new EventSource(`${GROUPS_API}/${groupId}/events`);
        _groupEventSource = es;
        es.onmessage = (e) => {
            if (_activeGroupId !== groupId) { es.close(); return; }
            let ev;
            try { ev = JSON.parse(e.data); } catch { return; }
            if (ev.type === 'message' && ev.message) {
                _appendGroupMessage(ev.message);
                if (ev.message.author_role === 'companion') _refreshGroupScratchpad(groupId);
            } else if (ev.type === 'typing') {
                if (ev.active) _groupTypers.set(ev.companion_id, ev.name || ev.companion_id);
                else _groupTypers.delete(ev.companion_id);
                _renderGroupTyping();
            } else if (ev.type === 'reaction') {
                _applyGroupReaction(ev);
            } else if (ev.type === 'notice' && typeof showToast === 'function') {
                showToast(ev.text, 'info');
            }
        };
    }

    function _renderGroupTyping() {
        const el = document.getElementById('gc-typing-indicator');
        if (!el) return;
        const names = Array.from(_groupTypers.values());
        if (!names.length) { el.style.display = 'none'; el.innerHTML = ''; return; }
        const who = names.length === 1 ? `${names[0]} is typing`
            : names.length === 2 ? `${names[0]} and ${names[1]} are typing`
            : `${names.length} people are typing`;
        el.style.display = 'block';
        el.innerHTML = `<span class="gc-typing-pill"><span class="gc-typing-dots"><i></i><i></i><i></i></span> ${_esc(who)}…</span>`;
    }

    function _groupReactionsHTML(reactions) {
        if (!Array.isArray(reactions) || !reactions.length) return '';
        const byEmoji = new Map();
        reactions.forEach(r => {
            if (!byEmoji.has(r.emoji)) byEmoji.set(r.emoji, []);
            byEmoji.get(r.emoji).push(r.by_name || r.by);
        });
        return Array.from(byEmoji.entries()).map(([emoji, names]) =>
            `<span class="gc-reaction-pill" title="${_esc(names.join(', '))}">${_esc(emoji)}${names.length > 1 ? ` <b>${names.length}</b>` : ''}</span>`
        ).join('');
    }

    function _applyGroupReaction(ev) {
        const card = document.querySelector(`.gc-msg-card[data-msg-id="${CSS.escape(ev.message_id)}"]`);
        if (!card) return;
        const list = JSON.parse(card.dataset.reactions || '[]');
        if (list.some(r => r.by === ev.by && r.emoji === ev.emoji)) return;
        list.push({ emoji: ev.emoji, by: ev.by, by_name: ev.by_name });
        card.dataset.reactions = JSON.stringify(list);
        let row = card.querySelector('.gc-reactions-row');
        if (!row) {
            row = document.createElement('div');
            row.className = 'gc-reactions-row';
            card.appendChild(row);
        }
        row.innerHTML = _groupReactionsHTML(list);
    }

    function _groupMsgCardHTML(m) {
        if (m.author_role === 'system') {
            return `<div class="gc-system-pill">${_esc(m.content)}</div>`;
        }
        const isUser = m.author_role === 'user' || m.author_id === 'marcel';
        const color = m.accent_color || (isUser ? '#10b981' : '#6366f1');
        const timeStr = m.timestamp ? (new Date(m.timestamp)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
        const bubbleStyle = isUser
            ? 'background: rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.3);'
            : `background: ${color}14; border-color: ${color}38; box-shadow: 0 4px 14px ${color}10;`;
        const reactions = Array.isArray(m.reactions) ? m.reactions : [];
        return `
            <div class="gc-msg-card ${isUser ? 'is-user' : 'is-companion'}" style="${bubbleStyle}" data-msg-id="${_esc(m.id || '')}" data-reactions="${_esc(JSON.stringify(reactions))}">
                <div class="gc-msg-header">
                    <span class="gc-msg-author" style="color:${color};">
                        ${_renderGroupAvatar(m.author_id, m.author_name, isUser ? '👤' : m.avatar_symbol, color, 28)}
                        <span>${_esc(m.author_name || m.author_id)}</span>
                    </span>
                    ${m.mood ? `<span class="gc-msg-badge">${_esc(m.mood)}</span>` : ''}
                    <span class="gc-msg-time" style="margin-left:auto;">${timeStr}</span>
                </div>
                <div class="gc-msg-body">${_formatGroupMessageContent(m.content, m.attachments)}</div>
                ${reactions.length ? `<div class="gc-reactions-row">${_groupReactionsHTML(reactions)}</div>` : ''}
            </div>
        `;
    }

    /** Add one message to the open chat, once. Returns false if it was already there. */
    function _appendGroupMessage(m) {
        if (!m || (m.id && _groupSeenIds.has(m.id))) return false;
        if (m.id) _groupSeenIds.add(m.id);
        const msgsScroll = document.getElementById('gc-msgs-scroll');
        if (!msgsScroll) return false;
        const nearBottom = msgsScroll.scrollHeight - msgsScroll.scrollTop - msgsScroll.clientHeight < 160;
        msgsScroll.insertAdjacentHTML('beforeend', _groupMsgCardHTML(m));
        if (typeof _applyHighlight === 'function') _applyHighlight(msgsScroll);
        const isUser = m.author_role === 'user';
        if (nearBottom || isUser) _scrollGroupChatToBottom();
        if (_activeGroupData && Array.isArray(_activeGroupData.history)) _activeGroupData.history.push(m);
        return true;
    }

    function _formatGroupMessageContent(raw, attachments = null) {
        if (!raw) return '';
        let html = '';
        if (typeof _renderMd === 'function') {
            html = _renderMd(raw, true);
        } else {
            html = _esc(raw).replace(/\n/g, '<br>');
        }
        // Highlight @mentions in HTML
        html = html.replace(/@([A-Za-z0-9_]+)/g, '<span class="gc-mention-pill">@$1</span>');
        if (Array.isArray(attachments) && attachments.length && typeof _renderAttachmentsBlock === 'function') {
            html += _renderAttachmentsBlock(attachments, raw);
        }
        return html;
    }

    function _renderGroupChat(group) {
        const groupPane = document.getElementById('cc-group-pane');
        if (!groupPane) return;

        const members = group.members || [];
        const pace = _groupPace(group);
        const ambientOn = group.settings?.ambient_enabled !== false;
        const entriesCount = group.scratchpad_summary?.entries_count || 0;

        groupPane.innerHTML = `
            <!-- Header -->
            <div class="gc-header">
                <div class="gc-header-left">
                    <div class="gc-header-avatar" style="background:${_esc(group.accent_color)}25; color:${_esc(group.accent_color)};">
                        ${_esc(group.avatar_symbol || '🚀')}
                    </div>
                    <div>
                        <div class="gc-header-title">${_esc(group.title)}</div>
                        <div class="gc-header-desc">${_esc(group.description || 'Shared brainstorming room')}</div>
                    </div>
                </div>

                <div class="gc-header-right">
                    <!-- Members Bar -->
                    <div class="gc-members-row">
                        ${members.map(m => {
                            const isUser = m.is_user || m.id === 'marcel';
                            return `
                                <span class="gc-member-chip" style="background:${_esc(m.accent_color)}25; color:${_esc(m.accent_color)}; border-color:${_esc(m.accent_color)}40;" title="${isUser ? 'Marcel (User)' : 'Click to @mention ' + m.name}" onclick="window._groupChatInsertMention('${_esc(m.name)}')">
                                    ${_renderGroupAvatar(m.id, m.name, m.avatar_symbol, m.accent_color, 22)}
                                    <span>${_esc(m.name)}</span>
                                    ${!isUser ? `<i class="fas fa-times gc-member-kick-btn" title="Kick from group" onclick="event.stopPropagation(); window._groupChatKickMember('${_esc(group.id)}', '${_esc(m.id)}', '${_esc(m.name)}')"></i>` : ''}
                                </span>
                            `;
                        }).join('')}
                        <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" style="padding:2px 7px; font-size:0.72rem; border-radius:10px;" onclick="window._groupChatOpenInviteModal('${_esc(group.id)}')">
                            <i class="fas fa-user-plus"></i> Invite
                        </button>
                    </div>

                    <!-- Pacing Controller -->
                    <div class="gc-speed-wrap">
                        <span class="gc-speed-label"><i class="fas fa-gauge-high"></i> Pace:</span>
                        <select id="gc-pacing-select" class="gc-speed-select" title="Natural: companions answer when they have something to say, at human speed. Lively: more back-and-forth. Quiet: fewer, slower replies. Manual: nobody speaks unless you @mention them or press Converse.">
                            <option value="natural" ${pace === 'natural' ? 'selected' : ''}>💬 Natural</option>
                            <option value="lively" ${pace === 'lively' ? 'selected' : ''}>⚡ Lively</option>
                            <option value="quiet" ${pace === 'quiet' ? 'selected' : ''}>☕ Quiet</option>
                            <option value="manual" ${pace === 'manual' ? 'selected' : ''}>✋ Manual</option>
                        </select>
                        <label class="gc-ambient-toggle" title="When the chat has been silent for a while, a companion may start a conversation on its own (daytime only, a few times a day).">
                            <input type="checkbox" id="gc-ambient-toggle" ${ambientOn ? 'checked' : ''} />
                            <span>Starts topics</span>
                        </label>
                    </div>

                    <!-- Pause / Resume Toggle -->
                    <button type="button" id="gc-pacing-play-btn" class="gc-pause-btn ${_groupPacingPaused ? 'paused' : ''}">
                        <i class="fas ${_groupPacingPaused ? 'fa-play' : 'fa-pause'}"></i> ${_groupPacingPaused ? 'Resume' : 'Pause'}
                    </button>

                    <!-- Scratchpad Drawer Toggle -->
                    <button type="button" id="gc-scratchpad-toggle-btn" class="cc-btn cc-btn-secondary cc-btn-sm" style="display:flex; align-items:center; gap:0.35rem;">
                        <i class="fas fa-lightbulb" style="color:#f59e0b;"></i>
                        <span>Scratchpad</span>
                        <span id="gc-sp-badge" class="cc-group-members-badge">${entriesCount}</span>
                    </button>

                    <!-- Delete Group Option -->
                    <button type="button" class="cc-icon-btn" title="Delete Group Chat" style="color:#ef4444;" onclick="window._groupChatDelete('${_esc(group.id)}')">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            </div>

            <!-- Body Wrap -->
            <div class="gc-body-wrap">
                <!-- Chat Feed Column -->
                <div class="gc-chat-col">
                    <div class="gc-msgs-scroll" id="gc-msgs-scroll">
                        ${_renderGroupHistoryHTML(group.history || [])}
                    </div>

                    <!-- Floating Jump to Present button -->
                    <button id="gc-jump-bottom-btn" class="chat-jump-btn hidden" title="Jump to present">
                        <i class="fas fa-chevron-down"></i> Jump to present
                    </button>

                    <!-- Typing Indicator -->
                    <div id="gc-typing-indicator" style="display:none; padding:0.35rem 1rem;"></div>

                    <!-- Input Bar -->
                    <div class="gc-input-bar">
                        <!-- Quick Pings Row -->
                        <div class="gc-pings-row">
                            <span><i class="fas fa-at"></i> Ping:</span>
                            ${members.filter(m => !m.is_user && m.id !== 'marcel').map(m => `
                                <button type="button" class="gc-ping-btn" onclick="window._groupChatInsertMention('${_esc(m.name)}')">
                                    ${_renderGroupAvatar(m.id, m.name, m.avatar_symbol, m.accent_color, 20)}
                                    <span>@${_esc(m.name)}</span>
                                </button>
                            `).join('')}
                        </div>

                        <div class="gc-input-row">
                            <textarea id="gc-input-textarea" class="gc-textarea" placeholder="Message the group chat... (use @Name to direct a question)"></textarea>
                            <button type="button" id="gc-converse-btn" class="cc-btn cc-btn-secondary" title="Let companions discuss or bounce thoughts" style="white-space:nowrap;">
                                <i class="fas fa-comments"></i> Converse
                            </button>
                            <button type="button" id="gc-send-btn" class="cc-btn cc-btn-primary" style="padding:0.6rem 1rem;">
                                <i class="fas fa-paper-plane"></i>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Side Scratchpad Drawer -->
                <div class="gc-scratchpad-drawer ${_groupScratchpadOpen ? '' : 'collapsed'}" id="gc-scratchpad-drawer">
                    <div class="gc-sp-header">
                        <span style="display:flex; align-items:center; gap:0.4rem;">
                            <i class="fas fa-lightbulb" style="color:#f59e0b;"></i> Group Brainstorming Scratchpad
                        </span>
                        <div style="display:flex; gap:0.35rem;">
                            <button type="button" class="cc-btn cc-btn-ghost cc-btn-sm" title="Clear Scratchpad" onclick="window._groupChatClearScratchpad('${_esc(group.id)}')">
                                <i class="fas fa-trash-can"></i>
                            </button>
                            <button type="button" class="cc-btn cc-btn-ghost cc-btn-sm" onclick="document.getElementById('gc-scratchpad-drawer').classList.toggle('collapsed')">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                    <div class="gc-sp-body" id="gc-sp-body">
                        ${_renderGroupScratchpadHTML(group.scratchpad_summary?.plain_text || '')}
                    </div>
                    <div class="gc-sp-add-form">
                        <input type="text" id="gc-sp-note-input" class="cc-search-input" placeholder="Add idea to group scratchpad…" style="flex:1; border:1px solid var(--border); border-radius:6px; padding:0.4rem 0.6rem; background:rgba(0,0,0,0.25); color:#fff;" />
                        <button type="button" id="gc-sp-add-btn" class="cc-btn cc-btn-primary cc-btn-sm">
                            <i class="fas fa-plus"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;

        _initGroupChatEvents(group);
        if (typeof _applyHighlight === 'function') _applyHighlight(document.getElementById('gc-msgs-scroll'));
        _scrollGroupChatToBottom(true);
    }

    function _renderGroupHistoryHTML(history) {
        if (!history || !history.length) {
            return '<div style="text-align:center; padding:2rem; color:var(--text-secondary); font-size:0.85rem;">No messages yet. Send a message or use @Name to prompt companions!</div>';
        }
        _groupSeenIds = new Set(history.map(m => m.id).filter(Boolean));
        return history.map(_groupMsgCardHTML).join('');
    }

    function _renderGroupScratchpadHTML(rawText) {
        if (!rawText || !rawText.trim()) {
            return '<div style="color:var(--text-secondary); font-style:italic; padding:0.5rem 0;">Scratchpad is empty. Add ideas below or companions can append mechanics during chat!</div>';
        }
        // Basic line-by-line renderer with bold headings
        const lines = rawText.split('\n');
        return lines.map(line => {
            const trimmed = line.trim();
            if (trimmed.startsWith('# ')) return `<h3 style="color:#f8fafc; font-size:0.95rem; margin:0.6rem 0 0.3rem 0;">${_esc(trimmed.slice(2))}</h3>`;
            if (trimmed.startsWith('## ')) return `<h4 style="color:#a78bfa; font-size:0.86rem; margin:0.5rem 0 0.25rem 0;">${_esc(trimmed.slice(3))}</h4>`;
            if (trimmed.startsWith('### ')) return `<h5 style="color:#cbd5e1; font-size:0.8rem; margin:0.4rem 0 0.2rem 0;">${_esc(trimmed.slice(4))}</h5>`;
            if (trimmed.startsWith('- ')) return `<div style="padding-left:0.5rem; margin:0.2rem 0;">• ${_esc(trimmed.slice(2))}</div>`;
            return trimmed ? `<div>${_esc(trimmed)}</div>` : '<div style="height:0.4rem;"></div>';
        }).join('');
    }

    function _initGroupChatEvents(group) {
        const msgsScroll = document.getElementById('gc-msgs-scroll');
        const jumpBtn = document.getElementById('gc-jump-bottom-btn');
        const textarea = document.getElementById('gc-input-textarea');
        const sendBtn = document.getElementById('gc-send-btn');
        const converseBtn = document.getElementById('gc-converse-btn');
        const pacingSelect = document.getElementById('gc-pacing-select');
        const playBtn = document.getElementById('gc-pacing-play-btn');
        const scratchpadToggleBtn = document.getElementById('gc-scratchpad-toggle-btn');
        const spAddBtn = document.getElementById('gc-sp-add-btn');
        const spNoteInput = document.getElementById('gc-sp-note-input');

        // Pacing select change
        pacingSelect?.addEventListener('change', async () => {
            const pace = pacingSelect.value || 'natural';
            const speed = pace === 'manual' ? 0 : 3.0;
            if (_activeGroupData) {
                _activeGroupData.settings.pace = pace;
                _activeGroupData.settings.chat_speed_seconds = speed;
            }
            try {
                await fetch(`${GROUPS_API}/${group.id}/settings`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pace: pace, chat_speed_seconds: speed })
                });
            } catch {}
        });

        // "Starts topics" toggle: companions may open a conversation after a long silence
        document.getElementById('gc-ambient-toggle')?.addEventListener('change', async (e) => {
            const on = !!e.target.checked;
            if (_activeGroupData) _activeGroupData.settings.ambient_enabled = on;
            try {
                await fetch(`${GROUPS_API}/${group.id}/settings`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ambient_enabled: on })
                });
            } catch {}
        });

        // Play/Pause button: pausing is stored on the server so it also holds when this tab is closed
        playBtn?.addEventListener('click', async () => {
            _groupPacingPaused = !_groupPacingPaused;
            playBtn.classList.toggle('paused', _groupPacingPaused);
            playBtn.innerHTML = `<i class="fas ${_groupPacingPaused ? 'fa-play' : 'fa-pause'}"></i> ${_groupPacingPaused ? 'Resume' : 'Pause'}`;
            if (_activeGroupData) _activeGroupData.settings.paused = _groupPacingPaused;
            try {
                await fetch(`${GROUPS_API}/${group.id}/settings`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ paused: _groupPacingPaused })
                });
            } catch {}
        });

        // Scratchpad toggle
        scratchpadToggleBtn?.addEventListener('click', () => {
            const drawer = document.getElementById('gc-scratchpad-drawer');
            if (drawer) {
                drawer.classList.toggle('collapsed');
                _groupScratchpadOpen = !drawer.classList.contains('collapsed');
            }
        });

        // Scratchpad Add note
        const submitSpNote = async () => {
            const text = (spNoteInput?.value || '').trim();
            if (!text) return;
            spNoteInput.value = '';
            try {
                const res = await fetch(`${GROUPS_API}/${group.id}/scratchpad/append`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text, author: 'Marcel', section: 'Ideas' })
                });
                if (res.ok) {
                    await _refreshGroupScratchpad(group.id);
                }
            } catch {}
        };
        spAddBtn?.addEventListener('click', submitSpNote);
        spNoteInput?.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); submitSpNote(); }
        });

        // Textarea auto-resize & Enter-to-send
        textarea?.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(120, textarea.scrollHeight) + 'px';
        });
        textarea?.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                _sendGroupUserMessage();
            }
        });

        sendBtn?.addEventListener('click', _sendGroupUserMessage);

        // Converse button triggers next companion turn
        converseBtn?.addEventListener('click', async () => {
            if (_groupPace() !== 'manual') {
                // The server picks who speaks and paces it.
                try {
                    await fetch(`${GROUPS_API}/${group.id}/nudge`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({})
                    });
                } catch {}
                return;
            }
            if (_groupTurnInProgress) return;
            const companions = (group.members || []).filter(m => !m.is_user && m.id !== 'marcel');
            if (!companions.length) return;
            _orchestrateCompanionTurns([companions[0].id]);
        });

        // Jump button
        msgsScroll?.addEventListener('scroll', () => {
            const dist = msgsScroll.scrollHeight - msgsScroll.scrollTop - msgsScroll.clientHeight;
            if (jumpBtn) jumpBtn.classList.toggle('hidden', dist < 120);
        });
        jumpBtn?.addEventListener('click', () => _scrollGroupChatToBottom(false));
    }

    function _scrollGroupChatToBottom(immediate = false) {
        const msgsScroll = document.getElementById('gc-msgs-scroll');
        if (!msgsScroll) return;
        if (immediate) {
            msgsScroll.scrollTop = msgsScroll.scrollHeight;
        } else {
            msgsScroll.scrollTo({ top: msgsScroll.scrollHeight, behavior: 'smooth' });
        }
    }

    async function _refreshGroupScratchpad(groupId) {
        try {
            const res = await fetch(`${GROUPS_API}/${groupId}/scratchpad`);
            if (!res.ok) return;
            const d = await res.json();
            const sp = d.scratchpad || {};
            const pt = sp.plain_text || sp.content || '';
            const spBody = document.getElementById('gc-sp-body');
            if (spBody) spBody.innerHTML = _renderGroupScratchpadHTML(pt);
            const badge = document.getElementById('gc-sp-badge');
            if (badge) badge.textContent = sp.entries ? sp.entries.length : 0;
        } catch {}
    }

    async function _sendGroupUserMessage() {
        const textarea = document.getElementById('gc-input-textarea');
        if (!textarea) return;
        const text = textarea.value.trim();
        if (!text || !_activeGroupId) return;
        textarea.value = '';
        textarea.style.height = 'auto';

        const msgsScroll = document.getElementById('gc-msgs-scroll');

        try {
            const res = await fetch(`${GROUPS_API}/${_activeGroupId}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: text })
            });
            if (!res.ok) throw new Error('Failed to post message');
            const data = await res.json();
            const userMsg = data.message;
            const mentioned = data.mentioned_companions || [];

            // Show it now; the event stream may deliver the same message, which is then ignored.
            _appendGroupMessage(userMsg);

            // Manual pace: this tab asks the mentioned companions to answer, one at a time.
            // Every other pace: the server decides who answers and when.
            if (_groupPace() === 'manual' && mentioned.length) {
                _orchestrateCompanionTurns(mentioned);
            }

        } catch (err) {
            if (typeof showToast === 'function') showToast(`Failed to send: ${err.message}`, 'error');
        }
    }

    async function _orchestrateCompanionTurns(candidates = [], turnDepth = 0) {
        if (!_activeGroupId || _groupPacingPaused || turnDepth >= 4) return;
        if (_groupTurnInProgress) return;

        const group = _activeGroupData;
        if (!group) return;
        const companions = (group.members || []).filter(m => !m.is_user && m.id !== 'marcel');
        if (!companions.length) return;

        // Choose next candidate: first from mentions, otherwise pick one companion
        let targetCid = candidates.length ? candidates[0] : null;
        if (!targetCid) {
            targetCid = companions[Math.floor(Math.random() * companions.length)].id;
        }

        const compMember = companions.find(c => c.id === targetCid) || companions[0];
        _groupTurnInProgress = true;

        const typingEl = document.getElementById('gc-typing-indicator');
        if (typingEl) {
            typingEl.style.display = 'block';
            typingEl.innerHTML = `<span class="gc-typing-pill"><i class="fas fa-circle-notch fa-spin"></i> ${compMember.name} is thinking...</span>`;
            _scrollGroupChatToBottom();
        }

        const speedSec = parseFloat(group.settings?.chat_speed_seconds ?? 3.0);
        if (speedSec > 0) {
            await new Promise(r => setTimeout(r, Math.max(800, speedSec * 1000)));
        }

        try {
            const res = await fetch(`${GROUPS_API}/${_activeGroupId}/turn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ companion_id: compMember.id, reason: 'conversation' })
            });
            if (!res.ok) throw new Error('Turn failed: ' + res.status);
            const data = await res.json();
            const msg = data.message;
            const nextPinged = data.next_pinged_companions || [];

            if (typingEl) typingEl.style.display = 'none';
            if (msg) _appendGroupMessage(msg);

            // Also refresh group scratchpad in case the companion added a note
            await _refreshGroupScratchpad(_activeGroupId);

            _groupTurnInProgress = false;

            // If another companion was pinged and pacing is active, continue turn loop!
            if (nextPinged.length && !_groupPacingPaused && speedSec > 0) {
                _orchestrateCompanionTurns(nextPinged, turnDepth + 1);
            }

        } catch (err) {
            if (typingEl) typingEl.style.display = 'none';
            _groupTurnInProgress = false;
            console.warn('[CompanionGroupChat] Turn error:', err);
        }
    }

    // Window helpers for group chat interactions
    window._groupChatInsertMention = function(name) {
        const textarea = document.getElementById('gc-input-textarea');
        if (!textarea) return;
        const mention = `@${name} `;
        if (!textarea.value.includes(mention)) {
            textarea.value = textarea.value.trim() ? `${textarea.value.trim()} ${mention}` : mention;
        }
        textarea.focus();
    };

    window._groupChatOpenInviteModal = async function(groupId) {
        try {
            const allRes = await fetch(`${API}/all`);
            const allData = await allRes.json();
            const allComps = allData.companions || [];

            const group = _activeGroupData;
            const existingIds = (group?.members || []).map(m => m.id);
            const candidates = allComps.filter(c => !existingIds.includes(c.id));

            if (!candidates.length) {
                if (typeof showToast === 'function') showToast('All available companions are already in this group!', 'info');
                return;
            }

            let modal = document.getElementById('cc-invite-group-modal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = 'cc-invite-group-modal';
                modal.className = 'cc-snapshot-modal';
                document.body.appendChild(modal);
            }

            modal.innerHTML = `
                <div class="cc-snapshot-modal-backdrop" onclick="document.getElementById('cc-invite-group-modal').classList.remove('open')"></div>
                <div class="cc-snapshot-modal-box" style="max-width:440px; background:var(--bg-secondary); border:1px solid var(--border); border-radius:12px; overflow:hidden;">
                    <div class="cc-snapshot-modal-header" style="background:rgba(255,255,255,0.03); border-bottom:1px solid var(--border); padding:0.85rem 1.25rem;">
                        <span style="font-weight:700; color:#fff;"><i class="fas fa-user-plus"></i> Invite Companion to Group</span>
                        <button type="button" class="cc-snapshot-modal-close" onclick="document.getElementById('cc-invite-group-modal').classList.remove('open')">&times;</button>
                    </div>
                    <div style="padding:1rem; display:flex; flex-direction:column; gap:0.5rem; max-height:280px; overflow-y:auto;">
                        ${candidates.map(c => `
                            <div style="display:flex; align-items:center; justify-content:space-between; padding:0.5rem 0.65rem; border-radius:8px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);">
                                <div style="display:flex; align-items:center; gap:0.5rem;">
                                    ${_renderGroupAvatar(c.id, c.name, c.avatar_symbol, c.accent_color || '#6366f1', 28)}
                                    <div>
                                        <div style="font-size:0.82rem; font-weight:700; color:#f8fafc;">${_esc(c.name)}</div>
                                        <div style="font-size:0.7rem; color:var(--text-secondary);">${_esc(c.description || '')}</div>
                                    </div>
                                </div>
                                <button type="button" class="cc-btn cc-btn-primary cc-btn-sm" onclick="window._groupChatSubmitInvite('${_esc(groupId)}', '${_esc(c.id)}')">
                                    <i class="fas fa-plus"></i> Invite
                                </button>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            modal.classList.add('open');
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Invite failed: ${err.message}`, 'error');
        }
    };

    window._groupChatSubmitInvite = async function(groupId, companionId) {
        document.getElementById('cc-invite-group-modal')?.classList.remove('open');
        try {
            const res = await fetch(`${GROUPS_API}/${groupId}/members/invite`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ companion_id: companionId })
            });
            if (!res.ok) throw new Error('Invite failed');
            const d = await res.json();
            _activeGroupData = d.group;
            _renderGroupChat(_activeGroupData);
            _loadGroupChats();
            if (typeof showToast === 'function') showToast('Companion invited to group!', 'success');
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Invite failed: ${err.message}`, 'error');
        }
    };

    window._groupChatKickMember = async function(groupId, companionId, name) {
        if (!confirm(`Are you sure you want to remove ${name} from this group chat?`)) return;
        try {
            const res = await fetch(`${GROUPS_API}/${groupId}/members/kick`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ companion_id: companionId })
            });
            if (!res.ok) throw new Error('Kick failed');
            const d = await res.json();
            _activeGroupData = d.group;
            _renderGroupChat(_activeGroupData);
            _loadGroupChats();
            if (typeof showToast === 'function') showToast(`${name} removed from group`, 'info');
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Failed to remove member: ${err.message}`, 'error');
        }
    };

    window._groupChatClearScratchpad = async function(groupId) {
        if (!confirm('Reset the group brainstorming scratchpad back to the template?')) return;
        try {
            await fetch(`${GROUPS_API}/${groupId}/scratchpad/clear`, { method: 'POST' });
            await _refreshGroupScratchpad(groupId);
            if (typeof showToast === 'function') showToast('Group scratchpad reset', 'info');
        } catch {}
    };

    window._groupChatDelete = async function(groupId) {
        if (!confirm('Are you sure you want to delete this group chat?')) return;
        try {
            await fetch(`${GROUPS_API}/${groupId}`, { method: 'DELETE' });
            _activeGroupId = null;
            _activeGroupData = null;
            document.getElementById('cc-group-pane')?.classList.add('hidden');
            document.getElementById('cc-empty-state')?.classList.remove('hidden');
            await _loadGroupChats();
            if (typeof showToast === 'function') showToast('Group chat deleted', 'info');
        } catch (err) {
            if (typeof showToast === 'function') showToast(`Delete failed: ${err.message}`, 'error');
        }
    };

    function openCompanion(companionId) {
        if (!companionId) return;
        const isBuiltin = ['axiom', 'lyra', 'misakacipher'].includes(companionId);
        init();
        _editCompanion(companionId, isBuiltin);
    }

    window.addEventListener('companion-proactive-message', (e) => {
        const d = e.detail;
        if (d && d.companion_id && d.companion_id === _editingId) {
            _appendMessage('companion', d.response);
            _chatHistory.push({ role: 'assistant', content: d.response });
            if (d.mood || d.expression) {
                _updatePortraitMoodAndExpr(d.mood, d.expression);
            }
        }
    });

    return { init, openCompanion, openGroupChat: _openGroupChat };
})();

window.CompanionCreator = CompanionCreator;

// panelLoaded fires after the lazy script injection — this is the correct pattern
document.addEventListener('panelLoaded', function (e) {
    if (e.detail && e.detail.tabName === 'companion-creator') {
        CompanionCreator.init();
    }
});