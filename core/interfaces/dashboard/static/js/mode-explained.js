/**
 * Aethvion - AI Explained Logic
 */

(function() {
    let exSidebar, exCollapseBtn, exExpandBtn;
    let exPrompt, exStyle, exModel, exGenerateBtn;
    let exStatusArea, exStatusText, exProgressFill;
    let exPlaceholder, exFrame;
    let exHistoryList;

    let exIsGenerating = false;
    let exCurrentThreadId = null;

    async function initExplained() {
        // Capture Elements
        exSidebar = document.getElementById('explained-sidebar');
        exCollapseBtn = document.getElementById('explained-collapse-btn');
        exExpandBtn = document.getElementById('explained-expand-btn');
        
        exPrompt = document.getElementById('explained-prompt');
        exStyle = document.getElementById('explained-style');
        exModel = document.getElementById('explained-model-select');
        exGenerateBtn = document.getElementById('explained-generate-btn');
        
        exStatusArea = document.getElementById('explained-status-area');
        exStatusText = document.getElementById('explained-status-text');
        exProgressFill = document.getElementById('explained-progress-fill');
        
        exPlaceholder = document.getElementById('explained-placeholder');
        exFrame = document.getElementById('explained-frame');
        exHistoryList = document.getElementById('explained-history-list');

        // Event Listeners
        if (exCollapseBtn) exCollapseBtn.addEventListener('click', toggleSidebar);
        if (exExpandBtn) exExpandBtn.addEventListener('click', toggleSidebar);
        if (exGenerateBtn) exGenerateBtn.addEventListener('click', startGeneration);

        // Load Initial Data
        fetchModels();
        loadHistory();
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
                // Reuse global generateCategorizedModelOptions if available
                if (window.generateCategorizedModelOptions) {
                    exModel.innerHTML = window.generateCategorizedModelOptions(data, 'chat', 'auto');
                } else {
                    // Fallback
                    let html = '<option value="auto">Auto Select</option>';
                    for (const m of data.models || []) {
                        html += `<option value="${m.id}">${m.name || m.id}</option>`;
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
            if (window.showToast) window.showToast('Please enter a topic to explain.', 'warn');
            return;
        }

        const modelId = exModel.value;
        const style = exStyle.value;

        setLoading(true);
        updateStatus('Initializing Agent...', 10);

        try {
            const res = await fetch('/api/explained/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    topic: topic,
                    style: style,
                    model_id: modelId
                })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Generation failed');
            }

            const data = await res.json();
            exCurrentThreadId = data.thread_id;
            
            // Start polling for status or wait for direct response
            // For now assume the backend takes some time and we might need to poll
            // but the user wants results "right away" (streaming or fast).
            // Let's assume the endpoint returns the final HTML once done for MVP.
            
            updateStatus('Building visual components...', 60);
            
            if (data.html) {
                displayResult(data.html);
                addToHistory(topic, data.thread_id);
            } else if (data.task_id) {
                // If it's a background task, we'd poll here. 
                // Given the instructions, we'll implement the backend to be as responsive as possible.
                pollTask(data.task_id);
            }

        } catch (e) {
            console.error(e);
            if (window.showToast) window.showToast('Error: ' + e.message, 'error');
            updateStatus('Failed to generate.', 0);
        } finally {
            if (!exIsGenerating) setLoading(false);
        }
    }

    async function pollTask(taskId) {
        let progress = 60;
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/explained/status/${taskId}`);
                if (!res.ok) return;
                const data = await res.json();
                
                if (data.status === 'completed') {
                    clearInterval(interval);
                    updateStatus('Completed!', 100);
                    displayResult(data.html);
                    setLoading(false);
                    addToHistory(data.topic, data.thread_id);
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    setLoading(false);
                    if (window.showToast) window.showToast('Generation failed: ' + data.error, 'error');
                } else {
                    progress = Math.min(95, progress + 2);
                    updateStatus(data.step || 'Assembling page...', progress);
                }
            } catch (e) {
                console.error("Poll error", e);
            }
        }, 2000);
    }

    function displayResult(html) {
        exPlaceholder.classList.add('hidden');
        exFrame.classList.remove('hidden');
        
        const doc = exFrame.contentWindow.document;
        doc.open();
        doc.write(html);
        doc.close();
        
        // Auto-collapse sidebar after successful generation to show full page
        if (!exSidebar.classList.contains('collapsed')) {
            toggleSidebar();
        }
    }

    function setLoading(loading) {
        exIsGenerating = loading;
        exGenerateBtn.disabled = loading;
        exGenerateBtn.innerHTML = loading ? 
            '<i class="fas fa-spinner fa-spin"></i> Building...' : 
            '<i class="fas fa-wand-sparkles"></i> Build Page';
        
        exStatusArea.style.display = loading ? 'flex' : 'none';
        if (!loading) {
            updateStatus('', 0);
        }
    }

    function updateStatus(text, progress) {
        if (exStatusText) exStatusText.innerText = text;
        if (exProgressFill) exProgressFill.style.width = progress + '%';
    }

    function addToHistory(topic, threadId) {
        let history = JSON.parse(localStorage.getItem('explained_history') || '[]');
        // Remove existing with same threadId if any
        history = history.filter(h => h.threadId !== threadId);
        history.unshift({ topic, threadId, timestamp: Date.now() });
        // Cap at 20
        if (history.length > 20) history = history.slice(0, 20);
        localStorage.setItem('explained_history', JSON.stringify(history));
        loadHistory();
    }

    function loadHistory() {
        if (!exHistoryList) return;
        const history = JSON.parse(localStorage.getItem('explained_history') || '[]');
        
        if (history.length === 0) {
            exHistoryList.innerHTML = '<div class="es-empty">No history yet</div>';
            return;
        }

        let html = '';
        for (const item of history) {
            html += `<div class="es-item" title="${item.topic}" onclick="loadExplanation('${item.threadId}')">
                <i class="fas fa-history"></i> ${item.topic}
            </div>`;
        }
        exHistoryList.innerHTML = html;
    }

    window.loadExplanation = async function(threadId) {
        setLoading(true);
        updateStatus('Loading past explanation...', 50);
        try {
            const res = await fetch(`/api/explained/thread/${threadId}`);
            if (!res.ok) throw new Error('Failed to load thread');
            const data = await res.json();
            displayResult(data.html);
        } catch (e) {
            if (window.showToast) window.showToast('Error loading: ' + e.message, 'error');
        } finally {
            setLoading(false);
        }
    }

    // Initialization hook from custom event (partial-loader.js)
    document.addEventListener('panelLoaded', (e) => {
        if (e.detail.tabName === 'explained') {
            initExplained();
        }
    });

})();
