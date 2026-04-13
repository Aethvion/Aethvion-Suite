/**
 * Aethvion Suite — Sidebar Manager (Profiles Edition)
 *
 * Adds named sidebar profiles on top of the folder system.
 * Each profile is a fully independent config (hidden tabs, folders, order).
 * The user can create, rename, delete and switch profiles at any time.
 * Customize mode still works identically — it just writes to the active profile.
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
        { id: 'logs',              label: 'Logs',             icon: 'fas fa-scroll',             mode: ['ai']   },
        { id: 'documentation',     label: 'Docs',             icon: 'fas fa-book-open',          mode: ['ai']   },
        { id: 'usage',             label: 'Usage',            icon: 'fas fa-chart-bar',          mode: ['ai']   },
        { id: 'status',            label: 'Status',           icon: 'fas fa-traffic-light',      mode: ['ai']   },
        { id: 'ports',             label: 'Ports',            icon: 'fas fa-plug',               mode: ['ai']   },
    ];

    const TAB_MAP = Object.fromEntries(TABS.map(t => [t.id, t]));

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
                { type: 'folder', id: 'f-models',     children: ['local-models','image-models','audio-models','api-providers'] },
                { type: 'folder', id: 'f-system',     children: ['logs','documentation','usage','status','ports'] },
            ],
        };
    }

    // ── Storage ───────────────────────────────────────────────────────────────
    function storeLoad() {
        try {
            // Try new format
            const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
            if (saved?.profiles) {
                // Surface any new tabs into all profiles
                Object.values(saved.profiles).forEach(p => surfaceNewTabs(p));
                return saved;
            }

            // Migrate old single-config format
            const old = JSON.parse(localStorage.getItem(OLD_KEY));
            const store = {
                activeProfile: 'default',
                profiles: {
                    default: old
                        ? { ...old, name: 'Default' }
                        : defaultProfileData('Default'),
                },
            };
            localStorage.removeItem(OLD_KEY);
            return store;

        } catch (_) {
            return {
                activeProfile: 'default',
                profiles: { default: defaultProfileData('Default') },
            };
        }
    }

    /** Ensure any freshly added tabs appear in the profile (at root level). */
    function surfaceNewTabs(profile) {
        if (!profile?.order) return;
        const placed = new Set();
        for (const entry of profile.order) {
            if (entry.type === 'tab') placed.add(entry.id);
            else if (entry.type === 'folder') (entry.children || []).forEach(id => placed.add(id));
        }
        TABS.forEach(t => { if (!placed.has(t.id)) profile.order.push({ type: 'tab', id: t.id }); });
    }

    function storeSave() {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(store)); } catch (_) {}
    }

    // ── State ─────────────────────────────────────────────────────────────────
    let store    = null;   // full store object
    let config   = null;   // alias → store.profiles[store.activeProfile]
    let editMode = false;
    let dropdownOpen = false;

    // Drag state
    let dragging    = null;
    let dropCurrent = null;

    /* Sync config alias to the current active profile */
    function syncConfig() {
        config = store.profiles[store.activeProfile];
    }

    // ── Mode detection ────────────────────────────────────────────────────────
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
    }

    function createProfile() {
        const id   = 'p-' + Date.now();
        const name = 'New Profile';
        store.profiles[id] = defaultProfileData(name);
        store.activeProfile = id;
        syncConfig();
        storeSave();
        closeProfileDropdown();
        render();
        updateProfileSwitcherBtn();
        // Trigger inline rename
        setTimeout(() => startProfileRename(id), 50);
    }

    function duplicateProfile(srcId) {
        const src  = store.profiles[srcId];
        if (!src) return;
        const id   = 'p-' + Date.now();
        store.profiles[id] = JSON.parse(JSON.stringify(src));
        store.profiles[id].name = src.name + ' (copy)';
        store.activeProfile = id;
        syncConfig();
        storeSave();
        closeProfileDropdown();
        render();
        updateProfileSwitcherBtn();
    }

    function deleteProfile(profileId) {
        const ids = Object.keys(store.profiles);
        if (ids.length <= 1) return; // can't delete the last profile

        delete store.profiles[profileId];

        // If we deleted the active one, switch to the first remaining
        if (store.activeProfile === profileId) {
            store.activeProfile = Object.keys(store.profiles)[0];
            syncConfig();
        }
        storeSave();
        renderProfileDropdown();
        updateProfileSwitcherBtn();
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
        input.focus();
        input.select();

        function commit() {
            const newName = input.value.trim() || current;
            if (store.profiles[profileId]) store.profiles[profileId].name = newName;
            storeSave();
            renderProfileDropdown();
            updateProfileSwitcherBtn();
        }

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter')  input.blur();
            if (e.key === 'Escape') { input.value = current; input.blur(); }
        });
    }

    // ── Profile Switcher UI ───────────────────────────────────────────────────

    function buildProfileSwitcher() {
        const wrapper = document.createElement('div');
        wrapper.id        = 'profile-switcher';
        wrapper.className = 'profile-switcher';

        const btn = document.createElement('button');
        btn.id        = 'profile-btn';
        btn.className = 'profile-btn';
        updateProfileBtnContent(btn);
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleProfileDropdown(wrapper);
        });

        wrapper.appendChild(btn);
        return wrapper;
    }

    function updateProfileSwitcherBtn() {
        const btn = document.getElementById('profile-btn');
        if (btn) updateProfileBtnContent(btn);
    }

    function updateProfileBtnContent(btn) {
        const name = store.profiles[store.activeProfile]?.name || 'Default';
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

        // Close on outside click
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
            setTimeout(() => {
                document.addEventListener('click', outsideDropdownClose, { capture: true, once: true });
            }, 30);
        }
    }

    function renderProfileDropdown(wrapper) {
        // Remove existing
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

            // Active dot
            const dot = document.createElement('span');
            dot.className = isActive ? 'profile-item-dot active' : 'profile-item-dot';
            item.appendChild(dot);

            // Name
            const nameSpan = document.createElement('span');
            nameSpan.className = 'profile-item-name';
            nameSpan.textContent = profile.name;
            item.appendChild(nameSpan);

            // Action buttons
            const actions = document.createElement('span');
            actions.className = 'profile-item-actions';

            // Duplicate button (always visible)
            const dupBtn = document.createElement('button');
            dupBtn.className = 'profile-action-btn';
            dupBtn.title = 'Duplicate profile';
            dupBtn.innerHTML = '<i class="fas fa-copy"></i>';
            dupBtn.addEventListener('click', (e) => { e.stopPropagation(); duplicateProfile(id); });
            actions.appendChild(dupBtn);

            // Rename button (edit mode only)
            if (editMode) {
                const renBtn = document.createElement('button');
                renBtn.className = 'profile-action-btn';
                renBtn.title = 'Rename';
                renBtn.innerHTML = '<i class="fas fa-pen"></i>';
                renBtn.addEventListener('click', (e) => { e.stopPropagation(); startProfileRename(id); });
                actions.appendChild(renBtn);

                // Delete button (edit mode + more than 1 profile)
                if (profileIds.length > 1) {
                    const delBtn = document.createElement('button');
                    delBtn.className = 'profile-action-btn danger';
                    delBtn.title = 'Delete profile';
                    delBtn.innerHTML = '<i class="fas fa-trash"></i>';
                    delBtn.addEventListener('click', (e) => { e.stopPropagation(); deleteProfile(id); });
                    actions.appendChild(delBtn);
                }
            }

            item.appendChild(actions);

            // Click item to switch (unless it's already active)
            item.addEventListener('click', () => {
                if (id !== store.activeProfile) switchProfile(id);
                else closeProfileDropdown();
            });

            dropdown.appendChild(item);
        });

        // Divider + Add new profile
        const divider = document.createElement('div');
        divider.className = 'profile-dropdown-divider';
        dropdown.appendChild(divider);

        const addBtn = document.createElement('button');
        addBtn.className = 'profile-add-btn';
        addBtn.innerHTML = '<i class="fas fa-plus"></i><span>New Profile</span>';
        addBtn.addEventListener('click', (e) => { e.stopPropagation(); createProfile(); });
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
            grip.title = 'Drag to reorder';
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
            eye.dataset.tabid = tabId;
            eye.title = isHidden ? 'Enable' : 'Disable';
            eye.innerHTML = `<i class="fas ${isHidden ? 'fa-eye-slash' : 'fa-eye'}"></i>`;
            eye.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleTabVisibility(tabId);
            });
            btn.appendChild(eye);
        }

        btn.addEventListener('click', (e) => {
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
            grip.title = 'Drag to reorder';
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
            actions.querySelector('.folder-rename-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                startFolderRename(entry.id, nameSpan);
            });
            actions.querySelector('.folder-delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                deleteFolder(entry.id);
            });
            header.appendChild(actions);
        }

        header.addEventListener('click', (e) => {
            if (e.target.closest('.folder-actions')) return;
            if (e.target.closest('.drag-grip')) return;
            if (dragging) return;
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
    function toggleFolder(folderId) {
        if (!config.folders[folderId]) return;
        config.folders[folderId].expanded = !config.folders[folderId].expanded;
        storeSave();
        render();
    }

    function addFolder() {
        const id = 'f-' + Date.now();
        config.folders[id] = { name: 'New Folder', expanded: true };
        config.order.push({ type: 'folder', id, children: [] });
        storeSave();
        render();
        const wrapper = document.querySelector(`.sidebar-folder[data-folder-id="${id}"]`);
        const nameSpan = wrapper?.querySelector('.folder-name');
        if (nameSpan) startFolderRename(id, nameSpan);
    }

    function startFolderRename(folderId, nameSpan) {
        const current = config.folders[folderId]?.name || '';
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'folder-rename-input';
        input.value = current;

        nameSpan.replaceWith(input);
        input.focus();
        input.select();

        function commit() {
            const newName = input.value.trim() || current;
            if (config.folders[folderId]) config.folders[folderId].name = newName;
            storeSave();
            render();
        }

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
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
        storeSave();
        render();
    }

    function toggleTabVisibility(tabId) {
        config.hidden[tabId] = !config.hidden[tabId];
        storeSave();
        render();
    }

    // ── Drag and drop ─────────────────────────────────────────────────────────
    function setupDragDrop(container) {
        dropIndicator = document.createElement('div');
        dropIndicator.className = 'drop-indicator';
        dropIndicator.style.display = 'none';
        document.body.appendChild(dropIndicator);

        container.addEventListener('dragstart', onDragStart, true);
        container.addEventListener('drag',      () => {},    true);
        container.addEventListener('dragend',   onDragEnd,   true);
        container.addEventListener('dragover',  onDragOver,  true);
        container.addEventListener('drop',      onDrop,      true);
    }

    function onDragStart(e) {
        const grip = e.target.closest('.drag-grip');
        if (!grip) { e.preventDefault(); return; }

        const tab          = grip.closest('.main-tab');
        const folderHeader = grip.closest('.folder-header');

        if (tab) {
            dragging = { type: 'tab', id: tab.dataset.maintab, srcFolderId: tab.dataset.folderId || null };
            tab.classList.add('is-dragging');
        } else if (folderHeader && grip.classList.contains('folder-drag-grip')) {
            dragging = { type: 'folder', id: folderHeader.dataset.folderId };
            folderHeader.closest('.sidebar-folder')?.classList.add('is-dragging');
        } else {
            e.preventDefault(); return;
        }

        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', '');
    }

    function onDragEnd() {
        clearDropHighlights();
        if (dropIndicator) { dropIndicator.remove(); dropIndicator = null; }
        dragging = null;
        dropCurrent = null;
    }

    function onDragOver(e) {
        e.preventDefault();
        if (!dragging) return;

        clearDropHighlights();
        if (!dropIndicator) return;

        const tab          = e.target.closest('.main-tab:not(.is-dragging)');
        const folderHeader = e.target.closest('.folder-header');
        const folderBody   = e.target.closest('.folder-body');
        const container    = document.getElementById('sidebar-tab-list');

        if (dragging.type === 'tab') {
            if (folderHeader && !tab) {
                folderHeader.classList.add('drop-target-folder');
                dropCurrent = { type: 'into-folder', folderId: folderHeader.dataset.folderId };
                dropIndicator.style.display = 'none';
            } else if (tab) {
                const after = e.clientY > tab.getBoundingClientRect().top + tab.getBoundingClientRect().height / 2;
                positionIndicator(tab, after);
                dropCurrent = { type: after ? 'after-tab' : 'before-tab', tabId: tab.dataset.maintab, folderId: tab.dataset.folderId || null };
            } else if (folderBody && !tab) {
                folderBody.classList.add('drop-target-folder');
                dropCurrent = { type: 'into-folder', folderId: folderBody.dataset.folderId };
                dropIndicator.style.display = 'none';
            } else if (container) {
                positionAtRoot(e.clientY, container);
            }
        } else if (dragging.type === 'folder') {
            const targetFolder = e.target.closest('.sidebar-folder:not(.is-dragging)');
            if (targetFolder) {
                const rect  = targetFolder.getBoundingClientRect();
                const after = e.clientY > rect.top + rect.height / 2;
                positionIndicator(targetFolder, after);
                dropCurrent = { type: after ? 'after-folder' : 'before-folder', folderId: targetFolder.dataset.folderId };
            }
        }
    }

    function positionIndicator(el, after) {
        if (!dropIndicator) return;
        const rect = el.getBoundingClientRect();
        dropIndicator.style.display  = 'block';
        dropIndicator.style.position = 'fixed';
        dropIndicator.style.left     = rect.left + 'px';
        dropIndicator.style.width    = rect.width + 'px';
        dropIndicator.style.top      = (after ? rect.bottom - 1 : rect.top) + 'px';
    }

    function positionAtRoot(clientY, container) {
        const children = [...container.children].filter(el =>
            !el.classList.contains('drop-indicator') &&
            !el.classList.contains('sidebar-add-folder-btn')
        );
        let insertBefore = null;
        for (const child of children) {
            const r = child.getBoundingClientRect();
            if (clientY < r.top + r.height / 2) { insertBefore = child; break; }
        }
        const ref = insertBefore || children[children.length - 1];
        if (ref) positionIndicator(ref, !insertBefore);
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
            const { id: tabId, srcFolderId } = dragging;
            const dc = dropCurrent;

            removeTabFromConfig(tabId, srcFolderId);

            if (dc.type === 'into-folder') {
                const fe = config.order.find(e => e.type === 'folder' && e.id === dc.folderId);
                if (fe) { fe.children.push(tabId); if (config.folders[dc.folderId]) config.folders[dc.folderId].expanded = true; }
            } else if (dc.type === 'before-tab' || dc.type === 'after-tab') {
                insertTabNearTab(tabId, dc.tabId, dc.folderId, dc.type === 'after-tab');
            } else {
                config.order.push({ type: 'tab', id: tabId });
            }
        } else if (dragging.type === 'folder') {
            const dc = dropCurrent;
            if (dc.type === 'before-folder' || dc.type === 'after-folder') {
                const srcEntry = config.order.find(e => e.type === 'folder' && e.id === dragging.id);
                const tgtEntry = config.order.find(e => e.type === 'folder' && e.id === dc.folderId);
                if (srcEntry && tgtEntry) {
                    config.order.splice(config.order.indexOf(srcEntry), 1);
                    const ti = config.order.indexOf(tgtEntry);
                    config.order.splice(dc.type === 'after-folder' ? ti + 1 : ti, 0, srcEntry);
                }
            }
        }

        storeSave();
        onDragEnd();
        render();
    }

    function removeTabFromConfig(tabId, srcFolderId) {
        if (srcFolderId) {
            const entry = config.order.find(e => e.type === 'folder' && e.id === srcFolderId);
            if (entry) entry.children = entry.children.filter(id => id !== tabId);
        } else {
            const idx = config.order.findIndex(e => e.type === 'tab' && e.id === tabId);
            if (idx >= 0) config.order.splice(idx, 1);
        }
    }

    function insertTabNearTab(tabId, nearTabId, nearFolderId, after) {
        if (nearFolderId) {
            const entry = config.order.find(e => e.type === 'folder' && e.id === nearFolderId);
            if (entry) {
                const idx = entry.children.indexOf(nearTabId);
                entry.children.splice(after ? idx + 1 : idx, 0, tabId);
            }
        } else {
            const idx = config.order.findIndex(e => e.type === 'tab' && e.id === nearTabId);
            if (idx >= 0) config.order.splice(after ? idx + 1 : idx, 0, { type: 'tab', id: tabId });
            else config.order.push({ type: 'tab', id: tabId });
        }
    }

    // ── Edit mode toggle ──────────────────────────────────────────────────────
    function enterEditMode() {
        editMode = true;
        document.querySelector('.sidebar-nav')?.classList.add('sidebar-edit-mode');
        updateToggleBtn();
        // Re-render dropdown to show edit controls
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
        btn.id        = 'cust-toggle';
        btn.className = 'cust-toggle-btn';
        btn.title     = 'Customize sidebar';
        updateToggleBtnContent(btn);
        btn.addEventListener('click', () => editMode ? exitEditMode() : enterEditMode());
        return btn;
    }

    function updateToggleBtnContent(btn) {
        if (!btn) return;
        if (editMode) {
            btn.innerHTML = '<i class="fas fa-check"></i><span>Done</span>';
            btn.classList.add('edit-active');
        } else {
            btn.innerHTML = '<i class="fas fa-sliders"></i><span>Customize</span>';
            btn.classList.remove('edit-active');
        }
    }

    function updateToggleBtn() {
        updateToggleBtnContent(document.getElementById('cust-toggle'));
    }

    // ── Watch body class changes for mode switching ───────────────────────────
    function watchMode() {
        const observer = new MutationObserver(() => {
            applyMode(getCurrentMode());
            if (!editMode) render();
        });
        observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        const sidebarBottom = document.querySelector('.sidebar-nav .sidebar-bottom');
        if (!sidebarBottom) return;

        store = storeLoad();
        syncConfig();

        // Build controls — profile switcher + customize button
        const customizeBtn   = buildToggleBtn();
        const profileSwitcher = buildProfileSwitcher();

        sidebarBottom.prepend(customizeBtn);
        sidebarBottom.prepend(profileSwitcher);

        watchMode();
        render();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        setTimeout(init, 120);
    }
})();
