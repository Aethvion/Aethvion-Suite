/**
 * Aethvion - AI Explained Logic
 */

(function() {
    let exSidebar, exCollapseBtn, exExpandBtn, exNewBtn;
    let exPrompt, exModel, exGenerateBtn, exDeepDiveToggle;
    let exStatusArea, exStatusText, exProgressFill, exLogs;
    let exPlaceholder, exFrame;
    let exHistoryList;
    let exPageNav, exPageTabs;

    let exIsGenerating = false;
    let exCurrentThreadId = null;
    let exLastHtml = null;
    let exCurrentDeepDive = false;   // mode used when thread was created
    let exCurrentPage = 'index.html';

    async function initExplained() {
        // Capture Elements
        exSidebar    = document.getElementById('explained-sidebar');
        exCollapseBtn = document.getElementById('explained-collapse-btn');
        exExpandBtn  = document.getElementById('explained-expand-btn');
        exNewBtn     = document.getElementById('explained-new-btn');
        
        exPrompt     = document.getElementById('explained-prompt');
        exModel      = document.getElementById('explained-model-select');
        exGenerateBtn = document.getElementById('explained-generate-btn');
        exDeepDiveToggle = document.getElementById('explained-deep-dive-toggle');
        
        exStatusArea = document.getElementById('explained-status-area');
        exStatusText = document.getElementById('explained-status-text');
        exProgressFill = document.getElementById('explained-progress-fill');
        exLogs       = document.getElementById('explained-logs');
        
        exPlaceholder = document.getElementById('explained-placeholder');
        exFrame       = document.getElementById('explained-frame');
        exHistoryList = document.getElementById('explained-history-list');
        exPageNav     = document.getElementById('explained-page-nav');
        exPageTabs    = document.getElementById('explained-page-tabs');

        // Event Listeners
        if (exCollapseBtn) exCollapseBtn.addEventListener('click', toggleSidebar);
        if (exExpandBtn)   exExpandBtn.addEventListener('click', toggleSidebar);
        if (exNewBtn)      exNewBtn.addEventListener('click', resetSession);
        if (exGenerateBtn) exGenerateBtn.addEventListener('click', startGeneration);

        if (exModel) {
            exModel.addEventListener('change', () => {
                localStorage.setItem('explained_last_model', exModel.value);
            });
        }

        if (exDeepDiveToggle) {
            // Restore last state
            const saved = localStorage.getItem('explained_deep_dive') === 'true';
            exDeepDiveToggle.checked = saved;
            exDeepDiveToggle.addEventListener('change', () => {
                localStorage.setItem('explained_deep_dive', exDeepDiveToggle.checked);
            });
        }

        // Load Initial Data
        fetchModels();
        loadHistory();
    }

    function resetSession() {
        exCurrentThreadId = null;
        exLastHtml = null;
        exCurrentDeepDive = false;
        exCurrentPage = 'index.html';
        exPrompt.value = '';
        exPlaceholder.classList.remove('hidden');
        exFrame.classList.add('hidden');
        exFrame.src = 'about:blank';
        exGenerateBtn.innerHTML = '<i class="fas fa-wand-sparkles"></i> Build Page';
        hidePageNav();
        if (exSidebar.classList.contains('collapsed')) toggleSidebar();
        if (window.showToast) window.showToast('Ready for a new topic.', 'info');
    }

    function toggleSidebar() {
        exSidebar.classList.toggle('collapsed');
        if (exSidebar.classList.contains('collapsed')) {
            exExpandBtn.classList.remove('hidden');
        } else {
            exExpandBtn.classList.add('hidden');
        }
    }

    async function fetchModels() {
        try {
            const res = await fetch('/api/registry/models/chat');
            if (!res.ok) return;
            const data = await res.json();
            
            if (exModel) {
                const lastModel = localStorage.getItem('explained_last_model') || 'auto';
                if (window.generateCategorizedModelOptions) {
                    exModel.innerHTML = window.generateCategorizedModelOptions(data, 'chat', lastModel);
                } else {
                    let html = `<option value="auto" ${lastModel === 'auto' ? 'selected' : ''}>Auto Select</option>`;
                    for (const m of data.models || []) {
                        const s = m.id === lastModel ? 'selected' : '';
                        html += `<option value="${m.id}" ${s}>${m.name || m.id}</option>`;
                    }
                    exModel.innerHTML = html;
                }
            }
        } catch (e) {
            console.error("Failed to fetch Explained models", e);
        }
    }

    async function startGeneration() {
        if (exIsGenerating) return;
        
        const topic = exPrompt.value.trim();
        if (!topic) {
            if (window.showToast) window.showToast('Please enter a topic.', 'warn');
            return;
        }

        const modelId  = exModel.value;
        // Deep Dive mode is locked to the thread's creation mode; for new threads use the toggle
        const deepDive = exCurrentThreadId ? exCurrentDeepDive : (exDeepDiveToggle ? exDeepDiveToggle.checked : false);

        setLoading(true);
        if (exLogs) exLogs.innerHTML = ''; 
        updateStatus('Initializing...', 5);

        try {
            const res = await fetch('/api/explained/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    topic:     topic,
                    model_id:  modelId,
                    thread_id: exCurrentThreadId,
                    deep_dive: deepDive,
                })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Generation failed');
            }

            const data = await res.json();
            exCurrentThreadId  = data.thread_id;
            exCurrentDeepDive  = data.deep_dive || false;
            exCurrentPage      = 'index.html';
            
            if (data.task_id) {
                pollTask(data.task_id);
            }

        } catch (e) {
            console.error(e);
            if (window.showToast) window.showToast('Error: ' + e.message, 'error');
            updateStatus('Failed.', 0);
            setLoading(false);
        }
    }

    async function pollTask(taskId) {
        let lastLogCount = 0;
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/explained/status/${taskId}`);
                if (!res.ok) return;
                const data = await res.json();
                
                // Append new log entries
                if (data.logs && data.logs.length > lastLogCount) {
                    for (let i = lastLogCount; i < data.logs.length; i++) {
                        appendLog(data.logs[i]);
                    }
                    lastLogCount = data.logs.length;
                }

                // Refresh iframe whenever there is new HTML (intermediate or final)
                if (data.html && (data.html !== exLastHtml)) {
                    refreshIframe();
                    exLastHtml = data.html;
                }

                if (data.status === 'completed') {
                    clearInterval(interval);
                    updateStatus('Completed!', 100);
                    refreshIframe();
                    if (exCurrentDeepDive) await refreshPageNav();
                    setLoading(false);
                    // Use AI-generated title if available, otherwise fall back to prompt
                    const title = data.display_title || exPrompt.value.trim();
                    addToHistory(title, exCurrentThreadId, exCurrentDeepDive);
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    setLoading(false);
                    if (window.showToast) window.showToast('Generation failed: ' + (data.error || 'Unknown error'), 'error');
                } else {
                    updateStatus(data.step || 'Working...', null);
                }
            } catch (e) {
                console.error("Poll error", e);
            }
        }, 1500);
    }

    function appendLog(log) {
        if (!exLogs) return;
        const div = document.createElement('div');
        div.className = `es-log-entry ${log.type}`;
        div.innerText = `> ${log.msg}`;
        exLogs.appendChild(div);
        exLogs.scrollTop = exLogs.scrollHeight;
    }

    function refreshIframe() {
        if (!exCurrentThreadId) return;
        
        exPlaceholder.classList.add('hidden');
        exFrame.classList.remove('hidden');
        exGenerateBtn.innerHTML = '<i class="fas fa-sync"></i> Update Page';

        if (exCurrentDeepDive) {
            exFrame.src = `/api/explained/thread/${exCurrentThreadId}/page/${exCurrentPage}?t=${Date.now()}`;
        } else {
            exFrame.src = `/api/explained/thread/${exCurrentThreadId}/raw?t=${Date.now()}`;
        }
    }

    // ── Page Navigator (Deep Dive mode) ──────────────────────────────────────

    async function refreshPageNav() {
        if (!exCurrentThreadId || !exCurrentDeepDive) {
            hidePageNav();
            return;
        }
        try {
            const res = await fetch(`/api/explained/thread/${exCurrentThreadId}/pages`);
            if (!res.ok) return;
            const data = await res.json();
            renderPageNav(data.pages || []);
        } catch (e) {
            console.error('Failed to load page list', e);
        }
    }

    function renderPageNav(pages) {
        if (!exPageTabs || !exPageNav) return;
        if (!pages.length) { hidePageNav(); return; }

        exPageTabs.innerHTML = '';
        for (const p of pages) {
            const btn = document.createElement('button');
            btn.className = 'epn-tab' + (p.filename === exCurrentPage ? ' active' : '');
            btn.textContent = p.label;
            btn.dataset.filename = p.filename;
            btn.addEventListener('click', () => navigateToPage(p.filename));
            exPageTabs.appendChild(btn);
        }

        exPageNav.classList.remove('hidden');
    }

    function navigateToPage(filename) {
        exCurrentPage = filename;
        // Update active state on tabs
        if (exPageTabs) {
            exPageTabs.querySelectorAll('.epn-tab').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.filename === filename);
            });
        }
        if (exCurrentThreadId) {
            exPlaceholder.classList.add('hidden');
            exFrame.classList.remove('hidden');
            exFrame.src = `/api/explained/thread/${exCurrentThreadId}/page/${filename}?t=${Date.now()}`;
        }
    }

    function hidePageNav() {
        if (exPageNav) exPageNav.classList.add('hidden');
        if (exPageTabs) exPageTabs.innerHTML = '';
    }

    // ── Utility ───────────────────────────────────────────────────────────────

    function setLoading(loading) {
        exIsGenerating = loading;
        exGenerateBtn.disabled = loading;
        
        exStatusArea.style.display = loading ? 'flex' : 'none';
        if (!loading) {
            updateStatus('', 0);
        }
    }

    function updateStatus(text, progress) {
        if (exStatusText) exStatusText.innerText = text;
        if (progress !== null && exProgressFill) {
            exProgressFill.style.width = progress + '%';
        }
    }

    function addToHistory(title, threadId, deepDive) {
        let history = JSON.parse(localStorage.getItem('explained_history_v2') || '[]');
        history = history.filter(h => h.threadId !== threadId);
        
        // Find existing or next number
        let displayId = 0;
        if (history.length > 0) {
            displayId = Math.max(...history.map(h => h.displayId || 0)) + 1;
        }

        history.unshift({ title, threadId, displayId, deepDive: !!deepDive, timestamp: Date.now() });
        if (history.length > 30) history = history.slice(0, 30);
        localStorage.setItem('explained_history_v2', JSON.stringify(history));
        loadHistory();
    }

    function loadHistory() {
        if (!exHistoryList) return;
        const history = JSON.parse(localStorage.getItem('explained_history_v2') || '[]');
        
        if (history.length === 0) {
            exHistoryList.innerHTML = '<div class="es-empty">No creations yet</div>';
            return;
        }

        let html = '';
        for (const item of history) {
            const displayTitle = item.title || 'Untitled';
            const displayId    = item.displayId !== undefined ? `#${item.displayId}` : '';
            const badge        = item.deepDive
                ? `<span class="es-deep-badge" title="Deep Dive">⬡</span>`
                : '';
            
            html += `
                <div class="es-item" data-id="${item.threadId}">
                    <div class="es-item-main" onclick="loadExplanation('${item.threadId}')">
                        <span class="es-item-id">${displayId}</span>
                        ${badge}
                        <span class="es-item-text" title="${displayTitle}">${displayTitle}</span>
                    </div>
                    <button class="es-item-delete" onclick="deleteExplanation('${item.threadId}', event)" title="Delete Creation">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            `;
        }
        exHistoryList.innerHTML = html;
    }

    window.loadExplanation = async function(threadId) {
        setLoading(true);
        updateStatus('Loading...', 50);
        try {
            const res = await fetch(`/api/explained/thread/${threadId}`);
            if (!res.ok) throw new Error('Failed to load thread');
            const data = await res.json();
            
            exCurrentThreadId = threadId;
            exLastHtml        = data.html;
            exCurrentDeepDive = data.deep_dive || false;
            exCurrentPage     = 'index.html';
            exPrompt.value    = data.topic || '';

            // Sync the Deep Dive toggle to reflect this thread's mode (read-only info)
            if (exDeepDiveToggle) exDeepDiveToggle.checked = exCurrentDeepDive;

            refreshIframe(true);

            if (exCurrentDeepDive) {
                await refreshPageNav();
            } else {
                hidePageNav();
            }
        } catch (e) {
            if (window.showToast) window.showToast('Error loading: ' + e.message, 'error');
        } finally {
            setLoading(false);
        }
    }

    window.deleteExplanation = async function(threadId, event) {
        if (event) event.stopPropagation();
        
        if (!confirm('Are you sure you want to delete this creation?')) return;

        try {
            const res = await fetch(`/api/explained/thread/${threadId}`, { method: 'DELETE' });
            if (res.ok) {
                // Remove from local storage
                let history = JSON.parse(localStorage.getItem('explained_history_v2') || '[]');
                history = history.filter(h => h.threadId !== threadId);
                localStorage.setItem('explained_history_v2', JSON.stringify(history));
                
                if (exCurrentThreadId === threadId) {
                    resetSession();
                }
                
                loadHistory();
                if (window.showToast) window.showToast('Creation deleted.', 'success');
            } else {
                throw new Error('Failed to delete on server');
            }
        } catch (e) {
            if (window.showToast) window.showToast('Delete error: ' + e.message, 'error');
        }
    }

    document.addEventListener('panelLoaded', (e) => {
        if (e.detail.tabName === 'explained') {
            initExplained();
        }
    });

})();
