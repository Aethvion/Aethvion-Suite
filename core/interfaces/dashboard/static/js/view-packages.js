// Misaka Cipher - Packages View
// Handles interacting with the Package Registry table

let allPackages = [];
let packageSort = { column: 'updated', direction: 'desc' };

async function loadPackages() {
    await loadAllPackages();
}

async function loadAllPackages() {
    const tbody = document.getElementById('packages-table-body');
    if (tbody && !allPackages.length) {
        if (typeof showSkeleton !== 'undefined') showSkeleton(tbody, 5);
    }
    try {
        const response = await fetch('/api/packages/all');
        const data = await response.json();

        allPackages = data.packages || [];
        renderPackagesTable();

        if (!window.packageListenersSetup) {
            setupPackageListeners();
            window.packageListenersSetup = true;
        }

    } catch (error) {
        console.error('Error loading packages:', error);
        const tbody = document.getElementById('packages-table-body');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="6" class="placeholder-text error">Error loading packages</td></tr>';
        }
    }
}

function setupPackageListeners() {
    const searchInput = document.getElementById('package-search');
    if (searchInput) searchInput.addEventListener('input', renderPackagesTable);

    const filterSelect = document.getElementById('package-status-filter');
    if (filterSelect) filterSelect.addEventListener('change', renderPackagesTable);

    const systemToggle = document.getElementById('hide-system-packages');
    if (systemToggle) {
        systemToggle.addEventListener('change', renderPackagesTable);
    }

    const refreshBtn = document.getElementById('refresh-packages-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', loadAllPackages);

    const syncBtn = document.getElementById('sync-packages-btn');
    if (syncBtn) {
        syncBtn.addEventListener('click', syncPackages);
    }

    document.querySelectorAll('#packages-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.dataset.sort;
            if (packageSort.column === column) {
                packageSort.direction = packageSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                packageSort.column = column;
                packageSort.direction = 'asc';
                if (column === 'usage' || column === 'updated' || column === 'safety') {
                    packageSort.direction = 'desc';
                }
            }
            renderPackagesTable();
        });
    });
}

function renderPackagesTable() {
    const tbody = document.getElementById('packages-table-body');
    if (!tbody) return;

    const searchInput = document.getElementById('package-search');
    const search = searchInput ? searchInput.value.toLowerCase() : '';
    const filterSelect = document.getElementById('package-status-filter');
    const filter = filterSelect ? filterSelect.value : 'all';
    const hideSystem = document.getElementById('hide-system-packages')?.checked || false;

    // 1. Filter
    let filtered = allPackages.filter(pkg => {
        if (filter !== 'all' && pkg.status !== filter) return false;
        if (hideSystem && pkg.requested_by === 'System Sync') return false;

        if (search) {
            const term = search.toLowerCase();
            return (
                pkg.package_name.toLowerCase().includes(term) ||
                (pkg.reason && pkg.reason.toLowerCase().includes(term)) ||
                (pkg.metadata && pkg.metadata.description && pkg.metadata.description.toLowerCase().includes(term))
            );
        }
        return true;
    });

    // 2. Sort
    filtered.sort((a, b) => {
        let valA, valB;

        switch (packageSort.column) {
            case 'name':
                valA = a.package_name.toLowerCase();
                valB = b.package_name.toLowerCase();
                break;
            case 'status':
                valA = a.status;
                valB = b.status;
                break;
            case 'usage':
                valA = a.usage_count || 0;
                valB = b.usage_count || 0;
                break;
            case 'safety':
                valA = (a.metadata?.safety_score) || 0;
                valB = (b.metadata?.safety_score) || 0;
                break;
            case 'updated':
                valA = new Date(a.last_used_at || a.installed_at || a.approved_at || a.requested_at || 0).getTime();
                valB = new Date(b.last_used_at || b.installed_at || b.approved_at || b.requested_at || 0).getTime();
                break;
            default:
                return 0;
        }

        if (valA < valB) return packageSort.direction === 'asc' ? -1 : 1;
        if (valA > valB) return packageSort.direction === 'asc' ? 1 : -1;
        return 0;
    });

    // Capture currently open details
    const openDetails = Array.from(document.querySelectorAll('.package-details-row'))
        .filter(row => row.style.display !== 'none')
        .map(row => row.id);

    // 3. Render
    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="placeholder-text">No packages match your criteria</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(pkg => {
        const meta = pkg.metadata || {};
        const safeLevel = meta.safety_level || 'UNKNOWN';
        let safeColor = 'var(--text-secondary)';
        if (safeLevel === 'HIGH') safeColor = '#10b981';
        if (safeLevel === 'MEDIUM') safeColor = '#f59e0b';
        if (safeLevel === 'LOW') safeColor = '#ef4444';

        const detailsId = `details-${pkg.package_name.replace(/[^a-zA-Z0-9]/g, '-')}`;

        let actionsHtml = '';
        if (pkg.status === 'pending') {
            actionsHtml = `
                <button class="icon-btn approve-btn" data-pkg="${pkg.package_name}" title="Approve">✓</button>
                <button class="icon-btn deny-btn" data-pkg="${pkg.package_name}" title="Deny">✗</button>
            `;
        } else if (pkg.status === 'installed') {
            actionsHtml = `<span class="dim-text">Active</span>`;
        } else if (pkg.status === 'approved') {
            actionsHtml = `<span class="dim-text">Installing...</span>`;
        } else if (pkg.status === 'denied') {
            actionsHtml = `<span class="dim-text">Denied</span>`;
        } else if (pkg.status === 'failed') {
            actionsHtml = `<span class="error-text">Failed</span>`;
        } else if (pkg.status === 'uninstalled') {
            actionsHtml = `<span class="dim-text">Uninstalled</span>`;
        }

        // Expanded actions
        let expandedActions = '';
        if (pkg.status === 'installed' || pkg.status === 'failed' || pkg.status === 'approved') {
            expandedActions += `<button class="action-btn small danger uninstall-btn" data-pkg="${pkg.package_name}">Uninstall</button>`;
        }
        if (pkg.status === 'failed' || pkg.status === 'uninstalled' || pkg.status === 'denied') {
            expandedActions += `<button class="action-btn small primary retry-btn" data-pkg="${pkg.package_name}">Retry / Install</button>`;
        }

        const mainRow = `
            <tr class="package-row ${pkg.status}" onclick="togglePackageDetails('${detailsId}')">
                <td>
                    <div class="pkg-name">
                        <span class="expand-icon">▶</span> ${pkg.package_name}
                    </div>
                </td>
                <td><span class="status-badge ${pkg.status}">${pkg.status}</span></td>
                <td>
                    <div class="usage-count">${pkg.usage_count || 0} calls</div>
                    <div class="last-used">${pkg.last_used_at ? formatDate(pkg.last_used_at) : 'Never'}</div>
                </td>
                <td>
                    <div class="safety-score" style="color: ${safeColor}">
                        ${Math.round(meta.safety_score || 0)}%
                    </div>
                </td>
                <td>${formatDate(pkg.installed_at || pkg.requested_at)}</td>
                <td onclick="event.stopPropagation()">${actionsHtml}</td>
            </tr>
        `;

        const detailsRow = `
            <tr id="${detailsId}" class="package-details-row" style="display: none;">
                <td colspan="6">
                    <div class="details-content">
                        <div class="detail-grid">
                            <div class="detail-item">
                                <span class="label">Version:</span>
                                <span class="value">${meta.version || 'Unknown'}</span>
                            </div>
                            <div class="detail-item">
                                <span class="label">Author:</span>
                                <span class="value">${meta.author || 'Unknown'}</span>
                            </div>
                            <div class="detail-item">
                                <span class="label">Downloads:</span>
                                <span class="value">${meta.downloads_last_month ? formatNumber(meta.downloads_last_month) + '/mo' : 'N/A'}</span>
                            </div>
                            <div class="detail-item">
                                <span class="label">Last Release:</span>
                                <span class="value">${meta.last_release ? formatDate(meta.last_release) : 'Unknown'}</span>
                            </div>
                             <div class="detail-item" style="grid-column: span 2;">
                                <span class="label">Description:</span>
                                <span class="value">${meta.description || pkg.reason || 'No description'}</span>
                            </div>
                        </div>
                        <div class="detail-actions">
                            ${expandedActions}
                        </div>
                    </div>
                </td>
            </tr>
        `;

        return mainRow + detailsRow;
    }).join('');

    // Restore open details
    openDetails.forEach(id => {
        const row = document.getElementById(id);
        if (row) {
            row.style.display = 'table-row';
            const prev = row.previousElementSibling;
            if (prev) {
                const icon = prev.querySelector('.expand-icon');
                if (icon) icon.style.transform = 'rotate(90deg)';
            }
        }
    });

    // Attach row action listeners
    tbody.querySelectorAll('.approve-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            approvePackage(btn.dataset.pkg);
        });
    });
    tbody.querySelectorAll('.deny-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            denyPackage(btn.dataset.pkg);
        });
    });

    // Attach details action listeners
    tbody.querySelectorAll('.uninstall-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            uninstallPackage(btn.dataset.pkg);
        });
    });
    tbody.querySelectorAll('.retry-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            retryPackage(btn.dataset.pkg);
        });
    });
}

function togglePackageDetails(rowId) {
    const row = document.getElementById(rowId);
    if (!row) return;

    if (row.style.display === 'none') {
        row.style.display = 'table-row';
        const prev = row.previousElementSibling;
        const icon = prev.querySelector('.expand-icon');
        if (icon) icon.style.transform = 'rotate(90deg)';
    } else {
        row.style.display = 'none';
        const prev = row.previousElementSibling;
        const icon = prev.querySelector('.expand-icon');
        if (icon) icon.style.transform = 'rotate(0deg)';
    }
}

async function syncPackages() {
    const btn = document.getElementById('sync-packages-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spin fa-sync"></i> Syncing...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/packages/sync', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            showToast('Package sync complete', 'success');
            loadAllPackages();
        } else {
            showToast('Sync failed: ' + data.message, 'error');
        }
    } catch (e) {
        console.error('Sync error:', e);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function uninstallPackage(packageName) {
    showConfirm(
        'Uninstall Package',
        `Uninstall "${packageName}"? This calls pip uninstall.`,
        async () => {
            try {
                const response = await fetch(`/api/packages/uninstall/${packageName}`, { method: 'POST' });
                const data = await response.json();
                if (data.success) { showToast(`${packageName} uninstalled`, 'success'); loadAllPackages(); }
                else showToast('Uninstall failed: ' + data.message, 'error');
            } catch (e) { console.error('Uninstall error:', e); }
        },
        { confirmLabel: 'Uninstall', icon: 'fa-trash' }
    );
}

async function retryPackage(packageName) {
    showConfirm(
        'Retry Installation',
        `Retry installation of "${packageName}"?`,
        async () => {
            try {
                const response = await fetch(`/api/packages/retry/${packageName}`, { method: 'POST' });
                const data = await response.json();
                if (data.success) { showToast(`Retrying ${packageName}…`, 'info'); loadAllPackages(); }
                else showToast('Retry failed: ' + data.message, 'error');
            } catch (e) { console.error('Retry error:', e); }
        },
        { confirmLabel: 'Retry', icon: 'fa-rotate-right' }
    );
}

async function approvePackage(packageName) {
    showConfirm(
        'Install Package',
        `Install package "${packageName}"?`,
        async () => {
            try {
                const response = await fetch(`/api/packages/approve/${packageName}`, { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showToast(`${packageName} approved for install`, 'success');
                    const pkg = allPackages.find(p => p.package_name === packageName);
                    if (pkg) pkg.status = 'approved';
                    renderPackagesTable();
                    loadAllPackages();
                } else { showToast('Failed: ' + data.message, 'error'); }
            } catch (error) { console.error('Error approving:', error); }
        },
        { confirmLabel: 'Install', icon: 'fa-download' }
    );
}

async function denyPackage(packageName) {
    showConfirm(
        'Deny Package',
        `Deny package "${packageName}"? It will be blocked from installation.`,
        async () => {
            try {
                const response = await fetch(`/api/packages/deny/${packageName}`, { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showToast(`${packageName} denied`, 'warn');
                    const pkg = allPackages.find(p => p.package_name === packageName);
                    if (pkg) pkg.status = 'denied';
                    renderPackagesTable();
                    loadAllPackages();
                } else { showToast('Failed: ' + data.message, 'error'); }
            } catch (error) { console.error('Error denying:', error); }
        },
        { confirmLabel: 'Deny', icon: 'fa-ban' }
    );
}

function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

function formatDate(isoString) {
    if (!isoString) return 'Never';
    const date = new Date(isoString);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'today';
    if (diffDays === 1) return '1 day ago';
    if (diffDays < 30) return `${diffDays} days ago`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
    return `${Math.floor(diffDays / 365)} years ago`;
}

function applyPackagePreferencesToUI() {
    const statusFilter = document.getElementById('package-status-filter');
    if (statusFilter) {
        statusFilter.value = prefs.get('package_filters.status', 'all');
    }

    const hideSystemPkg = document.getElementById('hide-system-packages'); // Main tab toggle
    if (hideSystemPkg) {
        hideSystemPkg.checked = prefs.get('package_filters.hide_system', false);
    }

    // Also sync the settings tab toggle if it exists
    const settingHideSystem = document.getElementById('setting-hide-system-pkgs');
    if (settingHideSystem) {
        settingHideSystem.checked = prefs.get('package_filters.hide_system', false);
    }

    const searchInput = document.getElementById('package-search');
    if (searchInput) {
        searchInput.value = prefs.get('package_filters.search', '');
    }

    packageSort.column = prefs.get('package_sort.column', 'updated');
    packageSort.direction = prefs.get('package_sort.direction', 'desc');
}

// Updates to setupPackageListeners to attach save logic
const originalSetupPackageListeners = setupPackageListeners;
setupPackageListeners = function () {
    originalSetupPackageListeners();

    // Attach save logic to elements
    const statusFilter = document.getElementById('package-status-filter');
    statusFilter.addEventListener('change', (e) => savePreference('package_filters.status', e.target.value));

    const hideSystem = document.getElementById('hide-system-packages');
    if (hideSystem) {
        hideSystem.addEventListener('change', (e) => {
            savePreference('package_filters.hide_system', e.target.checked);
            // Sync settings toggle
            const settingToggle = document.getElementById('setting-hide-system-pkgs');
            if (settingToggle) settingToggle.checked = e.target.checked;
        });
    }

    const searchInput = document.getElementById('package-search');
    searchInput.addEventListener('input', (e) => savePreference('package_filters.search', e.target.value));

    // Settings Tab Listeners
    const settingHideSystem = document.getElementById('setting-hide-system-pkgs');
    if (settingHideSystem) {
        settingHideSystem.addEventListener('change', (e) => {
            const checked = e.target.checked;
            savePreference('package_filters.hide_system', checked);
            // Sync main toggle
            const mainToggle = document.getElementById('hide-system-packages');
            if (mainToggle) {
                mainToggle.checked = checked;
                mainToggle.dispatchEvent(new Event('change'));
            } else {
                renderPackagesTable();
            }
        });
    }

};

// Override sort click to save
// We can't easily override the inner function closure of setupPackageListeners without replacing it totally.
// So we'll inject the apply logic into renderPackagesTable or loadAllPackages.

const originalRenderPackagesTable = renderPackagesTable;
renderPackagesTable = function () {
    // Before first render or if needed, sync UI variables from DOM which might have been set by Apply
    // But wait, render uses DOM values.

    // Let's modify loadAllPackages to Apply prefs to UI before first render
    originalRenderPackagesTable();
}

// Modify loadAllPackages to apply prefs
const originalLoadAllPackages = loadAllPackages;
loadAllPackages = async function () {
    try {
        const response = await fetch('/api/packages/all');
        const data = await response.json();

        allPackages = data.packages || [];

        // CHECKPOINT: Apply prefs to UI inputs before rendering
        if (!window.packagePrefsApplied) {
            applyPackagePreferencesToUI();
            window.packagePrefsApplied = true;
        }

        originalRenderPackagesTable();

        if (!window.packageListenersSetup) {
            setupPackageListeners();
            window.packageListenersSetup = true;
        }

    } catch (error) {
        console.error('Error loading packages:', error);
        document.getElementById('packages-table-body').innerHTML =
            '<tr><td colspan="6" class="placeholder-text error">Error loading packages</td></tr>';
    }
};

