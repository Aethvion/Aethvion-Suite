// Handles fetching and rendering repository documentation

// ── View switching ────────────────────────────────────────────────────────────

var _docCurrentView = localStorage.getItem('doc_view') || 'repo';

function switchDocView(view) {
    _docCurrentView = view;
    localStorage.setItem('doc_view', view);

    var container = document.getElementById('documentation-container');
    var frame     = document.getElementById('interactive-docs-frame');
    var btnRepo   = document.getElementById('btn-repo-docs');
    var btnWeb    = document.getElementById('btn-interactive-docs');
    var meta      = document.getElementById('doc-view-meta');

    if (view === 'interactive') {
        if (container) container.style.display = 'none';
        if (frame)     frame.style.display     = 'block';
        if (btnRepo)   btnRepo.classList.remove('active');
        if (btnWeb)    btnWeb.classList.add('active');
        if (meta)      meta.textContent = 'Interactive Tutorial Website';
    } else {
        if (container) container.style.display = '';
        if (frame)     frame.style.display     = 'none';
        if (btnRepo)   btnRepo.classList.add('active');
        if (btnWeb)    btnWeb.classList.remove('active');
        if (meta)      meta.textContent = 'Aggregated Markdown Docs';
        // Load markdown docs if not already loaded
        if (container && container.querySelector('.loading-placeholder')) {
            loadDocumentation();
        }
    }
}

async function loadDocumentation() {
    const container = document.getElementById('documentation-container');
    if (!container) return;

    container.innerHTML = '<div class="loading-placeholder">Scanning repository for .md files...</div>';

    try {
        const response = await fetch('/api/documentation');
        if (!response.ok) throw new Error('Failed to fetch documentation');

        const data = await response.json();
        
        if (!data || !data.docs) {
            throw new Error('Invalid documentation data received from server');
        }
        
        const docs = data.docs;
        if (Object.keys(docs).length === 0) {
            container.innerHTML = '<div class="empty-state">No documentation files found in the repository.</div>';
            return;
        }

        let html = '';

        // Sort folders alphabetically
        const folders = Object.keys(docs).sort((a, b) => {
            if (a === 'Root') return -1;
            if (b === 'Root') return 1;
            return a.localeCompare(b);
        });

        folders.forEach(folder => {
            html += `<div class="doc-folder-section">
                <h3 class="doc-folder-title"><i class="fas fa-folder"></i> ${folder}</h3>
                <div class="doc-folder-items">`;

            docs[folder].forEach(doc => {
                const docId = `doc-${folder.replace(/[^a-zA-Z0-9]/g, '-')}-${doc.name.replace(/[^a-zA-Z0-9]/g, '-')}`;
                
                // Fix for .env files which often use ```env but highlight.js doesn't know it
                let content = doc.content;
                if (doc.name.endsWith('.env') || doc.name.includes('.env.')) {
                    content = content.replace(/```env/g, '```properties');
                }

                // Custom renderer to fix relative image paths in Markdown ![alt](url) syntax
                const renderer = new marked.Renderer();
                const docDir = (doc.directory === "Root" || doc.directory === ".") ? "" : doc.directory;
                
                renderer.image = (href, title, text) => {
                    if (href && !href.startsWith('http') && !href.startsWith('/') && !href.startsWith('data:')) {
                        const fullPath = docDir ? `${docDir}/${href}` : href;
                        const src = `/api/workspace/files/serve?path=${encodeURIComponent(fullPath.replace(/\\/g, '/'))}`;
                        return `<img src="${src}" title="${title || ''}" alt="${text || ''}" style="max-width: 100%; height: auto; border-radius: 8px; margin: 10px 0;">`;
                    }
                    return `<img src="${href}" title="${title || ''}" alt="${text || ''}" style="max-width: 100%; height: auto; border-radius: 8px; margin: 10px 0;">`;
                };

                let renderedHtml = marked.parse(content, { renderer });

                // Also fix HTML <img> tags which marked doesn't handle via renderer
                renderedHtml = renderedHtml.replace(/<img[^>]+src=["']([^"']+)["'][^>]*>/g, (match, src) => {
                    if (src && !src.startsWith('http') && !src.startsWith('/') && !src.startsWith('data:')) {
                        const fullPath = docDir ? `${docDir}/${src}` : src;
                        const newSrc = `/api/workspace/files/serve?path=${encodeURIComponent(fullPath.replace(/\\/g, '/'))}`;
                        return match.replace(src, newSrc);
                    }
                    return match;
                });

                html += `
                    <details class="doc-file-details" id="${docId}">
                        <summary class="doc-file-summary">
                            <span class="file-name"><i class="far fa-file-alt"></i> ${doc.name}</span>
                            <span class="file-path">${doc.path}</span>
                            <i class="fas fa-chevron-down foldout-arrow"></i>
                        </summary>
                        <div class="doc-file-content markdown-body">
                            ${renderedHtml}
                        </div>
                    </details>
                `;
            });

            html += `</div></div>`;
        });

        container.innerHTML = html;

        // Apply syntax highlighting
        if (window.hljs) {
            container.querySelectorAll('pre code').forEach((block) => {
                // Map 'env' to 'properties' if it's there as a class
                if (block.classList.contains('language-env')) {
                    block.classList.remove('language-env');
                    block.classList.add('language-properties');
                }
                hljs.highlightElement(block);
            });
        }

    } catch (error) {
        console.error('Error loading documentation:', error);
        container.innerHTML = `
            <div class="error-state">
                <i class="fas fa-exclamation-triangle"></i>
                <p>Failed to load documentation: ${error.message}</p>
                <button class="action-btn sm-btn" onclick="loadDocumentation()">Retry</button>
            </div>
        `;
    }
}

// Add CSS for documentation
const docStyles = `
/* ── View toggle ── */
#doc-view-toggle {
    display: flex;
    gap: 6px;
}
.doc-toggle-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    background: transparent;
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    border-radius: 6px;
    color: var(--text-muted, #94a3b8);
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    transition: color 0.15s, border-color 0.15s, background 0.15s;
    white-space: nowrap;
}
.doc-toggle-btn:hover {
    color: var(--text, #e2e8f0);
    border-color: rgba(255,255,255,0.2);
    background: rgba(255,255,255,0.04);
}
.doc-toggle-btn.active {
    color: var(--primary, #60a5fa);
    border-color: rgba(96,165,250,0.4);
    background: rgba(96,165,250,0.08);
}
/* Make the panel flex so the iframe fills height */
#documentation-panel {
    display: flex !important;
    flex-direction: column;
}
#interactive-docs-frame {
    flex: 1;
    min-height: 0;
    border: none;
    border-radius: 0;
}

/* ── Markdown docs ── */
.doc-folder-section {
    margin-bottom: 2rem;
}
.doc-folder-title {
    font-size: 1rem;
    color: var(--primary);
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.doc-folder-items {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
}
.doc-file-details {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    transition: all 0.2s ease;
}
.doc-file-details:hover {
    border-color: var(--primary-muted);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.doc-file-details[open] {
    border-color: var(--primary);
}
.doc-file-summary {
    padding: 1rem;
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: 500;
}
.doc-file-summary::-webkit-details-marker {
    display: none;
}
.doc-file-summary .file-name {
    display: flex;
    align-items: center;
    gap: 0.8rem;
}
.doc-file-summary .file-path {
    font-size: 0.8rem;
    color: var(--text-muted);
    font-family: var(--font-mono);
    margin-left: auto;
    margin-right: 1.5rem;
    opacity: 0.6;
}
.doc-file-summary .foldout-arrow {
    transition: transform 0.3s ease;
    font-size: 0.8rem;
    color: var(--text-muted);
}
.doc-file-details[open] .foldout-arrow {
    transform: rotate(180deg);
}
.doc-file-content {
    padding: 1.5rem;
    border-top: 1px solid var(--border);
    background: rgba(0,0,0,0.05);
}
.loading-placeholder, .empty-state, .error-state {
    padding: 3rem;
    text-align: center;
    color: var(--text-muted);
}
.error-state i {
    font-size: 2rem;
    color: var(--error);
    margin-bottom: 1rem;
}
`;

const styleSheet = document.createElement("style");
styleSheet.innerText = docStyles;
document.head.appendChild(styleSheet);

// Initialize when the tab is clicked or if it's already active on load
document.addEventListener('DOMContentLoaded', () => {
    function onDocTabOpen() {
        // Restore saved view preference
        switchDocView(_docCurrentView);
        // If repo view and not yet loaded, trigger a load
        if (_docCurrentView === 'repo') {
            var container = document.getElementById('documentation-container');
            if (container && container.querySelector('.loading-placeholder')) {
                loadDocumentation();
            }
        }
    }

    // Listen for tab changes from core.js
    document.addEventListener('tabChanged', (e) => {
        if (e.detail && (e.detail.tab === 'documentation' || e.detail.tab === 'panel-documentation')) {
            onDocTabOpen();
        }
    });

    // Auto-load if the documentation panel is already showing (e.g. on refresh)
    const docPanel = document.getElementById('documentation-panel');
    if (docPanel && (docPanel.classList.contains('active') || window.getComputedStyle(docPanel).display !== 'none')) {
        setTimeout(onDocTabOpen, 200);
    }

    // Fallback for click if event doesn't fire for some reason
    const docBtn = document.querySelector('[data-subtab="documentation"]') || document.querySelector('[data-maintab="documentation"]');
    if (docBtn) {
        docBtn.addEventListener('click', () => {
            onDocTabOpen();
        });
    }
});
