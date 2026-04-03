// Aethvion Suite - Memory View
// Handles interacting with the Memory Database tables

// Wire buttons and load data when the memory partial is injected
document.addEventListener('panelLoaded', function (e) {
    if (e.detail.panelId === 'memory-panel') {
        const refreshBtn = document.getElementById('refresh-memory-btn');
        if (refreshBtn) refreshBtn.addEventListener('click', loadMemoryData);
        loadMemoryData();
    }
});

async function loadMemoryData() {
    try {
        const response = await fetch('/api/memory/overview');
        if (!response.ok) throw new Error("Failed to load memory overview");

        const data = await response.json();

        renderPermanentMemory(data.permanent);
        renderThreadMemory(data.threads);

    } catch (error) {
        console.error("Memory load error:", error);
        const container = document.getElementById('thread-memory-container');
        if (container) {
            container.innerHTML = `<p class="error-text">Failed to load memory data: ${error.message}</p>`;
        }
    }
}

function renderPermanentMemory(insights) {
    const tbody = document.getElementById('permanent-memory-body');
    if (!tbody) return;

    if (!insights || insights.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" class="placeholder-text" style="text-align:center; padding:15px;">No permanent insights yet.</td></tr>';
        return;
    }

    tbody.innerHTML = insights.map(i => `
        <tr>
            <td style="font-family: monospace; color: var(--text-secondary);">${i.id}</td>
            <td>${i.summary}</td>
            <td>${typeof formatDate === 'function' ? formatDate(i.created_at) : new Date(i.created_at).toLocaleString()}</td>
        </tr>
    `).join('');
}

function renderThreadMemory(threads) {
    const container = document.getElementById('thread-memory-container');
    if (!container) return;

    if (!threads || threads.length === 0) {
        container.innerHTML = '<p class="placeholder-text">No thread memories found.</p>';
        return;
    }

    container.innerHTML = threads.map(thread => {
        const rows = thread.memories && thread.memories.length > 0
            ? thread.memories.map(mem => {
                const dateObj = new Date(mem.timestamp);
                const dateStr = dateObj.toLocaleDateString() + ' ' + dateObj.toLocaleTimeString();

                let detailsRow = '';
                if (mem.details) {
                    const jsonStr = JSON.stringify(mem.details, null, 2);
                    const detailsId = `mem-details-${mem.memory_id.replace(/[^a-zA-Z0-9]/g, '-')}`;
                    detailsRow = `
                        <tr id="${detailsId}" class="memory-details-row" style="display:none; background: rgba(0,0,0,0.1);">
                            <td colspan="5">
                                <div class="memory-details-content" style="padding: 10px;">
                                    <strong style="display:block; margin-bottom:5px; color:var(--accent-primary);">Raw Task Data:</strong>
                                    <pre style="background:rgba(0,0,0,0.3); padding:10px; border-radius:4px; max-height:300px; overflow:auto; font-size:0.8em;">${jsonStr}</pre>
                                </div>
                            </td>
                        </tr>
                    `;
                }

                const onclickAttr = mem.details ? `onclick="toggleMemoryDetails(this, '${mem.memory_id.replace(/[^a-zA-Z0-9]/g, '-')}')" style="cursor:pointer;"` : '';
                const expandIcon = mem.details ? '<span class="expand-icon">▶</span> ' : '';

                return `
                    <tr ${onclickAttr} class="memory-row">
                        <td style="font-family:var(--font-mono); font-size:0.8em; color:var(--text-secondary); width: 140px;">${mem.memory_id}</td>
                        <td><span class="status-badge" style="font-size:0.8em">${mem.event_type}</span></td>
                        <td>${expandIcon}${mem.summary}</td>
                        <td style="font-family:var(--font-mono); font-size:0.85em; color:var(--text-secondary);">${mem.content ? mem.content.substring(0, 50) + (mem.content.length > 50 ? '...' : '') : '-'}</td>
                        <td style="font-size:0.85em; white-space:nowrap;">${dateStr}</td>
                    </tr>
                    ${detailsRow}
                `;
            }).join('')
            : '<tr><td colspan="5" class="placeholder-text" style="text-align:center; padding:10px;">No memories for this thread.</td></tr>';

        return `
            <div class="thread-memory-card" style="margin-bottom: 2rem; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; overflow: hidden;">
                <div class="thread-header" style="padding: 1rem; background: rgba(0,0,0,0.2); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h4 style="margin: 0; color: var(--primary);">${thread.title}</h4>
                        <span style="font-size: 0.8em; color: var(--text-secondary); font-family: var(--font-mono);">${thread.id}</span>
                    </div>
                    <div style="font-size: 0.9rem; color: var(--text-secondary);">
                        ${thread.memory_count} memories
                    </div>
                </div>
                
                <div class="memory-table-wrapper">
                    <table class="data-table" style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="text-align: left; border-bottom: 1px solid var(--border); font-size: 0.9em; position: sticky; top: 0; background: var(--bg-secondary); z-index: 1;">
                                <th style="padding: 10px; width: 140px;">ID</th>
                                <th style="padding: 10px; width: 100px;">Event</th>
                                <th style="padding: 10px;">Summary</th>
                                <th style="padding: 10px;">Content Snippet</th>
                                <th style="padding: 10px; width: 160px;">Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }).join('');
}

function toggleMemoryDetails(row, id) {
    const detailsRow = document.getElementById(`mem-details-${id}`);
    if (detailsRow) {
        const isHidden = detailsRow.style.display === 'none';
        detailsRow.style.display = isHidden ? 'table-row' : 'none';

        const icon = row.querySelector('.expand-icon');
        if (icon) {
            icon.style.transform = isHidden ? 'rotate(90deg)' : 'rotate(0deg)';
            icon.style.display = 'inline-block';
            icon.style.transition = 'transform 0.2s';
        }
    }
}

async function searchMemory() {
    const searchInput = document.getElementById('memory-search');
    const query = searchInput ? searchInput.value : '';
    const domainFilter = document.getElementById('memory-domain-filter');
    const domain = domainFilter ? domainFilter.value : '';

    if (!query) return;

    try {
        const response = await fetch('/api/memory/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, domain: domain || null, limit: 10 })
        });

        const data = await response.json();
        const results = document.getElementById('memory-results');
        if (!results) return;

        if (data.count === 0) {
            results.innerHTML = '<p class="placeholder-text">No memories found</p>';
            return;
        }

        results.innerHTML = data.results.map(mem => `
            <div class="memory-card">
                <div style="color: var(--primary); font-weight: 600;">${mem.event_type}</div>
                <div style="margin: 0.5rem 0;">${mem.summary}</div>
                <div style="font-size: 0.8rem; color: var(--text-secondary);">
                    <span>${mem.domain}</span> • 
                    <span>${new Date(mem.timestamp).toLocaleString()}</span> • 
                    <span style="font-family: 'Fira Code', monospace; color: var(--accent);">${mem.memory_id}</span>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Memory search error:', error);
    }
}
