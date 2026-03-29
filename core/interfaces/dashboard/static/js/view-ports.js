/**
 * Port Manager Dashboard View Logic (v12)
 */

document.addEventListener('DOMContentLoaded', () => {
    const portsPanel = document.getElementById('ports-panel');
    if (!portsPanel) return;

    const refreshBtn = document.getElementById('refresh-ports-btn');
    const tbody = document.getElementById('ports-tbody');
    const countDisplay = document.getElementById('ports-count-display');
    const lastScanDisplay = document.getElementById('ports-last-scan');

    async function fetchPorts() {
        try {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-sync fa-spin"></i> Scanning...';
            
            const response = await fetch('/api/system/ports');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const portsData = await response.json();
            renderPortsTable(portsData);
            
            // Update last scan time
            const now = new Date();
            lastScanDisplay.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch (error) {
            console.error('Error fetching registered ports:', error);
            tbody.innerHTML = `<tr><td colspan="4" class="error-msg" style="text-align: center; padding: 40px; color: #ef4444;">
                <i class="fas fa-exclamation-triangle" style="font-size: 2rem; margin-bottom: 10px; display: block;"></i>
                Failed to load port data. Is the backend server offline?
            </td></tr>`;
            countDisplay.textContent = 'ERROR';
        } finally {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="fas fa-sync"></i> Refresh Status';
        }
    }

    function renderPortsTable(portsData) {
        tbody.innerHTML = '';
        const entries = Object.entries(portsData);
        
        if (entries.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="empty-msg" style="text-align: center; padding: 40px; color: var(--text-tertiary);">
                <i class="fas fa-ghost" style="font-size: 2rem; margin-bottom: 10px; display: block;"></i>
                No dynamic ports currently active.
            </td></tr>`;
            countDisplay.textContent = '0';
            return;
        }

        // Sort by port number ascending
        entries.sort((a, b) => parseInt(a[0]) - parseInt(b[0]));
        
        let rowHtml = '';
        for (const [port, moduleName] of entries) {
            // Clean up module name for display
            const displayName = moduleName.charAt(0).toUpperCase() + moduleName.slice(1);
            
            rowHtml += `
            <tr data-port="${port}">
                <td>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="width: 8px; height: 8px; background: #4ade80; border-radius: 50%; box-shadow: 0 0 8px #4ade80;"></div>
                        <span style="font-weight: 600; color: var(--text-primary); font-size: 0.95rem;">${escapeHtml(displayName)} Service</span>
                    </div>
                </td>
                <td>
                    <span class="port-tag">:${port}</span>
                </td>
                <td>
                    <a href="http://localhost:${port}" target="_blank" style="color: var(--primary); text-decoration: none; font-weight: 600; font-size: 0.85rem; display: flex; align-items: center; gap: 5px;">
                        Local Link <i class="fas fa-external-link-alt" style="font-size: 0.7rem;"></i>
                    </a>
                </td>
                <td style="text-align: right;">
                    ${moduleName === 'Aethvion Suite Nexus' ? `
                        <span style="font-size: 0.75rem; color: var(--text-tertiary); font-style: italic; margin-right: 10px;">System Service</span>
                    ` : `
                        <button class="terminate-btn" onclick="terminatePortApp(${port}, '${escapeHtml(moduleName)}')">
                            <i class="fas fa-power-off"></i> Terminate
                        </button>
                    `}
                </td>
            </tr>`;
        }
        
        tbody.innerHTML = rowHtml;
        countDisplay.textContent = entries.length;
    }

    // Global function for the onclick handler
    window.terminatePortApp = async (port, name) => {
        if (!confirm(`Are you sure you want to forcefully close the ${name} service on port ${port}?\n\nAny unsaved work in that app will be lost.`)) {
            return;
        }

        const row = document.querySelector(`tr[data-port="${port}"]`);
        const btn = row.querySelector('.terminate-btn');
        const originalHtml = btn.innerHTML;

        try {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Killing...';
            btn.style.opacity = '0.6';

            const response = await fetch(`/api/system/ports/${port}/terminate`, {
                method: 'POST'
            });

            const result = await response.json();
            
            if (response.ok) {
                // Smoothly remove the row
                row.style.transition = 'all 0.4s ease';
                row.style.opacity = '0';
                row.style.transform = 'translateX(20px)';
                setTimeout(() => {
                    fetchPorts(); // Refresh full list and stats
                }, 400);
            } else {
                alert(`Failed to close app: ${result.detail || 'Unknown error'}`);
                btn.disabled = false;
                btn.innerHTML = originalHtml;
                btn.style.opacity = '1';
            }
        } catch (error) {
            console.error('Error terminating app:', error);
            alert('A network error occurred while trying to terminate the app.');
            btn.disabled = false;
            btn.innerHTML = originalHtml;
            btn.style.opacity = '1';
        }
    };

    // Utility to prevent XSS
    function escapeHtml(unsafe) {
        return (unsafe || '').toString()
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Manual refresh
    refreshBtn.addEventListener('click', fetchPorts);
    
    // Auto-refresh when tab opened
    document.querySelectorAll('.main-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            if (tab.dataset.maintab === 'ports') {
                fetchPorts();
            }
        });
    });

    // Initial fetch
    fetchPorts();
});
