// Misaka Cipher - Tools View
// Handles interacting with the Tool Registry table

let allTools = [];
let toolSort = { column: 'name', direction: 'asc' };
let showSystemTools = false;

async function loadTools() {
    try {
        const prefResponse = await fetch('/api/preferences/get?key=show_system_tools');
        if (prefResponse.ok) {
            const prefData = await prefResponse.json();
            if (prefData && prefData.value !== undefined) {
                showSystemTools = prefData.value;
            }
        }
    } catch (e) {
        console.log("Could not load preferences, using default");
    }

    const checkbox = document.getElementById('hide-system-tools');
    const shouldHide = await getHideToolsPref();
    if (checkbox) checkbox.checked = shouldHide;

    await loadAllTools();
}

async function getHideToolsPref() {
    try {
        const prefResponse = await fetch('/api/preferences/get?key=tool_filters.hide_system');
        if (prefResponse.ok) {
            const prefData = await prefResponse.json();
            return prefData.value === true;
        }
    } catch (e) { }
    return false; // Default show all
}

async function loadAllTools() {
    const tbody = document.getElementById('tools-table-body');
    if (tbody && !allTools.length) {
        if (typeof showSkeleton !== 'undefined') showSkeleton(tbody, 4);
    }
    try {
        const response = await fetch('/api/tools/list');
        const data = await response.json();

        allTools = data.tools || [];
        populateToolDomains();
        renderToolsTable();

        if (!window.toolListenersSetup) {
            setupToolListeners();
            window.toolListenersSetup = true;
        }

    } catch (error) {
        console.error('Error loading tools:', error);
        const tbody = document.getElementById('tools-table-body');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="6" class="placeholder-text error">Error loading tools</td></tr>';
        }
    }
}

function populateToolDomains() {
    const domains = new Set(allTools.map(t => t.domain).filter(d => d));
    const select = document.getElementById('tool-domain-filter');
    if (!select) return;

    const currentValue = select.value;

    select.innerHTML = '<option value="">All Domains</option>';

    Array.from(domains).sort().forEach(domain => {
        const option = document.createElement('option');
        option.value = domain;
        option.textContent = domain;
        select.appendChild(option);
    });

    if (domains.has(currentValue)) {
        select.value = currentValue;
    }
}

function setupToolListeners() {
    const searchInput = document.getElementById('tool-search');
    if (searchInput) searchInput.addEventListener('input', renderToolsTable);

    const filterSelect = document.getElementById('tool-domain-filter');
    if (filterSelect) filterSelect.addEventListener('change', renderToolsTable);

    const systemToggle = document.getElementById('hide-system-tools');
    if (systemToggle) {
        systemToggle.addEventListener('change', async (e) => {
            const hide = e.target.checked;
            renderToolsTable();

            try {
                await fetch('/api/preferences/set', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        key: 'tool_filters.hide_system',
                        value: hide
                    })
                });
            } catch (err) {
                console.error("Failed to save preference:", err);
            }
        });
    }

    const refreshBtn = document.getElementById('refresh-tools-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', loadAllTools);

    document.querySelectorAll('#tools-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.dataset.sort;
            if (toolSort.column === column) {
                toolSort.direction = toolSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                toolSort.column = column;
                toolSort.direction = 'asc';
                if (column === 'created' || column === 'usage') {
                    toolSort.direction = 'desc';
                }
            }
            renderToolsTable();
        });
    });
}

function renderToolsTable() {
    const tbody = document.getElementById('tools-table-body');
    if (!tbody) return;

    const searchInput = document.getElementById('tool-search');
    const search = searchInput ? searchInput.value.toLowerCase() : '';
    const domainFilter = document.getElementById('tool-domain-filter')?.value;
    const hideSystem = document.getElementById('hide-system-tools')?.checked || false;

    // 1. Filter
    let filtered = allTools.filter(tool => {
        if (hideSystem && tool.is_system) return false;
        if (domainFilter && tool.domain !== domainFilter) return false;
        if (search) {
            const term = search.toLowerCase();
            return (
                tool.name.toLowerCase().includes(term) ||
                (tool.description && tool.description.toLowerCase().includes(term))
            );
        }
        return true;
    });

    // 2. Sort
    filtered.sort((a, b) => {
        let valA, valB;

        switch (toolSort.column) {
            case 'name':
                valA = a.name.toLowerCase();
                valB = b.name.toLowerCase();
                break;
            case 'domain':
                valA = (a.domain || '').toLowerCase();
                valB = (b.domain || '').toLowerCase();
                break;
            case 'created':
                valA = new Date(a.created_at || 0).getTime();
                valB = new Date(b.created_at || 0).getTime();
                break;
            case 'usage':
                valA = a.usage_count || 0;
                valB = b.usage_count || 0;
                break;
            default:
                return 0;
        }

        if (valA < valB) return toolSort.direction === 'asc' ? -1 : 1;
        if (valA > valB) return toolSort.direction === 'asc' ? 1 : -1;
        return 0;
    });

    // 3. Render
    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="placeholder-text">No tools match your criteria</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(tool => {
        const detailsId = `tool-details-${tool.name.replace(/[^a-zA-Z0-9]/g, '-')}`;
        const createdDate = typeof formatDate === 'function' ? formatDate(tool.created_at || new Date()) : new Date(tool.created_at).toLocaleString();

        const mainRow = `
            <tr class="package-row" onclick="toggleToolDetails('${detailsId}')">
                <td>
                    <div class="pkg-name">
                        <span class="expand-icon">▶</span> ${tool.name}
                    </div>
                </td>
                <td><span class="status-badge installed">${tool.domain || 'N/A'}</span></td>
                <td>${tool.usage_count || 0}</td>
                <td>${tool.description || 'No description'}</td>
                <td>${createdDate}</td>
                <td onclick="event.stopPropagation()">
                    ${tool.is_system
                ? '<span class="status-badge" style="background:var(--accent-secondary); opacity:0.8; cursor:default;">System</span>'
                : `<button class="action-btn small danger delete-tool-btn" onclick="deleteTool('${tool.name}')">Delete</button>`
            }
                </td>
            </tr>
        `;

        const detailsRow = `
            <tr id="${detailsId}" class="package-details-row" style="display: none;">
                <td colspan="6">
                    <div class="details-content">
                        <div class="detail-grid">
                            <div class="detail-item">
                                <span class="label">Parameters:</span>
                                <span class="value code-block">${JSON.stringify(tool.parameters, null, 2)}</span>
                            </div>
                            <div class="detail-item">
                                <span class="label">File Path:</span>
                                <span class="value">${tool.file_path || 'Unknown'}</span>
                            </div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
        return mainRow + detailsRow;
    }).join('');
}

function toggleToolDetails(id) {
    const row = document.getElementById(id);
    if (!row) return;

    const isHidden = row.style.display === 'none';
    row.style.display = isHidden ? 'table-row' : 'none';

    const prevRow = row.previousElementSibling;
    if (prevRow) {
        const icon = prevRow.querySelector('.expand-icon');
        if (icon) {
            icon.style.transform = isHidden ? 'rotate(90deg)' : 'rotate(0deg)';
        }
    }
}

async function deleteTool(toolName) {
    showConfirm(
        'Delete Tool',
        `Delete tool "${toolName}"? This cannot be undone.`,
        async () => {
            try {
                const response = await fetch(`/api/tools/${toolName}`, { method: 'DELETE' });
                const result = await response.json();
                if (result.success) {
                    showToast(`Tool "${toolName}" deleted`, 'success');
                    loadAllTools();
                } else {
                    showToast('Failed to delete tool: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error deleting tool:', error);
                showToast('Error deleting tool: ' + error.message, 'error');
            }
        },
        { confirmLabel: 'Delete', icon: 'fa-trash' }
    );
}
