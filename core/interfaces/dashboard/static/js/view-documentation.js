// Repository Documentation — Split-pane Markdown reader

let _docsCatalog = []; // Flat list of { id, name, path, folder, directory, content }
let _docsFolders = []; // Ordered folder names
let _activeDocPath = localStorage.getItem('doc_active_path') || '';

function _escDoc(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function _renderMarkdownContent(doc) {
    let content = doc.content || '';
    if (doc.name.endsWith('.env') || doc.name.includes('.env.')) {
        content = content.replace(/```env/g, '```properties');
    }

    const renderer = new marked.Renderer();
    const docDir = (doc.directory === 'Root' || doc.directory === '.') ? '' : doc.directory;

    renderer.image = (href, title, text) => {
        if (href && !href.startsWith('http') && !href.startsWith('/') && !href.startsWith('data:')) {
            const fullPath = docDir ? `${docDir}/${href}` : href;
            const src = `/api/workspace/files/serve?path=${encodeURIComponent(fullPath.replace(/\\/g, '/'))}`;
            return `<img src="${src}" title="${_escDoc(title || '')}" alt="${_escDoc(text || '')}">`;
        }
        return `<img src="${_escDoc(href || '')}" title="${_escDoc(title || '')}" alt="${_escDoc(text || '')}">`;
    };

    let renderedHtml = marked.parse(content, { renderer });

    renderedHtml = renderedHtml.replace(/<img[^>]+src=["']([^"']+)["'][^>]*>/g, (match, src) => {
        if (src && !src.startsWith('http') && !src.startsWith('/') && !src.startsWith('data:')) {
            const fullPath = docDir ? `${docDir}/${src}` : src;
            const newSrc = `/api/workspace/files/serve?path=${encodeURIComponent(fullPath.replace(/\\/g, '/'))}`;
            return match.replace(src, newSrc);
        }
        return match;
    });

    return renderedHtml;
}

function _selectDocByPath(docPath) {
    const doc = _docsCatalog.find(d => d.path === docPath) || _docsCatalog[0];
    if (!doc) return;

    _activeDocPath = doc.path;
    localStorage.setItem('doc_active_path', doc.path);

    // Update sidebar active state
    const sidebar = document.getElementById('docs-sidebar-list');
    if (sidebar) {
        sidebar.querySelectorAll('.docs-nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.path === doc.path);
        });
    }

    // Update right pane
    const headerPath = document.getElementById('docs-reader-filepath');
    const headerTitle = document.getElementById('docs-reader-title');
    const readerBody = document.getElementById('docs-reader-body');
    const readerPane = document.getElementById('docs-reader-pane');

    if (headerTitle) headerTitle.textContent = doc.name;
    if (headerPath) headerPath.textContent = doc.path;

    if (readerBody) {
        readerBody.innerHTML = _renderMarkdownContent(doc);

        // Rewrite relative .md links inside the reader so clicking them opens the target doc in-app
        const docDir = (doc.directory === 'Root' || doc.directory === '.') ? '' : doc.directory;
        readerBody.querySelectorAll('a[href]').forEach(a => {
            const href = a.getAttribute('href');
            if (!href || href.startsWith('http') || href.startsWith('#') || href.startsWith('file://')) return;
            const cleanHref = href.split('#')[0];
            if (!cleanHref.toLowerCase().endsWith('.md')) return;

            const parts = (docDir ? `${docDir}/${cleanHref}` : cleanHref).replace(/\\/g, '/').split('/');
            const resolved = [];
            for (const p of parts) {
                if (!p || p === '.') continue;
                if (p === '..') resolved.pop();
                else resolved.push(p);
            }
            const targetPath = resolved.join('/');
            if (_docsCatalog.some(d => d.path === targetPath)) {
                a.addEventListener('click', (e) => {
                    e.preventDefault();
                    _selectDocByPath(targetPath);
                });
            }
        });

        if (window.hljs) {
            readerBody.querySelectorAll('pre code').forEach(block => {
                if (block.classList.contains('language-env')) {
                    block.classList.remove('language-env');
                    block.classList.add('language-properties');
                }
                hljs.highlightElement(block);
            });
        }
    }

    if (readerPane) readerPane.scrollTop = 0;
}

function _renderSidebarTree(filterText = '') {
    const listEl = document.getElementById('docs-sidebar-list');
    if (!listEl) return;

    const query = filterText.trim().toLowerCase();
    let html = '';
    let visibleCount = 0;

    _docsFolders.forEach(folder => {
        const items = _docsCatalog.filter(d => d.folder === folder && (
            !query ||
            d.name.toLowerCase().includes(query) ||
            d.path.toLowerCase().includes(query)
        ));
        if (!items.length) return;
        visibleCount += items.length;

        html += `<div class="docs-nav-group">
            <div class="docs-nav-folder">
                <i class="fas fa-folder-open"></i>
                <span>${_escDoc(folder)}</span>
                <span class="docs-nav-count">${items.length}</span>
            </div>
            <div class="docs-nav-items">`;

        items.forEach(doc => {
            const isActive = doc.path === _activeDocPath ? ' active' : '';
            html += `<button class="docs-nav-item${isActive}" data-path="${_escDoc(doc.path)}" title="${_escDoc(doc.path)}">
                <i class="far fa-file-lines"></i>
                <span class="docs-nav-name">${_escDoc(doc.name)}</span>
            </button>`;
        });

        html += `</div></div>`;
    });

    if (!visibleCount) {
        html = `<div class="docs-nav-empty">No matching Markdown files</div>`;
    }

    listEl.innerHTML = html;
    listEl.querySelectorAll('.docs-nav-item').forEach(btn => {
        btn.addEventListener('click', () => _selectDocByPath(btn.dataset.path));
    });
}

async function loadDocumentation(force = false) {
    const container = document.getElementById('documentation-container');
    if (!container) return;

    if (!force && _docsCatalog.length > 0 && container.querySelector('#docs-reader-pane')) {
        return;
    }

    container.innerHTML = '<div class="loading-placeholder">Scanning repository for .md files...</div>';

    try {
        const response = await fetch('/api/documentation');
        if (!response.ok) throw new Error('Failed to fetch documentation');

        const data = await response.json();
        if (!data || !data.docs) {
            throw new Error('Invalid documentation data received from server');
        }

        const docs = data.docs;
        const folderKeys = Object.keys(docs).sort((a, b) => {
            if (a === 'docs') return -1;
            if (b === 'docs') return 1;
            if (a === 'Root') return -1;
            if (b === 'Root') return 1;
            return a.localeCompare(b);
        });

        _docsFolders = folderKeys;
        _docsCatalog = [];

        folderKeys.forEach(folder => {
            const sortedFiles = [...docs[folder]].sort((a, b) => a.name.localeCompare(b.name));
            sortedFiles.forEach(doc => {
                _docsCatalog.push({
                    name: doc.name,
                    path: doc.path,
                    folder,
                    directory: doc.directory,
                    content: doc.content
                });
            });
        });

        if (_docsCatalog.length === 0) {
            container.innerHTML = '<div class="empty-state">No documentation files found in the repository.</div>';
            return;
        }

        const metaEl = document.getElementById('doc-view-meta');
        if (metaEl) {
            metaEl.textContent = `${_docsCatalog.length} Markdown files across ${_docsFolders.length} folders`;
        }

        container.innerHTML = `
            <div class="docs-split-layout">
                <aside class="docs-sidebar-pane">
                    <div class="docs-search-wrap">
                        <i class="fas fa-magnifying-glass"></i>
                        <input type="text" id="docs-search-input" placeholder="Filter docs..." autocomplete="off" />
                    </div>
                    <div class="docs-sidebar-list" id="docs-sidebar-list"></div>
                </aside>
                <main class="docs-reader-pane" id="docs-reader-pane">
                    <div class="docs-reader-bar">
                        <div class="docs-reader-meta">
                            <span class="docs-reader-title" id="docs-reader-title"></span>
                            <code class="docs-reader-filepath" id="docs-reader-filepath"></code>
                        </div>
                        <button class="doc-toolbar-btn" id="docs-copy-path-btn" title="Copy relative file path">
                            <i class="far fa-copy"></i> Copy Path
                        </button>
                    </div>
                    <article class="docs-reader-article markdown-body" id="docs-reader-body"></article>
                </main>
            </div>
        `;

        const searchInput = document.getElementById('docs-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => _renderSidebarTree(e.target.value));
        }

        const copyBtn = document.getElementById('docs-copy-path-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', async () => {
                if (!_activeDocPath) return;
                try {
                    await navigator.clipboard.writeText(_activeDocPath);
                    copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied';
                    setTimeout(() => {
                        copyBtn.innerHTML = '<i class="far fa-copy"></i> Copy Path';
                    }, 1400);
                } catch (_) {}
            });
        }

        // Default selection: saved path -> docs/README.md -> README.md -> first file
        const preferred =
            _docsCatalog.find(d => d.path === _activeDocPath) ||
            _docsCatalog.find(d => d.path === 'docs/README.md') ||
            _docsCatalog.find(d => d.path === 'README.md') ||
            _docsCatalog[0];

        _activeDocPath = preferred.path;
        _renderSidebarTree();
        _selectDocByPath(preferred.path);
    } catch (error) {
        console.error('Error loading documentation:', error);
        container.innerHTML = `
            <div class="error-state">
                <i class="fas fa-exclamation-triangle"></i>
                <p>Failed to load documentation: ${_escDoc(error.message)}</p>
                <button class="action-btn sm-btn" onclick="loadDocumentation(true)">Retry</button>
            </div>
        `;
    }
}

const docStyles = `
#documentation-panel {
    display: flex !important;
    flex-direction: column;
    height: 100%;
    min-height: 0;
}
.docs-panel-header {
    padding-bottom: 12px !important;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
}
.doc-toolbar-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    border-radius: 6px;
    color: var(--text-muted, #94a3b8);
    font-size: 0.78rem;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
}
.doc-toolbar-btn:hover {
    color: var(--text, #e2e8f0);
    border-color: rgba(255,255,255,0.22);
    background: rgba(255,255,255,0.08);
}
.docs-workspace {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 0 !important;
}
.docs-split-layout {
    display: flex;
    flex: 1;
    min-height: 0;
    height: 100%;
    overflow: hidden;
}
.docs-sidebar-pane {
    width: 290px;
    min-width: 240px;
    max-width: 340px;
    border-right: 1px solid var(--border, rgba(255,255,255,0.08));
    background: rgba(0, 0, 0, 0.16);
    display: flex;
    flex-direction: column;
    min-height: 0;
}
.docs-search-wrap {
    position: relative;
    padding: 12px;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.07));
}
.docs-search-wrap i {
    position: absolute;
    left: 22px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.78rem;
    color: var(--text-muted, #64748b);
    pointer-events: none;
}
#docs-search-input {
    width: 100%;
    padding: 7px 10px 7px 30px;
    border-radius: 6px;
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    background: rgba(255,255,255,0.04);
    color: var(--text, #e2e8f0);
    font-size: 0.82rem;
    font-family: inherit;
    outline: none;
    box-sizing: border-box;
}
#docs-search-input:focus {
    border-color: var(--primary, #60a5fa);
    background: rgba(255,255,255,0.06);
}
.docs-sidebar-list {
    flex: 1;
    overflow-y: auto;
    padding: 10px 8px 20px;
}
.docs-nav-group {
    margin-bottom: 14px;
}
.docs-nav-folder {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 4px 10px 6px;
    font-size: 0.71rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted, #94a3b8);
}
.docs-nav-folder i {
    color: var(--primary, #60a5fa);
    font-size: 0.72rem;
}
.docs-nav-count {
    margin-left: auto;
    font-size: 0.68rem;
    padding: 1px 6px;
    border-radius: 999px;
    background: rgba(255,255,255,0.06);
    color: var(--text-muted, #94a3b8);
}
.docs-nav-items {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.docs-nav-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    text-align: left;
    padding: 7px 10px;
    border-radius: 6px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-muted, #cbd5e1);
    font-size: 0.82rem;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.14s ease, color 0.14s ease, border-color 0.14s ease;
}
.docs-nav-item i {
    font-size: 0.78rem;
    opacity: 0.7;
    flex-shrink: 0;
}
.docs-nav-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.docs-nav-item:hover {
    background: rgba(255,255,255,0.05);
    color: var(--text, #f8fafc);
}
.docs-nav-item.active {
    background: rgba(96, 165, 250, 0.12);
    border-color: rgba(96, 165, 250, 0.35);
    color: var(--primary, #60a5fa);
    font-weight: 600;
}
.docs-nav-item.active i {
    opacity: 1;
}
.docs-nav-empty {
    padding: 20px 12px;
    text-align: center;
    font-size: 0.82rem;
    color: var(--text-muted, #94a3b8);
}

.docs-reader-pane {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    background: rgba(0, 0, 0, 0.06);
}
.docs-reader-bar {
    position: sticky;
    top: 0;
    z-index: 5;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 28px;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
}
.docs-reader-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    flex-wrap: wrap;
}
.docs-reader-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: var(--text, #f1f5f9);
}
.docs-reader-filepath {
    font-size: 0.76rem;
    padding: 2px 8px;
    border-radius: 5px;
    background: rgba(255,255,255,0.06);
    color: var(--text-muted, #94a3b8);
    font-family: var(--font-mono, monospace);
}
.docs-reader-article {
    width: 100%;
    max-width: 880px;
    margin: 0 auto;
    padding: 28px 34px 64px;
    line-height: 1.7;
    font-size: 0.94rem;
    color: var(--text, #e2e8f0);
    box-sizing: border-box;
}
.docs-reader-article h1,
.docs-reader-article h2,
.docs-reader-article h3,
.docs-reader-article h4 {
    margin-top: 1.6em;
    margin-bottom: 0.6em;
    line-height: 1.3;
    font-weight: 650;
    color: var(--text, #f8fafc);
}
.docs-reader-article h1:first-child {
    margin-top: 0;
}
.docs-reader-article h1 {
    font-size: 1.75rem;
    padding-bottom: 0.45rem;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.1));
}
.docs-reader-article h2 {
    font-size: 1.3rem;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.07));
}
.docs-reader-article h3 {
    font-size: 1.08rem;
}
.docs-reader-article p {
    margin: 0.75em 0;
}
.docs-reader-article ul,
.docs-reader-article ol {
    padding-left: 1.5rem;
    margin: 0.75em 0;
}
.docs-reader-article li + li {
    margin-top: 0.3em;
}
.docs-reader-article a {
    color: var(--primary, #60a5fa);
    text-decoration: none;
}
.docs-reader-article a:hover {
    text-decoration: underline;
}
.docs-reader-article code {
    font-family: var(--font-mono, monospace);
    font-size: 0.85em;
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(255,255,255,0.08);
}
.docs-reader-article pre {
    margin: 1em 0;
    padding: 14px 16px;
    border-radius: 8px;
    border: 1px solid var(--border, rgba(255,255,255,0.09));
    background: rgba(0, 0, 0, 0.32);
    overflow-x: auto;
}
.docs-reader-article pre code {
    padding: 0;
    background: transparent;
    font-size: 0.84rem;
    line-height: 1.55;
}
.docs-reader-article blockquote {
    margin: 1em 0;
    padding: 10px 16px;
    border-left: 3px solid var(--primary, #60a5fa);
    background: rgba(96, 165, 250, 0.06);
    border-radius: 0 6px 6px 0;
    color: var(--text-muted, #cbd5e1);
}
.docs-reader-article table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.1em 0;
    font-size: 0.88rem;
}
.docs-reader-article th,
.docs-reader-article td {
    padding: 9px 12px;
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    text-align: left;
}
.docs-reader-article th {
    background: rgba(255,255,255,0.05);
    font-weight: 600;
}
.docs-reader-article tr:nth-child(even) td {
    background: rgba(255,255,255,0.02);
}
.docs-reader-article hr {
    border: none;
    border-top: 1px solid var(--border, rgba(255,255,255,0.1));
    margin: 1.8em 0;
}
.docs-reader-article img {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    margin: 12px 0;
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
@media (max-width: 820px) {
    .docs-split-layout {
        flex-direction: column;
    }
    .docs-sidebar-pane {
        width: 100%;
        max-width: none;
        max-height: 220px;
        border-right: none;
        border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
    }
    .docs-reader-article {
        padding: 20px 18px 40px;
    }
    .docs-reader-bar {
        padding: 10px 16px;
    }
}
`;

const styleSheet = document.createElement('style');
styleSheet.innerText = docStyles;
document.head.appendChild(styleSheet);

document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('tabChanged', (e) => {
        if (e.detail && (e.detail.tab === 'documentation' || e.detail.tab === 'panel-documentation')) {
            loadDocumentation();
        }
    });

    const docPanel = document.getElementById('documentation-panel');
    if (docPanel && (docPanel.classList.contains('active') || window.getComputedStyle(docPanel).display !== 'none')) {
        setTimeout(() => loadDocumentation(), 200);
    }

    const docBtn = document.querySelector('[data-subtab="documentation"]') || document.querySelector('[data-maintab="documentation"]');
    if (docBtn) {
        docBtn.addEventListener('click', () => loadDocumentation());
    }
});
