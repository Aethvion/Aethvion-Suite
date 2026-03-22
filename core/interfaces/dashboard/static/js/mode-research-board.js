/**
 * Aethvion - Research Board (Board of Directors) Logic
 */

let rbActiveThreadId = null;
let rbPersonas = [];
let rbAllPersonas = [];
let rbSelectedMemberIds = ['director_greedy', 'director_consumer', 'director_dev', 'director_marketer'];
let rbTotalRounds = 3;
let rbCurrentTurn = 0;
let rbIsRunning = false;
let rbRegistryData = null;

// Elements (initialized in init)
let rbPromptInput, rbRoundsSelect, rbModelSelect, rbStartBtn, rbTranscript;
let rbDirectorsStrip, rbStatusText, rbProgressInfo, rbSynthesisPane, rbSynthesisBody, rbAddMemberBtn;

async function initResearchBoard() {
    // Capture elements
    rbPromptInput = document.getElementById('rb-prompt');
    rbRoundsSelect = document.getElementById('rb-rounds');
    rbModelSelect = document.getElementById('rb-model-select');
    rbStartBtn = document.getElementById('rb-start-btn');
    rbTranscript = document.getElementById('rb-transcript');
    rbDirectorsStrip = document.getElementById('rb-directors-strip');
    rbStatusText = document.getElementById('rb-status-text');
    rbProgressInfo = document.getElementById('rb-progress-info');
    rbSynthesisPane = document.getElementById('rb-synthesis-pane');
    rbSynthesisBody = document.getElementById('rb-synthesis-body');
    rbAddMemberBtn = document.getElementById('rb-add-member-btn');
    if (rbStartBtn) {
        rbStartBtn.addEventListener('click', startBoardMeeting);
    }
    if (rbAddMemberBtn) {
        rbAddMemberBtn.addEventListener('click', () => {
            if (rbIsRunning) return;
            openAddMemberSelector();
        });
    }

    await fetchRbModels();
    await fetchRbAllPersonas();
    renderDirectorPills();
}

async function fetchRbModels() {
    try {
        const res = await fetch('/api/registry/models/chat');
        if (!res.ok) return;
        rbRegistryData = await res.json();
        
        if (rbModelSelect) {
            rbModelSelect.innerHTML = generateCategorizedModelOptions(rbRegistryData, 'chat', 'auto');
        }
    } catch (e) {
        console.error("Failed to fetch RB models", e);
    }
}

async function fetchRbAllPersonas() {
    try {
        const res = await fetch('/api/board/directors');
        if (!res.ok) return;
        rbAllPersonas = await res.json();
    } catch (e) {
        console.error("Failed to fetch all personas for RB", e);
    }
}

function renderDirectorPills() {
    let html = '';
    
    // Sort to keep default directors first?
    const currentMembers = rbAllPersonas.filter(p => rbSelectedMemberIds.includes(p.id));
    
    // Fallback if none found yet
    if (currentMembers.length === 0 && rbAllPersonas.length > 0) {
        // Just show what we selected by ID even if no full persona data yet (will re-render)
    }

    for (const p of currentMembers) {
        const icon = p.id.includes('greedy') ? 'fa-chart-line' : 
                     p.id.includes('consumer') ? 'fa-users' : 
                     p.id.includes('dev') ? 'fa-code' : 
                     p.id.includes('marketer') ? 'fa-bullhorn' : 'fa-user-tie';
        
        const isRemovable = !rbIsRunning && rbSelectedMemberIds.length > 1;

        html += `
            <div class="rb-director-pill ${isRemovable ? 'removable' : ''}" id="pill-${p.id}">
                <i class="fas ${icon}"></i> 
                <span>${p.name}</span>
                ${isRemovable ? `<i class="fas fa-times rb-remove-btn" onclick="removeBoardMember('${p.id}')"></i>` : ''}
            </div>
        `;
    }
    
    if (!rbIsRunning) {
        html += `
            <div class="rb-director-pill add-more" onclick="openAddMemberSelector()">
                <i class="fas fa-plus"></i> <span>Add Member</span>
            </div>
        `;
    }

    rbDirectorsStrip.innerHTML = html;
}

window.removeBoardMember = function(id) {
    if (rbIsRunning) return;
    rbSelectedMemberIds = rbSelectedMemberIds.filter(mid => mid !== id);
    renderDirectorPills();
}

window.openAddMemberSelector = function() {
    // Simple prompt-based or inline select for now, but we want it premium.
    // Let's create a custom dropdown/overlay if possible.
    const unselected = rbAllPersonas.filter(p => !rbSelectedMemberIds.includes(p.id));
    if (unselected.length === 0) {
        showToast('No other personas available. Create one in the Sandbox!', 'info');
        return;
    }

    // Creating a quick dynamic list
    let listHtml = '<div style="max-height: 200px; overflow-y: auto; padding: 0.5rem;">';
    for (const p of unselected) {
        listHtml += `<div class="rb-member-option" onclick="addBoardMember('${p.id}'); this.parentElement.parentElement.remove();" 
            style="padding: 0.5rem; cursor: pointer; border-radius: 4px; display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-user-circle"></i> ${p.name}
        </div>`;
    }
    listHtml += '</div>';

    const overlay = document.createElement('div');
    overlay.style = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center;';
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    
    const box = document.createElement('div');
    box.style = 'background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; width: 300px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);';
    box.innerHTML = `<div style="padding: 0.75rem; border-bottom: 1px solid var(--border); font-weight: 600; display: flex; justify-content: space-between;">
        <span>Select Member</span>
        <i class="fas fa-times" onclick="this.parentElement.parentElement.parentElement.remove()" style="cursor: pointer;"></i>
    </div>` + listHtml;
    
    overlay.appendChild(box);
    document.body.appendChild(overlay);
}

window.addBoardMember = function(id) {
    if (!rbSelectedMemberIds.includes(id)) {
        rbSelectedMemberIds.push(id);
        renderDirectorPills();
    }
};

async function startBoardMeeting() {
    if (rbIsRunning) return;

    const topic = rbPromptInput.value.trim();
    if (!topic) {
        showToast('Please enter a decision topic.', 'warn');
        return;
    }

    rbTotalRounds = parseInt(rbRoundsSelect.value) || 3;
    const modelId = rbModelSelect ? rbModelSelect.value : 'auto';

    rbIsRunning = true;
    rbStartBtn.disabled = true;
    rbStartBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Initializing...';
    
    // Clear previous
    rbTranscript.innerHTML = '';
    rbSynthesisPane.style.display = 'none';

    try {
        const res = await fetch('/api/board/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic: topic,
                round_count: rbTotalRounds,
                model_id: modelId,
                participants: rbSelectedMemberIds
            })
        });

        if (!res.ok) throw new Error('Failed to start board');

        const data = await res.json();
        rbActiveThreadId = data.thread.id;
        rbPersonas = data.personas;

        renderDirectorPills();
        updateRbStatus('Meeting in progress...', true);
        
        // Start autonomous loop
        await runDebateLoop();

    } catch (e) {
        console.error(e);
        showToast('Error starting board meeting: ' + e.message, 'error');
        resetRb();
        renderDirectorPills();
    }
}

async function runDebateLoop() {
    const totalTurns = rbTotalRounds * rbPersonas.length;
    rbCurrentTurn = 0;

    const modelId = rbModelSelect ? rbModelSelect.value : 'auto';

    for (let r = 1; r <= rbTotalRounds; r++) {
        for (let pIdx = 0; pIdx < rbPersonas.length; pIdx++) {
            if (!rbIsRunning) break;
            
            rbCurrentTurn++;
            const persona = rbPersonas[pIdx];
            
            // UI Update
            updateTurnUi(persona, r);
            
            // Simulation Wait (Small pause for realism)
            await new Promise(r => setTimeout(r, 800));

            try {
                const genRes = await fetch(`/api/board/sessions/${rbActiveThreadId}/generate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        person_id: persona.id,
                        model_id: modelId,
                        max_context: 20
                    })
                });

                if (!genRes.ok) throw new Error('Generation failed');
                const genData = await genRes.json();

                appendRbMessage(genData.message, persona.id);

            } catch (e) {
                console.error(e);
                appendRbMessage({ role: 'system', content: `[ERROR] ${persona.name} failed to respond.` });
            }
        }
    }

    // Finished debate
    updateRbStatus('Debate concluded. Synthesizing final recommendation...', true);
    await synthesizeBoard();
    
    rbIsRunning = false;
    rbStartBtn.disabled = false;
    rbStartBtn.innerHTML = '<i class="fas fa-play"></i> Start Board Meeting';
    renderDirectorPills(); // Re-render to show add/remove buttons again
}

function updateTurnUi(persona, round) {
    // Reset all pills
    document.querySelectorAll('.rb-director-pill').forEach(el => el.classList.remove('active'));
    // Activate current
    const pill = document.getElementById(`pill-${persona.id}`);
    if (pill) pill.classList.add('active');

    rbStatusText.innerHTML = `<i class="fas fa-comment-dots"></i> ${persona.name} is speaking...`;
    rbProgressInfo.innerText = `ROUND: ${round} / ${rbTotalRounds}`;
}

function appendRbMessage(msg, personaId = null) {
    if (msg.role === 'system') {
        const html = `<div class="message system-message" style="margin-bottom: 1rem; opacity: 0.7;"><i>${msg.content}</i></div>`;
        rbTranscript.insertAdjacentHTML('beforeend', html);
        rbTranscript.scrollTop = rbTranscript.scrollHeight;
        return;
    }

    // Find the simple ID for the CSS class prefix (e.g., rb-msg-greedy)
    let simpleId = 'custom';
    if (personaId) {
        if (personaId.includes('greedy')) simpleId = 'greedy';
        else if (personaId.includes('consumer')) simpleId = 'consumer';
        else if (personaId.includes('dev')) simpleId = 'dev';
        else if (personaId.includes('marketer')) simpleId = 'marketer';
    }

    const persona = rbPersonas.find(p => p.id === personaId) || { name: msg.name || 'Unknown' };

    const html = `
        <div class="rb-message rb-msg-${simpleId}">
            <div class="rb-message-header">
                <span class="rb-message-name">${persona.name}</span>
                <span class="rb-message-role">Director</span>
            </div>
            <div class="rb-message-body">
                ${msg.content}
                ${msg.tldr ? `<div style="margin-top:0.75rem; font-size:0.78rem; border-top:1px solid rgba(255,255,255,0.05); padding-top:0.5rem; opacity:0.6;"><strong>Rationale:</strong> ${msg.tldr}</div>` : ''}
            </div>
        </div>
    `;
    
    rbTranscript.insertAdjacentHTML('beforeend', html);
    rbTranscript.scrollTop = rbTranscript.scrollHeight;
}

async function synthesizeBoard() {
    rbStatusText.innerHTML = `<i class="fas fa-brain"></i> Synthesizing Final Recommendation...`;
    const modelId = rbModelSelect ? rbModelSelect.value : 'auto';
    
    try {
        const res = await fetch('/api/board/synthesize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                thread_id: rbActiveThreadId,
                model_id: modelId
            })
        });

        if (!res.ok) throw new Error('Synthesis failed');
        const data = await res.json();

        // Show Synthesis Pane
        rbSynthesisPane.style.display = 'flex';
        // Simple MD render (assuming it's formatted as requested)
        rbSynthesisBody.innerHTML = `<h3>Final Decision Report</h3>` + formatMarkdown(data.synthesis);
        
        updateRbStatus('Session complete.', false);
        showToast('Final recommendation generated!', 'success');

    } catch (e) {
        console.error(e);
        showToast('Failed to synthesize recommendation.', 'error');
        updateRbStatus('Session complete (synthesis failed).', false);
    }
}

function updateRbStatus(text, pulsing = false) {
    rbStatusText.innerHTML = (pulsing ? '<span class="rb-pulse"></span> ' : '') + text;
}

function resetRb() {
    rbIsRunning = false;
    rbStartBtn.disabled = false;
    rbStartBtn.innerHTML = '<i class="fas fa-play"></i> Start Board Meeting';
}

// Basic markdown-to-html for synthesis
function formatMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/\n\n/g, '<br><br>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/### (.*?)(<br>|$)/g, '<h4>$1</h4>')
        .replace(/## (.*?)(<br>|$)/g, '<h3>$1</h3>')
        .replace(/^- (.*?)(<br>|$)/gm, '• $1<br>');
}

// Global initialization hook
window.initResearchBoard = initResearchBoard;

document.addEventListener('DOMContentLoaded', () => {
    // Check for either the panel or the tab button being present
    if (document.getElementById('researchboard-panel')) {
        setTimeout(initResearchBoard, 600);
    }
});
