/**
 * Aethvion Suite - Hybrid Log Control Center
 * Manages real-time WebSockets (Live Feed) and file-based forensic analysis.
 */

async function initializeLogsView() {
    console.log("[LogsView] Initializing Hybrid Log Suite...");
    const fileListEl = document.getElementById('logs-file-list');
    const refreshBtn = document.getElementById('refresh-logs-btn');
    const scrollBtn = document.getElementById('scroll-to-bottom-btn');
    const modeBtns = document.querySelectorAll('.mode-btn');

    // --- Mode Switching (Live vs Forensic) ---
    modeBtns.forEach(btn => {
        btn.onclick = () => {
            const mode = btn.dataset.mode;
            modeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            document.querySelectorAll('.log-mode-pane').forEach(p => p.classList.remove('active'));
            document.getElementById(`pane-${mode}`).classList.add('active');
        };
    });

    if (refreshBtn) refreshBtn.onclick = loadLogFileList;
    if (scrollBtn) {
        scrollBtn.onclick = () => {
            const viewer = document.getElementById('forensic-viewer');
            if (viewer) viewer.scrollTop = viewer.scrollHeight;
        };
    }

    loadLogFileList();

    // --- WebSocket Implementation (Live Feed) ---
    // These functions are called by core.js when messages arrive on /ws/logs
    window.handleLogMessage = (event) => {
        try {
            const log = JSON.parse(event.data);
            const container = document.getElementById('logs-container');
            if (!container || !log || log.type === 'heartbeat') return;

            const msg = (log.message || "").toString();
            // Block extremely noisy system polling from polluting the feed
            if (msg.includes("GET /api/system/status") || msg.includes("GET /api/workspace/files")) return;

            const level = (log.level || 'info').toUpperCase();
            if (level === 'DEBUG') return;

            const logLine = document.createElement('div');
            logLine.className = 'log-line';
            let levelClass = 'log-info';
            if (level === 'WARNING') levelClass = 'log-warning';
            if (level === 'ERROR') levelClass = 'log-error';

            const source = log.source ? `${log.source}: ` : '';
            logLine.innerHTML = `<span class="${levelClass}">[${level}]</span> <span class="log-source">${source}</span><span class="log-msg">${msg}</span>`;

            container.appendChild(logLine);
            if (container.children.length > 300) container.removeChild(container.firstChild);
            container.scrollTop = container.scrollHeight;
        } catch (e) {
            console.warn("[LogsView] Live log parse error:", e);
        }
    };

    window.updateSystemTerminal = (message, title, agent, status) => {
        const terminal = document.getElementById('terminal-content');
        if (!terminal) return;

        const line = document.createElement('div');
        line.className = 'terminal-line';
        const time = new Date().toLocaleTimeString([], { hour12: false });

        let icon = 'ℹ️';
        if (status === 'running') icon = '⏳';
        if (status === 'completed') icon = '✓';
        if (status === 'failed') icon = '❌';

        line.innerHTML = `<span class="term-time">[${time}]</span> <span class="term-agent">${agent || 'SYSTEM'}</span> <span class="term-action">${title || ''}:</span> <span>${message}</span> <span class="term-status">${icon}</span>`;
        terminal.appendChild(line);
        if (terminal.children.length > 500) terminal.removeChild(terminal.firstChild);
        terminal.scrollTop = terminal.scrollHeight;
    };
}

/**
 * Loads the list of available .log/.txt files from the backend registry.
 */
async function loadLogFileList() {
    const listContainer = document.getElementById('logs-file-list');
    if (!listContainer) return;

    listContainer.innerHTML = '<div class="loading-spinner"></div>';
    
    try {
        const res = await fetch('/api/logs/list');
        if (!res.ok) throw new Error("Registry unavailable");
        const data = await res.json();

        listContainer.innerHTML = '';
        if (data.logs.length === 0) {
            listContainer.innerHTML = '<div class="log-empty-state">No system logs found.</div>';
            return;
        }

        data.logs.forEach(log => {
            const item = document.createElement('div');
            item.className = 'log-file-item';
            const sizeKB = (log.size / 1024).toFixed(1);
            
            item.innerHTML = `<i class="far fa-file-alt"></i> ${log.name} <span style="font-size:0.7rem; opacity:0.5; margin-left:auto;">${sizeKB}KB</span>`;
            item.onclick = () => {
                document.querySelectorAll('.log-file-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                loadLogFile(log.name);
            };
            listContainer.appendChild(item);
        });
    } catch (e) {
        console.error('[LogsView] List load error:', e);
        listContainer.innerHTML = '<div class="error">Failed to load index.</div>';
    }
}

/**
 * Fetches and renders a specific log file for forensic inspection.
 */
async function loadLogFile(filename) {
    const viewer = document.getElementById('forensic-viewer');
    const title = document.getElementById('current-log-filename');
    if (!viewer) return;

    viewer.innerHTML = '<div class="loading-spinner"></div> Initializing forensic capture...';
    title.innerText = filename;

    try {
        const res = await fetch(`/api/logs/read/${filename}`);
        if (!res.ok) throw new Error("Capture failed");
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        // Render forensic data with basic status colorization
        viewer.innerHTML = data.content.split('\n').map(line => {
            let cls = 'log-line';
            if (line.includes('[ERROR]')) cls += ' log-error';
            if (line.includes('[WARNING]')) cls += ' log-warning';
            return `<div class="${cls}">${line}</div>`;
        }).join('');

        viewer.scrollTop = viewer.scrollHeight;
    } catch (e) {
        console.error('[LogsView] Read error:', e);
        viewer.innerHTML = `<div class="error">Forensic sequence interrupted: ${e.message}</div>`;
    }
}

// Register initialization with the dashboard registry
registerTabInit('logs', initializeLogsView);
