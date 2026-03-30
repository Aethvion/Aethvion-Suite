// Aethvion Suite - Chat & Terminal Mode
// Handles chat messages, terminal logging, and agent actions

// Configure Marked options
if (typeof marked !== 'undefined') {
    marked.setOptions({
        gfm: true,
        breaks: true,
        headerIds: false,
        mangle: false,
        sanitize: false // We trust backend content
    });
} else {
    console.error('CRITICAL: Marked library not loaded!');
}

function handleChatMessage(event) {
    const data = JSON.parse(event.data);

    if (data.type === 'response') {
        addMessage('ai', data.response, {
            trace_id: data.trace_id,
            actions: data.actions,
            tools: data.tools_forged,
            agents: data.agents_spawned
        });

        // Reload files if any were created
        if (currentMainTab === 'files' && typeof loadFiles === 'function') {
            loadFiles();
        }
    } else if (data.type === 'agent_step') {
        // Route to System Terminal
        if (typeof updateSystemTerminal === 'function') {
            updateSystemTerminal(
                data.content,
                data.title,
                data.agent_name,
                data.status
            );
        }

    } else if (data.type === 'package_installed') {
        console.log('Package installed:', data.package);
        if (typeof loadAllPackages === 'function') loadAllPackages();
    } else if (data.type === 'package_failed') {
        console.warn('Package failed:', data.package, data.error);
        if (typeof loadAllPackages === 'function') loadAllPackages();
    }
}

function addMessage(sender, content, metadata = {}) {
    const messages = document.getElementById('chat-messages');
    if (!messages) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;

    let html = '';

    if (sender === 'ai') {
        html = `
            <div class="message-header">
                <span class="message-sender">Misaka</span>
                ${metadata.trace_id ? `<span class="trace-id">${metadata.trace_id}</span>` : ''}
            </div>
            <div class="message-content">${marked.parse(content)}</div>
        `;

        // Handle details/summary if present (custom logic)
        if (content.includes('<details>')) {
            const parts = content.split('<details>');
            if (parts.length > 0) {
                const markdownPart = marked.parse(parts[0]);
                const detailsPart = '<details>' + parts.slice(1).join('<details>');
                html = `
                    <div class="message-header">
                        <span class="message-sender">Misaka</span>
                        ${metadata.trace_id ? `<span class="trace-id">${metadata.trace_id}</span>` : ''}
                    </div>
                    <div class="message-content">
                        ${markdownPart}
                        ${detailsPart}
                    </div>
                `;
            }
        }

        if (metadata.actions && metadata.actions.length > 0) {
            html += `<div class="action-pills">`;
            metadata.actions.forEach(action => {
                html += `<span class="action-pill">${action}</span>`;
            });
            html += `</div>`;
        }
    } else if (sender === 'agent_step') {
        const title = metadata.title || 'Agent Action';
        const agentName = metadata.agent_name;
        const status = metadata.status || 'completed';
        const isError = status === 'failed';

        html = `
            <details class="agent-step-details" ${isError ? 'open' : ''}>
                <summary class="agent-step-summary ${isError ? 'error' : ''}">
                    <span class="step-icon">${isError ? '⚠️' : '🤖'}</span>
                    <span class="step-title">${title}</span>
                    ${agentName ? `<span class="step-agent">${agentName}</span>` : ''}
                </summary>
                <div class="step-content">
                    ${marked.parse(content)}
                </div>
            </details>
        `;
    } else if (sender === 'user') {
        html = `
            <div class="message-header">
                <span class="message-sender">You</span>
            </div>
            <div class="message-content">${content}</div>
        `;
    } else {
        html = `<div class="message-content">${content}</div>`;
    }

    messageDiv.innerHTML = html;
    messages.appendChild(messageDiv);
    messages.scrollTop = messages.scrollHeight;

    // Syntax highlighting for code blocks
    if (typeof hljs !== 'undefined') {
        messageDiv.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
    }
}

// ===== Log Handling =====

function handleLogMessage(event) {
    try {
        const log = JSON.parse(event.data);
        const container = document.getElementById('logs-container');
        if (!container) return;

        if (!log || typeof log !== 'object') return;
        if (log.type === 'heartbeat') return;

        const msg = (log.message || "").toString();
        if (msg.includes("GET /api/system/status") ||
            msg.includes("GET /api/workspace/files") ||
            msg.includes("WebSocket connected")) {
            return;
        }

        const level = (log.level || 'info').toUpperCase();
        if (level === 'DEBUG') return; // Hide debug logs in UI

        const logLine = document.createElement('div');
        logLine.className = 'log-line';

        let levelClass = 'log-info';
        if (level === 'WARNING') levelClass = 'log-warning';
        if (level === 'ERROR') levelClass = 'log-error';

        const source = log.source ? `${log.source}: ` : '';

        const isSystem = ['uvicorn', 'uvicorn.access', 'uvicorn.error', 'watchfiles', 'multipart', 'asyncio'].includes(log.source) ||
            msg.includes('WebSocket') ||
            source.includes('watchfiles');

        if (isSystem) {
            logLine.classList.add('log-system');
        }

        logLine.innerHTML = `<span class="${levelClass}">[${level}]</span> <span class="log-source">${source}</span><span class="log-msg">${msg}</span>`;

        container.appendChild(logLine);

        while (container.children.length > 200) {
            container.removeChild(container.firstChild);
        }

        container.scrollTop = container.scrollHeight;
    } catch (error) {
        console.warn('Invalid log message:', error);
    }
}

// ===== System Terminal =====

// Expose to window for threads.js
window.updateTerminalVisibility = function () {
    const terminal = document.getElementById('system-terminal');
    if (!terminal) return;

    const currentThreadId = window.currentThreadId || 'default';
    const thread = (window.threads && window.threads[currentThreadId]);

    // Default to true
    let enabled = true;
    if (thread && thread.settings && thread.settings.system_terminal_enabled === false) {
        enabled = false;
    }

    terminal.style.display = enabled ? 'flex' : 'none';
};

function updateSystemTerminal(message, title, agent, status) {
    const terminal = document.getElementById('terminal-content');
    if (!terminal) return;

    const line = document.createElement('div');
    line.className = 'terminal-line';

    const time = new Date().toLocaleTimeString([], { hour12: false });

    // Status Icon
    let icon = 'ℹ️';
    if (status === 'running') icon = '⏳';
    if (status === 'completed') icon = '✓';
    if (status === 'failed') icon = '❌';

    // Build line content
    let html = `<span class="term-time">[${time}]</span>`;

    if (agent) {
        html += `<span class="term-agent">${agent}</span>`;
    }

    if (title) {
        html += `<span class="term-action">${title}:</span> `;
    }

    let textContent = message;

    html += `<span>${textContent}</span>`;
    html += `<span class="term-status">${icon}</span>`;

    line.innerHTML = html;

    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;

    if (terminal.children.length > 500) {
        terminal.removeChild(terminal.firstChild);
    }
}
