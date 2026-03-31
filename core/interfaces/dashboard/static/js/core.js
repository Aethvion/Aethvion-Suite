// Aethvion Suite - Core
// Handles WebSocket connections, global UI state, and initialization

// ─── Toast System ─────────────────────────────────────────────────
/**
 * Show a toast notification.
 * @param {string} message
 * @param {'success'|'error'|'warn'|'info'} type
 * @param {number} duration ms (default 3500)
 */
/**
 * Show a toast notification.
 * @param {string} message
 * @param {'success'|'error'|'warn'|'info'} type
 * @param {number} duration ms (default 3500)
 * @param {{ undoLabel?: string, onUndo?: Function }} opts
 * @returns {{ dismiss: Function }} handle to dismiss programmatically
 */
function showToast(message, type = 'info', duration = 3500, opts = {}) {
    const container = document.getElementById('toast-container');
    if (!container) { console.warn('[toast]', message); return { dismiss: () => {} }; }

    const icons = {
        success: 'fa-circle-check',
        error:   'fa-circle-xmark',
        warn:    'fa-triangle-exclamation',
        info:    'fa-circle-info',
    };
    const toast = document.createElement('div');
    toast.className = `ae-toast ae-toast-${type}`;
    toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${message}</span>`;

    if (opts.undoLabel && opts.onUndo) {
        const undoBtn = document.createElement('button');
        undoBtn.className = 'ae-toast-undo-btn';
        undoBtn.textContent = opts.undoLabel;
        undoBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            clearTimeout(timer);
            opts.onUndo();
            remove();
        });
        toast.appendChild(undoBtn);
    }

    container.appendChild(toast);

    const remove = () => {
        toast.classList.add('removing');
        toast.addEventListener('animationend', () => toast.remove(), { once: true });
    };
    const timer = setTimeout(remove, duration);
    toast.addEventListener('click', () => { clearTimeout(timer); remove(); });
    return { dismiss: () => { clearTimeout(timer); remove(); } };
}
window.showToast = showToast;

// ─── Confirm Modal ────────────────────────────────────────────────
/**
 * Non-blocking confirmation dialog (replaces window.confirm).
 * @param {string} title
 * @param {string} body
 * @param {Function} onConfirm callback when user clicks OK
 * @param {object} opts  { confirmLabel, icon }
 */
function showConfirm(title, body, onConfirm, opts = {}) {
    const overlay  = document.getElementById('confirm-modal');
    if (!overlay) { if (confirm(body)) onConfirm(); return; }

    document.getElementById('confirm-modal-title').textContent = title;
    document.getElementById('confirm-modal-body').textContent  = body;

    const okBtn  = document.getElementById('confirm-modal-ok');
    const canBtn = document.getElementById('confirm-modal-cancel');
    okBtn.textContent = opts.confirmLabel || 'Confirm';

    const iconEl = document.getElementById('confirm-modal-icon-i');
    if (iconEl) iconEl.className = `fas ${opts.icon || 'fa-exclamation-triangle'}`;

    // Save focus so we can restore it on close
    const previousFocus = document.activeElement;
    overlay.style.display = 'flex';
    // Autofocus OK after paint
    requestAnimationFrame(() => okBtn.focus());

    const close = () => {
        overlay.classList.add('hiding');
        overlay.addEventListener('animationend', () => {
            overlay.style.display = 'none';
            overlay.classList.remove('hiding');
            // Restore focus to what was active before the modal
            if (previousFocus && typeof previousFocus.focus === 'function') {
                previousFocus.focus();
            }
        }, { once: true });
    };

    const handleOk  = () => { close(); onConfirm(); cleanup(); };
    const handleCan = () => { close(); cleanup(); };
    const handleKey = (e) => {
        if (e.key === 'Escape') { handleCan(); return; }
        if (e.key === 'Enter')  { handleOk();  return; }
        // Focus trap — keep Tab cycling inside modal
        if (e.key === 'Tab') {
            e.preventDefault();
            if (document.activeElement === okBtn) { canBtn.focus(); }
            else { okBtn.focus(); }
        }
    };

    const cleanup = () => {
        okBtn.removeEventListener('click', handleOk);
        canBtn.removeEventListener('click', handleCan);
        document.removeEventListener('keydown', handleKey);
    };

    okBtn.addEventListener('click', handleOk);
    canBtn.addEventListener('click', handleCan);
    document.addEventListener('keydown', handleKey);
}
window.showConfirm = showConfirm;

// ─── Keyboard Shortcuts Overlay ───────────────────────────────────
function initKeyboardShortcuts() {
    const overlay = document.getElementById('kbd-overlay');
    if (!overlay) return;

    const open  = () => { overlay.style.display = 'flex'; }
    const close = () => {
        overlay.classList.add('hiding');
        overlay.addEventListener('animationend', () => {
            overlay.style.display = 'none';
            overlay.classList.remove('hiding');
        }, { once: true });
    };

    document.addEventListener('keydown', (e) => {
        const tag = document.activeElement.tagName;
        const editable = tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement.isContentEditable;

        // ? opens overlay (only when not in an input)
        if (e.key === '?' && !editable) { e.preventDefault(); open(); return; }
        // Esc closes overlay
        if (e.key === 'Escape' && overlay.style.display !== 'none') { e.preventDefault(); close(); return; }

        // Global shortcuts (work even in inputs for Ctrl/Alt combos)
        if (e.ctrlKey && !e.shiftKey && !e.altKey) {
            if (e.key === 'b' || e.key === 'B') {
                e.preventDefault();
                const nav = document.getElementById('sidebar-nav');
                if (nav) {
                    const collapsed = nav.classList.toggle('collapsed');
                    if (typeof prefs !== 'undefined') prefs.set('sidebar_collapsed', collapsed);
                }
                return;
            }
            if (e.key === 'h' || e.key === 'H') {
                e.preventDefault();
                const btn = document.getElementById('toggle-threads-btn');
                if (btn) btn.click();
                return;
            }
            if (e.key === 't' || e.key === 'T') {
                e.preventDefault();
                const newBtn = document.getElementById('new-thread-button') || document.getElementById('header-new-thread-btn');
                if (newBtn) newBtn.click();
                return;
            }
            if (e.key === 'l' || e.key === 'L') {
                e.preventDefault();
                const input = document.getElementById('chat-input');
                if (input) input.focus();
                return;
            }
            if (e.key === '1') { e.preventDefault(); switchMainTab('suite-home'); return; }
            if (e.key === '2') { e.preventDefault(); switchMainTab('chat'); return; }
        }
        if (e.altKey && !e.ctrlKey) {
            if (e.key === '1') { e.preventDefault(); setDashboardMode('home'); return; }
            if (e.key === '2') { e.preventDefault(); setDashboardMode('ai'); return; }
        }
    });

    // Close on backdrop click
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
}

// Global variables
let chatWs = null;
let logsWs = null;
let agentsWs = null;
// Global UI State
let currentMainTab = 'chat';
let dashboardMode = 'home'; // 'home' or 'ai'
let devModeActive = false;

function initDevMode() {
    const btn = document.getElementById('btn-toggle-dev-mode');
    if (!btn || btn.dataset.initialized) return;
    btn.dataset.initialized = 'true';

    btn.addEventListener('click', () => {
        devModeActive = !devModeActive;
        const icon = btn.querySelector('i');
        const envContainer = document.getElementById('env-status-container');

        if (devModeActive) {
            btn.classList.add('active');
            icon.className = 'fas fa-lock-open';
            if (typeof loadEnvStatus === 'function') loadEnvStatus();
        } else {
            btn.classList.remove('active');
            icon.className = 'fas fa-lock';
            if (envContainer) envContainer.innerHTML = '<div class="locked-placeholder"><i class="fas fa-lock"></i> Developer Mode Restricted</div>';
        }
    });

    // Handle initial state
    if (devModeActive) {
        const icon = btn.querySelector('i');
        btn.classList.add('active');
        icon.className = 'fas fa-lock-open';
        if (typeof loadEnvStatus === 'function') loadEnvStatus();
    }
}

// Available Workspaces (from server config if any, mostly legacy but kept for reference)
let availableWorkspaces = [];

document.addEventListener('DOMContentLoaded', async () => {
    // Start polling startup status (non-blocking)
    pollStartupStatus();

    initializeWebSockets();
    const refreshMemory = document.getElementById('refresh-memory-btn');
    if (refreshMemory) refreshMemory.addEventListener('click', loadMemoryData);

    initializeUI();
    updateSystemInfo();

    // Apply default mode immediately so nothing looks broken on load
    setDashboardMode('home', false);

    try {
        // Load preferences safely before heavy data initialization
        if (typeof prefs !== 'undefined' && typeof prefs.load === 'function') {
            await prefs.load();

            // Restore dashboard mode
            const mode = prefs.get('dashboard_mode', 'home');
            setDashboardMode(mode, false);

            // Restore sidebar state
            const sidebarCollapsed = prefs.get('sidebar_collapsed', false);
            if (sidebarCollapsed === true || sidebarCollapsed === 'true') {
                const sidebarNav = document.getElementById('sidebar-nav');
                if (sidebarNav) sidebarNav.classList.add('collapsed');
            }
            
            // Restore threads collapsed state
            const threadsCollapsed = prefs.get('threads_collapsed', false);
            if (threadsCollapsed === true || threadsCollapsed === 'true') {
                const layout = document.querySelector('.three-column-layout');
                if (layout) layout.classList.add('threads-collapsed');
            }

            // Restore category collapse states
            initCategoryCollapse();

            // Apply interface visibility preferences (hidden tabs/categories)
            applyNavVisibility();

            // The active tab is now restored automatically by setDashboardMode
        } else {
            // Fallback (redundant fetch but keeping for safety if view-settings isn't loaded)
            let fallbackMode = 'home';
            const modeRes = await fetch('/api/preferences/get?key=dashboard_mode');
            if (modeRes.ok) {
                const modeData = await modeRes.json();
                if (modeData.value) {
                    fallbackMode = modeData.value;
                    setDashboardMode(fallbackMode, false);
                }
            }
            const tabRes = await fetch(`/api/preferences/get?key=active_tab_${fallbackMode}`);
            if (tabRes.ok) {
                const tabData = await tabRes.json();
                if (tabData.value) switchMainTab(tabData.value, false);
            }
            const sidebarRes = await fetch('/api/preferences/get?key=sidebar_collapsed');
            if (sidebarRes.ok) {
                const sidebarData = await sidebarRes.json();
                if (sidebarData.value === true || sidebarData.value === 'true') {
                    const sidebarNav = document.getElementById('sidebar-nav');
                    if (sidebarNav) sidebarNav.classList.add('collapsed');
                }
            }
            const threadsRes = await fetch('/api/preferences/get?key=threads_collapsed');
            if (threadsRes.ok) {
                const threadsData = await threadsRes.json();
                if (threadsData.value === true || threadsData.value === 'true') {
                    const layout = document.querySelector('.three-column-layout');
                    if (layout) layout.classList.add('threads-collapsed');
                }
            }
        }
    } catch (e) {
        console.warn("Error restoring UI state:", e);
    }

    // Now proceed with potentially failing heavier data loads
    try {
        initDevMode();
        initKeyboardShortcuts();
        initColumnResizeHandles();
        await loadInitialData();
        if (window.runStartupUpdateCheck) window.runStartupUpdateCheck();
    } catch (e) {
        console.error("Error during initial data load:", e);
    }
});

/**
 * Polls the system startup status and updates the splash screen.
 */
async function pollStartupStatus() {
    const splash = document.getElementById('startup-splash');
    const progressBar = document.getElementById('splash-progress');
    const statusText = document.getElementById('splash-status-text');

    if (!splash) return;

    // Fetch version independently for the splash screen
    const splashVersion = document.getElementById('splash-version');
    if (splashVersion) {
        fetch('/static/assets/system-status.json?v=' + Date.now())
            .then(r => r.json())
            .then(data => {
                if (data.system) {
                    splashVersion.textContent = `BUILD v${data.system.version}`;
                }
            }).catch(e => console.warn("Could not load version for splash:", e));
    }

    return new Promise((resolve) => {
        const checkStatus = async () => {
            try {
                const response = await fetch('/api/system/startup-status');
                if (response.ok) {
                    const data = await response.json();

                    if (progressBar) progressBar.style.width = `${data.progress}%`;
                    if (statusText) statusText.textContent = data.status;

                    if (data.initialized) {
                        // All systems go!
                        setTimeout(() => {
                            splash.classList.add('fade-out');
                            setTimeout(() => {
                                splash.style.display = 'none';
                                window.dispatchEvent(new CustomEvent('systemReady'));
                                resolve();
                            }, 800);
                        }, 500);
                        return;
                    }

                    if (data.error) {
                        if (statusText) {
                            statusText.textContent = `CRITICAL ERROR: ${data.error}`;
                            statusText.style.color = 'var(--error)';
                        }
                        return; // Stop polling on hard error
                    }
                }
            } catch (err) {
                console.warn("Startup status fetch failed, retrying...", err);
            }
            // Poll again in 500ms
            setTimeout(checkStatus, 500);
        };

        checkStatus();
    });
}

// ===== WebSocket Management =====

function initializeWebSockets() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = window.location.host;

    // Chat WebSocket
    chatWs = new WebSocket(`${wsProtocol}//${wsHost}/ws/chat`);
    chatWs.onopen = () => updateConnectionStatus(true);
    chatWs.onclose = () => {
        updateConnectionStatus(false);
        setTimeout(initializeWebSockets, 3000); // Reconnect
    };
    if (typeof handleChatMessage === 'function') chatWs.onmessage = handleChatMessage;

    // Logs WebSocket
    logsWs = new WebSocket(`${wsProtocol}//${wsHost}/ws/logs`);
    if (typeof handleLogMessage === 'function') logsWs.onmessage = handleLogMessage;

    // Agents WebSocket
    agentsWs = new WebSocket(`${wsProtocol}//${wsHost}/ws/agents`);
    if (typeof handleAgentsUpdate === 'function') agentsWs.onmessage = handleAgentsUpdate;
}

function updateConnectionStatus(connected) {
    const indicator = document.getElementById('status-indicator');
    if (!indicator) return;
    const dot = indicator.querySelector('.status-dot');
    const text = indicator.querySelector('.status-text');

    if (connected) {
        dot.classList.add('connected');
        text.textContent = 'Connected';
    } else {
        dot.classList.remove('connected');
        text.textContent = 'Disconnected';
    }
}

// ===== UI Initialization =====

function initializeUI() {
    // Main tab switching
    document.querySelectorAll('.main-tab').forEach(tab => {
        if (tab.dataset.maintab) {
            tab.addEventListener('click', (e) => {
                if (e.target.closest('.launch-shortcut')) return;
                switchMainTab(tab.dataset.maintab);
            });
        }
    });

    // Unified Module Launch Listener (Sidebar shortcuts and Panel buttons)
    document.addEventListener('click', (e) => {
        const launchBtn = e.target.closest('.launch-shortcut, .module-launch-btn');
        if (launchBtn) {
            e.stopPropagation(); // Prevent tab switching if it's a shortcut inside a button
            if (launchBtn.disabled) return;
            const moduleName = launchBtn.getAttribute('data-launch');
            launchModule(moduleName);
        }
    });

    // Module Panel Action Listeners
    document.addEventListener('click', async (e) => {
        const runBtn = e.target.closest('.run-module-btn');
        if (runBtn) {
            const moduleName = runBtn.getAttribute('data-module');
            await runModuleService(moduleName);
        }

        const folderBtn = e.target.closest('.open-folder-btn');
        if (folderBtn) {
            const path = folderBtn.getAttribute('data-path');
            await openModuleFolder(path);
        }
    });
    
    // Periodically update module badges
    setInterval(updateModuleStatusBadges, 10000);
    setTimeout(updateModuleStatusBadges, 2000);

    // Sidebar Toggle
    const sidebarToggleBtn = document.getElementById('sidebar-toggle');
    const sidebarNav = document.getElementById('sidebar-nav');
    if (sidebarToggleBtn && sidebarNav) {
        sidebarToggleBtn.addEventListener('click', () => {
            sidebarNav.classList.toggle('collapsed');
            if (typeof savePreference === 'function') {
                savePreference('sidebar_collapsed', sidebarNav.classList.contains('collapsed'));
            }
        });
    }

    // Register mode toggle handlers
    document.querySelectorAll('#dashboard-mode-toggle .mode-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            setDashboardMode(this.dataset.value);
        });
    });

    // Threads Collapse Toggle
    const toggleThreadsBtn = document.getElementById('toggle-threads-btn');
    const threeColumnLayout = document.querySelector('.three-column-layout');
    
    if (toggleThreadsBtn && threeColumnLayout) {
        toggleThreadsBtn.addEventListener('click', () => {
            threeColumnLayout.classList.toggle('threads-collapsed');
            if (typeof savePreference === 'function') {
                savePreference('threads_collapsed', threeColumnLayout.classList.contains('threads-collapsed'));
            }
        });
    }

    // Chat interaction
    const chatInput = document.getElementById('chat-input');

    // Auto-resize textarea
    if (chatInput) {
        chatInput.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
            if (this.value === '') this.style.height = '';
        });
    }

    // Files filters
    const domainFilter = document.getElementById('domain-filter');
    const typeFilter = document.getElementById('type-filter');
    const refreshFilesList = document.getElementById('refresh-files');

    if (domainFilter) domainFilter.addEventListener('change', loadFiles);
    if (typeFilter) typeFilter.addEventListener('change', loadFiles);
    // if (refreshFilesList) refreshFilesList.addEventListener('click', loadFiles);

    // Tools forge button
    const forgeBtn = document.getElementById('forge-tool-button');
    if (forgeBtn) {
        forgeBtn.addEventListener('click', () => {
            showToast('Tool forging via UI coming soon! Use chat: "Create a tool to…"', 'info', 5000);
        });
    }

    // Voice Mode Toggle
    const voiceButton = document.getElementById('voice-mode-toggle');
    if (voiceButton) {
        voiceButton.addEventListener('click', () => {
            startVoiceInput();
        });
    }

    // Add File Button (Main Chat)
    const addFileBtn = document.querySelector('.add-file-btn');
    const chatFileInput = document.getElementById('chat-file-input');
    window._mainChatAttachedFile = null;

    if (addFileBtn && chatFileInput) {
        addFileBtn.addEventListener('click', () => {
            chatFileInput.click();
        });

        chatFileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;

            window._mainChatAttachedFile = { name: file.name, file: file };

            // Find or create the pill
            let pill = document.getElementById('chat-file-pill');
            if (!pill) {
                pill = document.createElement('div');
                pill.id = 'chat-file-pill';
                pill.className = 'chat-file-pill';
                // Insert it before the add-file-btn
                addFileBtn.parentNode.insertBefore(pill, addFileBtn);
            }

            pill.innerHTML = `
                <i class="fas fa-file-alt"></i>
                <span>${file.name}</span>
                <button class="pill-clear" title="Remove attachment">✕</button>
            `;

            pill.querySelector('.pill-clear').addEventListener('click', (ev) => {
                ev.stopPropagation();
                window.clearMainChatAttachment();
            });

            // Reset input
            e.target.value = '';
        });
    }

    window.clearMainChatAttachment = function () {
        window._mainChatAttachedFile = null;
        const pill = document.getElementById('chat-file-pill');
        if (pill) {
            pill.remove();
        }
    };

    // Package tab switching
    document.querySelectorAll('.package-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.packagetab;

            document.querySelectorAll('.package-tab').forEach(t => {
                t.classList.toggle('active', t.dataset.packagetab === tabName);
            });

            document.querySelectorAll('.package-tab-panel').forEach(panel => {
                panel.classList.toggle('active', panel.id === `${tabName}-packages`);
            });
        });
    });

    // Split Button Logic (Chat/Agent/Image/Arena)
    const dropdownWrapper = document.querySelector('.main-tab-dropdown');
    const arrowBtn = dropdownWrapper ? dropdownWrapper.querySelector('.split-arrow-action') : null;
    const mainActionBtn = dropdownWrapper ? dropdownWrapper.querySelector('.split-main-action') : null;

    if (arrowBtn && dropdownWrapper) {
        arrowBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdownWrapper.classList.toggle('open');
        });
    }

    if (mainActionBtn) {
        mainActionBtn.addEventListener('click', () => {
            const mode = mainActionBtn.dataset.maintab;
            switchMainTab(mode);
        });
    }

    // Dropdown items
    document.querySelectorAll('.tab-dropdown-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            const subtab = item.dataset.subtab;
            switchMainTab(subtab);
            if (dropdownWrapper) dropdownWrapper.classList.remove('open');
        });
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', () => {
        if (dropdownWrapper) dropdownWrapper.classList.remove('open');
    });

    if (typeof initializeArena === 'function') initializeArena();
    if (typeof initializeImageStudio === 'function') initializeImageStudio();
}

/**
 * Updates system-wide information like version number from system-status.json
 */
async function updateSystemInfo() {
    const heroVersion = document.getElementById('suite-hero-version');
    if (!heroVersion) return;

    try {
        const response = await fetch('/static/assets/system-status.json?v=' + Date.now());
        if (response.ok) {
            const data = await response.json();
            if (data.system && data.system.version) {
                heroVersion.textContent = `Version ${data.system.version}`;
            }
        }
    } catch (e) {
        console.warn("Failed to update system info:", e);
    }
}

// ------------------------------------------------------------------
// Main Navigation Logic
// ------------------------------------------------------------------
function setDashboardMode(mode, save = true) {
    if (mode !== 'home' && mode !== 'ai') return;
    dashboardMode = mode;

    if (save && typeof savePreference === 'function') {
        savePreference('dashboard_mode', dashboardMode);
    }

    // Update toggle buttons UI visually
    document.querySelectorAll('#dashboard-mode-toggle .mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.value === dashboardMode);
    });

    // Toggle body classes for theme overrides
    document.body.classList.remove('theme-home', 'theme-ai');
    document.body.classList.add(`theme-${dashboardMode}`);

    // Hide/Show navigation elements based on mode
    const modeClasses = ['mode-home', 'mode-ai'];
    document.querySelectorAll('[class*="mode-"]').forEach(el => {
        const classes = Array.from(el.classList).filter(cls => modeClasses.includes(cls));
        if (classes.length === 0) return;
        if (el.classList.contains(`mode-${dashboardMode}`)) {
            el.classList.remove('mode-hidden');
        } else {
            el.classList.add('mode-hidden');
        }
    });

    // Restore the last active tab for this mode
    let targetTab = dashboardMode === 'home' ? 'suite-home' : 'chat';
    if (typeof prefs !== 'undefined' && typeof prefs.get === 'function') {
        const savedTab = prefs.get(`active_tab_${dashboardMode}`);
        if (savedTab) targetTab = savedTab;
    }

    // Validate target tab exists and isn't hidden
    const targetBtn = document.querySelector(`.main-tab[data-maintab="${targetTab}"]`);
    if (!targetBtn || targetBtn.classList.contains('mode-hidden')) {
        targetTab = dashboardMode === 'home' ? 'suite-home' : 'chat';
    }

    switchMainTab(targetTab, false);
}

// ─── Sidebar Category Collapse ───────────────────────────────────
function initCategoryCollapse() {
    document.querySelectorAll('.sidebar-category[data-cat]').forEach(catEl => {
        const catId = catEl.dataset.cat;
        const body  = document.querySelector(`.cat-body[data-cat-body="${catId}"]`);
        if (!body) return;

        // Add tab count to label
        const tabCount = body.querySelectorAll('.main-tab').length;
        const labelEl = catEl.querySelector('.cat-label');
        if (labelEl && tabCount > 0) {
            if (!labelEl.dataset.origText) labelEl.dataset.origText = labelEl.textContent.trim();
            labelEl.textContent = `${labelEl.dataset.origText} (${tabCount})`;
        }

        // Restore saved state
        const collapsed = typeof prefs !== 'undefined' && prefs.get(`cat_collapsed_${catId}`, false);
        if (collapsed === true || collapsed === 'true') {
            body.classList.add('cat-collapsed');
            catEl.classList.add('cat-is-collapsed');
        }

        // Attach click listener (only once)
        if (!catEl.dataset.catInit) {
            catEl.dataset.catInit = '1';
            catEl.addEventListener('click', () => toggleCategory(catId));
        }
    });
}

function toggleCategory(catId) {
    const catEl = document.querySelector(`.sidebar-category[data-cat="${catId}"]`);
    const body  = document.querySelector(`.cat-body[data-cat-body="${catId}"]`);
    if (!catEl || !body) return;

    const isNowCollapsed = body.classList.toggle('cat-collapsed');
    catEl.classList.toggle('cat-is-collapsed', isNowCollapsed);

    if (typeof savePreference === 'function') {
        savePreference(`cat_collapsed_${catId}`, isNowCollapsed);
    }
}

function applyNavVisibility() {
    if (typeof prefs === 'undefined') return;

    // Categories
    document.querySelectorAll('.sidebar-category[data-cat]').forEach(catEl => {
        const catId = catEl.dataset.cat;
        const hidden = prefs.get(`nav_cat_hidden_${catId}`, false);
        const isHidden = hidden === true || hidden === 'true';
        const body = document.querySelector(`.cat-body[data-cat-body="${catId}"]`);
        catEl.classList.toggle('nav-hidden', isHidden);
        if (body) body.classList.toggle('nav-hidden', isHidden);
    });

    // Individual tabs (skip settings and version which are always visible)
    document.querySelectorAll('.main-tab[data-maintab]').forEach(tabEl => {
        const tabId = tabEl.dataset.maintab;
        if (!tabId || tabId === 'settings' || tabId === 'version') return;
        const hidden = prefs.get(`nav_tab_hidden_${tabId}`, false);
        tabEl.classList.toggle('nav-hidden', hidden === true || hidden === 'true');
    });
}
window.applyNavVisibility = applyNavVisibility;

// ─── Tab scroll-position memory ──────────────────────────────────
const _tabScrollPos = {};  // tabName → scrollTop

function _saveTabScroll(tabName) {
    const panel = document.getElementById(`${tabName}-panel`);
    if (panel) _tabScrollPos[tabName] = panel.scrollTop;
}
function _restoreTabScroll(tabName) {
    requestAnimationFrame(() => {
        const panel = document.getElementById(`${tabName}-panel`);
        if (panel && _tabScrollPos[tabName] !== undefined) {
            panel.scrollTop = _tabScrollPos[tabName];
        }
    });
}

// ─── Panel last-updated badge ─────────────────────────────────────
const _panelFetchTimes = {};

function markPanelUpdated(panelKey) {
    _panelFetchTimes[panelKey] = Date.now();
    _renderPanelTimestamp(panelKey);
}

function _renderPanelTimestamp(panelKey) {
    const ts = _panelFetchTimes[panelKey];
    if (!ts) return;
    const el = document.querySelector(`[data-panel-ts="${panelKey}"]`);
    if (!el) return;
    const diff = Math.round((Date.now() - ts) / 1000);
    let label = diff < 10 ? 'just now'
        : diff < 60  ? `${diff}s ago`
        : diff < 3600 ? `${Math.floor(diff/60)}m ago`
        : `${Math.floor(diff/3600)}h ago`;
    el.textContent = `Updated ${label}`;
    el.title = new Date(ts).toLocaleTimeString();
}

// Refresh all displayed timestamps every 30s
setInterval(() => {
    Object.keys(_panelFetchTimes).forEach(_renderPanelTimestamp);
}, 30000);
window.markPanelUpdated = markPanelUpdated;

function switchMainTab(tabName, save = true) {
    if (!tabName) return;

    // Save scroll of the tab we're leaving
    if (currentMainTab) _saveTabScroll(currentMainTab);
    // Clear thread search when leaving chat
    if (currentMainTab === 'chat' && tabName !== 'chat' && window._clearThreadSearch) {
        window._clearThreadSearch();
    }

    let actualTabName = tabName;
    if (tabName === 'agent') actualTabName = 'chat'; // Legacy mapping

    currentMainTab = actualTabName;
    if (save && typeof savePreference === 'function') {
        savePreference(`active_tab_${dashboardMode}`, actualTabName);
    }

    // Update tab buttons
    document.querySelectorAll('.main-tab').forEach(tab => {
        if (tab.closest('.main-tab-dropdown')) {
            if (tab.classList.contains('split-main-action')) {
                const categories = ['chat', 'photo', 'audio', 'arena', 'aiconv', 'advaiconv'];
                const isActive = categories.includes(actualTabName);
                tab.classList.toggle('active', isActive);

                if (isActive) {
                    tab.dataset.maintab = actualTabName;
                    let icon = '💬';
                    let label = 'Chat';
                    if (actualTabName === 'photo') { icon = '🎨'; label = 'Photo'; }
                    if (actualTabName === 'audio') { icon = '🎙️'; label = 'Audio'; }
                    if (actualTabName === 'arena') { icon = '⚔️'; label = 'Arena'; }
                    if (actualTabName === 'aiconv') { icon = '🎭'; label = 'AI Conv'; }
                    if (actualTabName === 'advaiconv') { icon = '🧪'; label = 'Adv AI Conv'; }
                    tab.innerHTML = `<span class="tab-icon">${icon}</span>${label}`;
                }
            } else if (tab.classList.contains('split-arrow-action')) {
                const categories = ['chat', 'photo', 'audio', 'arena', 'aiconv', 'advaiconv'];
                const isActive = categories.includes(actualTabName);
                tab.classList.toggle('active', isActive);
            }
        } else if (tab.closest('.nav-dropdown')) {
            const dropdownTrigger = tab.closest('.nav-dropdown').querySelector('.dropdown-trigger');
            if (dropdownTrigger) {
                const subItems = tab.closest('.nav-dropdown').querySelectorAll('.nav-dropdown-item');
                let isParentActive = false;
                subItems.forEach(item => {
                    if (item.dataset.subtab === actualTabName) isParentActive = true;
                });
                dropdownTrigger.classList.toggle('active', isParentActive);
            }
        } else {
            tab.classList.toggle('active', tab.dataset.maintab === actualTabName);
        }
    });

    // Update Nav Dropdown active state
    document.querySelectorAll('.nav-dropdown-item').forEach(item => {
        item.classList.toggle('active', item.dataset.subtab === actualTabName);
    });

    // Update Sub-tab active state in split dropdown
    document.querySelectorAll('.tab-dropdown-item').forEach(item => {
        item.classList.toggle('active', item.dataset.subtab === actualTabName);
    });

    // Update panels
    document.querySelectorAll('.main-tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });

    // Files sub-tabs re-use files-panel
    let panelId = `${actualTabName}-panel`;
    const filesTabs = ['output', 'screenshots', 'camera', 'uploads'];
    if (filesTabs.includes(actualTabName)) panelId = 'files-panel';

    const targetPanel = document.getElementById(panelId);
    if (targetPanel) targetPanel.classList.add('active');

    // Load data for tab dynamically
    if (filesTabs.includes(actualTabName) && typeof loadFiles === 'function') loadFiles(actualTabName);
    else if (actualTabName === 'files' && typeof loadFiles === 'function') loadFiles('output');
    else if (actualTabName === 'tracking' && typeof loadTrackingDashboard === 'function') loadTrackingDashboard();
    else if (actualTabName === 'vtuber' && typeof loadVTuberDashboard === 'function') loadVTuberDashboard();
    else if (actualTabName === 'settings' && typeof loadProviderSettings === 'function') loadProviderSettings();
    else if (actualTabName === 'usage' && typeof loadUsageDashboard === 'function') loadUsageDashboard();
    else if (actualTabName === 'image' && typeof loadImageModels === 'function') loadImageModels();
    else if (actualTabName === 'arena' && typeof loadArenaModels === 'function') {
        loadArenaModels();
        if (typeof loadArenaLeaderboard === 'function') loadArenaLeaderboard();
    }
    else if (actualTabName === 'aiconv' && typeof loadArenaModels === 'function') loadArenaModels();
    else if (actualTabName === 'status' && typeof loadSystemStatusTab === 'function') loadSystemStatusTab();
    else if (actualTabName === 'audio' && typeof initializeAudioStudio === 'function') {
        initializeAudioStudio();
    }
    else if (actualTabName === 'misaka-cipher' && typeof initializeMisakaCipher === 'function') {
        initializeMisakaCipher();
    }
    else if (actualTabName === 'misaka-memory' && typeof refreshMisakaMemory === 'function') {
        refreshMisakaMemory();
    }
    else if (actualTabName.startsWith('game-') && typeof handleGameTabSwitch === 'function') {
        const gameType = actualTabName.replace('game-', '');
        handleGameTabSwitch(gameType);
    }
    else if (actualTabName === 'agents' && typeof onAgentsPanelActivated === 'function') {
        onAgentsPanelActivated();
    }
    else if (actualTabName === 'agent-corp' && typeof onCorpPanelActivated === 'function') {
        onCorpPanelActivated();
    }
    else if (actualTabName === 'documentation' && typeof loadDocumentation === 'function') {
        loadDocumentation();
    }

    // Restore scroll position for the new tab
    _restoreTabScroll(actualTabName);

    // Dispatch event for other views to react
    document.dispatchEvent(new CustomEvent('tabChanged', { detail: { tab: actualTabName } }));
}

/**
 * Tab initialization registry
 */
const tabInitializers = {};
function registerTabInit(tabName, initFn) {
    tabInitializers[tabName] = initFn;
    // If we're already on this tab, run it now
    if (typeof currentMainTab !== 'undefined' && currentMainTab === tabName) {
        initFn();
    }
}

/**
 * Ensures a specific main tab is active, and then optionally switches to a subtab.
 * @param {string} mainTab - The ID of the main tab (e.g., 'settings').
 * @param {string} [subTab] - The ID of the subtab (e.g., 'env').
 */
function ensureTabAndSubTab(mainTab, subTab = null) {
    if (currentMainTab !== mainTab) {
        switchMainTab(mainTab);
    }

    if (subTab) {
        if (mainTab === 'settings' && typeof window.switchSettingsSubTab === 'function') {
            window.switchSettingsSubTab(subTab);
        }
        // Add other subtab handlers here if needed (e.g., for 'files' or 'tools')
    }
}

// Attach to window
window.ensureTabAndSubTab = ensureTabAndSubTab;



/**
 * Launches an Aethvion module in a new tab by looking up its registered port.
 */
async function launchModule(name) {
    try {
        console.log(`Launching module: ${name}`);
        const response = await fetch('/api/system/ports');
        if (!response.ok) throw new Error("Failed to fetch registered ports");
        
        const ports = await response.json();
        // Fuzzy search for the module name in the registered list
        let port = null;
        const nameLower = name.toLowerCase();
        for (const [p, m] of Object.entries(ports)) {
            if (m.toLowerCase().includes(nameLower)) {
                port = p;
                break;
            }
        }
        if (port) {
            window.open(`http://localhost:${port}`, '_blank');
        } else {
            // Fallback to default ports if not registered yet
            const defaults = { 'vtuber': 8081, 'tracking': 8082, 'photo': 8083, 'audio': 8083, 'driveinfo': 8084, 'finance': 8085 };
            const defaultPort = defaults[name.toLowerCase()];
            if (defaultPort) {
                console.warn(`Module ${name} not found in dynamic ports, trying default :${defaultPort}`);
                window.open(`http://localhost:${defaultPort}`, '_blank');
            } else {
                showToast(`Module "${name}" is not running. Start the service first.`, 'warn');
            }
        }
    } catch (error) {
        console.error("Module launch error:", error);
        showToast('Failed to launch module. Check the console for details.', 'error');
    }
}

/**
 * Runs a module startup script via the backend.
 */
async function runModuleService(moduleName) {
    const btn = document.querySelector(`.run-module-btn[data-module="${moduleName}"]`);
    const originalText = btn ? btn.innerText : 'START SERVICE';
    
    if (btn) {
        btn.disabled = true;
        btn.innerText = 'STARTING...';
    }

    try {
        const response = await fetch('/api/system/modules/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ module: moduleName, action: 'run' })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to start module");
        }

        const result = await response.json();
        console.log(result.message);
        showToast(`Starting ${moduleName}…`, 'info');

        // Wait a bit and then check for ports
        setTimeout(() => {
            if (window.updateRegisteredPorts) window.updateRegisteredPorts();
            updateModuleStatusBadges();
        }, 3000);

    } catch (error) {
        console.error("Run module error:", error);
        showToast(`Failed to start module: ${error.message}`, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = originalText;
        }
    }
}

/**
 * Opens a folder path in Windows Explorer via the backend.
 */
async function openModuleFolder(path) {
    try {
        const response = await fetch('/api/system/modules/open-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });

        if (!response.ok) throw new Error("Failed to open folder");
    } catch (error) {
        console.error("Open folder error:", error);
        showToast('Failed to open folder.', 'error');
    }
}

/**
 * Updates status badges for modules based on registered ports.
 */
async function updateModuleStatusBadges() {
    try {
        const response = await fetch('/api/system/ports');
        if (!response.ok) return;
        const ports = await response.json();
        
        const registeredModules = Object.values(ports).map(m => m.toLowerCase());

        ['vtuber', 'tracking', 'photo', 'audio', 'driveinfo', 'finance'].forEach(mod => {
            const badge = document.getElementById(`${mod}-status-badge`);
            const headerLaunchBtn = document.querySelector(`.module-launch-btn[data-launch="${mod}"]`);
            const isOnline = registeredModules.some(m => m.includes(mod));

            // Update existing status badge if present
            if (badge) {
                badge.className = isOnline ? 'status-badge online' : 'status-badge offline';
                const txt = badge.querySelector('.status-text');
                if (txt) txt.innerText = isOnline ? 'RUNNING' : 'NOT RUNNING';
                if (headerLaunchBtn) headerLaunchBtn.disabled = !isOnline;
            }

            // Update hub card status dot
            const dot = document.querySelector(`.entry-status-dot[data-module="${mod}"]`);
            if (dot) {
                dot.className = `entry-status-dot ${isOnline ? 'running' : 'stopped'}`;
                dot.title = isOnline ? `${mod} — Running` : `${mod} — Not running`;
            }
        });
    } catch (e) {
        console.error("Badge update error:", e);
    }
}

// ===== Common Utilities =====

function formatNumber(n) {
    return new Intl.NumberFormat().format(n);
}

function formatCost(v) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(v);
}

// Attach to window
window.formatNumber = formatNumber;
window.formatCost = formatCost;

// ===== Initial Data Rendering =====
async function loadInitialData() {
    if (typeof loadPreferences === 'function') await loadPreferences();
    if (typeof loadHeaderStatus === 'function') await loadHeaderStatus();
    if (typeof loadSystemStatusTab === 'function') await loadSystemStatusTab();
    if (typeof loadTools === 'function') await loadTools();
    if (typeof loadPackages === 'function') loadPackages();
    if (typeof loadMemoryData === 'function') loadMemoryData();
    if (typeof loadChatModels === 'function') loadChatModels();

    if (typeof initThreadManagement === 'function') {
        initThreadManagement();
    }

    // On first boot the backend may not be fully ready when loadThreads() runs above.
    // Re-fetch once the system confirms it is initialized (splash dismissed → systemReady).
    window.addEventListener('systemReady', () => {
        if (typeof loadThreads === 'function') loadThreads();
    }, { once: true });

    if (currentMainTab === 'misaka-cipher' && typeof initializeMisakaCipher === 'function') {
        initializeMisakaCipher();
    }

    if (typeof loadSystemStatus === 'function') setInterval(loadSystemStatus, 5000);
    if (typeof loadPackages === 'function') setInterval(loadPackages, 10000);
    if (typeof loadHeaderStatus === 'function') setInterval(loadHeaderStatus, 15000);
}

// ===== Common UI Utilities =====

/**
 * Generates HTML options string for a categorized model dropdown.
 * @param {Object} data The registry data from /api/registry/models/{category}
 * @param {String} type 'chat' or 'agent' for profile selection
 * @param {String} selectedId Optional ID to mark as selected
 * @returns {String} HTML string of <optgroup> and <option> tags
 */
function generateCategorizedModelOptions(data, type = 'chat', selectedId = null) {
    if (!data) return '';

    // 1. Group Profiles
    let profilesHtml = `<optgroup label="${type === 'chat' ? 'Chat' : 'Agent'} Profiles">`;
    const autoSelected = (selectedId === 'auto' || !selectedId) ? 'selected' : '';

    // Only add Auto option if there is more than one model
    if (data.models && data.models.length > 1) {
        profilesHtml += `<option value="auto" ${autoSelected}>Auto (Complexity Routing)</option>`;
    }

    const profiles = type === 'chat' ? (data.chat_profiles || {}) : (data.agent_profiles || {});
    for (const [pName, pList] of Object.entries(profiles)) {
        const val = `profile:${type}:${pName}`;
        const s = val === selectedId ? 'selected' : '';
        profilesHtml += `<option value="${val}" ${s}>Profile: ${pName}</option>`;
    }
    profilesHtml += `</optgroup>`;

    // 2. Group Models by Provider
    const categorizedModels = {};
    for (const m of data.models || []) {
        if (!categorizedModels[m.provider]) {
            categorizedModels[m.provider] = [];
        }
        categorizedModels[m.provider].push(m);
    }

    let modelsHtml = '';
    const providerOrder = ['google_ai', 'openai', 'anthropic', 'grok', 'local'];

    for (const p of providerOrder) {
        if (!categorizedModels[p] || categorizedModels[p].length === 0) continue;

        const readableName = p === 'google_ai' ? 'Google AI' : p === 'openai' ? 'OpenAI' : p.charAt(0).toUpperCase() + p.slice(1);
        modelsHtml += `<optgroup label="${readableName}">`;

        for (const m of categorizedModels[p]) {
            const costHint = (m.input_cost_per_1m_tokens || m.output_cost_per_1m_tokens)
                ? ` ($${m.input_cost_per_1m_tokens}/$${m.output_cost_per_1m_tokens})`
                : '';
            const s = m.id === selectedId ? 'selected' : '';
            modelsHtml += `<option value="${m.id}" title="${m.description || ''}" ${s}>${m.id}${costHint}</option>`;
        }
        modelsHtml += `</optgroup>`;
    }

    return profilesHtml + modelsHtml;
}


// ===== Global Modal & Notification Handlers =====

/**
 * Shows a toast notification.
 * @param {string} message - The message to display.
 * @param {string} type - The type of notification (success, error, warning, info).
 * @param {number} duration - Duration in ms (default 3000).
 */
function showNotification(message, type = 'info', duration = 3000) {
    const container = document.getElementById('notification-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = 'info-circle';
    if (type === 'success') icon = 'check-circle';
    if (type === 'error') icon = 'exclamation-circle';
    if (type === 'warning') icon = 'exclamation-triangle';

    toast.innerHTML = `
        <div class="toast-icon"><i class="fas fa-${icon}"></i></div>
        <div class="toast-content">${message}</div>
        <div class="toast-close"><i class="fas fa-times"></i></div>
    `;

    container.appendChild(toast);

    // Fade in
    setTimeout(() => toast.classList.add('show'), 10);

    const close = () => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    };

    toast.querySelector('.toast-close').onclick = close;

    if (duration > 0) {
        setTimeout(close, duration);
    }
}

// Attach to window for global access
window.showNotification = showNotification;

function openCustomModal(htmlContent) {
    let modalOverlay = document.getElementById('global-modal-overlay');
    if (!modalOverlay) {
        modalOverlay = document.createElement('div');
        modalOverlay.id = 'global-modal-overlay';
        modalOverlay.className = 'modal-overlay';
        document.body.appendChild(modalOverlay);

        // click outside to close
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeModal();
        });
    }

    modalOverlay.innerHTML = htmlContent;
    modalOverlay.style.display = 'flex';
}

function closeModal() {
    const modalOverlay = document.getElementById('global-modal-overlay');
    if (modalOverlay) {
        modalOverlay.style.display = 'none';
        modalOverlay.innerHTML = '';
    }
}

// ===== Voice Input =====

// Voice input state
let _voiceRecognition = null;
let _voiceMediaRecorder = null;
let _voiceAudioChunks = [];
let _voiceInputActive = false;

async function getVoiceInputModel() {
    try {
        const res = await fetch('/api/settings');
        const settings = await res.json();
        return {
            model: (settings.voice && settings.voice.input_model) || 'browser',
            provider: (settings.voice && settings.voice.input_provider) || 'browser'
        };
    } catch (e) {
        return { model: 'browser', provider: 'browser' };
    }
}

function startVoiceInput() {
    const voiceButton = document.getElementById('voice-mode-toggle');
    if (_voiceInputActive) {
        stopVoiceInput();
        return;
    }

    // Check voice model from settings asynchronously, default to browser
    getVoiceInputModel().then(({ model, provider }) => {
        if (model === 'browser' || provider === 'browser') {
            _startBrowserSpeechRecognition(voiceButton);
        } else {
            _startMediaRecorderInput(voiceButton, model, provider);
        }
    });
}

function stopVoiceInput() {
    const voiceButton = document.getElementById('voice-mode-toggle');
    _voiceInputActive = false;

    if (_voiceRecognition) {
        _voiceRecognition.stop();
        _voiceRecognition = null;
    }
    if (_voiceMediaRecorder && _voiceMediaRecorder.state !== 'inactive') {
        _voiceMediaRecorder.stop();
    }

    if (voiceButton) {
        voiceButton.classList.remove('active');
        voiceButton.innerHTML = '<i class="fas fa-microphone"></i>';
        voiceButton.style.color = '';
        voiceButton.title = 'Voice Input';
    }
}

function _startBrowserSpeechRecognition(voiceButton) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        showNotification('Speech recognition is not supported in this browser. Try Chrome or Edge.', 'warning');
        return;
    }

    _voiceInputActive = true;
    if (voiceButton) {
        voiceButton.classList.add('active');
        voiceButton.innerHTML = '<i class="fas fa-stop"></i>';
        voiceButton.style.color = 'var(--accent)';
        voiceButton.title = 'Stop listening';
    }

    _voiceRecognition = new SpeechRecognition();
    _voiceRecognition.continuous = false;
    _voiceRecognition.interimResults = false;
    _voiceRecognition.lang = 'en-US';

    _voiceRecognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        const chatInput = document.getElementById('chat-input');
        if (chatInput && transcript) {
            chatInput.value = (chatInput.value ? chatInput.value + ' ' : '') + transcript;
            chatInput.dispatchEvent(new Event('input'));
        }
        stopVoiceInput();
    };

    _voiceRecognition.onerror = (event) => {
        if (event.error !== 'aborted') {
            showNotification(`Voice recognition error: ${event.error}`, 'error');
        }
        stopVoiceInput();
    };

    _voiceRecognition.onend = () => {
        if (_voiceInputActive) stopVoiceInput();
    };

    _voiceRecognition.start();
    showNotification('Listening... speak now', 'info');
}

function _startMediaRecorderInput(voiceButton, model, provider) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showNotification('Microphone access is not supported in this browser.', 'error');
        return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
        _voiceInputActive = true;
        _voiceAudioChunks = [];

        if (voiceButton) {
            voiceButton.classList.add('active');
            voiceButton.innerHTML = '<i class="fas fa-stop"></i>';
            voiceButton.style.color = 'var(--accent)';
            voiceButton.title = 'Stop recording';
        }
        showNotification('Recording... click mic to stop', 'info');

        // Pick the best supported mimeType for cross-browser compatibility
        const mimeTypes = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
        const supportedMime = mimeTypes.find(m => MediaRecorder.isTypeSupported(m)) || '';
        _voiceMediaRecorder = new MediaRecorder(stream, supportedMime ? { mimeType: supportedMime } : {});
        const recordedMime = _voiceMediaRecorder.mimeType || 'audio/webm';

        _voiceMediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) _voiceAudioChunks.push(e.data);
        };

        _voiceMediaRecorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            const blob = new Blob(_voiceAudioChunks, { type: recordedMime });
            _voiceAudioChunks = [];

            // Convert to base64 and send to backend for transcription
            const reader = new FileReader();
            reader.onloadend = async () => {
                try {
                    const res = await fetch('/api/voice/transcribe', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ audio: reader.result, model, provider })
                    });
                    const data = await res.json();
                    if (data.success && data.text) {
                        const chatInput = document.getElementById('chat-input');
                        if (chatInput) {
                            chatInput.value = (chatInput.value ? chatInput.value + ' ' : '') + data.text;
                            chatInput.dispatchEvent(new Event('input'));
                        }
                        showNotification('Voice transcribed successfully', 'success');
                    } else {
                        showNotification('Transcription failed: ' + (data.error || 'Unknown error'), 'error');
                    }
                } catch (err) {
                    showNotification('Voice transcription error: ' + err.message, 'error');
                }
            };
            reader.readAsDataURL(blob);
            stopVoiceInput();
        };

        _voiceMediaRecorder.start();
    }).catch((err) => {
        showNotification('Microphone access denied: ' + err.message, 'error');
        stopVoiceInput();
    });
}

window.startVoiceInput = startVoiceInput;
window.stopVoiceInput = stopVoiceInput;

// ─── Skeleton Loader Utility ──────────────────────────────────────
/**
 * Show a skeleton placeholder inside a container element.
 * @param {string|HTMLElement} target  CSS selector or element
 * @param {number} rows  number of skeleton lines to show
 */
function showSkeleton(target, rows = 4) {
    const el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el) return;
    el.dataset.skeletonPrev = el.innerHTML;
    el.innerHTML = Array.from({ length: rows }, (_, i) => `
        <div class="skeleton-card">
            <div class="skeleton skeleton-line ${i % 3 === 0 ? 'short' : i % 2 === 0 ? 'medium' : 'full'}"></div>
            <div class="skeleton skeleton-line full" style="height:10px;margin-top:6px;opacity:.6;"></div>
        </div>`).join('');
}

/**
 * Remove skeleton and restore previous content if available.
 * @param {string|HTMLElement} target
 */
function hideSkeleton(target) {
    const el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el || !el.dataset.skeletonPrev) return;
    el.innerHTML = el.dataset.skeletonPrev;
    delete el.dataset.skeletonPrev;
}
window.showSkeleton = showSkeleton;
window.hideSkeleton = hideSkeleton;

// ─── Column Resize Handles ────────────────────────────────────────
function initColumnResizeHandles() {
    const layout = document.querySelector('.three-column-layout');
    if (!layout) return;

    const setupHandle = (handleId, colVar, minPx, maxPx, side) => {
        const handle = document.getElementById(handleId);
        if (!handle) return;

        let startX = 0, startVal = 0;

        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            startX = e.clientX;
            const current = parseInt(getComputedStyle(layout).getPropertyValue(colVar)) || minPx;
            startVal = current;
            handle.classList.add('dragging');

            const onMove = (ev) => {
                const delta = side === 'left'
                    ? ev.clientX - startX
                    : startX - ev.clientX;
                const newVal = Math.min(maxPx, Math.max(minPx, startVal + delta));
                layout.style.setProperty(colVar, newVal + 'px');
            };
            const onUp = () => {
                handle.classList.remove('dragging');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    };

    // Threads column (left of chat): dragging right expands threads
    setupHandle('resize-threads-chat', '--col-threads', 160, 400, 'left');
    // Agents column (right of chat): dragging left expands agents
    setupHandle('resize-chat-agents',  '--col-agents',  200, 500, 'right');
}

// ── Preferences (defined here so all scripts can use `prefs` on load) ─────────
window.prefs = {
    data: {},

    async load() {
        try {
            const response = await fetch('/api/preferences');
            this.data = await response.json();
            if (!window._hasCheckedUpdates) {
                window._hasCheckedUpdates = true;
                setTimeout(() => { if (typeof runStartupUpdateCheck === 'function') runStartupUpdateCheck(); }, 2500);
            }
            return this.data;
        } catch (error) {
            console.error('Failed to load preferences:', error);
            return {};
        }
    },

    get(key, defaultValue) {
        if (key.includes('.')) {
            const parts = key.split('.');
            let current = this.data;
            for (const part of parts) {
                if (current === undefined || current === null) return defaultValue;
                current = current[part];
            }
            return current !== undefined ? current : defaultValue;
        }
        return this.data[key] !== undefined ? this.data[key] : defaultValue;
    },

    async set(key, value) {
        if (key.includes('.')) {
            const parts = key.split('.');
            if (!this.data[parts[0]]) this.data[parts[0]] = {};
            this.data[parts[0]][parts[1]] = value;
        } else {
            this.data[key] = value;
        }
        try {
            await fetch(`/api/preferences/${key}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value })
            });
        } catch (error) {
            console.error(`Failed to save preference ${key}:`, error);
        }
    }
};
