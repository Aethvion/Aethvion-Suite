/**
 * Aethvion - AI Explained Logic
 */

(function() {
    let exSidebar, exCollapseBtn, exExpandBtn, exNewBtn;
    let exPrompt, exModel, exGenerateBtn, exDeepDiveToggle, exFolderBtn;
    let exStatusArea, exStatusText, exProgressFill, exLogs;
    let exPlaceholder, exFrame;
    let exHistoryList;
    let exPageNav, exPageTabs;
    let exUsageCard, esuModel, esuTokens, esuCost, esuDuration;
    let exEditToolbar, exEditToggleBtn, exEditHint;
    let exCommentsTray, exCommentsList, ectCount, ectSubmitBtn;
    let exAnnotPopup, eapTitle, eapInput;

    let exIsGenerating   = false;
    let exCurrentThreadId = null;
    let exLastHtml        = null;
    let exCurrentDeepDive = false;
    let exCurrentPage     = 'index.html';

    // ── Edit Mode State ────────────────────────────────────────────────────────
    let _editModeActive      = false;
    let _sectionComments     = {};   // { sectionIdx: { heading, comment } }
    let _pendingPopupSection = null;

    // CSS injected into the iframe when edit mode is active
    const IFRAME_EDIT_CSS = `
#expl-edit-banner {
    position: fixed !important;
    top: 0 !important; left: 0 !important; right: 0 !important;
    background: rgba(0,217,255,0.07) !important;
    border-bottom: 1px solid rgba(0,217,255,0.2) !important;
    color: #00d9ff !important;
    text-align: center !important;
    padding: 5px 12px !important;
    font-size: 11px !important;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif !important;
    z-index: 99998 !important;
    pointer-events: none !important;
    letter-spacing: 0.05em !important;
    box-sizing: border-box !important;
}
.expl-annotatable {
    outline: 1px dashed transparent !important;
    transition: outline-color 0.2s !important;
    position: relative !important;
}
.expl-annotatable:hover {
    outline-color: rgba(0,217,255,0.25) !important;
    outline-offset: 2px !important;
}
.expl-annot-btn {
    position: absolute !important;
    top: 6px !important; right: 6px !important;
    background: rgba(10,10,20,0.85) !important;
    border: 1px solid rgba(0,217,255,0.45) !important;
    border-radius: 4px !important;
    color: #00d9ff !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif !important;
    padding: 2px 8px !important;
    cursor: pointer !important;
    z-index: 99999 !important;
    white-space: nowrap !important;
    transition: background 0.15s, border-color 0.15s !important;
    line-height: 1.6 !important;
}
.expl-annot-btn:hover {
    background: rgba(0,217,255,0.15) !important;
    border-color: rgba(0,217,255,0.7) !important;
}
.expl-annot-btn.has-comment {
    background: rgba(99,102,241,0.25) !important;
    border-color: rgba(99,102,241,0.6) !important;
    color: #a5b4fc !important;
}`;

    // ── Init ───────────────────────────────────────────────────────────────────

    async function initExplained() {
        exSidebar    = document.getElementById('explained-sidebar');
        exCollapseBtn = document.getElementById('explained-collapse-btn');
        exExpandBtn  = document.getElementById('explained-expand-btn');
        exNewBtn     = document.getElementById('explained-new-btn');
        exPrompt     = document.getElementById('explained-prompt');
        exModel      = document.getElementById('explained-model-select');
        exGenerateBtn = document.getElementById('explained-generate-btn');
        exDeepDiveToggle = document.getElementById('explained-deep-dive-toggle');
        exFolderBtn     = document.getElementById('explained-folder-btn');
        exStatusArea = document.getElementById('explained-status-area');
        exStatusText = document.getElementById('explained-status-text');
        exProgressFill = document.getElementById('explained-progress-fill');
        exLogs       = document.getElementById('explained-logs');
        exPlaceholder = document.getElementById('explained-placeholder');
        exFrame       = document.getElementById('explained-frame');
        exHistoryList = document.getElementById('explained-history-list');
        exPageNav     = document.getElementById('explained-page-nav');
        exPageTabs    = document.getElementById('explained-page-tabs');
        exUsageCard   = document.getElementById('explained-usage-card');
        esuModel      = document.getElementById('esu-model');
        esuTokens     = document.getElementById('esu-tokens');
        esuCost       = document.getElementById('esu-cost');
        esuDuration   = document.getElementById('esu-duration');
        exEditToolbar    = document.getElementById('expl-edit-toolbar');
        exEditToggleBtn  = document.getElementById('expl-edit-toggle-btn');
        exEditHint       = document.getElementById('expl-edit-hint');
        exCommentsTray   = document.getElementById('expl-comments-tray');
        exCommentsList   = document.getElementById('ect-list');
        ectCount         = document.getElementById('ect-count');
        ectSubmitBtn     = document.getElementById('expl-submit-comments');
        exAnnotPopup     = document.getElementById('expl-annot-popup');
        eapTitle         = document.getElementById('eap-section-title');
        eapInput         = document.getElementById('eap-input');

        // Existing listeners
        if (exCollapseBtn) exCollapseBtn.addEventListener('click', toggleSidebar);
        if (exExpandBtn)   exExpandBtn.addEventListener('click', toggleSidebar);
        if (exNewBtn)      exNewBtn.addEventListener('click', resetSession);
        if (exGenerateBtn) exGenerateBtn.addEventListener('click', startGeneration);
        if (exFolderBtn)   exFolderBtn.addEventListener('click', openCurrentFolder);
        if (exModel) {
            exModel.addEventListener('change', () => {
                localStorage.setItem('explained_last_model', exModel.value);
            });
        }
        if (exDeepDiveToggle) {
            const saved = localStorage.getItem('explained_deep_dive') === 'true';
            exDeepDiveToggle.checked = saved;
            exDeepDiveToggle.addEventListener('change', () => {
                localStorage.setItem('explained_deep_dive', exDeepDiveToggle.checked);
            });
        }

        // Edit mode listeners
        if (exEditToggleBtn) exEditToggleBtn.addEventListener('click', toggleEditMode);

        // Comments tray listeners
        document.getElementById('expl-clear-comments')?.addEventListener('click', () => {
            _sectionComments = {};
            _clearIframeCommentBadges();
            renderCommentsTray();
        });
        if (ectSubmitBtn) ectSubmitBtn.addEventListener('click', submitAnnotatedUpdate);

        // Annotation popup listeners
        document.getElementById('eap-cancel-btn')?.addEventListener('click', hideAnnotationPopup);
        document.getElementById('eap-add-btn')?.addEventListener('click', applyAnnotationComment);
        if (eapInput) {
            eapInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); applyAnnotationComment(); }
            });
        }
        // Quick action chips
        exAnnotPopup?.querySelectorAll('.eap-quick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                exAnnotPopup.querySelectorAll('.eap-quick-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                if (eapInput) eapInput.value = btn.dataset.val;
                if (eapInput) eapInput.focus();
            });
        });
        // Close popup when clicking outside
        document.addEventListener('click', (e) => {
            if (exAnnotPopup && !exAnnotPopup.classList.contains('hidden') &&
                !exAnnotPopup.contains(e.target)) {
                hideAnnotationPopup();
            }
        });

        // Load initial data
        fetchModels();
        loadHistory();
    }

    // ── Edit Mode ──────────────────────────────────────────────────────────────

    function toggleEditMode() {
        _editModeActive = !_editModeActive;
        if (exEditToggleBtn) exEditToggleBtn.classList.toggle('active', _editModeActive);
        if (exEditHint) exEditHint.classList.toggle('hidden', !_editModeActive);

        if (_editModeActive) {
            injectEditMode();
        } else {
            clearEditMode();
        }
    }

    function injectEditMode() {
        if (!exFrame || exFrame.classList.contains('hidden')) return;
        try {
            const iframeDoc = exFrame.contentDocument || exFrame.contentWindow?.document;
            if (!iframeDoc || !iframeDoc.body) return;

            // Inject CSS once
            if (!iframeDoc.getElementById('expl-edit-styles')) {
                const style = iframeDoc.createElement('style');
                style.id = 'expl-edit-styles';
                style.textContent = IFRAME_EDIT_CSS;
                iframeDoc.head.appendChild(style);
            }

            // Banner
            if (!iframeDoc.getElementById('expl-edit-banner')) {
                const banner = iframeDoc.createElement('div');
                banner.id = 'expl-edit-banner';
                banner.textContent = '✏  Edit Mode Active — click any section to annotate it';
                iframeDoc.body.prepend(banner);
            }

            // Detect annotatable sections
            // Prioritise semantic containers; fall back to heading elements
            const SELECTORS = [
                'section', 'article',
                '[class*="section"]', '[class*="card"]', '[class*="chapter"]',
                '[class*="topic"]', '[class*="block"]', '[class*="panel"]',
                'h2', 'h3'
            ].join(', ');

            const candidates = [...iframeDoc.querySelectorAll(SELECTORS)];

            // Deduplicate: skip an element if an ancestor is already in the set
            const selected = [];
            const selectedSet = new Set();
            for (const el of candidates) {
                let dominated = false;
                let p = el.parentElement;
                while (p) {
                    if (selectedSet.has(p)) { dominated = true; break; }
                    p = p.parentElement;
                }
                if (!dominated) {
                    selected.push(el);
                    selectedSet.add(el);
                }
            }

            selected.forEach((el, idx) => {
                if (el.querySelector('.expl-annot-btn')) return; // already injected

                const currentPos = iframeDoc.defaultView?.getComputedStyle(el)?.position;
                if (!currentPos || currentPos === 'static') el.style.position = 'relative';
                el.classList.add('expl-annotatable');
                el.dataset.explIdx = String(idx);

                const btn = iframeDoc.createElement('button');
                btn.className = 'expl-annot-btn';
                btn.dataset.explIdx = String(idx);

                // Restore any existing comment badge
                if (_sectionComments[idx]) {
                    btn.classList.add('has-comment');
                    const short = _sectionComments[idx].comment;
                    btn.textContent = '✏ ' + short.slice(0, 22) + (short.length > 22 ? '…' : '');
                } else {
                    btn.textContent = '+ Comment';
                }

                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    e.preventDefault();

                    // Map click position to parent-window coordinates
                    const iframeRect = exFrame.getBoundingClientRect();
                    const btnRect    = btn.getBoundingClientRect();
                    const x = iframeRect.left + btnRect.left;
                    const y = iframeRect.top  + btnRect.bottom + 6;

                    // Extract a clean heading label
                    const rawText = (el.textContent || '')
                        .replace(/\+\s*Comment/g, '')
                        .replace(/✏[^\n]*/g, '')
                        .trim()
                        .replace(/\s+/g, ' ')
                        .slice(0, 72);

                    showAnnotationPopup(idx, rawText, x, y, btn);
                });

                el.appendChild(btn);
            });
        } catch (err) {
            console.warn('[Explained] Edit mode inject failed:', err);
        }
    }

    function clearEditMode() {
        hideAnnotationPopup();
        try {
            const iframeDoc = exFrame?.contentDocument || exFrame?.contentWindow?.document;
            if (!iframeDoc) return;
            iframeDoc.getElementById('expl-edit-styles')?.remove();
            iframeDoc.getElementById('expl-edit-banner')?.remove();
            iframeDoc.querySelectorAll('.expl-annot-btn').forEach(el => el.remove());
            iframeDoc.querySelectorAll('.expl-annotatable').forEach(el => {
                el.classList.remove('expl-annotatable');
            });
        } catch (e) {}
    }

    function _clearIframeCommentBadges() {
        try {
            const iframeDoc = exFrame?.contentDocument || exFrame?.contentWindow?.document;
            if (!iframeDoc) return;
            iframeDoc.querySelectorAll('.expl-annot-btn').forEach(btn => {
                btn.classList.remove('has-comment');
                btn.textContent = '+ Comment';
            });
        } catch (e) {}
    }

    // ── Annotation popup ───────────────────────────────────────────────────────

    function showAnnotationPopup(sectionIdx, heading, x, y, triggerBtn) {
        if (!exAnnotPopup) return;
        _pendingPopupSection = { sectionIdx, triggerBtn };

        if (eapTitle) eapTitle.textContent = heading || 'Section';

        // Reset quick buttons
        exAnnotPopup.querySelectorAll('.eap-quick-btn').forEach(b => b.classList.remove('active'));

        // Pre-fill existing comment if any
        const existing = _sectionComments[sectionIdx];
        if (eapInput) {
            eapInput.value = existing ? existing.comment : '';
            if (existing) {
                exAnnotPopup.querySelectorAll('.eap-quick-btn').forEach(b => {
                    if (b.dataset.val === existing.comment) b.classList.add('active');
                });
            }
        }

        // Position within viewport
        if (exAnnotPopup.parentNode !== document.body) {
            document.body.appendChild(exAnnotPopup);
        }
        exAnnotPopup.classList.remove('hidden');
        const iframeRect = exFrame.getBoundingClientRect();
        const pw = exAnnotPopup.offsetWidth  || 290;
        const ph = exAnnotPopup.offsetHeight || 210;
        let left = Math.min(x, iframeRect.right - pw - 12);
        let top  = y;
        if (top + ph > window.innerHeight - 12) top = y - ph - 55;
        exAnnotPopup.style.left = Math.max(8, left) + 'px';
        exAnnotPopup.style.top  = Math.max(8, top)  + 'px';

        if (eapInput) eapInput.focus();
    }

    function hideAnnotationPopup() {
        if (exAnnotPopup) exAnnotPopup.classList.add('hidden');
        _pendingPopupSection = null;
    }

    function applyAnnotationComment() {
        if (!_pendingPopupSection) return;
        const comment = eapInput?.value.trim();
        if (!comment) { hideAnnotationPopup(); return; }

        const { sectionIdx, triggerBtn } = _pendingPopupSection;
        const heading = eapTitle?.textContent || 'Section';

        _sectionComments[sectionIdx] = { heading, comment };

        // Update the iframe badge
        if (triggerBtn) {
            triggerBtn.classList.add('has-comment');
            triggerBtn.textContent = '✏ ' + comment.slice(0, 22) + (comment.length > 22 ? '…' : '');
        }

        hideAnnotationPopup();
        renderCommentsTray();
    }

    // ── Comments tray ──────────────────────────────────────────────────────────

    function renderCommentsTray() {
        const entries = Object.entries(_sectionComments);
        const count   = entries.length;

        if (ectCount)    ectCount.textContent = count;
        if (ectSubmitBtn) {
            ectSubmitBtn.innerHTML = `<i class="fas fa-wand-sparkles"></i> Update Page (${count})`;
        }

        if (!exCommentsTray) return;
        exCommentsTray.classList.toggle('hidden', count === 0);
        if (!exCommentsList) return;

        exCommentsList.innerHTML = entries.map(([idx, c]) => `
            <div class="ect-item">
                <div class="ect-item-body">
                    <span class="ect-item-section">${_escHtml(c.heading)}</span>
                    <span class="ect-item-arrow">→</span>
                    <span class="ect-item-comment">${_escHtml(c.comment)}</span>
                </div>
                <button class="ect-item-remove" onclick="explRemoveSectionComment(${idx})" title="Remove">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');
    }

    window.explRemoveSectionComment = function(idx) {
        delete _sectionComments[idx];
        // Reset the badge in iframe
        try {
            const iframeDoc = exFrame?.contentDocument;
            const btn = iframeDoc?.querySelector(`.expl-annot-btn[data-expl-idx="${idx}"]`);
            if (btn) { btn.classList.remove('has-comment'); btn.textContent = '+ Comment'; }
        } catch (e) {}
        renderCommentsTray();
    };

    function buildUpdatePrompt() {
        const entries = Object.values(_sectionComments);
        if (!entries.length) return '';
        const changes = entries.map(c =>
            `[Section: "${c.heading}"]\n→ ${c.comment}`
        ).join('\n\n');
        return `Apply the following targeted changes to specific sections of this page:\n\n${changes}\n\nUpdate only the affected sections — keep everything else intact.`;
    }

    async function submitAnnotatedUpdate() {
        const prompt = buildUpdatePrompt();
        if (!prompt) { if (window.showToast) window.showToast('No comments to apply.', 'warn'); return; }
        if (!exCurrentThreadId) { if (window.showToast) window.showToast('No active page.', 'warn'); return; }
        if (exIsGenerating) return;

        // Exit edit mode
        if (_editModeActive) {
            _editModeActive = false;
            if (exEditToggleBtn) exEditToggleBtn.classList.remove('active');
            if (exEditHint) exEditHint.classList.add('hidden');
            clearEditMode();
        }
        // Clear comments now
        _sectionComments = {};
        renderCommentsTray();

        setLoading(true);
        if (exLogs) exLogs.innerHTML = '';
        updateStatus('Applying changes...', 10);

        try {
            const res = await fetch('/api/explained/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    topic:     prompt,
                    model_id:  exModel.value,
                    thread_id: exCurrentThreadId,
                    deep_dive: exCurrentDeepDive,
                })
            });
            if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Update failed'); }
            const data = await res.json();
            if (data.task_id) pollTask(data.task_id);
        } catch (e) {
            console.error(e);
            if (window.showToast) window.showToast('Update failed: ' + e.message, 'error');
            updateStatus('Failed.', 0);
            setLoading(false);
        }
    }

    // ── Core generation ────────────────────────────────────────────────────────

    function resetSession() {
        exCurrentThreadId = null;
        exLastHtml        = null;
        exCurrentDeepDive = false;
        exCurrentPage     = 'index.html';
        exPrompt.value    = '';
        exPlaceholder.classList.remove('hidden');
        exFrame.classList.add('hidden');
        exFrame.src = 'about:blank';
        exGenerateBtn.innerHTML = '<i class="fas fa-wand-sparkles"></i> Build Page';
        if (exFolderBtn) exFolderBtn.classList.add('hidden');
        hidePageNav();
        if (exUsageCard) exUsageCard.classList.add('hidden');
        if (exSidebar.classList.contains('collapsed')) toggleSidebar();

        // Reset edit mode
        _editModeActive  = false;
        _sectionComments = {};
        _pendingPopupSection = null;
        if (exEditToggleBtn) exEditToggleBtn.classList.remove('active');
        if (exEditHint)  exEditHint.classList.add('hidden');
        if (exEditToolbar) exEditToolbar.classList.add('hidden');
        hideAnnotationPopup();
        renderCommentsTray();

        if (window.showToast) window.showToast('Ready for a new topic.', 'info');
    }

    function toggleSidebar() {
        exSidebar.classList.toggle('collapsed');
        exExpandBtn.classList.toggle('hidden', !exSidebar.classList.contains('collapsed'));
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
        if (!topic) { if (window.showToast) window.showToast('Please enter a topic.', 'warn'); return; }

        const modelId  = exModel.value;
        const deepDive = exCurrentThreadId ? exCurrentDeepDive : (exDeepDiveToggle ? exDeepDiveToggle.checked : false);

        setLoading(true);
        if (exLogs) exLogs.innerHTML = '';
        updateStatus('Initializing...', 5);

        try {
            const res = await fetch('/api/explained/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic, model_id: modelId, thread_id: exCurrentThreadId, deep_dive: deepDive })
            });
            if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Generation failed'); }
            const data = await res.json();
            exCurrentThreadId = data.thread_id;
            exCurrentDeepDive = data.deep_dive || false;
            exCurrentPage     = 'index.html';
            if (data.task_id) pollTask(data.task_id);
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

                if (data.logs && data.logs.length > lastLogCount) {
                    for (let i = lastLogCount; i < data.logs.length; i++) appendLog(data.logs[i]);
                    lastLogCount = data.logs.length;
                }

                if (data.html && data.html !== exLastHtml) {
                    refreshIframe();
                    exLastHtml = data.html;
                }

                if (data.status === 'completed') {
                    clearInterval(interval);
                    updateStatus('Completed!', 100);
                    refreshIframe();
                    if (exCurrentDeepDive) await refreshPageNav();
                    setLoading(false);
                    const title = data.display_title || exPrompt.value.trim();
                    addToHistory(title, exCurrentThreadId, exCurrentDeepDive);
                    updateUsageInfo(data.usage, data.duration, data.actual_model || data.model_id);
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    setLoading(false);
                    if (window.showToast) window.showToast('Generation failed: ' + (data.error || 'Unknown error'), 'error');
                } else {
                    updateStatus(data.step || 'Working...', null);
                }
            } catch (e) { console.error("Poll error", e); }
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

    async function openCurrentFolder() {
        if (!exCurrentThreadId) return;
        try {
            const res = await fetch(`/api/explained/thread/${exCurrentThreadId}/folder-path`);
            if (!res.ok) throw new Error('Could not get folder path');
            const data = await res.json();
            if (window.openModuleFolder) {
                window.openModuleFolder(data.path);
            } else {
                await fetch('/api/system/modules/open-folder', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: data.path })
                });
            }
        } catch (e) { if (window.showToast) window.showToast('Could not open folder: ' + e.message, 'error'); }
    }

    function refreshIframe() {
        if (!exCurrentThreadId) return;

        exPlaceholder.classList.add('hidden');
        exFrame.classList.remove('hidden');
        exGenerateBtn.innerHTML = '<i class="fas fa-sync"></i> Update Page';
        if (exFolderBtn) exFolderBtn.classList.remove('hidden');
        if (exEditToolbar) exEditToolbar.classList.remove('hidden');

        const url = exCurrentDeepDive
            ? `/api/explained/thread/${exCurrentThreadId}/page/${exCurrentPage}?t=${Date.now()}`
            : `/api/explained/thread/${exCurrentThreadId}/raw?t=${Date.now()}`;

        exFrame.src = url;

        // Re-inject edit mode after iframe loads (content changed after update)
        exFrame.onload = () => {
            if (_editModeActive) injectEditMode();
        };
    }

    // ── Page Navigator (Deep Dive) ─────────────────────────────────────────────

    async function refreshPageNav() {
        if (!exCurrentThreadId || !exCurrentDeepDive) { hidePageNav(); return; }
        try {
            const res = await fetch(`/api/explained/thread/${exCurrentThreadId}/pages`);
            if (!res.ok) return;
            const data = await res.json();
            renderPageNav(data.pages || []);
        } catch (e) { console.error('Failed to load page list', e); }
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
        // Exit edit mode when switching pages (comments are per-view)
        if (_editModeActive) {
            _editModeActive = false;
            if (exEditToggleBtn) exEditToggleBtn.classList.remove('active');
            if (exEditHint) exEditHint.classList.add('hidden');
            clearEditMode();
        }

        exCurrentPage = filename;
        if (exPageTabs) {
            exPageTabs.querySelectorAll('.epn-tab').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.filename === filename);
            });
        }
        if (exCurrentThreadId) {
            exPlaceholder.classList.add('hidden');
            exFrame.classList.remove('hidden');
            exFrame.src = `/api/explained/thread/${exCurrentThreadId}/page/${filename}?t=${Date.now()}`;
            exFrame.onload = () => { if (_editModeActive) injectEditMode(); };
        }
    }

    function hidePageNav() {
        if (exPageNav) exPageNav.classList.add('hidden');
        if (exPageTabs) exPageTabs.innerHTML = '';
    }

    // ── Utility ────────────────────────────────────────────────────────────────

    function setLoading(loading) {
        exIsGenerating = loading;
        exGenerateBtn.disabled = loading;
        exStatusArea.style.display = loading ? 'flex' : 'none';
        if (!loading) updateStatus('', 0);
    }

    function updateStatus(text, progress) {
        if (exStatusText) exStatusText.innerText = text;
        if (progress !== null && exProgressFill) exProgressFill.style.width = progress + '%';
    }

    function addToHistory(title, threadId, deepDive) {
        let history = JSON.parse(localStorage.getItem('explained_history_v2') || '[]');
        history = history.filter(h => h.threadId !== threadId);
        let displayId = history.length > 0 ? Math.max(...history.map(h => h.displayId || 0)) + 1 : 0;
        history.unshift({ title, threadId, displayId, deepDive: !!deepDive, timestamp: Date.now() });
        if (history.length > 30) history = history.slice(0, 30);
        localStorage.setItem('explained_history_v2', JSON.stringify(history));
        loadHistory();
    }

    function loadHistory() {
        if (!exHistoryList) return;
        const history = JSON.parse(localStorage.getItem('explained_history_v2') || '[]');
        if (history.length === 0) { exHistoryList.innerHTML = '<div class="es-empty">No creations yet</div>'; return; }
        let html = '';
        for (const item of history) {
            const displayTitle = item.title || 'Untitled';
            const displayId    = item.displayId !== undefined ? `#${item.displayId}` : '';
            const badge        = item.deepDive ? `<span class="es-deep-badge" title="Deep Dive">⬡</span>` : '';
            html += `
                <div class="es-item" data-id="${item.threadId}">
                    <div class="es-item-main" onclick="loadExplanation('${item.threadId}')">
                        <span class="es-item-id">${displayId}</span>${badge}
                        <span class="es-item-text" title="${displayTitle}">${displayTitle}</span>
                    </div>
                    <button class="es-item-delete" onclick="deleteExplanation('${item.threadId}', event)" title="Delete">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>`;
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
            if (exDeepDiveToggle) exDeepDiveToggle.checked = exCurrentDeepDive;
            refreshIframe(true);
            if (exFolderBtn) exFolderBtn.classList.remove('hidden');
            if (exCurrentDeepDive) await refreshPageNav(); else hidePageNav();
            updateUsageInfo(data.usage, data.duration, data.actual_model);
        } catch (e) {
            if (window.showToast) window.showToast('Error loading: ' + e.message, 'error');
        } finally { setLoading(false); }
    };

    function updateUsageInfo(usage, duration, actualModel) {
        if (!exUsageCard) return;
        if (!usage && !duration) { exUsageCard.classList.add('hidden'); return; }
        if (esuModel)   esuModel.innerText   = actualModel || 'AI';
        if (esuTokens)  esuTokens.innerText  = usage ? (usage.total_tokens || '-') : '-';
        if (esuCost)    esuCost.innerText     = usage ? `$${(usage.total_cost || 0).toFixed(4)}` : '$0.00';
        if (esuDuration) {
            const sec = Math.round(duration || 0);
            esuDuration.innerText = sec > 60 ? `${Math.floor(sec/60)}m ${sec%60}s` : `${sec}s`;
        }
        exUsageCard.classList.remove('hidden');
    }

    window.deleteExplanation = async function(threadId, event) {
        if (event) event.stopPropagation();
        if (!confirm('Are you sure you want to delete this creation?')) return;
        try {
            const res = await fetch(`/api/explained/thread/${threadId}`, { method: 'DELETE' });
            if (res.ok) {
                let history = JSON.parse(localStorage.getItem('explained_history_v2') || '[]');
                history = history.filter(h => h.threadId !== threadId);
                localStorage.setItem('explained_history_v2', JSON.stringify(history));
                if (exCurrentThreadId === threadId) resetSession();
                loadHistory();
                if (window.showToast) window.showToast('Creation deleted.', 'success');
            } else { throw new Error('Failed to delete on server'); }
        } catch (e) { if (window.showToast) window.showToast('Delete error: ' + e.message, 'error'); }
    };

    function _escHtml(str) {
        return String(str)
            .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    // ── Panel load hook ────────────────────────────────────────────────────────

    document.addEventListener('panelLoaded', (e) => {
        if (e.detail.tabName === 'explained') initExplained();
    });

})();
