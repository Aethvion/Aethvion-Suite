// Handles fetching and rendering repository documentation

async function loadDocumentation() {
    const container = document.getElementById('documentation-container');
    if (!container) return;

    container.innerHTML = '<div class="loading-placeholder">Scanning repository for .md files...</div>';

    try {
        const response = await fetch('/api/documentation');
        if (!response.ok) throw new Error('Failed to fetch documentation');

        const data = await response.json();
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
                html += `
                    <details class="doc-file-details" id="${docId}">
                        <summary class="doc-file-summary">
                            <span class="file-name"><i class="far fa-file-alt"></i> ${doc.name}</span>
                            <span class="file-path">${doc.path}</span>
                            <i class="fas fa-chevron-down foldout-arrow"></i>
                        </summary>
                        <div class="doc-file-content markdown-body">
                            ${marked.parse(doc.content)}
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

// Initialize when the tab is clicked (handled by core.js general tab logic usually, 
// but we might need a custom hook if it doesn't auto-load)
document.addEventListener('DOMContentLoaded', () => {
    // We listen for the custom event if available or check on tab change
    const docBtn = document.querySelector('[data-subtab="documentation"]');
    if (docBtn) {
        docBtn.addEventListener('click', () => {
            loadDocumentation();
        });
    }
});
