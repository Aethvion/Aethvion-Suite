/**
 * Aethvion Suite — Sidebar Manager (Profiles + Onboarding Edition)
 *
 * Adds:
 *  - Named sidebar profiles (fully independent configs)
 *  - 5 premade preset layouts + Custom (blank) option
 *  - Profile onboarding modal (auto-shown on first launch)
 *  - Suite-home profiles widget (chip row + Add Layout button)
 *
 * Storage key: 'sidebar_profiles_v1'
 * Migrates old 'sidebar_v2' format automatically.
 */

(function () {
    'use strict';

    const STORAGE_KEY = 'sidebar_profiles_v1';
    const OLD_KEY     = 'sidebar_v2';

    // ── Tab Registry ─────────────────────────────────────────────────────────
    const TABS = [
        { id: 'suite-home',        label: 'Home',             icon: 'fas fa-house',              mode: ['home'] },
        { id: 'chat',              label: 'Chat',             icon: 'fas fa-comments',            mode: ['ai']   },
        { id: 'agents',            label: 'Agents',           icon: 'fas fa-robot',              mode: ['ai']   },
        { id: 'agent-corp',        label: 'Agent Corp',       icon: 'fas fa-building',           mode: ['ai']   },
        { id: 'schedule',          label: 'Schedule',         icon: 'fas fa-calendar-alt',       mode: ['ai']   },
        { id: 'photo',             label: 'Photo',            icon: 'fas fa-image',              mode: ['ai']   },
        { id: 'audio',             label: 'Audio',            icon: 'fas fa-microphone',         mode: ['ai']   },
        { id: 'advaiconv',         label: 'Adv. AI Conv.',    icon: 'fas fa-flask',              mode: ['ai']   },
        { id: 'researchboard',     label: 'Directors',        icon: 'fas fa-balance-scale',      mode: ['ai']   },
        { id: 'arena',             label: 'Arena',            icon: 'fas fa-shield-halved',      mode: ['ai']   },
        { id: 'aiconv',            label: 'AI Conv.',         icon: 'fas fa-masks-theater',      mode: ['ai']   },
        { id: 'explained',         label: 'Explained',        icon: 'fas fa-lightbulb',          mode: ['ai']   },
        { id: 'misaka-cipher',     label: 'Misaka Cipher',    icon: 'fas fa-wand-magic-sparkles',mode: ['ai']   },
        { id: 'axiom',             label: 'Axiom',            icon: 'fas fa-atom',               mode: ['ai']   },
        { id: 'lyra',              label: 'Lyra',             icon: 'fas fa-music',              mode: ['ai']   },
        { id: 'companion-creator', label: 'Create Companion', icon: 'fas fa-plus-circle',        mode: ['ai']   },
        { id: 'games-center',      label: 'Games Center',     icon: 'fas fa-gamepad',            mode: ['ai']   },
        { id: 'memory',            label: 'Memory',           icon: 'fas fa-book',               mode: ['ai']   },
        { id: 'companion-memory',  label: 'Companion Memory', icon: 'fas fa-dna',                mode: ['ai']   },
        { id: 'persistent-memory', label: 'Persistent',       icon: 'fas fa-brain',              mode: ['ai']   },
        { id: 'sched-overview',    label: 'Scheduled',        icon: 'fas fa-calendar-check',     mode: ['ai']   },
        { id: 'output',            label: 'Output',           icon: 'fas fa-upload',             mode: ['ai']   },
        { id: 'screenshots',       label: 'Gallery',          icon: 'fas fa-camera-retro',       mode: ['ai']   },
        { id: 'camera',            label: 'Camera',           icon: 'fas fa-camera',             mode: ['ai']   },
        { id: 'uploads',           label: 'Uploads',          icon: 'fas fa-folder',             mode: ['ai']   },
        { id: 'local-models',      label: 'Text & Chat',      icon: 'fas fa-microchip',          mode: ['ai']   },
        { id: 'image-models',      label: 'Image Models',     icon: 'fas fa-mountain-sun',       mode: ['ai']   },
        { id: 'audio-models',      label: 'Audio & Speech',   icon: 'fas fa-volume-high',        mode: ['ai']   },
        { id: 'api-providers',     label: 'API Providers',    icon: 'fas fa-plug',               mode: ['ai']   },
        { id: '3d-models',         label: '3D Models',        icon: 'fas fa-cube',               mode: ['ai']   },
        { id: '3d-gen',            label: '3D Workspace',     icon: 'fas fa-vector-square',      mode: ['ai']   },
        { id: 'logs',              label: 'Logs',             icon: 'fas fa-scroll',             mode: ['ai']   },
        { id: 'documentation',     label: 'Docs',             icon: 'fas fa-book-open',          mode: ['ai']   },
        { id: 'usage',             label: 'Usage',            icon: 'fas fa-chart-bar',          mode: ['ai']   },
        { id: 'status',            label: 'Status',           icon: 'fas fa-traffic-light',      mode: ['ai']   },
        { id: 'ports',             label: 'Ports',            icon: 'fas fa-plug',               mode: ['ai']   },
    ];

    const TAB_MAP = Object.fromEntries(TABS.map(t => [t.id, t]));

    // ── Preset Layouts ────────────────────────────────────────────────────────
    const PRESETS = [
        {
            id: 'professional',
            name: 'Professional',
            icon: 'fas fa-briefcase',
            accent: '#6366f1',
            description: 'Productivity workspace with agents, scheduling, and system management.',
            highlights: ['Chat & Agents', 'Schedule', 'Model Hub', 'System'],
            folders: [
                { name: 'Workspace', expanded: true,  tabs: ['chat', 'agents', 'agent-corp', 'schedule'] },
                { name: 'Models',    expanded: false, tabs: ['local-models', 'api-providers'] },
                { name: 'System',    expanded: false, tabs: ['logs', 'status', 'ports'] },
            ],
            enabled: new Set(['suite-home', 'chat', 'agents', 'agent-corp', 'schedule',
                              'local-models', 'api-providers', '3d-models', 'logs', 'status', 'ports']),
        },
        {
            id: 'creative',
            name: 'Creative Studio',
            icon: 'fas fa-palette',
            accent: '#ec4899',
            description: 'Photo, audio, and AI tools built for artists and content creators.',
            highlights: ['Photo Studio', 'Audio', 'AI Conversations', 'Output'],
            folders: [
                { name: 'Studio',   expanded: true,  tabs: ['photo', 'audio', 'output', 'screenshots'] },
                { name: 'AI Tools', expanded: false, tabs: ['chat', 'explained', 'advaiconv'] },
            ],
            enabled: new Set(['suite-home', 'chat', 'photo', 'audio', 'explained',
                              'advaiconv', 'output', 'screenshots']),
        },
        {
            id: 'researcher',
            name: 'Researcher',
            icon: 'fas fa-microscope',
            accent: '#10b981',
            description: 'Deep analysis, model comparisons, and knowledge management for advanced research.',
            highlights: ['Directors', 'Arena', 'AI Conv.', 'Explained', 'Persistent Memory'],
            folders: [
                { name: 'Research',  expanded: true,  tabs: ['advaiconv', 'researchboard', 'arena', 'aiconv', 'explained'] },
                { name: 'Knowledge', expanded: false, tabs: ['chat', 'persistent-memory', 'documentation'] },
            ],
            enabled: new Set(['suite-home', 'chat', 'advaiconv', 'researchboard', 'arena',
                              'aiconv', 'explained', 'persistent-memory', 'documentation']),
        },
        {
            id: 'companion',
            name: 'Companion Hub',
            icon: 'fas fa-heart',
            accent: '#a855f7',
            description: 'Personal AI companions, entertainment, and memory in one focused layout.',
            highlights: ['Misaka Cipher', 'Axiom', 'Lyra', 'Games', 'Memory'],
            folders: [
                { name: 'Companions',    expanded: true,  tabs: ['misaka-cipher', 'axiom', 'lyra', 'companion-creator'] },
                { name: 'Entertainment', expanded: false, tabs: ['games-center', 'chat'] },
                { name: 'Memory',        expanded: false, tabs: ['memory', 'companion-memory'] },
            ],
            enabled: new Set(['suite-home', 'chat', 'misaka-cipher', 'axiom', 'lyra',
                              'companion-creator', 'games-center', 'memory', 'companion-memory']),
        },
        {
            id: 'full',
            name: 'Full Suite',
            icon: 'fas fa-layer-group',
            accent: '#f59e0b',
            description: 'Everything enabled with the complete default folder layout. Nothing hidden.',
            highlights: ['All Tabs', 'All Folders', 'Full Access'],
            folders: null, // uses default
            enabled: null, // all enabled
        },
        {
            id: 'custom',
            name: 'Custom',
            icon: 'fas fa-sliders',
            accent: '#6b7280',
            description: 'Start blank — every tab disabled. Build your perfect sidebar from scratch.',
            highlights: ['Start fresh', 'Full control', 'Your layout'],
            folders: [],   // no folders
            enabled: new Set(['suite-home']), // only home tab visible
        },
    ];

    // ── Default profile data ──────────────────────────────────────────────────
    function defaultProfileData(name = 'Default') {
        return {
            name,
            hidden: {},
            folders: {
                'f-workspace':  { name: 'Workspace',    expanded: true  },
                'f-research':   { name: 'Research',     expanded: false },
                'f-companions': { name: 'Companions',   expanded: false },
                'f-fun':        { name: 'Entertainment',expanded: false },
                'f-memory':     { name: 'Memory',       expanded: false },
                'f-storage':    { name: 'Storage',      expanded: false },
                'f-models':     { name: 'Model Hub',    expanded: false },
                'f-system':     { name: 'System',       expanded: false },
            },
            order: [
                { type: 'tab',    id: 'suite-home' },
                { type: 'folder', id: 'f-workspace',  children: ['chat','agents','agent-corp','schedule','photo','audio'] },
                { type: 'folder', id: 'f-research',   children: ['advaiconv','researchboard','arena','aiconv','explained'] },
                { type: 'folder', id: 'f-companions', children: ['misaka-cipher','axiom','lyra','companion-creator'] },
                { type: 'folder', id: 'f-fun',        children: ['games-center'] },
                { type: 'folder', id: 'f-memory',     children: ['memory','companion-memory','persistent-memory','sched-overview'] },
                { type: 'folder', id: 'f-storage',    children: ['output','screenshots','camera','uploads'] },
                { type: 'folder', id: 'f-models',     children: ['local-models','image-models','audio-models','3d-models','3d-gen','api-providers'] },
                { type: 'folder', id: 'f-system',     children: ['logs','documentation','usage','status','ports'] },
            ],
        };
    }

    /** Build a profile config from a preset definition. */
    function buildPresetConfig(preset, name) {
        if (preset.id === 'full') return defaultProfileData(name);

        const d = defaultProfileData(name);

        if (preset.id === 'custom') {
            // Hide everything except suite-home
            TABS.forEach(t => { if (t.id !== 'suite-home') d.hidden[t.id] = true; });
            d.folders = {};
            d.order   = [{ type: 'tab', id: 'suite-home' }];
            return d;
        }

        // Hide tabs not in this preset's enabled set
        TABS.forEach(t => {
            if (!preset.enabled.has(t.id)) d.hidden[t.id] = true;
        });

        // Build folder structure from preset definition
        d.folders = {};
        d.order   = [{ type: 'tab', id: 'suite-home' }];
        preset.folders.forEach((def, i) => {
            const fid = `f-preset-${i}`;
            d.folders[fid] = { name: def.name, expanded: def.expanded };
            d.order.push({ type: 'folder', id: fid, children: def.tabs });
        });

        return d;
    }

    // ── Storage ───────────────────────────────────────────────────────────────
    let isFirstTime = false;

    function storeLoad() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                const saved = JSON.parse(raw);
                if (saved?.profiles) {
                    Object.values(saved.profiles).forEach(surfaceNewTabs);
                    return saved;
                }
            }

            // Migrate old single-config format
            const old = localStorage.getItem(OLD_KEY);
            if (old) {
                const parsed = JSON.parse(old);
                localStorage.removeItem(OLD_KEY);
                return {
                    activeProfile: 'default',
                    profiles: { default: { ...parsed, name: 'Default' } },
                };
            }

            // Brand new user
            isFirstTime = true;
            return {
                activeProfile: 'default',
                profiles: { default: defaultProfileData('Default') },
            };
        } catch (_) {
            isFirstTime = true;
            return {
                activeProfile: 'default',
                profiles: { default: defaultProfileData('Default') },
            };
        }
    }

    function surfaceNewTabs(profile) {
        if (!profile?.order) return;
        const placed = new Set();
        for (const e of profile.order) {
            if (e.type === 'tab')    placed.add(e.id);
            else if (e.type === 'folder') (e.children || []).forEach(id => placed.add(id));
        }
        TABS.forEach(t => { if (!placed.has(t.id)) profile.order.push({ type: 'tab', id: t.id }); });
    }

    function storeSave() {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(store)); } catch (_) {}
    }

    // ── State ─────────────────────────────────────────────────────────────────
    let store           = null;
    let config          = null;  // alias → store.profiles[store.activeProfile]
    let editMode        = false;
    let dropdownOpen    = false;
    let selectedPreset  = null;  // id of the preset currently highlighted in the modal

    // Drag state
    let dragging    = null;
    let dropCurrent = null;

    function syncConfig() { config = store.profiles[store.activeProfile]; }

    // ── Helpers ───────────────────────────────────────────────────────────────
    function getCurrentMode() {
        if (document.body.classList.contains('theme-ai'))   return 'ai';
        if (document.body.classList.contains('theme-home')) return 'home';
        return window.dashboardMode || 'home';
    }

    function esc(s) {
        return String(s)
            .replace(/&/g,'&amp;').replace(/</g,'&lt;')
            .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    // ── Profile operations ────────────────────────────────────────────────────
    function switchProfile(profileId) {
        if (!store.profiles[profileId]) return;
        store.activeProfile = profileId;
        syncConfig();
        storeSave();
        closeProfileDropdown();
        render();
        updateProfileSwitcherBtn();
        refreshHomeWidget();
        window._suiteHomeUpdate?.();
    }

    function createFromPreset(presetId, profileName) {
        const preset = PRESETS.find(p => p.id === presetId);
        if (!preset) return;
        const id  = 'p-' + Date.now();
        const cfg = buildPresetConfig(preset, profileName || preset.name);
        cfg.presetId = preset.id;   // store preset type for home page awareness
        store.profiles[id] = cfg;
        store.activeProfile = id;
        syncConfig();
        storeSave();
        hideOnboardingModal();
        render();
        updateProfileSwitcherBtn();
        refreshHomeWidget();
        window._suiteHomeUpdate?.();
    }

    function createProfile() {
        const id = 'p-' + Date.now();
        store.profiles[id] = defaultProfileData('New Profile');
        store.activeProfile = id;
        syncConfig();
        storeSave();
        closeProfileDropdown();
        render();
        updateProfileSwitcherBtn();
        refreshHomeWidget();
        setTimeout(() => startProfileRename(id), 50);
    }

    function duplicateProfile(srcId) {
        const src = store.profiles[srcId];
        if (!src) return;
        const id = 'p-' + Date.now();
        store.profiles[id] = JSON.parse(JSON.stringify(src));
        store.profiles[id].name = src.name + ' (copy)';
        store.activeProfile = id;
        syncConfig();
        storeSave();
        closeProfileDropdown();
        render();
        updateProfileSwitcherBtn();
        refreshHomeWidget();
    }

    function deleteProfile(profileId) {
        if (Object.keys(store.profiles).length <= 1) return;
        delete store.profiles[profileId];
        if (store.activeProfile === profileId) {
            store.activeProfile = Object.keys(store.profiles)[0];
            syncConfig();
        }
        storeSave();
        renderProfileDropdown();
        updateProfileSwitcherBtn();
        refreshHomeWidget();
    }

    function startProfileRename(profileId) {
        const item = document.querySelector(`.profile-item[data-profile-id="${profileId}"] .profile-item-name`);
        if (!item) return;
        const current = store.profiles[profileId]?.name || '';
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'profile-rename-input';
        input.value = current;
        item.replaceWith(input);
        input.focus(); input.select();
        function commit() {
            const newName = input.value.trim() || current;
            if (store.profiles[profileId]) store.profiles[profileId].name = newName;
            storeSave(); renderProfileDropdown(); updateProfileSwitcherBtn(); refreshHomeWidget();
        }
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter')  input.blur();
            if (e.key === 'Escape') { input.value = current; input.blur(); }
        });
    }

    // ── Onboarding modal ──────────────────────────────────────────────────────
    function showOnboardingModal() {
        selectedPreset = null;
        const overlay = document.getElementById('profile-onboarding-overlay');
        if (!overlay) return;

        // Render preset cards
        const grid = document.getElementById('pon-preset-grid');
        if (grid) {
            grid.innerHTML = '';
            PRESETS.forEach(preset => {
                const card = document.createElement('div');
                card.className = 'pon-preset-card';
                card.dataset.presetId = preset.id;
                card.style.setProperty('--preset-accent', preset.accent);
                card.innerHTML = `
                    <div class="pon-card-icon"><i class="${preset.icon}"></i></div>
                    <div class="pon-card-name">${esc(preset.name)}</div>
                    <div class="pon-card-desc">${esc(preset.description)}</div>
                    <div class="pon-card-tags">${preset.highlights.map(h => `<span class="pon-tag">${esc(h)}</span>`).join('')}</div>
                `;
                card.addEventListener('click', () => selectPreset(preset.id, preset.name));
                grid.appendChild(card);
            });
        }

        // Name input default
        const nameInput = document.getElementById('pon-name-input');
        if (nameInput) nameInput.value = '';

        // Wire footer buttons
        const skipBtn   = document.getElementById('pon-skip-btn');
        const createBtn = document.getElementById('pon-create-btn');
        if (skipBtn)   skipBtn.onclick   = hideOnboardingModal;
        if (createBtn) createBtn.onclick = handleOnboardingCreate;

        // Show
        overlay.classList.add('visible');
        overlay.setAttribute('aria-hidden', 'false');
        overlay.addEventListener('click', e => { if (e.target === overlay) hideOnboardingModal(); }, { once: true });
    }

    function hideOnboardingModal() {
        const overlay = document.getElementById('profile-onboarding-overlay');
        if (!overlay) return;
        overlay.classList.remove('visible');
        overlay.setAttribute('aria-hidden', 'true');
        selectedPreset = null;
    }

    function selectPreset(presetId, presetName) {
        selectedPreset = presetId;
        // Highlight selected card
        document.querySelectorAll('.pon-preset-card').forEach(c => {
            c.classList.toggle('selected', c.dataset.presetId === presetId);
        });
        // Pre-fill name input if it's empty or has the previous preset's name
        const nameInput = document.getElementById('pon-name-input');
        if (nameInput && (!nameInput.value.trim() || PRESETS.some(p => p.name === nameInput.value.trim()))) {
            nameInput.value = presetName;
        }
    }

    function handleOnboardingCreate() {
        if (!selectedPreset) {
            // Wiggle the grid to indicate selection needed
            const grid = document.getElementById('pon-preset-grid');
            if (grid) { grid.classList.add('pon-shake'); setTimeout(() => grid.classList.remove('pon-shake'), 400); }
            return;
        }
        const nameInput = document.getElementById('pon-name-input');
        const name = nameInput?.value.trim() || PRESETS.find(p => p.id === selectedPreset)?.name || 'My Profile';
        createFromPreset(selectedPreset, name);
    }

    // ── Suite-home profiles widget ─────────────────────────────────────────────
    function refreshHomeWidget() {
        const chips = document.getElementById('spw-chips');
        if (!chips) return;

        chips.innerHTML = '';

        Object.entries(store.profiles).forEach(([id, profile]) => {
            const isActive = id === store.activeProfile;
            const chip = document.createElement('button');
            chip.className = `spw-chip${isActive ? ' active' : ''}`;
            chip.title = `Switch to ${profile.name}`;
            chip.innerHTML = `
                <span class="spw-chip-dot${isActive ? ' active' : ''}"></span>
                <span class="spw-chip-name">${esc(profile.name)}</span>
            `;
            chip.addEventListener('click', () => {
                if (id !== store.activeProfile) switchProfile(id);
            });
            chips.appendChild(chip);
        });

        // Wire "Add Layout" button
        const addBtn = document.getElementById('spw-add-btn');
        if (addBtn) {
            addBtn.onclick = showOnboardingModal;
        }
    }

    function watchSuiteHomePanel() {
        const panel = document.getElementById('suite-home-panel');
        if (!panel) return;

        function check() {
            if (panel.classList.contains('active') && !panel.querySelector('.partial-loading')) {
                refreshHomeWidget();
            }
        }

        const obs = new MutationObserver(check);
        obs.observe(panel, { attributes: true, attributeFilter: ['class'], childList: true });
        check();
    }

    // ── Profile Switcher (sidebar bottom) ─────────────────────────────────────
    function buildProfileSwitcher() {
        const wrapper = document.createElement('div');
        wrapper.id        = 'profile-switcher';
        wrapper.className = 'profile-switcher';

        const btn = document.createElement('button');
        btn.id        = 'profile-btn';
        btn.className = 'profile-btn';
        updateProfileBtnContent(btn);
        btn.addEventListener('click', e => { e.stopPropagation(); toggleProfileDropdown(wrapper); });

        wrapper.appendChild(btn);
        return wrapper;
    }

    function updateProfileSwitcherBtn() {
        const btn = document.getElementById('profile-btn');
        if (btn) updateProfileBtnContent(btn);
    }

    function updateProfileBtnContent(btn) {
        const name  = store.profiles[store.activeProfile]?.name || 'Default';
        const count = Object.keys(store.profiles).length;
        btn.innerHTML = `
            <span class="profile-dot"></span>
            <span class="profile-btn-name">${esc(name)}</span>
            <span class="profile-count">${count}</span>
            <i class="fas fa-chevron-up profile-chevron"></i>
        `;
    }

    function toggleProfileDropdown(wrapper) {
        if (dropdownOpen) { closeProfileDropdown(); return; }
        dropdownOpen = true;
        renderProfileDropdown(wrapper);
        setTimeout(() => {
            document.addEventListener('click', outsideDropdownClose, { capture: true, once: true });
        }, 30);
    }

    function closeProfileDropdown() {
        dropdownOpen = false;
        document.getElementById('profile-dropdown')?.remove();
    }

    function outsideDropdownClose(e) {
        const dropdown = document.getElementById('profile-dropdown');
        const btn      = document.getElementById('profile-btn');
        if (dropdown && !dropdown.contains(e.target) && btn && !btn.contains(e.target)) {
            closeProfileDropdown();
        } else if (dropdownOpen) {
            setTimeout(() => document.addEventListener('click', outsideDropdownClose, { capture: true, once: true }), 30);
        }
    }

    function renderProfileDropdown(wrapper) {
        document.getElementById('profile-dropdown')?.remove();
        const target = wrapper || document.getElementById('profile-switcher');
        if (!target) return;

        const dropdown = document.createElement('div');
        dropdown.id        = 'profile-dropdown';
        dropdown.className = 'profile-dropdown';

        const profileIds = Object.keys(store.profiles);

        profileIds.forEach(id => {
            const profile  = store.profiles[id];
            const isActive = id === store.activeProfile;

            const item = document.createElement('div');
            item.className = `profile-item${isActive ? ' active' : ''}`;
            item.dataset.profileId = id;

            const dot = document.createElement('span');
            dot.className = `profile-item-dot${isActive ? ' active' : ''}`;
            item.appendChild(dot);

            const nameSpan = document.createElement('span');
            nameSpan.className = 'profile-item-name';
            nameSpan.textContent = profile.name;
            item.appendChild(nameSpan);

            const actions = document.createElement('span');
            actions.className = 'profile-item-actions';

            const dupBtn = document.createElement('button');
            dupBtn.className = 'profile-action-btn';
            dupBtn.title = 'Duplicate';
            dupBtn.innerHTML = '<i class="fas fa-copy"></i>';
            dupBtn.addEventListener('click', e => { e.stopPropagation(); duplicateProfile(id); });
            actions.appendChild(dupBtn);

            if (editMode) {
                const renBtn = document.createElement('button');
                renBtn.className = 'profile-action-btn';
                renBtn.title = 'Rename';
                renBtn.innerHTML = '<i class="fas fa-pen"></i>';
                renBtn.addEventListener('click', e => { e.stopPropagation(); startProfileRename(id); });
                actions.appendChild(renBtn);

                if (profileIds.length > 1) {
                    const delBtn = document.createElement('button');
                    delBtn.className = 'profile-action-btn danger';
                    delBtn.title = 'Delete';
                    delBtn.innerHTML = '<i class="fas fa-trash"></i>';
                    delBtn.addEventListener('click', e => { e.stopPropagation(); deleteProfile(id); });
                    actions.appendChild(delBtn);
                }
            }

            item.appendChild(actions);
            item.addEventListener('click', () => {
                if (id !== store.activeProfile) switchProfile(id);
                else closeProfileDropdown();
            });

            dropdown.appendChild(item);
        });

        // Divider + New Profile
        const div = document.createElement('div');
        div.className = 'profile-dropdown-divider';
        dropdown.appendChild(div);

        const addBtn = document.createElement('button');
        addBtn.className = 'profile-add-btn';
        addBtn.innerHTML = '<i class="fas fa-plus"></i><span>New Profile</span>';
        addBtn.addEventListener('click', e => { e.stopPropagation(); showOnboardingModal(); closeProfileDropdown(); });
        dropdown.appendChild(addBtn);

        target.appendChild(dropdown);
    }

    // ── Tab list render ───────────────────────────────────────────────────────
    let dropIndicator = null;

    function render() {
        const container = document.getElementById('sidebar-tab-list');
        if (!container) return;
        clearDropHighlights();
        container.innerHTML = '';

        const mode = getCurrentMode();

        for (const entry of config.order) {
            if (entry.type === 'tab') {
                const el = renderTab(entry.id, null, mode);
                if (el) container.appendChild(el);
            } else if (entry.type === 'folder') {
                const el = renderFolder(entry, mode);
                if (el) container.appendChild(el);
            }
        }

        if (editMode) {
            const addBtn = document.createElement('button');
            addBtn.className = 'sidebar-add-folder-btn';
            addBtn.innerHTML = '<i class="fas fa-folder-plus"></i><span>New Folder</span>';
            addBtn.addEventListener('click', addFolder);
            container.appendChild(addBtn);
        }

        applyMode(mode);
        if (editMode) setupDragDrop(container);
    }

    function renderTab(tabId, folderId, mode) {
        const tab = TAB_MAP[tabId];
        if (!tab) return null;
        const isHidden = config.hidden[tabId] === true;
        if (!editMode && isHidden) return null;

        const modeClasses = tab.mode.map(m => `mode-${m}`).join(' ');
        const btn = document.createElement('button');
        btn.className = `main-tab ${modeClasses}`;
        btn.dataset.maintab = tabId;
        btn.dataset.tooltip  = tab.label;
        if (folderId) btn.dataset.folderId = folderId;
        if (editMode && isHidden) btn.classList.add('edit-hidden');

        if (editMode) {
            const grip = document.createElement('span');
            grip.className = 'drag-grip';
            grip.draggable = true;
            grip.innerHTML = '<i class="fas fa-grip-vertical"></i>';
            btn.appendChild(grip);
        }

        const icon = document.createElement('span');
        icon.className = 'tab-icon';
        icon.innerHTML = `<i class="${tab.icon}"></i>`;
        btn.appendChild(icon);

        const label = document.createElement('span');
        label.className = 'tab-label';
        label.textContent = tab.label;
        btn.appendChild(label);

        if (editMode) {
            const eye = document.createElement('button');
            eye.className = 'vis-toggle';
            eye.title = isHidden ? 'Enable' : 'Disable';
            eye.innerHTML = `<i class="fas ${isHidden ? 'fa-eye-slash' : 'fa-eye'}"></i>`;
            eye.addEventListener('click', e => { e.stopPropagation(); toggleTabVisibility(tabId); });
            btn.appendChild(eye);
        }

        btn.addEventListener('click', e => {
            if (e.target.closest('.drag-grip') || e.target.closest('.vis-toggle')) return;
            if (dragging) return;
            if (typeof switchMainTab === 'function') switchMainTab(tabId);
        });

        return btn;
    }

    function renderFolder(entry, mode) {
        const folder = config.folders[entry.id];
        if (!folder) return null;
        const children = entry.children || [];

        if (!editMode) {
            const hasVisible = children.some(id => {
                if (config.hidden[id]) return false;
                const t = TAB_MAP[id];
                return t && t.mode.includes(mode);
            });
            if (!hasVisible) return null;
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'sidebar-folder';
        wrapper.dataset.folderId = entry.id;

        const header = document.createElement('div');
        header.className = 'folder-header';
        header.dataset.folderId = entry.id;

        if (editMode) {
            const grip = document.createElement('span');
            grip.className = 'drag-grip folder-drag-grip';
            grip.innerHTML = '<i class="fas fa-grip-vertical"></i>';
            header.appendChild(grip);
        }

        const chevron = document.createElement('i');
        chevron.className = `fas fa-chevron-right folder-chevron${folder.expanded ? ' expanded' : ''}`;
        header.appendChild(chevron);

        const nameSpan = document.createElement('span');
        nameSpan.className = 'folder-name';
        nameSpan.textContent = folder.name;
        header.appendChild(nameSpan);

        if (editMode) {
            const actions = document.createElement('span');
            actions.className = 'folder-actions';
            actions.innerHTML = `
                <button class="folder-rename-btn" title="Rename"><i class="fas fa-pen"></i></button>
                <button class="folder-delete-btn" title="Delete"><i class="fas fa-trash"></i></button>
            `;
            actions.querySelector('.folder-rename-btn').addEventListener('click', e => {
                e.stopPropagation(); startFolderRename(entry.id, nameSpan);
            });
            actions.querySelector('.folder-delete-btn').addEventListener('click', e => {
                e.stopPropagation(); deleteFolder(entry.id);
            });
            header.appendChild(actions);
        }

        header.addEventListener('click', e => {
            if (e.target.closest('.folder-actions') || e.target.closest('.drag-grip') || dragging) return;
            toggleFolder(entry.id);
        });

        wrapper.appendChild(header);

        const body = document.createElement('div');
        body.className = `folder-body${folder.expanded ? ' expanded' : ''}`;
        body.dataset.folderId = entry.id;

        for (const tabId of children) {
            const tabEl = renderTab(tabId, entry.id, mode);
            if (tabEl) {
                body.appendChild(tabEl);
                if (tabId === 'lyra') {
                    const customDiv = document.createElement('div');
                    customDiv.id = 'custom-companions-sidebar';
                    body.appendChild(customDiv);
                }
            }
        }

        wrapper.appendChild(body);
        return wrapper;
    }

    // ── Mode visibility ───────────────────────────────────────────────────────
    function applyMode(mode) {
        document.querySelectorAll('#sidebar-tab-list .main-tab').forEach(btn => {
            btn.classList.toggle('mode-hidden', !btn.classList.contains(`mode-${mode}`));
        });
    }

    // ── Folder operations ─────────────────────────────────────────────────────
    function toggleFolder(id) {
        if (!config.folders[id]) return;
        config.folders[id].expanded = !config.folders[id].expanded;
        storeSave(); render();
    }

    function addFolder() {
        const id = 'f-' + Date.now();
        config.folders[id] = { name: 'New Folder', expanded: true };
        config.order.push({ type: 'folder', id, children: [] });
        storeSave(); render();
        const nameSpan = document.querySelector(`.sidebar-folder[data-folder-id="${id}"] .folder-name`);
        if (nameSpan) startFolderRename(id, nameSpan);
    }

    function startFolderRename(folderId, nameSpan) {
        const current = config.folders[folderId]?.name || '';
        const input = document.createElement('input');
        input.type = 'text'; input.className = 'folder-rename-input'; input.value = current;
        nameSpan.replaceWith(input);
        input.focus(); input.select();
        function commit() {
            if (config.folders[folderId]) config.folders[folderId].name = input.value.trim() || current;
            storeSave(); render();
        }
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter')  input.blur();
            if (e.key === 'Escape') { input.value = current; input.blur(); }
        });
    }

    function deleteFolder(folderId) {
        const entry = config.order.find(e => e.type === 'folder' && e.id === folderId);
        if (!entry) return;
        const idx    = config.order.indexOf(entry);
        const orphans = (entry.children || []).map(id => ({ type: 'tab', id }));
        config.order.splice(idx, 1, ...orphans);
        delete config.folders[folderId];
        storeSave(); render();
    }

    function toggleTabVisibility(tabId) {
        config.hidden[tabId] = !config.hidden[tabId];
        storeSave(); render();
    }

    // ── Drag and drop ─────────────────────────────────────────────────────────
    function setupDragDrop(container) {
        dropIndicator = document.createElement('div');
        dropIndicator.className = 'drop-indicator';
        dropIndicator.style.display = 'none';
        document.body.appendChild(dropIndicator);
        container.addEventListener('dragstart', onDragStart, true);
        container.addEventListener('dragend',   onDragEnd,   true);
        container.addEventListener('dragover',  onDragOver,  true);
        container.addEventListener('drop',      onDrop,      true);
    }

    function onDragStart(e) {
        const grip = e.target.closest('.drag-grip');
        if (!grip) { e.preventDefault(); return; }
        const tab    = grip.closest('.main-tab');
        const fhdr   = grip.closest('.folder-header');
        if (tab) {
            dragging = { type: 'tab', id: tab.dataset.maintab, srcFolderId: tab.dataset.folderId || null };
            tab.classList.add('is-dragging');
        } else if (fhdr && grip.classList.contains('folder-drag-grip')) {
            dragging = { type: 'folder', id: fhdr.dataset.folderId };
            fhdr.closest('.sidebar-folder')?.classList.add('is-dragging');
        } else { e.preventDefault(); return; }
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', '');
    }

    function onDragEnd() {
        clearDropHighlights();
        if (dropIndicator) { dropIndicator.remove(); dropIndicator = null; }
        dragging = null; dropCurrent = null;
    }

    function onDragOver(e) {
        e.preventDefault();
        if (!dragging) return;
        clearDropHighlights();
        if (!dropIndicator) return;

        const tab    = e.target.closest('.main-tab:not(.is-dragging)');
        const fhdr   = e.target.closest('.folder-header');
        const fbody  = e.target.closest('.folder-body');
        const cont   = document.getElementById('sidebar-tab-list');

        if (dragging.type === 'tab') {
            if (fhdr && !tab) {
                fhdr.classList.add('drop-target-folder');
                dropCurrent = { type: 'into-folder', folderId: fhdr.dataset.folderId };
                dropIndicator.style.display = 'none';
            } else if (tab) {
                const r = tab.getBoundingClientRect();
                const after = e.clientY > r.top + r.height / 2;
                positionIndicator(tab, after);
                dropCurrent = { type: after ? 'after-tab' : 'before-tab', tabId: tab.dataset.maintab, folderId: tab.dataset.folderId || null };
            } else if (fbody && !tab) {
                fbody.classList.add('drop-target-folder');
                dropCurrent = { type: 'into-folder', folderId: fbody.dataset.folderId };
                dropIndicator.style.display = 'none';
            } else if (cont) {
                positionAtRoot(e.clientY, cont);
            }
        } else if (dragging.type === 'folder') {
            const tf = e.target.closest('.sidebar-folder:not(.is-dragging)');
            if (tf) {
                const r = tf.getBoundingClientRect();
                const after = e.clientY > r.top + r.height / 2;
                positionIndicator(tf, after);
                dropCurrent = { type: after ? 'after-folder' : 'before-folder', folderId: tf.dataset.folderId };
            }
        }
    }

    function positionIndicator(el, after) {
        if (!dropIndicator) return;
        const r = el.getBoundingClientRect();
        dropIndicator.style.display  = 'block';
        dropIndicator.style.position = 'fixed';
        dropIndicator.style.left     = r.left + 'px';
        dropIndicator.style.width    = r.width + 'px';
        dropIndicator.style.top      = (after ? r.bottom - 1 : r.top) + 'px';
    }

    function positionAtRoot(clientY, container) {
        const children = [...container.children].filter(el =>
            !el.classList.contains('drop-indicator') && !el.classList.contains('sidebar-add-folder-btn')
        );
        let before = null;
        for (const child of children) {
            const r = child.getBoundingClientRect();
            if (clientY < r.top + r.height / 2) { before = child; break; }
        }
        const ref = before || children[children.length - 1];
        if (ref) positionIndicator(ref, !before);
        dropCurrent = { type: 'root' };
    }

    function clearDropHighlights() {
        document.querySelectorAll('.drop-target-folder').forEach(el => el.classList.remove('drop-target-folder'));
        document.querySelectorAll('.is-dragging').forEach(el => el.classList.remove('is-dragging'));
        if (dropIndicator) dropIndicator.style.display = 'none';
    }

    function onDrop(e) {
        e.preventDefault();
        if (!dragging || !dropCurrent) { onDragEnd(); return; }
        if (dragging.type === 'tab') {
            const { id, srcFolderId } = dragging;
            const dc = dropCurrent;
            removeTabFromConfig(id, srcFolderId);
            if (dc.type === 'into-folder') {
                const fe = config.order.find(e => e.type === 'folder' && e.id === dc.folderId);
                if (fe) { fe.children.push(id); if (config.folders[dc.folderId]) config.folders[dc.folderId].expanded = true; }
            } else if (dc.type === 'before-tab' || dc.type === 'after-tab') {
                insertTabNearTab(id, dc.tabId, dc.folderId, dc.type === 'after-tab');
            } else {
                config.order.push({ type: 'tab', id });
            }
        } else if (dragging.type === 'folder') {
            const dc = dropCurrent;
            if (dc.type === 'before-folder' || dc.type === 'after-folder') {
                const src = config.order.find(e => e.type === 'folder' && e.id === dragging.id);
                const tgt = config.order.find(e => e.type === 'folder' && e.id === dc.folderId);
                if (src && tgt) {
                    config.order.splice(config.order.indexOf(src), 1);
                    const ti = config.order.indexOf(tgt);
                    config.order.splice(dc.type === 'after-folder' ? ti + 1 : ti, 0, src);
                }
            }
        }
        storeSave(); onDragEnd(); render();
    }

    function removeTabFromConfig(tabId, srcFolderId) {
        if (srcFolderId) {
            const e = config.order.find(e => e.type === 'folder' && e.id === srcFolderId);
            if (e) e.children = e.children.filter(id => id !== tabId);
        } else {
            const i = config.order.findIndex(e => e.type === 'tab' && e.id === tabId);
            if (i >= 0) config.order.splice(i, 1);
        }
    }

    function insertTabNearTab(tabId, nearId, nearFolderId, after) {
        if (nearFolderId) {
            const e = config.order.find(e => e.type === 'folder' && e.id === nearFolderId);
            if (e) { const i = e.children.indexOf(nearId); e.children.splice(after ? i + 1 : i, 0, tabId); }
        } else {
            const i = config.order.findIndex(e => e.type === 'tab' && e.id === nearId);
            if (i >= 0) config.order.splice(after ? i + 1 : i, 0, { type: 'tab', id: tabId });
            else config.order.push({ type: 'tab', id: tabId });
        }
    }

    // ── Edit mode ─────────────────────────────────────────────────────────────
    function enterEditMode() {
        editMode = true;
        document.querySelector('.sidebar-nav')?.classList.add('sidebar-edit-mode');
        updateToggleBtn();
        if (dropdownOpen) renderProfileDropdown();
        render();
    }

    function exitEditMode() {
        editMode = false;
        document.querySelector('.sidebar-nav')?.classList.remove('sidebar-edit-mode');
        updateToggleBtn();
        if (dropdownOpen) renderProfileDropdown();
        render();
    }

    // ── Customize button ──────────────────────────────────────────────────────
    function buildToggleBtn() {
        const btn = document.createElement('button');
        btn.id = 'cust-toggle'; btn.className = 'cust-toggle-btn'; btn.title = 'Customize sidebar';
        updateToggleBtnContent(btn);
        btn.addEventListener('click', () => editMode ? exitEditMode() : enterEditMode());
        return btn;
    }

    function updateToggleBtnContent(btn) {
        if (!btn) return;
        if (editMode) { btn.innerHTML = '<i class="fas fa-check"></i><span>Done</span>'; btn.classList.add('edit-active'); }
        else          { btn.innerHTML = '<i class="fas fa-sliders"></i><span>Customize</span>'; btn.classList.remove('edit-active'); }
    }

    function updateToggleBtn() { updateToggleBtnContent(document.getElementById('cust-toggle')); }

    // ── Mode watcher ──────────────────────────────────────────────────────────
    function watchMode() {
        const obs = new MutationObserver(() => {
            applyMode(getCurrentMode());
            if (!editMode) render();
        });
        obs.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        const sidebarBottom = document.querySelector('.sidebar-nav .sidebar-bottom');
        if (!sidebarBottom) return;

        store = storeLoad();
        syncConfig();

        sidebarBottom.prepend(buildToggleBtn());
        sidebarBottom.prepend(buildProfileSwitcher());

        // Expose public API for home-page buttons
        window._sidebarMgr = {
            showOnboarding: showOnboardingModal,
            enterEdit:      enterEditMode,
            switchProfile,
        };

        watchMode();
        watchSuiteHomePanel();
        render();

        // Auto-show onboarding for first-time users
        if (isFirstTime) setTimeout(showOnboardingModal, 500);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        setTimeout(init, 120);
    }
})();
