// Aethvion Suite - Persistent Memory View
// Handles management of the cross-thread persistent JSON memory store.

const PersistentMemory = {
    isInitializing: false,
    lastLoadTime: 0,

    async init() {
        if (this.isInitializing) return;
        
        // Don't re-init if loaded within last 2 seconds (debounce)
        if (Date.now() - this.lastLoadTime < 2000) return;

        console.log("[PersistentMemory] Initializing visualization...");
        this.isInitializing = true;
        
        try {
            await this.load();
        } finally {
            this.isInitializing = false;
        }
    },

    async load() {
        const grid = document.getElementById('persistent-memory-grid');
        if (grid) grid.innerHTML = '<div class="loading-placeholder">Searching neural nodes...</div>';

        console.log("[PersistentMemory] Fetching from API...");
        try {
            const response = await fetch('/api/memory/persistent');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            
            console.log(`[PersistentMemory] Received ${Object.keys(data).length} topics`);
            this.lastLoadTime = Date.now();
            this.render(data);
        } catch (err) {
            console.error("[PersistentMemory] load error:", err);
            if (grid) grid.innerHTML = `
                <div class="error-notice" style="padding: 2rem; text-align: center; color: var(--error);">
                    <i class="fas fa-exclamation-triangle" style="font-size: 2rem; margin-bottom: 1rem;"></i>
                    <p>Failed to retrieve persistent memory.</p>
                    <small style="opacity: 0.7;">${err.message}</small>
                </div>
            `;
        }
    },

    render(memory) {
        const grid = document.getElementById('persistent-memory-grid');
        if (!grid) return;

        if (!memory || typeof memory !== 'object') {
            console.warn("[PersistentMemory] Received invalid memory data:", memory);
            return;
        }

        const topics = Object.keys(memory).sort();
        this.updateStats(memory);

        if (topics.length === 0) {
            grid.innerHTML = `
                <div class="empty-state-notice" style="grid-column: 1 / -1; text-align: center; padding: 4rem; background: rgba(255,255,255,0.02); border-radius: 12px; border: 1px dashed var(--border); margin: 1rem;">
                    <i class="fas fa-brain" style="font-size: 3.5rem; opacity: 0.15; margin-bottom: 1.5rem; display: block;"></i>
                    <h3 style="font-family: 'Orbitron', sans-serif; letter-spacing: 1px; color: var(--text-primary);">No persistent insights indexed yet</h3>
                    <p style="color: var(--text-tertiary); max-width: 400px; margin: 1rem auto; font-size: 0.9rem;">As you interact with the AI, important facts and preferences will be distilled into this long-term knowledge base.</p>
                </div>
            `;
            return;
        }

        grid.innerHTML = topics.map(topic => {
            const data = memory[topic];
            // Support both old string format and new object format
            const content = (data && typeof data === 'object') ? (data.content || '') : String(data || '');
            const updated = (data && typeof data === 'object') ? data.updated_at : null;
            const safeTopic = topic.replace(/"/g, '&quot;');
            
            const updatedStr = updated ? new Date(updated).toLocaleString('en-GB', { 
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' 
            }) : 'Historical';

            return `
                <div class="memory-card" data-topic="${safeTopic}" style="background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 10px; display: flex; flex-direction: column; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); overflow: hidden; position: relative;">
                    <div class="card-header" style="padding: 1.2rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: flex-start; background: rgba(255,255,255,0.02);">
                        <div style="flex: 1; padding-right: 12px;">
                            <h4 style="margin: 0; color: var(--primary); font-family: 'Orbitron', sans-serif; font-size: 0.85rem; line-height: 1.4; word-break: break-all; letter-spacing: 0.5px;">${topic}</h4>
                            <div style="font-size: 0.68rem; color: var(--text-tertiary); margin-top: 6px; display: flex; gap: 12px; align-items: center; font-family: 'Fira Code', monospace;">
                                <span><i class="far fa-clock" style="margin-right: 4px;"></i>${updatedStr}</span>
                                <span><i class="fas fa-hashtag" style="margin-right: 4px;"></i>${content.length} chars</span>
                            </div>
                        </div>
                        <div class="card-actions" style="display: flex; gap: 6px;">
                            <button class="icon-btn xs-btn edit-btn" onclick="PersistentMemory.editTopic('${safeTopic}')" title="Modify Knowledge"><i class="fas fa-pen-nib"></i></button>
                            <button class="icon-btn xs-btn danger delete-btn" onclick="PersistentMemory.deleteTopic('${safeTopic}')" title="Prune Insight"><i class="fas fa-trash-alt"></i></button>
                        </div>
                    </div>
                    <div class="card-body" style="padding: 1.5rem; flex: 1; max-height: 350px; overflow-y: auto; font-size: 0.88rem; line-height: 1.7; color: var(--text-secondary); white-space: pre-wrap; font-family: 'Inter', sans-serif; scrollbar-width: thin;">${content.trim()}</div>
                </div>
            `;
        }).join('');
    },

    formatContent(content) {
        return content.trim();
    },

    updateStats(memory) {
        const topics = Object.keys(memory);
        const count = topics.length;
        let totalChars = 0;
        
        topics.forEach(t => {
            const data = memory[t];
            const content = (data && typeof data === 'object') ? (data.content || '') : String(data || '');
            totalChars += content.length;
        });

        const estTokens = Math.ceil(totalChars / 3.75);
        const totalSizeKB = (totalChars / 1024).toFixed(1);

        const countEl = document.getElementById('pm-stat-count');
        const sizeEl = document.getElementById('pm-stat-size');
        const tokensEl = document.getElementById('pm-stat-tokens');

        if (countEl) countEl.innerText = count;
        if (sizeEl) sizeEl.innerText = `${totalSizeKB} KB`;
        if (tokensEl) tokensEl.innerText = estTokens.toLocaleString();
    },

    async deleteTopic(topic) {
        if (!confirm(`Permanently remove insight "${topic}" from neural memory?`)) return;

        try {
            const response = await fetch(`/api/memory/persistent/${encodeURIComponent(topic)}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                showToast(`Pruned topic: ${topic}`, 'info');
                await this.load();
            } else {
                throw new Error("Delete operation failed");
            }
        } catch (err) {
            showToast("Failed to prune topic: " + err.message, 'error');
        }
    },

    async editTopic(topic) {
        const card = document.querySelector(`.memory-card[data-topic="${topic}"]`);
        if (!card) return;

        const body = card.querySelector('.card-body');
        const currentContent = body.innerText;

        card.classList.add('editing');

        body.innerHTML = `
            <textarea style="width: 100%; min-height: 250px; background: rgba(0,0,0,0.3); color: #fff; border: 1px solid var(--primary); border-radius: 6px; padding: 1rem; font-family: 'Fira Code', monospace; font-size: 0.85rem; outline: none; resize: vertical; line-height: 1.6; box-shadow: inset 0 2px 10px rgba(0,0,0,0.5);">${currentContent}</textarea>
            <div style="margin-top: 12px; font-size: 0.72rem; color: var(--text-tertiary); font-style: italic; background: rgba(99, 102, 241, 0.05); padding: 8px; border-radius: 4px; border-left: 2px solid var(--primary);">
                <i class="fas fa-info-circle"></i> Direct neural modification will synchronize across all active AI instances.
            </div>
        `;

        const actions = card.querySelector('.card-actions');
        actions.innerHTML = `
            <button class="action-btn sm-btn primary save-btn" onclick="PersistentMemory.saveTopic('${topic.replace(/"/g, '&quot;')}')"><i class="fas fa-save"></i> Commit</button>
            <button class="action-btn sm-btn secondary cancel-btn" onclick="PersistentMemory.cancelEdit('${topic.replace(/"/g, '&quot;')}')"><i class="fas fa-times"></i> Revert</button>
        `;
    },

    cancelEdit(topic) {
        this.load();
    },

    async saveTopic(topic) {
        const card = document.querySelector(`.memory-card[data-topic="${topic}"]`);
        if (!card) return;

        const textarea = card.querySelector('textarea');
        const newContent = textarea.value;

        try {
            const response = await fetch('/api/memory/persistent/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic, content: newContent })
            });

            if (response.ok) {
                showToast(`Synchronized insight: ${topic}`, 'success');
                await this.load();
            } else {
                const errData = await response.json();
                throw new Error(errData.detail || "Update synchronized failure");
            }
        } catch (err) {
            showToast("Sync error: " + err.message, 'error');
        }
    }
};

// Load data + wire buttons when the partial is injected (partial always loads before active class is set)
document.addEventListener('panelLoaded', function (e) {
    if (e.detail.panelId === 'persistent-memory-panel') {
        const refreshBtn = document.getElementById('refresh-persistent-memory-btn');
        if (refreshBtn) refreshBtn.onclick = () => PersistentMemory.load();
        PersistentMemory.init();
    }
});

// Re-load on subsequent tab visits (partial already loaded, so panelLoaded won't fire again)
document.addEventListener('tabChanged', function (e) {
    if (e.detail && e.detail.tab === 'persistent-memory') PersistentMemory.init();
});
