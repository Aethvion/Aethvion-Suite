// Aethvion Suite - Files View
// Handles interacting with the local workspace files table

let currentFiles = [];
let currentCategory = 'output'; // Track active category for refresh/etc.
let currentViewMode = 'grid'; // 'grid' or 'list'
let hideFolders = false;
let semanticMode = false;
let currentSort = { key: 'name', dir: 'asc' };
let previousSort = { key: 'name', dir: 'asc' };
let searchDebounceTimer = null;

document.addEventListener('DOMContentLoaded', () => {
    // Setup event listeners for the files page
    document.getElementById('refresh-files')?.addEventListener('click', () => loadFiles(currentCategory, true));
    document.getElementById('file-search')?.addEventListener('input', handleSearchInput);
    document.getElementById('type-filter')?.addEventListener('change', renderFiles);
    document.getElementById('semantic-search-toggle')?.addEventListener('click', toggleSemanticMode);

    // New Feature Listeners
    document.getElementById('exclude-folders-toggle')?.addEventListener('change', handleExcludeFoldersChange);
    document.getElementById('sort-filter')?.addEventListener('change', handleSortDropdownChange);

    // View toggles
    document.getElementById('view-grid-btn')?.addEventListener('click', () => setViewMode('grid'));
    document.getElementById('view-list-btn')?.addEventListener('click', () => setViewMode('list'));

    // Do not call loadFilePreferences() immediately on DOM load to avoid race conditions.
    // It will be triggered by systemReady when all global data is hydrated.
});

// Rely on systemReady heavily
window.addEventListener('systemReady', () => {
    loadFilePreferences();
});

async function loadFilePreferences() {
    try {
        // Use the global prefs object loaded during startup
        hideFolders = prefs.get('files_filters.hide_folders', true);
        const toggle = document.getElementById('exclude-folders-toggle');
        if (toggle) toggle.checked = hideFolders;

        // Load View Mode
        const savedViewMode = prefs.get('files_filters.view_mode', 'grid');
        setViewMode(savedViewMode, false); // Don't trigger save during load

        // Load Sort
        const savedSort = prefs.get('files_filters.sort', { key: 'name', dir: 'asc' });
        currentSort = savedSort;
        const sortDropdown = document.getElementById('sort-filter');
        if (sortDropdown) sortDropdown.value = `${currentSort.key}_${currentSort.dir}`;

        // Re-render files if they're already loaded before preferences finished fetching
        if (currentFiles && currentFiles.length > 0) {
            renderFiles();
        }
    } catch (e) {
        console.error("Could not load preferences from global object", e);
    }
}

async function handleExcludeFoldersChange(e) {
    hideFolders = e.target.checked;
    renderFiles();
    try {
        // Save via global prefs wrapper
        await prefs.set('files_filters.hide_folders', hideFolders);
    } catch (e) { console.error("Could not save preference", e); }
}

function handleSortDropdownChange(e) {
    const val = e.target.value; // e.g., 'name_asc', 'date_desc'
    const parts = val.split('_');
    currentSort = { key: parts[0], dir: parts[1] };

    // Save to preferences
    prefs.set('files_filters.sort', currentSort).catch(console.error);

    renderFiles();
}

function handleSortHeaderClick(key) {
    if (currentSort.key === key) {
        currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort = { key: key, dir: 'asc' };
    }

    // Sync dropdown if exists
    const dd = document.getElementById('sort-filter');
    if (dd) {
        dd.value = `${currentSort.key}_${currentSort.dir}`;
    }

    // Save to preferences
    prefs.set('files_filters.sort', currentSort).catch(console.error);

    renderFiles();
}

function setViewMode(mode, save = true) {
    currentViewMode = mode;

    const gridBtn = document.getElementById('view-grid-btn');
    const listBtn = document.getElementById('view-list-btn');
    const container = document.getElementById('files-grid');

    if (gridBtn && listBtn && container) {
        if (mode === 'grid') {
            gridBtn.classList.add('active');
            listBtn.classList.remove('active');
            container.classList.remove('files-list-view');
            container.classList.add('files-grid-view');
        } else {
            listBtn.classList.add('active');
            gridBtn.classList.remove('active');
            container.classList.remove('files-grid-view');
            container.classList.add('files-list-view');
        }
    }

    if (save) {
        prefs.set('files_filters.view_mode', mode).catch(console.error);
    }

    renderFiles();
}

async function loadFiles(category = 'output', refresh = false) {
    currentCategory = category;
    
    const grid = document.getElementById('files-grid');
    if (!grid) return;

    // 1. Clear grid immediately and show loading indicator
    grid.innerHTML = `
        <div class="loading-container" style="text-align: center; padding: 3rem;">
            <div class="loading-spinner"></div>
            <p style="margin-top: 1rem; color: var(--text-secondary);">Scanning ${category}...</p>
        </div>
    `;

    try {
        const url = `/api/workspace/files?category=${category}${refresh ? '&refresh=true' : ''}`;

        const response = await fetch(url);
        const data = await response.json();

        if (data.count === 0) {
            let placeholder = 'No files yet. Ask Misaka to create reports, analysis, or other outputs!';
            if (category === 'screenshots') placeholder = 'No screenshots found in media/screenshots.';
            if (category === 'camera') placeholder = 'No webcam captures found in media/webcam.';
            if (category === 'uploads') placeholder = 'No uploaded files found in workspace/uploads.';

            grid.innerHTML = `<p class="placeholder-text">${placeholder}</p>`;
            renderStats({}, 0);
            return;
        }

        currentFiles = data.files || [];

        renderStats(data.stats || {}, data.count || 0);
        renderFiles();

    } catch (error) {
        console.error('Files load error:', error);
        const grid = document.getElementById('files-grid');
        if (grid) {
            grid.innerHTML = '<p class="placeholder-text" style="color: var(--danger);">Error loading files</p>';
        }
    }
}

function renderStats(stats, totalCount) {
    document.getElementById('file-total-count').textContent = `${totalCount} files mapped`;

    const bar = document.getElementById('file-stats-bar');
    const legend = document.getElementById('file-stats-legend');

    if (!bar || !legend) return;

    const colors = {
        'json': '#eab308',
        'txt': '#9ca3af',
        'md': '#3b82f6',
        'markdown': '#3b82f6',
        'csv': '#10b981',
        'pdf': '#ef4444',
        'html': '#f97316',
        'py': '#3b82f6', // Python blue
        'js': '#fbbf24'  // JS yellow
    };

    let barHtml = '';
    let legendHtml = '';

    // Sort stats by percentage descending
    const sortedStats = Object.entries(stats).sort((a, b) => b[1] - a[1]);

    for (const [ext, percentage] of sortedStats) {
        if (percentage > 0) {
            const color = colors[ext] || `hsl(${Math.random() * 360}, 70%, 50%)`;
            barHtml += `<div style="width: ${percentage}%; background-color: ${color};" title="${ext}: ${percentage}%"></div>`;
            legendHtml += `
                <div style="display: flex; align-items: center; gap: 4px;">
                    <div style="width: 8px; height: 8px; border-radius: 50%; background-color: ${color};"></div>
                    <span>${ext.toUpperCase()}: ${percentage}%</span>
                </div>
            `;
        }
    }

    bar.innerHTML = barHtml || '<div style="width: 100%; background-color: var(--border);"></div>';
    legend.innerHTML = legendHtml || '<span>No data</span>';
}

function renderFiles() {
    const container = document.getElementById('files-grid');
    if (!container) return;

    if (currentFiles.length === 0) {
        container.innerHTML = '<p class="placeholder-text">No files found.</p>';
        return;
    }

    const searchQuery = (document.getElementById('file-search')?.value || '').toLowerCase();
    const typeFilter = document.getElementById('type-filter')?.value || '';

    // First, Filter
    let filteredFiles = currentFiles;

    // Only filter locally if NOT in semantic mode (unless search is empty)
    const skipLocalFilter = arguments[0] === true;

    if (!skipLocalFilter) {
        filteredFiles = currentFiles.filter(file => {
            if (hideFolders && file.is_dir) return false;

            const matchesSearch = file.filename.toLowerCase().includes(searchQuery) ||
                file.path.toLowerCase().includes(searchQuery);
            const matchesType = !typeFilter || file.file_type === typeFilter;
            return matchesSearch && matchesType;
        });
    }

    if (filteredFiles.length === 0) {
        container.innerHTML = '<p class="placeholder-text">No files match your filters.</p>';
        return;
    }

    // Second, Sort
    filteredFiles.sort((a, b) => {
        let valA, valB;
        switch (currentSort.key) {
            case 'relevance':
                valA = a.relevance || 0;
                valB = b.relevance || 0;
                break;
            case 'name':
                valA = a.filename.toLowerCase();
                valB = b.filename.toLowerCase();
                break;
            case 'path':
                valA = a.path.toLowerCase();
                valB = b.path.toLowerCase();
                break;
            case 'size':
                valA = a.is_dir ? -1 : a.size_bytes;
                valB = b.is_dir ? -1 : b.size_bytes;
                break;
            case 'date':
                valA = new Date(a.created_at).getTime();
                valB = new Date(b.created_at).getTime();
                break;
            default:
                valA = a.filename.toLowerCase();
                valB = b.filename.toLowerCase();
        }

        if (valA < valB) return currentSort.dir === 'asc' ? -1 : 1;
        if (valA > valB) return currentSort.dir === 'asc' ? 1 : -1;
        return 0;
    });

    // Render
    if (currentViewMode === 'grid') {
        container.innerHTML = filteredFiles.map(file => {
            const displayName = file.is_dir ? `${file.filename}/` : file.filename;
            const relevanceBadge = file.relevance ? `<span style="position: absolute; top: -6px; right: -6px; background: var(--primary); color: white; border-radius: 10px; padding: 2px 6px; font-size: 10px; font-weight: bold; border: 1px solid white;">${Math.round(file.relevance * 100)}%</span>` : '';
            const excerptHtml = file.excerpt ? `<div class="file-excerpt" style="font-size: 0.7rem; color: var(--text-secondary); margin-top: 4px; padding-top: 4px; border-top: 1px solid var(--border-subtle); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; line-height: 1.2;">${file.excerpt}</div>` : '';

            return `
            <div class="file-card" onclick="openExplorer('${file.path.replace(/'/g, "\\'")}')" title="${file.path}" style="position: relative;">
                <div class="file-icon" style="position: relative;">${getFileHTML(file)} ${relevanceBadge}</div>
                <div class="file-name">${displayName}</div>
                <div class="file-meta">
                    <div class="text-truncate" style="max-width: 100%;" title="${file.path}">${file.domain}/${file.path}</div>
                    <div>${file.is_dir ? 'Folder' : formatFileSize(file.size_bytes)}</div>
                    <div>${formatDate(file.created_at)}</div>
                    ${excerptHtml}
                </div>
            </div>
            `;
        }).join('');
    } else {
        const getSortIcon = (key) => {
            if (currentSort.key !== key) return '<i class="fas fa-sort"></i>';
            return currentSort.dir === 'asc' ? '<i class="fas fa-sort-up"></i>' : '<i class="fas fa-sort-down"></i>';
        };
        const getSortClass = (key) => currentSort.key === key ? 'sortable active-sort' : 'sortable';

        container.innerHTML = `
            <table class="data-table" style="width: 100%;">
                <thead>
                    <tr>
                        <th style="width: 60px; text-align: center;">Icon</th>
                        <th class="${getSortClass('name')}" onclick="handleSortHeaderClick('name')">Name ${getSortIcon('name')}</th>
                        <th class="${getSortClass('path')}" onclick="handleSortHeaderClick('path')">Path ${getSortIcon('path')}</th>
                        <th class="${getSortClass('size')}" onclick="handleSortHeaderClick('size')">Size ${getSortIcon('size')}</th>
                        <th class="${getSortClass('date')}" onclick="handleSortHeaderClick('date')">Date ${getSortIcon('date')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${filteredFiles.map(file => {
            const displayName = file.is_dir ? `${file.filename}/` : file.filename;
            const relevanceTd = file.relevance ? `<div style="font-weight: bold; color: var(--primary); font-size: 0.8rem;">${Math.round(file.relevance * 100)}% Match</div>` : '';
            return `
                        <tr class="file-list-row" onclick="openExplorer('${file.path.replace(/'/g, "\\'")}')" style="cursor: pointer;">
                            <td style="text-align: center; padding: 4px;">${getFileHTML(file)}</td>
                            <td>
                                <div style="font-weight: 500; color: var(--text-primary);">${displayName}</div>
                                ${relevanceTd}
                                ${file.excerpt ? `<div style="font-size: 0.75rem; color: var(--text-secondary); opacity: 0.8;">${file.excerpt}</div>` : ''}
                            </td>
                            <td class="text-truncate" style="max-width: 250px; color: var(--text-secondary);" title="${file.domain}/${file.path}">${file.domain}/${file.path}</td>
                            <td style="color: var(--text-secondary);">${file.is_dir ? '--' : formatFileSize(file.size_bytes)}</td>
                            <td style="color: var(--text-secondary);">${formatDate(file.created_at)}</td>
                        </tr>
                        `;
        }).join('')}
                </tbody>
            </table>
        `;
    }
}

async function openExplorer(pathStr) {
    try {
        const response = await fetch('/api/workspace/explorer/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: pathStr })
        });

        if (!response.ok) {
            console.error('Failed to open explorer');
        }
    } catch (e) {
        console.error('Explorer open error:', e);
    }
}

function getFileHTML(file) {
    if (file.is_dir) return '📁';

    // Check if image
    const imgExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'];
    if (imgExts.includes(file.file_type)) {
        // use serve endpoint
        return `<img src="/api/workspace/files/serve?path=${encodeURIComponent(file.path)}" alt="${file.filename}" class="image-preview" loading="lazy" />`;
    }

    const icons = {
        'pdf': '📄',
        'txt': '📝',
        'csv': '📊',
        'json': '🔧',
        'markdown': '📝',
        'md': '📝',
        'html': '🌐',
        'mp3': '🎵',
        'wav': '🎵',
        'py': '🐍',
        'js': '📜'
    };
    return icons[file.file_type] || '📄';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function handleSearchInput() {
    if (semanticMode) {
        // Debounce semantic search
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            performSemanticSearch();
        }, 500);
    } else {
        renderFiles();
    }
}

function toggleSemanticMode() {
    semanticMode = !semanticMode;
    const btn = document.getElementById('semantic-search-toggle');
    const sortDropdown = document.getElementById('sort-filter');

    if (btn) {
        if (semanticMode) {
            btn.classList.add('active');
            btn.style.background = 'var(--primary)';
            btn.style.color = 'white';
            btn.title = 'Semantic Search Active';

            // Save current sort before switching
            if (currentSort.key !== 'relevance') {
                previousSort = { ...currentSort };
            }

            // Switch to Best Match sort
            currentSort = { key: 'relevance', dir: 'desc' };
            if (sortDropdown) sortDropdown.value = 'relevance_desc';

            // Trigger search if something is already typed
            const query = document.getElementById('file-search')?.value;
            if (query && query.length > 2) performSemanticSearch();
        } else {
            btn.classList.remove('active');
            btn.style.background = 'var(--bg-tertiary)';
            btn.style.color = 'var(--text-secondary)';
            btn.title = 'Semantic Search Mode';

            // Restore previous sort
            currentSort = { ...previousSort };
            if (sortDropdown) sortDropdown.value = `${currentSort.key}_${currentSort.dir}`;

            renderFiles();
        }
    }
}

async function performSemanticSearch() {
    const query = document.getElementById('file-search')?.value;
    const container = document.getElementById('files-grid');
    if (!query || query.length < 3) {
        if (!query) renderFiles();
        return;
    }

    if (container) {
        container.innerHTML = '<div class="loading-container" style="text-align: center; padding: 2rem;"><div class="loading-spinner"></div><p style="margin-top: 1rem; color: var(--text-secondary);">Searching semantically...</p></div>';
    }

    try {
        const response = await fetch('/api/workspace/files/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                limit: 20
            })
        });

        if (!response.ok) throw new Error('Search failed');
        const data = await response.json();

        // Ensure we are sorting by relevance for these results
        if (currentSort.key !== 'relevance') {
            previousSort = { ...currentSort };
        }
        currentSort = { key: 'relevance', dir: 'desc' };
        const sortDropdown = document.getElementById('sort-filter');
        if (sortDropdown) sortDropdown.value = 'relevance_desc';

        // Temporarily override currentFiles with search results for rendering
        const originalFiles = [...currentFiles];
        currentFiles = data.results || [];

        renderFiles(true); // true means skip local filtering

        // Restore original files
        currentFiles = originalFiles;

    } catch (e) {
        console.error("Semantic search failed", e);
        if (container) container.innerHTML = '<p class="placeholder-text" style="color: var(--danger);">Search failed.</p>';
    }
}
