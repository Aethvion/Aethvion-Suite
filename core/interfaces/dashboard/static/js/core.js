// Misaka Cipher - Core
// Handles WebSocket connections, global UI state, and initialization

// Global variables
let chatWs = null;
let logsWs = null;
let agentsWs = null;
let currentMainTab = 'chat';
let prevChatArenaMode = 'chat'; // Used to resume chat/arena

document.addEventListener('DOMContentLoaded', async () => {
    // Start polling startup status (non-blocking)
    pollStartupStatus();

    initializeWebSockets();
    const refreshMemory = document.getElementById('refresh-memory-btn');
    if (refreshMemory) refreshMemory.addEventListener('click', loadMemoryData);

    initializeUI();
    initDevMode();
    await loadInitialData();

    // Restore persisted tab from server
    const response = await fetch('/api/preferences/get?key=active_tab');
    if (response.ok) {
        const data = await response.json();
        if (data.value) switchMainTab(data.value, false);
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
    // Main tab switching (skip dropdown-managed tabs)
    document.querySelectorAll('.main-tab').forEach(tab => {
        if (tab.closest('.main-tab-dropdown') || tab.closest('.nav-dropdown')) {
            // Dropdowns are handled differently
            if (tab.classList.contains('dropdown-trigger')) {
                // Trigger itself doesn't switch tabs, just shows dropdown via CSS
                return;
            }
        }
        tab.addEventListener('click', () => switchMainTab(tab.dataset.maintab));
    });

    // Nav Dropdown items
    document.querySelectorAll('.nav-dropdown-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            const subtab = item.dataset.subtab;
            switchMainTab(subtab);
        });
    });

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
    if (refreshFilesList) refreshFilesList.addEventListener('click', loadFiles);

    // Tools forge button
    const forgeBtn = document.getElementById('forge-tool-button');
    if (forgeBtn) {
        forgeBtn.addEventListener('click', () => {
            alert('Tool forging via UI coming soon! For now, use the chat: "Create a tool to..."');
        });
    }

    // Voice Mode Toggle
    const voiceButton = document.getElementById('voice-mode-toggle');
    if (voiceButton) {
        voiceButton.addEventListener('click', () => {
            voiceButton.classList.toggle('active');
            const isActive = voiceButton.classList.contains('active');

            if (isActive) {
                voiceButton.innerHTML = '<i class="fas fa-stop"></i>';
                voiceButton.style.color = 'var(--accent)';
                if (typeof addMessage === 'function') addMessage('system', 'Voice mode activated (Simulation)');
            } else {
                voiceButton.innerHTML = '<i class="fas fa-microphone"></i>';
                voiceButton.style.color = '';
                if (typeof addMessage === 'function') addMessage('system', 'Voice mode deactivated');
            }
        });
    }

    // Add File Button
    const addFileBtn = document.querySelector('.add-file-btn');
    if (addFileBtn) {
        addFileBtn.addEventListener('click', () => {
            alert('File upload coming soon!');
        });
    }

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

function switchMainTab(tabName, save = true) {
    if (!tabName) return;

    currentMainTab = tabName;
    if (save && typeof savePreference === 'function') {
        savePreference('active_tab', tabName);
    }

    // Update tab buttons
    document.querySelectorAll('.main-tab').forEach(tab => {
        if (tab.closest('.main-tab-dropdown')) {
            const categories = ['chat', 'agent', 'image', 'audio', 'arena', 'aiconv', 'advaiconv'];
            const isActive = categories.includes(tabName);

            if (tab.classList.contains('split-main-action')) {
                tab.classList.toggle('active', isActive);

                if (isActive) {
                    tab.dataset.maintab = tabName;
                    let icon = '💬';
                    let label = 'Chat';
                    if (tabName === 'agent') { icon = '🤖'; label = 'Agent'; }
                    if (tabName === 'image') { icon = '🎨'; label = 'Image'; }
                    if (tabName === 'audio') { icon = '🎙️'; label = 'Audio'; }
                    if (tabName === 'arena') { icon = '⚔️'; label = 'Arena'; }
                    if (tabName === 'aiconv') { icon = '🎭'; label = 'AI Conv'; }
                    if (tabName === 'advaiconv') { icon = '🧪'; label = 'Adv AI Conv'; }
                    tab.innerHTML = `<span class="tab-icon">${icon}</span>${label}`;
                }
            } else if (tab.classList.contains('split-arrow-action')) {
                tab.classList.toggle('active', isActive);
            }
        } else if (tab.classList.contains('dropdown-trigger')) {
            // Check if any sub-item of this dropdown is active
            const parent = tab.closest('.nav-dropdown');
            const subItems = parent.querySelectorAll('.nav-dropdown-item');
            let isParentActive = false;
            subItems.forEach(item => {
                if (item.dataset.subtab === tabName) isParentActive = true;
            });
            tab.classList.toggle('active', isParentActive);
        } else {
            tab.classList.toggle('active', tab.dataset.maintab === tabName);
        }
    });

    // Update Nav Dropdown active state
    document.querySelectorAll('.nav-dropdown-item').forEach(item => {
        item.classList.toggle('active', item.dataset.subtab === tabName);
    });

    // Update Sub-tab active state in split dropdown
    document.querySelectorAll('.tab-dropdown-item').forEach(item => {
        item.classList.toggle('active', item.dataset.subtab === tabName);
    });

    // Update panels
    document.querySelectorAll('.main-tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });

    // Agent mode re-uses chat-panel
    let panelId = `${tabName}-panel`;
    if (tabName === 'agent') panelId = 'chat-panel';

    const targetPanel = document.getElementById(panelId);
    if (targetPanel) targetPanel.classList.add('active');

    // Load data for tab dynamically
    if (tabName === 'files' && typeof loadFiles === 'function') loadFiles();
    else if (tabName === 'tools' && typeof loadTools === 'function') loadTools();
    else if (tabName === 'settings' && typeof loadProviderSettings === 'function') loadProviderSettings();
    else if (tabName === 'usage' && typeof loadUsageDashboard === 'function') loadUsageDashboard();
    else if (tabName === 'arena' && typeof loadArenaModels === 'function') {
        loadArenaModels();
        if (typeof loadArenaLeaderboard === 'function') loadArenaLeaderboard();
    }
    else if (tabName === 'aiconv' && typeof loadArenaModels === 'function') loadArenaModels();
    else if (tabName === 'status' && typeof loadSystemStatusTab === 'function') loadSystemStatusTab();
    else if (tabName === 'audio' && typeof initializeAudioStudio === 'function') {
        initializeAudioStudio();
    }
    else if (tabName === 'misaka-cipher' && typeof initializeMisakaCipher === 'function') {
        initializeMisakaCipher();
    }
    else if (tabName === 'misaka-memory' && typeof refreshMisakaMemory === 'function') {
        refreshMisakaMemory();
    }

    // Update layout based on mode
    updateChatLayout();
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

function updateChatLayout() {
    const layout = document.querySelector('.three-column-layout');
    if (!layout) return;

    const agentsCol = document.querySelector('.agents-column');
    const showAgents = currentMainTab === 'agent';

    if (agentsCol) agentsCol.style.display = showAgents ? 'flex' : 'none';
    layout.style.gridTemplateColumns = showAgents ? '15% 1fr 20%' : '15% 1fr';
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
    profilesHtml += `<option value="auto" ${autoSelected}>Auto (Complexity Routing)</option>`;

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
