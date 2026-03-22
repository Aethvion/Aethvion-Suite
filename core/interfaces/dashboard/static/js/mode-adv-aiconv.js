/**
 * Misaka Cipher - Advanced AI Conversation (Research Mode)
 */

let allPersonas = [];
let activePersonas = [];
let activeAdvaiconvThreadId = null;
let advaiconvState = 'stopped'; // 'stopped', 'running', 'paused'
let advaiconvInterval = null;
let currentSpeakerIndex = 0;

// Elements
const advaiconvPersonSelect = document.getElementById('advaiconv-person-add');
const advaiconvPersonChips = document.getElementById('advaiconv-person-chips');
const advaiconvTopicInput = document.getElementById('advaiconv-topic');
const advaiconvSpeedInput = document.getElementById('advaiconv-speed-input');
const advaiconvContextInput = document.getElementById('advaiconv-context-input');
const btnAdvaiconvMain = document.getElementById('advaiconv-main-btn');
const advaiconvMessagesContainer = document.getElementById('advaiconv-messages');
const statusIndicator = document.getElementById('advaiconv-status-indicator');
const btnNewPersona = document.getElementById('advaiconv-new-person-btn');
const advaiconvThreadList = document.getElementById('advaiconv-thread-list');
const btnAdvaiconvNewThread = document.getElementById('advaiconv-new-thread-btn');
const titleAdvaiconvThread = document.getElementById('advaiconv-active-thread-title');

let allThreads = [];
let advaiconvRegistryData = null;

async function initAdvaiconv() {
    await fetchAdvaiconvModels();
    await fetchPersonas();
    await fetchThreads();

    // Bind Events
    if (advaiconvPersonSelect) {
        advaiconvPersonSelect.addEventListener('change', (e) => {
            if (e.target.value) {
                addPersonaToActive(e.target.value);
                e.target.value = "";
            }
        });
    }

    if (btnNewPersona) {
        btnNewPersona.addEventListener('click', openPersonaModal);
    }

    if (btnAdvaiconvMain) {
        btnAdvaiconvMain.addEventListener('click', toggleSimulationState);
    }

    if (btnAdvaiconvNewThread) {
        btnAdvaiconvNewThread.addEventListener('click', () => {
            stopSimulation();
            activeAdvaiconvThreadId = null;
            advaiconvMessagesContainer.innerHTML = `
                <div class="arena-placeholder" id="advaiconv-placeholder">
                    <span class="tab-icon" style="font-size:3rem;">🧪</span>
                    <p>Select subjects, configure the environment, and start the simulation!</p>
                </div>
            `;
            titleAdvaiconvThread.innerText = "New Simulation";
            advaiconvTopicInput.value = "";
            activePersonas = [];
            renderActivePersonChips();
            renderThreads();
        });
    }
}

async function fetchAdvaiconvModels() {
    try {
        const res = await fetch('/api/registry/models/chat');
        if (!res.ok) return;
        advaiconvRegistryData = await res.json();
    } catch (e) {
        console.error("Failed to fetch models for Advaiconv", e);
    }
}

async function fetchPersonas() {
    try {
        const res = await fetch('/api/research/people?type=research_subject');
        allPersonas = await res.json();

        let html = '<option value="" disabled selected>+ Add Person...</option>';
        for (const p of allPersonas) {
            html += `<option value="${p.id}">${p.name} (${p.gender})</option>`;
        }
        if (advaiconvPersonSelect) advaiconvPersonSelect.innerHTML = html;

    } catch (e) {
        console.error("Failed to load personas", e);
    }
}

async function fetchThreads() {
    try {
        const res = await fetch('/api/research/threads');
        allThreads = await res.json();
        renderThreads();
    } catch (e) {
        console.error("Failed to fetch threads", e);
    }
}

function renderThreads() {
    if (!advaiconvThreadList) return;
    let html = '';
    if (allThreads.length === 0) {
        html = '<div class="placeholder-text" style="padding: 0.5rem; font-size: 0.8rem;">No threads found.</div>';
    } else {
        for (const t of allThreads) {
            const isActive = t.id === activeAdvaiconvThreadId ? 'active' : '';
            const dateSplit = t.updated_at ? t.updated_at.split('T') : ['Unknown', ''];
            const dateStr = dateSplit[0] + ' ' + (dateSplit[1] ? dateSplit[1].substring(0, 5) : '');
            html += `
                <div class="advaiconv-thread-item ${isActive}" onclick="loadThread('${t.id}')" style="display:flex; flex-direction:row; justify-content:space-between; align-items:center;">
                    <div style="flex:1; overflow:hidden;">
                        <div class="advaiconv-thread-title" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${t.name || 'Unnamed Thread'}</div>
                        <div class="advaiconv-thread-date">${dateStr}</div>
                    </div>
                    <button onclick="event.stopPropagation(); deleteAdvaiconvThread('${t.id}')" class="icon-btn" title="Delete Thread" style="background:none; border:none; color:var(--text-secondary); cursor:pointer; padding: 4px;"><i class="fas fa-trash"></i></button>
                </div>
            `;
        }
    }
    advaiconvThreadList.innerHTML = html;
}

async function loadThread(threadId) {
    if (advaiconvState !== 'stopped') return;
    try {
        const res = await fetch(`/api/research/threads/${threadId}`);
        const data = await res.json();
        activeAdvaiconvThreadId = data.meta.id;
        titleAdvaiconvThread.innerText = data.meta.name;
        advaiconvTopicInput.value = data.meta.topic || "";

        // Restore participants
        activePersonas = [];
        for (const pid of data.meta.participants || []) {
            const p = allPersonas.find(x => x.id === pid);
            if (p) activePersonas.push(p);
        }
        renderActivePersonChips();

        // Render existing messages
        advaiconvMessagesContainer.innerHTML = '';
        for (const m of data.messages || []) {
            let fallbackTraits = null;
            const snap = (data.snapshots || []).find(s => s.message_id === m.id);
            if (snap) fallbackTraits = snap.traits;
            appendUiMessage(m, fallbackTraits);
        }

        renderThreads();
    } catch (e) {
        console.error(e);
    }
}

window.loadThread = loadThread;

async function deleteAdvaiconvThread(threadId) {
    if (!confirm('Are you sure you want to delete this thread?')) return;
    try {
        const res = await fetch(`/api/research/threads/${threadId}`, { method: 'DELETE' });
        if (res.ok) {
            allThreads = allThreads.filter(t => t.id !== threadId);
            if (activeAdvaiconvThreadId === threadId) {
                stopSimulation();
                titleAdvaiconvThread.innerText = "New Simulation";
                advaiconvMessagesContainer.innerHTML = `
                    <div class="arena-placeholder" id="advaiconv-placeholder">
                        <span class="tab-icon" style="font-size:3rem;">🧪</span>
                        <p>Select subjects, configure the environment, and start the simulation!</p>
                    </div>`;
                document.getElementById('advaiconv-backend-view').innerHTML = `<div class="placeholder-text" style="text-align: center; margin-top: 2rem;">No backend logs yet. Start the simulation to see prompts and raw generations.</div>`;
            }
            renderThreads();
        }
    } catch (e) {
        console.error("Failed to delete thread", e);
    }
}
window.deleteAdvaiconvThread = deleteAdvaiconvThread;

async function renameAdvaiconvThread() {
    if (!activeAdvaiconvThreadId) {
        showToast('Please select or start a thread to rename it.', 'warn');
        return;
    }
    const currentName = titleAdvaiconvThread.innerText;
    const newName = window.prompt("Enter new thread name:", currentName);
    if (!newName || newName === currentName) return;

    try {
        const res = await fetch(`/api/research/threads/${activeAdvaiconvThreadId}/name`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName })
        });
        if (res.ok) {
            titleAdvaiconvThread.innerText = newName;
            const t = allThreads.find(t => t.id === activeAdvaiconvThreadId);
            if (t) t.name = newName;
            renderThreads();
        }
    } catch (e) {
        console.error("Failed to rename thread", e);
    }
}
window.renameAdvaiconvThread = renameAdvaiconvThread;

function generateModelOptionsHtml(selectedModelId) {
    if (!advaiconvRegistryData) return '<option value="auto">auto</option>';
    return generateCategorizedModelOptions(advaiconvRegistryData, 'chat', selectedModelId);
}

async function addPersonaToActive(personId) {
    if (activePersonas.find(p => p.id === personId)) return; // already added

    const person = allPersonas.find(p => p.id === personId);
    if (!person) return;

    activePersonas.push(person);
    renderActivePersonChips();

    // Dynamically notify system if running/paused
    if (activeAdvaiconvThreadId && (advaiconvState === 'running' || advaiconvState === 'paused')) {
        await notifySystemEvent(`System Event: ${person.name} has joined the conversation.`);
    }
}

async function removePersonaFromActive(personId) {
    const pIndex = activePersonas.findIndex(p => p.id === personId);
    if (pIndex > -1) {
        const p = activePersonas[pIndex];
        activePersonas.splice(pIndex, 1);
        renderActivePersonChips();

        if (activeAdvaiconvThreadId && (advaiconvState === 'running' || advaiconvState === 'paused')) {
            await notifySystemEvent(`System Event: ${p.name} has left the conversation.`);
        }
    }
}

function renderActivePersonChips() {
    if (!advaiconvPersonChips) return;

    let html = '';
    for (const p of activePersonas) {
        // default to first model if none selected
        if (!p.selectedModel && p.model) {
            p.selectedModel = p.model;
        }
        if (!p.selectedModel && advaiconvRegistryData && advaiconvRegistryData.models && advaiconvRegistryData.models.length > 0) {
            p.selectedModel = advaiconvRegistryData.models[0].id;
        }

        const modelsHtml = generateModelOptionsHtml(p.selectedModel);

        html += `
            <div class="person-chip">
                <div class="person-chip-info" style="flex:1;">
                    <div style="display:flex; justify-content:space-between;">
                        <span class="person-chip-name">${p.name} <span class="person-chip-gender">(${p.gender})</span></span>
                        <span class="person-chip-remove" onclick="removePersonaFromActive('${p.id}')">
                            <i class="fas fa-times"></i>
                        </span>
                    </div>
                    <select class="persona-model-select" onchange="updatePersonaModel('${p.id}', this.value)">
                        ${modelsHtml}
                    </select>
                </div>
            </div>
        `;
    }
    advaiconvPersonChips.innerHTML = html;
}

window.updatePersonaModel = async function (personId, modelId) {
    const p = activePersonas.find(x => x.id === personId);
    if (p) {
        p.selectedModel = modelId;
        try {
            await fetch(`/api/research/people/${personId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId })
            });
        } catch (e) {
            console.error("Failed to save persona model", e);
        }
    }
}

window.switchAdvaiconvView = function (view) {
    document.querySelectorAll('.advaiconv-view-tab').forEach(bt => {
        if (bt.dataset.view === view) {
            bt.classList.add('active');
            bt.style.background = 'var(--bg-secondary)';
            bt.style.borderColor = 'var(--border)';
            bt.style.color = 'var(--text-primary)';
            bt.style.fontWeight = '500';
        } else {
            bt.classList.remove('active');
            bt.style.background = 'transparent';
            bt.style.borderColor = 'transparent';
            bt.style.color = 'var(--text-secondary)';
            bt.style.fontWeight = 'normal';
        }
    });

    document.getElementById('advaiconv-messages').style.display = view === 'simulation' ? 'flex' : 'none';
    document.getElementById('advaiconv-backend-view').style.display = view === 'backend' ? 'block' : 'none';
    document.getElementById('advaiconv-people-view').style.display = view === 'people' ? 'block' : 'none';
    document.getElementById('advaiconv-statistics-view').style.display = view === 'statistics' ? 'block' : 'none';

    if (view === 'backend') renderBackendView();
    if (view === 'people') renderPeopleView();
    if (view === 'statistics') renderStatisticsView();
}

async function renderBackendView() {
    const container = document.getElementById('advaiconv-backend-view');
    if (!activeAdvaiconvThreadId) {
        container.innerHTML = `<div class="placeholder-text" style="text-align: center; margin-top: 2rem;">No backed thread loaded.</div>`;
        return;
    }

    container.innerHTML = `<div class="placeholder-text" style="text-align: center; margin-top: 2rem;"><i class="fas fa-spinner fa-spin"></i> Loading raw logs...</div>`;

    try {
        const res = await fetch(`/api/research/threads/${activeAdvaiconvThreadId}`);
        const data = await res.json();

        if (!data.messages || data.messages.length === 0) {
            container.innerHTML = `<div class="placeholder-text" style="text-align: center; margin-top: 2rem;">No backend logs yet. Start the simulation to see prompts and raw generations.</div>`;
            return;
        }

        let html = '<div style="display:flex; flex-direction:column; gap: 1rem;">';
        for (const m of data.messages) {
            html += `
                <div style="background: var(--bg-tertiary); padding: 1rem; border-radius: 6px; border: 1px solid var(--border); font-family: monospace; font-size: 0.85rem; white-space: pre-wrap; overflow-x: auto;">
                    <div style="color: var(--primary); margin-bottom: 0.5rem; font-weight: bold;">[${m.role.toUpperCase()}] ${m.name || ''}</div>
                    <div style="color: var(--text-secondary);">${m.content}</div>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
        container.scrollTop = container.scrollHeight;
    } catch (e) {
        container.innerHTML = `<div class="placeholder-text" style="text-align: center; margin-top: 2rem; color: var(--danger);">Failed to load logs.</div>`;
    }
}

function renderPeopleView() {
    const container = document.getElementById('advaiconv-people-view');
    if (activePersonas.length === 0) {
        container.innerHTML = `<div class="placeholder-text" style="text-align: center; margin-top: 2rem;">No subjects in simulation.</div>`;
        return;
    }

    let html = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
            <h4 style="margin:0; color:var(--text-primary);">Active Subjects Info</h4>
            <button class="action-btn secondary xs-btn" onclick="refreshPeopleData()"><i class="fas fa-sync-alt"></i> Refresh Data</button>
        </div>
        <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem;">
    `;

    for (const p of activePersonas) {
        let traitsHtml = '';
        for (const [k, v] of Object.entries(p.traits || {})) {
            traitsHtml += `<span style="background: var(--bg-primary); padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; border: 1px solid var(--border);">${k}: ${v}</span>`;
        }

        html += `
            <div style="background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem;">
                <h4 style="margin: 0 0 0.5rem 0; color: var(--primary); font-size: 1.1rem;">${p.name} <span style="color:var(--text-secondary); font-size: 0.85rem; font-weight:normal;">(${p.gender})</span></h4>
                <div style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 1rem;">Model: <strong>${p.selectedModel || 'auto'}</strong></div>
                
                <h5 style="margin: 0 0 0.4rem 0; font-size: 0.85rem; color: var(--text-primary);">Current Traits</h5>
                <div style="display:flex; flex-wrap:wrap; gap: 0.4rem; margin-bottom: 1rem;">${traitsHtml}</div>
                
                <h5 style="margin: 0 0 0.4rem 0; font-size: 0.85rem; color: var(--text-primary);">Background</h5>
                <p style="margin: 0 0 1rem 0; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">${p.background}</p>
                
                <h5 style="margin: 0 0 0.4rem 0; font-size: 0.85rem; color: var(--text-primary);">Internal Memory</h5>
                <p style="margin: 0; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4; padding: 0.5rem; background: var(--bg-primary); border-radius: 4px; font-style: italic;">${p.memory || 'No memory recorded.'}</p>
            </div>
        `;
    }
    html += '</div>';
    container.innerHTML = html;
}

function renderStatisticsView() {
    const container = document.getElementById('advaiconv-statistics-view');
    if (activePersonas.length === 0) {
        container.innerHTML = `<div class="placeholder-text" style="text-align: center; margin-top: 2rem;">No subjects in simulation to generate statistics.</div>`;
        return;
    }

    let html = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
            <h4 style="margin:0; color:var(--text-primary);">Persona Divergence Statistics</h4>
            <button class="action-btn secondary xs-btn" onclick="refreshPeopleData()"><i class="fas fa-sync-alt"></i> Refresh Data</button>
        </div>
        <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 1rem;">
    `;

    for (const p of activePersonas) {
        const totalMessages = p.message_count || 0;

        // build visual bars for trait drift
        let driftHtml = '';
        const prevTraits = p.original_traits || p.traits || {};
        const currTraits = p.traits || {};
        const allKeys = new Set([...Object.keys(prevTraits), ...Object.keys(currTraits)]);

        allKeys.forEach(k => {
            const v1 = prevTraits[k] || 0;
            const v2 = currTraits[k] || 0;
            const MathAbs = Math.abs(v2 - v1);
            let arrow = v2 > v1 ? '<i class="fas fa-arrow-up" style="color:var(--success);"></i>' : (v2 < v1 ? '<i class="fas fa-arrow-down" style="color:var(--danger);"></i>' : '<i class="fas fa-equals" style="color:var(--text-secondary);"></i>');

            // max is 10 usually, if not we adapt 
            const maxVal = 10;
            const w1 = Math.min((v1 / maxVal) * 100, 100);
            const w2 = Math.min((v2 / maxVal) * 100, 100);

            driftHtml += `
                <div style="margin-bottom: 0.5rem;">
                    <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.2rem;">
                        <span>${k}</span>
                        <span>${arrow} ${v2} <span style="color:var(--text-secondary); font-size:0.75rem;">(Orig: ${v1})</span></span>
                    </div>
                    <!-- Combined tracking bar -->
                    <div style="width: 100%; height: 6px; background: var(--bg-primary); border-radius: 3px; position:relative; margin-bottom: 2px;">
                        <div style="position:absolute; left:0; top:0; height:100%; border-radius:3px; background:var(--text-secondary); opacity:0.5; width:${w1}%;"></div>
                        <div style="position:absolute; left:0; top:0; height:100%; border-radius:3px; background:var(--primary); width:${w2}%; mix-blend-mode: screen;"></div>
                    </div>
                </div>
            `;
        });

        html += `
            <div style="background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem;">
                <h4 style="margin: 0 0 0.5rem 0; color: var(--primary); font-size: 1.1rem;">${p.name}</h4>
                <div style="font-size: 0.9rem; color: var(--text-primary); margin-bottom: 1rem; display:flex; gap:1rem;">
                    <div style="background:var(--bg-secondary); padding:0.5rem; border-radius:4px; flex:1; text-align:center;">
                        <div style="font-size:1.5rem; font-weight:bold; color:var(--primary);">${totalMessages}</div>
                        <div style="font-size:0.75rem; color:var(--text-secondary);">Messages Sent</div>
                    </div>
                </div>
                
                <h5 style="margin: 0 0 0.8rem 0; font-size: 0.85rem; color: var(--text-primary);">Trait Drifting</h5>
                <div style="margin-bottom: 1.5rem;">
                    ${driftHtml}
                </div>
                
                <h5 style="margin: 0 0 0.4rem 0; font-size: 0.85rem; color: var(--text-primary);">Origin Snapshot</h5>
                <p style="margin: 0; font-size: 0.8rem; color: var(--text-secondary); line-height: 1.3; padding: 0.5rem; background: var(--bg-primary); border-radius: 4px; border: 1px dashed var(--border);">
                    <strong>Original Memory:</strong><br>
                    ${p.original_memory || p.memory || 'No memory recorded at start.'}
                </p>
            </div>
        `;
    }
    html += '</div>';
    container.innerHTML = html;
}

window.refreshPeopleData = async function () {
    await fetchPersonas();
    for (let p of activePersonas) {
        const up = allPersonas.find(x => x.id === p.id);
        if (up) {
            p.traits = up.traits;
            p.memory = up.memory;
            p.original_traits = up.original_traits;
            p.original_memory = up.original_memory;
            p.message_count = up.message_count;
            p.model = up.model;
        }
    }
    renderPeopleView();
    renderStatisticsView();
}

async function notifySystemEvent(msg) {
    if (!activeAdvaiconvThreadId) return;
    try {
        await fetch(`/api/research/threads/${activeAdvaiconvThreadId}/system_message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg })
        });
        appendUiMessage({ role: 'system', content: msg });

        // Also update participants list
        await fetch(`/api/research/threads/${activeAdvaiconvThreadId}/participants`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(activePersonas.map(p => p.id))
        });
    } catch (e) {
        console.error("System event failed", e);
    }
}

// ----- Simulation Loop ----- //

async function startSimulation() {
    if (activePersonas.length < 1) {
        showToast('Add at least one persona before starting.', 'warn');
        return;
    }

    if (advaiconvState === 'stopped') {
        const topic = advaiconvTopicInput.value.trim() || "Free conversation in a neutral environment.";
        if (!activeAdvaiconvThreadId) {
            try {
                // Create thread
                const res = await fetch('/api/research/threads', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: "Simulation " + new Date().toLocaleTimeString(),
                        topic: topic,
                        participants: activePersonas.map(p => p.id)
                    })
                });
                const threadData = await res.json();
                activeAdvaiconvThreadId = threadData.id;
                titleAdvaiconvThread.innerText = threadData.name;
                allThreads.unshift(threadData);
                renderThreads();
            } catch (e) {
                console.error(e);
                return;
            }
        }

        // clear ui
        if (document.getElementById('advaiconv-placeholder')) {
            document.getElementById('advaiconv-placeholder').remove();
        }
        advaiconvMessagesContainer.innerHTML = '';

        // Inject environment system prompt
        await notifySystemEvent(`Environment Setup: ${topic}`);

        currentSpeakerIndex = 0;
    }

    advaiconvState = 'running';
    updateControls();
    scheduleNextTurn();
}

function toggleSimulationState() {
    if (advaiconvState === 'stopped' || advaiconvState === 'paused') {
        if (!activeAdvaiconvThreadId && advaiconvState === 'stopped') {
            startSimulation(); // New Simulation
        } else {
            // Contiune simulation if thread is already active but paused/stopped
            advaiconvState = 'running';
            updateControls();
            scheduleNextTurn();
        }
    } else if (advaiconvState === 'running') {
        pauseSimulation();
    }
}

function pauseSimulation() {
    advaiconvState = 'paused';
    if (advaiconvInterval) clearTimeout(advaiconvInterval);
    updateControls();
}

function stopSimulation() {
    advaiconvState = 'stopped';
    if (advaiconvInterval) clearTimeout(advaiconvInterval);
    activeAdvaiconvThreadId = null;
    updateControls();
}

function updateControls() {
    statusIndicator.innerText = advaiconvState.toUpperCase();
    if (advaiconvState === 'running') {
        statusIndicator.style.color = 'var(--success)';
        if (btnAdvaiconvMain) {
            btnAdvaiconvMain.className = 'action-btn secondary';
            btnAdvaiconvMain.innerHTML = '<i class="fas fa-pause"></i> Pause Simulation';
        }
    } else if (advaiconvState === 'paused' || (advaiconvState === 'stopped' && activeAdvaiconvThreadId)) {
        statusIndicator.style.color = 'var(--warning)';
        if (btnAdvaiconvMain) {
            btnAdvaiconvMain.className = 'action-btn primary';
            btnAdvaiconvMain.innerHTML = '<i class="fas fa-play"></i> Continue Simulation';
        }
    } else {
        statusIndicator.style.color = 'var(--text-secondary)';
        if (btnAdvaiconvMain) {
            btnAdvaiconvMain.className = 'action-btn primary';
            btnAdvaiconvMain.innerHTML = '<i class="fas fa-play"></i> Start Simulation';
        }
    }
}

async function scheduleNextTurn() {
    if (advaiconvState !== 'running') return;

    const speaker = activePersonas[currentSpeakerIndex];
    statusIndicator.innerText = `RUNNING (${speaker.name} thinking...)`;

    // UI placeholder for typing
    const typingId = 'typing-' + Date.now();
    appendUiMessage({ role: 'system', id: typingId, content: `${speaker.name} is thinking...` });

    try {
        const selectedModel = speaker.selectedModel || "auto";
        const maxCxt = parseInt(advaiconvContextInput.value) || 20;

        const res = await fetch(`/api/research/threads/${activeAdvaiconvThreadId}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                person_id: speaker.id,
                model_id: selectedModel,
                max_context: maxCxt
            })
        });

        const data = await res.json();
        const tEl = document.getElementById(typingId);
        if (tEl) tEl.remove();

        if (data.message) {
            appendUiMessage(data.message, data.updated_person.traits);

            // update local persona traits so next turn uses it internally (backend already has it)
            speaker.traits = data.updated_person.traits;
        } else {
            console.error("No message in response", data);
            pauseSimulation();
            return;
        }

    } catch (e) {
        console.error("Turn failed", e);
        const tEl = document.getElementById(typingId);
        if (tEl) tEl.remove();
        appendUiMessage({ role: 'system', content: `Error: ${e.message}` });
        pauseSimulation();
        return;
    }

    if (advaiconvState === 'running') {
        currentSpeakerIndex = (currentSpeakerIndex + 1) % activePersonas.length;
        const delayMs = parseInt(advaiconvSpeedInput.value) || 2000;
        advaiconvInterval = setTimeout(scheduleNextTurn, delayMs);
    }
}

function appendUiMessage(msg, traits = null) {
    const isSystem = msg.role === 'system';

    let html = '';
    const wrapperId = msg.id || ('sys-' + Date.now());

    if (isSystem) {
        html = `
            <div id="${wrapperId}" class="message system-message" style="margin-bottom: 0.8rem;">
                <div class="message-content" style="color: var(--text-secondary); font-style: italic; font-size: 0.85rem;">
                    <strong>[System Env]</strong> ${msg.content}
                </div>
            </div>
        `;
    } else {
        // Build traits badges
        let traitHtml = '';
        if (traits) {
            for (const [key, val] of Object.entries(traits)) {
                traitHtml += `<span class="trait-badge">${key}: <strong>${val}</strong></span>`;
            }
        }

        let tldrHtml = '';
        if (msg.tldr) {
            tldrHtml = `<div class="trait-tldr"><strong>Logic:</strong> ${msg.tldr}</div>`;
        }

        html = `
            <div id="${wrapperId}" class="message bot-message" style="margin-bottom: 1.5rem; background: var(--bg-tertiary); padding: 1rem; border-radius: 8px; border: 1px solid var(--border);">
                <div style="font-weight: 600; color: var(--primary); margin-bottom: 0.5rem; display: flex; align-items: center; justify-content: space-between;">
                    ${msg.name}
                    ${traits ? `<div class="trait-badges" style="margin: 0; padding: 0; border: none;">${traitHtml}</div>` : ''}
                </div>
                <div class="message-content" style="line-height: 1.5; color: var(--text-primary);">
                    ${msg.content}
                </div>
                ${tldrHtml}
            </div>
        `;
    }

    advaiconvMessagesContainer.insertAdjacentHTML('beforeend', html);
    advaiconvMessagesContainer.scrollTop = advaiconvMessagesContainer.scrollHeight;
}

// ----- Persona Creation UI ----- //

function openPersonaModal() {
    // Standard modal logic hooking into main app
    const modalHtml = `
        <div class="modal-content" style="max-width: 500px;">
            <div class="modal-header">
                <h2>Create Research Persona</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="persona-modal-grid">
                    <div>
                        <label>Name</label>
                        <input type="text" id="p-name" class="term-input" style="width:100%;">
                    </div>
                    <div>
                        <label>Gender/Identity</label>
                        <input type="text" id="p-gender" class="term-input" style="width:100%;">
                    </div>
                    <div>
                        <label style="margin-bottom: 0;">Background Overview</label>
                        <span style="display:block; font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.4rem; padding-left: 1px;">The core identity of the persona. Describe their profession, general disposition, and underlying beliefs. This forms the foundation of their system prompt.</span>
                        <textarea id="p-bg" class="term-input" style="width:100%; height:80px;" placeholder="E.g., 'A logical structural engineer who prioritizes safety over aesthetics and speaks formally.'"></textarea>
                    </div>
                    <div>
                        <label>Initial Hidden Memory</label>
                        <textarea id="p-mem" class="term-input" style="width:100%; height:80px;" placeholder="Base memories before simulation starts..."></textarea>
                    </div>
                    <div>
                        <label>Traits (Scale 1-10)</label>
                        <div id="p-traits-container">
                            <div class="persona-trait-row">
                                <input type="text" class="term-input tt-name" placeholder="Trait (e.g., Happiness)" value="Happiness">
                                <input type="number" class="term-input tt-val" min="1" max="10" value="5">
                            </div>
                            <div class="persona-trait-row">
                                <input type="text" class="term-input tt-name" placeholder="Trait (e.g., Openness)" value="Openness">
                                <input type="number" class="term-input tt-val" min="1" max="10" value="5">
                            </div>
                            <div class="persona-trait-row">
                                <input type="text" class="term-input tt-name" placeholder="Trait (e.g., Skepticism)" value="Skepticism">
                                <input type="number" class="term-input tt-val" min="1" max="10" value="5">
                            </div>
                        </div>
                        <button onclick="addTraitRow()" class="action-btn secondary small" style="margin-top:0.5rem;">+ Add Trait</button>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="action-btn secondary" onclick="closeModal()">Cancel</button>
                <button class="action-btn primary" onclick="saveNewPersona()">Save</button>
            </div>
        </div>
    `;
    openCustomModal(modalHtml);
}

window.addTraitRow = function () {
    const c = document.getElementById('p-traits-container');
    c.insertAdjacentHTML('beforeend', `
        <div class="persona-trait-row">
            <input type="text" class="term-input tt-name" placeholder="Trait Name">
            <input type="number" class="term-input tt-val" min="1" max="10" value="5">
        </div>
    `);
}

window.saveNewPersona = async function () {
    const payload = {
        name: document.getElementById('p-name').value.trim(),
        gender: document.getElementById('p-gender').value.trim(),
        background: document.getElementById('p-bg').value.trim(),
        memory: document.getElementById('p-mem').value.trim(),
        traits: {}
    };

    if (!payload.name || !payload.background) {
        showToast('Name and Background are required.', 'warn');
        return;
    }

    const traitRows = document.querySelectorAll('#p-traits-container .persona-trait-row');
    traitRows.forEach(row => {
        const tname = row.querySelector('.tt-name').value.trim();
        const tval = parseInt(row.querySelector('.tt-val').value) || 5;
        if (tname) {
            payload.traits[tname] = tval;
        }
    });

    try {
        const res = await fetch('/api/research/people', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        await fetchPersonas();
        closeModal();
    } catch (e) {
        showToast('Failed: ' + e.message, 'error');
    }
}

// Hook into app initialization
document.addEventListener('DOMContentLoaded', () => {
    // Only init if we are on the page that has the panel
    if (document.getElementById('advaiconv-panel')) {
        setTimeout(initAdvaiconv, 500); // Give model-registry time to load
    }
});
