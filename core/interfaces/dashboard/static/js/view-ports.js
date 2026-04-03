/**
 * Port Manager Dashboard View Logic (v12)
 * Partial-loader aware: init deferred until ports-panel partial is injected.
 */

// ── Module-scope references (populated in _initPorts) ────────────────────────
let _portsRefreshBtn = null;
let _portsTbody      = null;
let _portsCount      = null;
let _portsLastScan   = null;
let _portsInitDone   = false;

async function _fetchPorts() {
    if (!_portsRefreshBtn) return;
    try {
        _portsRefreshBtn.disabled = true;
        _portsRefreshBtn.innerHTML = '<i class="fas fa-sync fa-spin"></i> Scanning...';

        const response = await fetch('/api/system/ports');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const portsData = await response.json();
        _renderPortsTable(portsData);

        const now = new Date();
        if (_portsLastScan) {
            _portsLastScan.textContent = now.toLocaleTimeString([], {
                hour: '2-digit', minute: '2-digit', second: '2-digit'
            });
        }
    } catch (error) {
        console.error('Error fetching registered ports:', error);
        if (_portsTbody) {
            _portsTbody.innerHTML = `<tr><td colspan="4" class="error-msg" style="text-align:center;padding:40px;color:#ef4444;">
                <i class="fas fa-exclamation-triangle" style="font-size:2rem;margin-bottom:10px;display:block;"></i>
                Failed to load port data. Is the backend server offline?
            </td></tr>`;
        }
        if (_portsCount) _portsCount.textContent = 'ERROR';
    } finally {
        if (_portsRefreshBtn) {
            _portsRefreshBtn.disabled = false;
            _portsRefreshBtn.innerHTML = '<i class="fas fa-sync"></i> Refresh Status';
        }
    }
}

function _renderPortsTable(portsData) {
    if (!_portsTbody) return;
    _portsTbody.innerHTML = '';
    const entries = Object.entries(portsData);

    if (entries.length === 0) {
        _portsTbody.innerHTML = `<tr><td colspan="4" class="empty-msg" style="text-align:center;padding:40px;color:var(--text-tertiary);">
            <i class="fas fa-ghost" style="font-size:2rem;margin-bottom:10px;display:block;"></i>
            No dynamic ports currently active.
        </td></tr>`;
        if (_portsCount) _portsCount.textContent = '0';
        return;
    }

    entries.sort((a, b) => parseInt(a[0]) - parseInt(b[0]));

    let rowHtml = '';
    for (const [port, moduleName] of entries) {
        const displayName = moduleName.charAt(0).toUpperCase() + moduleName.slice(1);
        rowHtml += `
        <tr data-port="${port}">
            <td>
                <div style="display:flex;align-items:center;gap:12px;">
                    <div style="width:8px;height:8px;background:#4ade80;border-radius:50%;box-shadow:0 0 8px #4ade80;"></div>
                    <span style="font-weight:600;color:var(--text-primary);font-size:0.95rem;">${_portsEsc(displayName)} Service</span>
                </div>
            </td>
            <td><span class="port-tag">:${port}</span></td>
            <td>
                <a href="http://localhost:${port}" target="_blank" style="color:var(--primary);text-decoration:none;font-weight:600;font-size:0.85rem;display:flex;align-items:center;gap:5px;">
                    Local Link <i class="fas fa-external-link-alt" style="font-size:0.7rem;"></i>
                </a>
            </td>
            <td style="text-align:right;">
                ${moduleName.toLowerCase().includes('nexus') ? `
                    <span style="font-size:0.75rem;color:var(--text-tertiary);font-style:italic;margin-right:10px;">System Service</span>
                ` : `
                    <button class="terminate-btn" onclick="terminatePortApp(${port}, '${_portsEsc(moduleName)}')">
                        <i class="fas fa-power-off"></i> Terminate
                    </button>
                `}
            </td>
        </tr>`;
    }
    _portsTbody.innerHTML = rowHtml;
    if (_portsCount) _portsCount.textContent = entries.length;
}

function _portsEsc(unsafe) {
    return (unsafe || '').toString()
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

window.terminatePortApp = async function (port, name) {
    if (!confirm(`Are you sure you want to forcefully close the ${name} service on port ${port}?\n\nAny unsaved work in that app will be lost.`)) return;

    const row = document.querySelector(`tr[data-port="${port}"]`);
    if (!row) return;
    const btn = row.querySelector('.terminate-btn');
    const originalHtml = btn ? btn.innerHTML : '';

    try {
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Killing...'; btn.style.opacity = '0.6'; }
        const response = await fetch(`/api/system/ports/${port}/terminate`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            row.style.transition = 'all 0.4s ease';
            row.style.opacity = '0';
            row.style.transform = 'translateX(20px)';
            setTimeout(() => _fetchPorts(), 400);
        } else {
            alert(`Failed to close app: ${result.detail || 'Unknown error'}`);
            if (btn) { btn.disabled = false; btn.innerHTML = originalHtml; btn.style.opacity = '1'; }
        }
    } catch (error) {
        console.error('Error terminating app:', error);
        alert('A network error occurred while trying to terminate the app.');
        if (btn) { btn.disabled = false; btn.innerHTML = originalHtml; btn.style.opacity = '1'; }
    }
};

// ── Init (safe to call multiple times — guards against double-setup) ──────────
function _initPorts() {
    const refreshBtn = document.getElementById('refresh-ports-btn');
    if (!refreshBtn || _portsInitDone) return;   // partial not loaded yet, or already set up
    _portsInitDone   = true;
    _portsRefreshBtn = refreshBtn;
    _portsTbody      = document.getElementById('ports-tbody');
    _portsCount      = document.getElementById('ports-count-display');
    _portsLastScan   = document.getElementById('ports-last-scan');

    _portsRefreshBtn.addEventListener('click', _fetchPorts);
    _fetchPorts();
}

// Try on DOMContentLoaded (works if panel was pre-loaded)
document.addEventListener('DOMContentLoaded', _initPorts);

// Also run when the ports partial is injected (lazy load case)
document.addEventListener('panelLoaded', function (e) {
    if (e.detail.panelId === 'ports-panel') _initPorts();
});

// Refresh on tab click (sidebar button is always present — safe to wire up early)
document.addEventListener('click', function (e) {
    const tab = e.target.closest('[data-maintab="ports"]');
    if (tab) _fetchPorts();
});
