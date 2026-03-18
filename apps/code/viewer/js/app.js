/**
 * Aethvion Code IDE — Main Application
 * Monaco Editor + File Tree + AI Copilot
 */

// ── State ───────────────────────────────────────────────────────────────────
const state = {
  workspace:        '',
  tabs:             [],       // [{path, name, language, dirty}]
  activeTab:        null,
  monacoModels:     new Map(),// path → ITextModel
  viewStates:       new Map(),// path → editor.saveViewState()
  chatHistory:      [],       // [{role, content}]
  currentThreadId:  null,     // active thread id
  selectedModel:    '',
  isRunning:        false,
  lastError:        '',       // last stderr output (used by Fix)
  treeExpanded:     new Set(),
  contextTarget:    null,     // {path, isDir, el}
  treeData:         null,
  treeFiles:        new Set(),// flat set of all file paths (populated by refreshTree)
  abortCtrl:        null,     // for cancelling run
  bottomCollapsed:  false,
  editor:           null,
  moveTargetDir:    null,     // selected folder in move picker
};

// ── Settings persistence (localStorage) ─────────────────────────────────────
function saveSettings() {
  try { localStorage.setItem('ide_settings', JSON.stringify({ selectedModel: state.selectedModel })); } catch {}
}
function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem('ide_settings') || '{}');
    if (s.selectedModel) state.selectedModel = s.selectedModel;
  } catch {}
}
loadSettings();

// ── DOM refs ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const dom = {
  topbar:        $('topbar'),
  workspacePill: $('workspacePill'),
  workspaceLabel:$('workspaceLabel'),
  tabsContainer: $('tabsContainer'),
  treeRoot:      $('treeRoot'),
  welcomeScreen: $('welcomeScreen'),
  monacoContainer:$('monacoContainer'),
  chatMessages:  $('chatMessages'),
  chatInput:     $('chatInput'),
  outputPre:     $('outputPre'),
  modelSel:      $('modelSel'),
  btnRun:        $('btnRun'),
  btnStop:       $('btnStop'),
  bottomPanel:   $('bottomPanel'),
  contextMenu:   $('contextMenu'),
  toastContainer:$('toastContainer'),
  fileTree:      $('fileTree'),
  aiPanel:       $('aiPanel'),
};

// ── Toast ─────────────────────────────────────────────────────────────────────
const TOAST_ICONS = { success:'fa-circle-check', error:'fa-circle-xmark', warn:'fa-triangle-exclamation', info:'fa-circle-info' };
function toast(msg, type = 'info', duration = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<i class="fa-solid ${TOAST_ICONS[type] || TOAST_ICONS.info}" aria-hidden="true"></i><span>${msg}</span>`;
  dom.toastContainer.appendChild(el);
  const remove = () => {
    el.classList.add('removing');
    el.addEventListener('animationend', () => el.remove(), { once: true });
  };
  const t = setTimeout(remove, duration);
  el.addEventListener('click', () => { clearTimeout(t); remove(); });
}

// ── File type icon map ────────────────────────────────────────────────────────
const FILE_ICONS = {
  py:'fa-snake icon-py', js:'fa-square-js icon-js', mjs:'fa-square-js icon-js',
  jsx:'fa-react icon-js', ts:'fa-code icon-ts', tsx:'fa-react icon-ts',
  html:'fa-html5 icon-html', htm:'fa-html5 icon-html',
  css:'fa-css3-alt icon-css', scss:'fa-css3-alt icon-css',
  json:'fa-brackets-curly icon-json', yaml:'fa-align-left icon-yaml', yml:'fa-align-left icon-yaml',
  md:'fa-markdown icon-md', sql:'fa-database icon-sql',
  sh:'fa-terminal icon-sh', bash:'fa-terminal icon-sh', zsh:'fa-terminal icon-sh',
  bat:'fa-terminal icon-bat', cmd:'fa-terminal icon-bat', ps1:'fa-terminal icon-bat',
  rs:'fa-gear icon-rust', go:'fa-g icon-go', java:'fa-java icon-java',
  c:'fa-c icon-file', cpp:'fa-c icon-file', h:'fa-c icon-file',
  cs:'fa-hashtag icon-file', rb:'fa-gem icon-file', php:'fa-php icon-file',
  txt:'fa-file-lines icon-file', env:'fa-lock icon-yaml', gitignore:'fa-code-branch icon-file',
  toml:'fa-sliders icon-yaml', ini:'fa-sliders icon-yaml', xml:'fa-code icon-file',
};
function fileIcon(name) {
  const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : name.toLowerCase();
  return FILE_ICONS[ext] || 'fa-file icon-file';
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

/** Stream an SSE endpoint; calls onChunk(text) per chunk, returns full text. */
async function streamSSE(path, body, onChunk) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: state.abortCtrl?.signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  let full = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const evt = JSON.parse(line.slice(6));
        if (evt.done) return full;
        if (evt.error) throw new Error(evt.error);
        if (evt.text) { full += evt.text; onChunk(evt.text); }
      } catch (e) { if (e.message !== 'Unexpected end of JSON input') throw e; }
    }
  }
  return full;
}

// ── Provider/model loading ────────────────────────────────────────────────────
function _buildModelOptions(data, selectedId = null) {
  if (!data || !data.models) return '';
  const providerLabels = { google_ai: 'Google AI', openai: 'OpenAI', anthropic: 'Anthropic', grok: 'Grok', local: 'Local' };
  const providerOrder  = ['google_ai', 'openai', 'anthropic', 'grok', 'local'];

  // Profiles group
  const profiles = data.chat_profiles || {};
  let html = '<optgroup label="Chat Profiles">';
  if (data.models.length > 1) {
    html += `<option value="auto"${(!selectedId || selectedId === 'auto') ? ' selected' : ''}>Auto (Complexity Routing)</option>`;
  }
  for (const [name] of Object.entries(profiles)) {
    const val = `profile:chat:${name}`;
    html += `<option value="${val}"${val === selectedId ? ' selected' : ''}>Profile: ${name}</option>`;
  }
  html += '</optgroup>';

  // Models grouped by provider
  const byProvider = {};
  for (const m of data.models) {
    (byProvider[m.provider] = byProvider[m.provider] || []).push(m);
  }
  for (const p of providerOrder) {
    if (!byProvider[p]?.length) continue;
    const label = providerLabels[p] || (p.charAt(0).toUpperCase() + p.slice(1));
    html += `<optgroup label="${label}">`;
    for (const m of byProvider[p]) {
      const cost = (m.input_cost_per_1m_tokens || m.output_cost_per_1m_tokens)
        ? ` ($${m.input_cost_per_1m_tokens}/$${m.output_cost_per_1m_tokens})` : '';
      html += `<option value="${m.id}"${m.id === selectedId ? ' selected' : ''} title="${m.description || ''}">${m.id}${cost}</option>`;
    }
    html += '</optgroup>';
  }
  return html;
}

async function loadProviders() {
  try {
    const data = await api('/api/registry/models');
    if (!data.models?.length) {
      dom.modelSel.innerHTML = '<option value="">No AI providers</option>';
      return;
    }
    dom.modelSel.innerHTML = _buildModelOptions(data, state.selectedModel || null);
    // Default to first non-auto model if nothing selected
    if (!state.selectedModel) {
      state.selectedModel = data.models[0].id;
      dom.modelSel.value   = state.selectedModel;
    }
  } catch { dom.modelSel.innerHTML = '<option value="">No providers</option>'; }
}

// ── Project persistence ───────────────────────────────────────────────────────
async function saveProjectState() {
  if (!state.workspace) return;
  try {
    await api('/api/project', {
      method: 'POST',
      body: JSON.stringify({
        workspace:  state.workspace,
        open_tabs:  state.tabs.map(t => t.path),
        active_tab: state.activeTab || null,
      }),
    });
  } catch { /* silent — persistence is best-effort */ }
}

async function restoreProjectState(workspace) {
  try {
    const proj = await api(`/api/project?workspace=${encodeURIComponent(workspace)}`);
    // Restore open tabs (skip any that fail to load)
    if (proj.open_tabs?.length) {
      for (const path of proj.open_tabs) {
        try { await openFile(path, true); } catch { /* file may have moved */ }
      }
      if (proj.active_tab) {
        const exists = state.tabs.find(t => t.path === proj.active_tab);
        if (exists) activateTab(proj.active_tab);
      }
    }
  } catch { /* no saved state yet */ }
}

// ── Workspace ─────────────────────────────────────────────────────────────────
async function loadWorkspace(path = '') {
  try {
    // Save state of the previous workspace first
    if (state.workspace) await saveProjectState();

    if (!path) {
      const roots = await api('/api/fs/roots');
      path = roots.last_workspace || roots.workspace;
    }
    // Close all current tabs silently
    for (const tab of [...state.tabs]) {
      state.monacoModels.get(tab.path)?.dispose();
      state.monacoModels.delete(tab.path);
      state.viewStates.delete(tab.path);
    }
    state.tabs = [];
    state.activeTab = null;
    state.chatHistory = [];
    state.currentThreadId = null;
    if (state.editor) state.editor.setModel(null);
    dom.welcomeScreen.style.display   = '';
    dom.monacoContainer.style.display = 'none';
    renderTabs();

    state.workspace = path;
    const short = path.split(/[\\/]/).slice(-2).join('/');
    dom.workspaceLabel.textContent = short;
    dom.workspaceLabel.title = path;
    await refreshTree(path);
    // Restore previously open files for this workspace
    await restoreProjectState(path);
    // Update auxiliary panels
    updateGitBranch();
    loadContextNotes();
    updateStatusBar();
    await initThreads();
  } catch (e) { toast(`Workspace error: ${e.message}`, 'error'); }
}

// ── File tree ─────────────────────────────────────────────────────────────────
async function refreshTree(path = state.workspace) {
  try {
    const data = await api(`/api/fs/tree?path=${encodeURIComponent(path)}`);
    state.treeData = data;
    // Rebuild flat file path index for FWC "Added vs Changed" detection
    state.treeFiles = new Set();
    function _collectPaths(node) {
      if (!node) return;
      if (node.type === 'file') state.treeFiles.add(node.path.replace(/\\/g, '/'));
      else if (node.children) node.children.forEach(_collectPaths);
    }
    _collectPaths(data);
    dom.treeRoot.innerHTML = '';
    if (data) renderTreeNode(data, dom.treeRoot, 0, true);
  } catch (e) { toast(`Tree error: ${e.message}`, 'error'); }
}

function renderTreeNode(node, container, depth, isRoot = false) {
  if (node.type === 'dir') {
    // Root: render children directly; non-root: add a collapsible dir item
    if (!isRoot) {
      const isExpanded = state.treeExpanded.has(node.path);
      const row = document.createElement('div');
      row.className = `tree-item${isExpanded ? ' expanded' : ''}`;
      row.style.paddingLeft = `${8 + depth * 14}px`;
      row.dataset.path = node.path;
      row.dataset.isdir = '1';
      row.innerHTML = `
        <i class="fa-solid fa-chevron-right ti-arrow" aria-hidden="true"></i>
        <i class="fa-solid ${isExpanded ? 'fa-folder-open icon-dir-open' : 'fa-folder icon-dir'} ti-icon" aria-hidden="true"></i>
        <span class="ti-name">${node.name}</span>`;
      row.addEventListener('click', e => { e.stopPropagation(); toggleDir(node, row); });
      row.addEventListener('contextmenu', e => showContextMenu(e, node.path, true, row));
      container.appendChild(row);

      const children = document.createElement('div');
      children.className = 'tree-children';
      children.style.display = isExpanded ? '' : 'none';
      container.appendChild(children);

      if (isExpanded && node.children) {
        for (const child of node.children) renderTreeNode(child, children, depth + 1);
      }
      // Store children container ref for lazy rendering
      row._childContainer = children;
      row._node = node;
    } else {
      // Root: render all children at depth 0
      if (node.children) {
        for (const child of node.children) renderTreeNode(child, container, 0);
      }
    }
  } else {
    const row = document.createElement('div');
    row.className = `tree-item${state.activeTab === node.path ? ' active' : ''}`;
    row.style.paddingLeft = `${8 + depth * 14}px`;
    row.dataset.path = node.path;
    row.innerHTML = `
      <i class="fa-solid ${fileIcon(node.name)} ti-icon" aria-hidden="true"></i>
      <span class="ti-name">${node.name}</span>`;
    row.addEventListener('click', e => { e.stopPropagation(); openFile(node.path); });
    row.addEventListener('contextmenu', e => showContextMenu(e, node.path, false, row));
    row.addEventListener('dblclick', e => { e.stopPropagation(); startInlineRename(row, node.path, false); });
    container.appendChild(row);
  }
}

function toggleDir(node, row) {
  const isExpanded = state.treeExpanded.has(node.path);
  const childContainer = row._childContainer;

  if (isExpanded) {
    state.treeExpanded.delete(node.path);
    row.classList.remove('expanded');
    const icon = row.querySelector('.ti-icon');
    if (icon) { icon.className = 'fa-solid fa-folder icon-dir ti-icon'; }
    if (childContainer) childContainer.style.display = 'none';
  } else {
    state.treeExpanded.add(node.path);
    row.classList.add('expanded');
    const icon = row.querySelector('.ti-icon');
    if (icon) { icon.className = 'fa-solid fa-folder-open icon-dir-open ti-icon'; }
    if (childContainer) {
      childContainer.style.display = '';
      if (!childContainer.children.length && node.children) {
        const depth = parseInt(row.style.paddingLeft) / 14;
        for (const child of node.children) renderTreeNode(child, childContainer, depth + 1);
      }
    }
  }
}

// ── Tab management ────────────────────────────────────────────────────────────
/**
 * Open a file.
 * @param {string} path - File path
 * @param {boolean} silent - If true, open without activating (used during restore)
 */
function openFile(path, silent = false) {
  const existing = state.tabs.find(t => t.path === path);
  if (existing) {
    if (!silent) activateTab(path);
    return Promise.resolve();
  }
  return fetch(`/api/fs/read?path=${encodeURIComponent(path)}`)
    .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })
    .then(data => {
      const tab = { path: data.path, name: data.name, language: data.language, dirty: false };
      state.tabs.push(tab);
      // Create Monaco model
      if (state.editor) {
        const uri = window.monaco.Uri.file(data.path);
        let model = state.monacoModels.get(data.path);
        if (!model) {
          model = window.monaco.editor.createModel(data.content, data.language, uri);
          model.onDidChangeContent(() => markDirty(data.path));
          state.monacoModels.set(data.path, model);
        }
      }
      renderTabs();
      if (!silent) { activateTab(data.path); highlightTreeItem(data.path); }
    })
    .catch(e => { if (!silent) toast(`Cannot open file: ${e.message}`, 'error'); });
}

function activateTab(path) {
  // Save view state of current tab
  if (state.activeTab && state.editor) {
    state.viewStates.set(state.activeTab, state.editor.saveViewState());
  }

  state.activeTab = path;
  dom.welcomeScreen.style.display  = 'none';
  dom.monacoContainer.style.display = '';

  if (state.editor) {
    const model = state.monacoModels.get(path);
    if (model) {
      state.editor.setModel(model);
      const vs = state.viewStates.get(path);
      if (vs) state.editor.restoreViewState(vs);
      state.editor.focus();
    }
  }

  renderTabs();
  highlightTreeItem(path);

  // Enable/disable run button based on language
  const tab = state.tabs.find(t => t.path === path);
  const runnable = ['python','javascript','shell','bat'].includes(tab?.language ?? '');
  dom.btnRun.disabled = !runnable;

  updateStatusBar();
}

function closeTab(path) {
  const tab = state.tabs.find(t => t.path === path);
  if (tab?.dirty) {
    if (!confirm(`"${tab.name}" has unsaved changes. Close anyway?`)) return;
  }
  state.tabs = state.tabs.filter(t => t.path !== path);
  state.monacoModels.get(path)?.dispose();
  state.monacoModels.delete(path);
  state.viewStates.delete(path);

  if (state.activeTab === path) {
    state.activeTab = null;
    const next = state.tabs[state.tabs.length - 1];
    if (next) activateTab(next.path);
    else {
      dom.welcomeScreen.style.display  = '';
      dom.monacoContainer.style.display = 'none';
      dom.btnRun.disabled = true;
      if (state.editor) state.editor.setModel(null);
    }
  }
  renderTabs();
  saveProjectState();   // persist updated tab list
}

function markDirty(path) {
  const tab = state.tabs.find(t => t.path === path);
  if (tab && !tab.dirty) { tab.dirty = true; renderTabs(); updateStatusBar(); }
}

function markClean(path) {
  const tab = state.tabs.find(t => t.path === path);
  if (tab) { tab.dirty = false; renderTabs(); updateStatusBar(); }
}

function renderTabs() {
  dom.tabsContainer.innerHTML = '';
  for (const tab of state.tabs) {
    const el = document.createElement('div');
    el.className = `tab${tab.path === state.activeTab ? ' active' : ''}`;
    el.innerHTML = `
      <i class="fa-solid ${fileIcon(tab.name)} ti-icon" style="font-size:11px" aria-hidden="true"></i>
      <span class="tab-name">${tab.name}</span>
      ${tab.dirty ? '<span class="tab-dirty" aria-label="unsaved">●</span>' : ''}
      <button class="tab-close" aria-label="Close ${tab.name}"><i class="fa-solid fa-xmark" aria-hidden="true"></i></button>`;
    el.addEventListener('click', e => {
      if (!e.target.closest('.tab-close')) activateTab(tab.path);
    });
    el.querySelector('.tab-close').addEventListener('click', e => {
      e.stopPropagation(); closeTab(tab.path);
    });
    dom.tabsContainer.appendChild(el);
  }
}

function highlightTreeItem(path) {
  dom.treeRoot.querySelectorAll('.tree-item').forEach(el => {
    el.classList.toggle('active', el.dataset.path === path);
  });
}

// ── Save ──────────────────────────────────────────────────────────────────────
async function saveActiveFile() {
  if (!state.activeTab || !state.editor) return;
  const content = state.editor.getValue();
  try {
    await api('/api/fs/write', { method: 'POST', body: JSON.stringify({ path: state.activeTab, content }) });
    markClean(state.activeTab);
    toast('Saved', 'success', 1800);
  } catch (e) { toast(`Save failed: ${e.message}`, 'error'); }
}

// ── Run code (streaming) ──────────────────────────────────────────────────────
async function runActiveFile() {
  if (!state.activeTab || state.isRunning) return;
  await saveActiveFile();
  const tab = state.tabs.find(t => t.path === state.activeTab);
  if (!tab) return;

  state.isRunning = true;
  state.abortCtrl  = new AbortController();
  dom.btnRun.style.display  = 'none';
  dom.btnStop.style.display = '';
  showBottomPanel();
  switchBtab('output');
  appendOutput(`\n<span class="out-meta">▶ Running ${tab.name}…</span>\n`, true);

  const t0 = Date.now();
  let collectedStderr = '';

  try {
    const res = await fetch('/api/code/run/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: tab.path, language: tab.language }),
      signal: state.abortCtrl.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.ch === 'stdout') {
            appendOutput(`<span class="out-stdout">${escHtml(evt.text)}</span>`);
          } else if (evt.ch === 'stderr') {
            appendOutput(`<span class="out-stderr">${escHtml(evt.text)}</span>`);
            collectedStderr += evt.text;
          } else if (evt.done) {
            if (collectedStderr) state.lastError = collectedStderr;
            const elapsed = ((Date.now() - t0) / 1000).toFixed(2);
            const ok = evt.returncode === 0;
            appendOutput(`<span class="${ok ? 'out-ok' : 'out-err'}">${ok ? '✓' : '✗'} Exit ${evt.returncode} · ${elapsed}s</span>\n`);
          }
        } catch { /* partial JSON */ }
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      appendOutput(`<span class="out-err">Error: ${escHtml(e.message)}</span>\n`);
    }
  } finally {
    state.isRunning  = false;
    state.abortCtrl  = null;
    dom.btnRun.style.display  = '';
    dom.btnStop.style.display = 'none';
  }
}

function stopRun() {
  state.abortCtrl?.abort();
  dom.btnRun.style.display  = '';
  dom.btnStop.style.display = 'none';
  state.isRunning = false;
  appendOutput('<span class="out-err">— Stopped —</span>\n');
}

function appendOutput(html, clear = false) {
  if (clear) dom.outputPre.innerHTML = '';
  dom.outputPre.innerHTML += html;
  dom.outputPre.scrollTop = dom.outputPre.scrollHeight;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Bottom panel ──────────────────────────────────────────────────────────────
function switchBtab(name) {
  document.querySelectorAll('.btab').forEach(b => b.classList.toggle('active', b.dataset.btab === name));
  document.querySelectorAll('.btab-content').forEach(c => c.classList.toggle('active', c.id === `${name}Content`));
}

function showBottomPanel() {
  if (state.bottomCollapsed) toggleBottomPanel();
}

function toggleBottomPanel() {
  state.bottomCollapsed = !state.bottomCollapsed;
  dom.bottomPanel.classList.toggle('collapsed', state.bottomCollapsed);
  const icon = $('btnToggleBottom').querySelector('i');
  icon.className = `fa-solid ${state.bottomCollapsed ? 'fa-chevron-up' : 'fa-chevron-down'}`;
}

// ── Context menu ──────────────────────────────────────────────────────────────
function showContextMenu(e, path, isDir, el) {
  e.preventDefault();
  e.stopPropagation();
  state.contextTarget = { path, isDir, el };
  const cm = dom.contextMenu;
  $('ctx-open').style.display      = isDir ? 'none' : '';
  $('ctx-duplicate').style.display = isDir ? 'none' : '';
  cm.style.display = '';
  const x = Math.min(e.clientX, window.innerWidth  - cm.offsetWidth  - 4);
  const y = Math.min(e.clientY, window.innerHeight - cm.offsetHeight - 4);
  cm.style.left = x + 'px';
  cm.style.top  = y + 'px';
}

function hideContextMenu() { dom.contextMenu.style.display = 'none'; }

document.addEventListener('click', hideContextMenu);
document.addEventListener('contextmenu', e => {
  if (!dom.contextMenu.contains(e.target)) hideContextMenu();
});

$('ctx-open').addEventListener('click', () => {
  if (state.contextTarget?.path) openFile(state.contextTarget.path);
});

$('ctx-rename').addEventListener('click', () => {
  if (!state.contextTarget) return;
  const { path, isDir, el } = state.contextTarget;
  startInlineRename(el, path, isDir);
});

$('ctx-delete').addEventListener('click', async () => {
  if (!state.contextTarget) return;
  const { path, isDir } = state.contextTarget;
  const name = path.split(/[\\/]/).pop();
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try {
    await api('/api/fs/delete', { method: 'DELETE', body: JSON.stringify({ path }) });
    if (!isDir) closeTab(path);
    await refreshTree();
    toast(`Deleted "${name}"`, 'warn');
  } catch (e) { toast(`Delete failed: ${e.message}`, 'error'); }
});

$('ctx-new-file').addEventListener('click', async () => {
  if (!state.contextTarget) return;
  let dir = state.contextTarget.isDir
    ? state.contextTarget.path
    : state.contextTarget.path.replace(/[/\\][^/\\]+$/, '');
  const name = prompt('New file name:');
  if (!name) return;
  const fullPath = dir + '/' + name;
  try {
    await api('/api/fs/write', { method: 'POST', body: JSON.stringify({ path: fullPath, content: '' }) });
    await refreshTree();
    openFile(fullPath);
  } catch (e) { toast(e.message, 'error'); }
});

$('ctx-new-folder').addEventListener('click', async () => {
  if (!state.contextTarget) return;
  let dir = state.contextTarget.isDir
    ? state.contextTarget.path
    : state.contextTarget.path.replace(/[/\\][^/\\]+$/, '');
  const name = prompt('New folder name:');
  if (!name) return;
  try {
    await api('/api/fs/mkdir', { method: 'POST', body: JSON.stringify({ path: dir + '/' + name }) });
    await refreshTree();
    toast(`Folder created`, 'success');
  } catch (e) { toast(e.message, 'error'); }
});

$('ctx-copy-path').addEventListener('click', () => {
  if (!state.contextTarget) return;
  navigator.clipboard.writeText(state.contextTarget.path).then(() => toast('Path copied', 'info'));
});

$('ctx-reveal').addEventListener('click', async () => {
  if (!state.contextTarget) return;
  try {
    await api('/api/fs/reveal', { method: 'POST', body: JSON.stringify({ path: state.contextTarget.path }) });
  } catch (e) { toast(`Could not open explorer: ${e.message}`, 'error'); }
});

$('ctx-duplicate').addEventListener('click', async () => {
  if (!state.contextTarget) return;
  const { path, isDir } = state.contextTarget;
  if (isDir) { toast('Duplicate is only for files', 'warn'); return; }
  try {
    const res = await api('/api/fs/duplicate', { method: 'POST', body: JSON.stringify({ path }) });
    await refreshTree();
    toast(`Duplicated → ${res.new_path.split('/').pop()}`, 'success');
  } catch (e) { toast(`Duplicate failed: ${e.message}`, 'error'); }
});

$('ctx-move').addEventListener('click', () => {
  if (!state.contextTarget) return;
  openMoveModal();
});

// ── Move-to folder picker ──────────────────────────────────────────────────
function openMoveModal() {
  state.moveTargetDir = null;
  $('moveModalConfirm').disabled = true;
  $('moveModal').style.display = 'flex';
  _renderMoveFolderTree();
}
function closeMoveModal() { $('moveModal').style.display = 'none'; }

function _renderMoveFolderTree() {
  const container = $('moveFolderTree');
  container.innerHTML = '';
  if (!state.treeData) return;
  function renderNode(node, depth) {
    if (!node.is_dir) return;
    const row = document.createElement('div');
    row.className = 'move-folder-row';
    row.style.paddingLeft = (8 + depth * 14) + 'px';
    row.innerHTML = `<i class="fa-solid fa-folder" style="color:var(--accent-primary);margin-right:6px;font-size:11px"></i>${node.name}`;
    row.dataset.path = node.path;
    row.addEventListener('click', e => {
      e.stopPropagation();
      container.querySelectorAll('.move-folder-row').forEach(r => r.classList.remove('move-folder-selected'));
      row.classList.add('move-folder-selected');
      state.moveTargetDir = node.path;
      $('moveModalConfirm').disabled = false;
    });
    container.appendChild(row);
    if (node.children) node.children.forEach(c => renderNode(c, depth + 1));
  }
  // Add workspace root itself
  const root = { name: state.workspace.split(/[\\/]/).pop(), path: state.workspace, is_dir: true, children: state.treeData };
  renderNode(root, 0);
}

$('moveModalClose').addEventListener('click', closeMoveModal);
$('moveModalCancel').addEventListener('click', closeMoveModal);
$('moveModal').addEventListener('click', e => { if (e.target === $('moveModal')) closeMoveModal(); });

$('moveModalConfirm').addEventListener('click', async () => {
  if (!state.contextTarget || !state.moveTargetDir) return;
  const { path, isDir } = state.contextTarget;
  const name = path.split(/[\\/]/).pop();
  try {
    const res = await api('/api/fs/move', { method: 'POST', body: JSON.stringify({ src: path, dst_dir: state.moveTargetDir }) });
    if (!isDir) {
      // Update open tab path
      const tab = state.tabs.find(t => t.path === path);
      if (tab) {
        const newPath = res.new_path;
        const model = state.monacoModels.get(tab.path);
        if (model) { state.monacoModels.set(newPath, model); state.monacoModels.delete(tab.path); }
        tab.path = newPath;
        if (state.activeTab === path) state.activeTab = newPath;
        renderTabs();
      }
    }
    closeMoveModal();
    await refreshTree();
    toast(`Moved "${name}" → ${state.moveTargetDir.split(/[\\/]/).pop()}`, 'success');
  } catch (e) { toast(`Move failed: ${e.message}`, 'error'); }
});

// Inline rename
function startInlineRename(row, path, isDir) {
  const nameEl = row.querySelector('.ti-name');
  if (!nameEl) return;
  const oldName = nameEl.textContent;
  const input = document.createElement('input');
  input.className = 'tree-rename-input';
  input.value = oldName;
  nameEl.replaceWith(input);
  input.focus();
  input.select();

  const commit = async () => {
    const newName = input.value.trim();
    if (!newName || newName === oldName) { input.replaceWith(nameEl); return; }
    const dir = path.replace(/[/\\][^/\\]+$/, '');
    const newPath = dir + '/' + newName;
    try {
      await api('/api/fs/rename', { method: 'POST', body: JSON.stringify({ old_path: path, new_path: newPath }) });
      if (!isDir) {
        const tab = state.tabs.find(t => t.path === path);
        if (tab) { tab.path = newPath; tab.name = newName; }
        if (state.activeTab === path) state.activeTab = newPath;
        const model = state.monacoModels.get(path);
        if (model) { state.monacoModels.set(newPath, model); state.monacoModels.delete(path); }
        renderTabs();
      }
      await refreshTree();
    } catch (e) { toast(e.message, 'error'); input.replaceWith(nameEl); }
  };

  input.addEventListener('blur', commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { input.replaceWith(nameEl); }
  });
}

// ── Workspace modal ───────────────────────────────────────────────────────────
async function openWorkspaceModal() {
  const modal = $('wsModal');
  modal.style.display = 'flex';
  const rootsEl   = $('wsRoots');
  const recentEl  = $('wsRecent');
  const recentLbl = $('wsRecentLabel');
  rootsEl.innerHTML  = '';
  recentEl.innerHTML = '';

  try {
    const data = await api('/api/fs/roots');

    // Quick-open roots (Project Root + Home)
    for (const r of data.roots) {
      const btn = document.createElement('button');
      btn.className = 'ws-root-btn';
      btn.innerHTML = `
        <i class="fa-solid fa-folder ws-root-icon" aria-hidden="true"></i>
        <div>
          <div class="ws-root-label">${r.label}</div>
          <div class="ws-root-path">${r.path}</div>
        </div>`;
      btn.addEventListener('click', () => {
        modal.style.display = 'none';
        loadWorkspace(r.path);
      });
      rootsEl.appendChild(btn);
    }

    // Recent workspaces
    const recent = data.recent_workspaces || [];
    if (recent.length) {
      recentLbl.style.display = '';
      for (const r of recent) {
        const item = document.createElement('div');
        item.className = 'ws-recent-item';
        const ago = r.last_opened
          ? _timeAgo(r.last_opened)
          : '';
        item.innerHTML = `
          <i class="fa-solid fa-clock-rotate-left" aria-hidden="true"></i>
          <div style="flex:1;min-width:0">
            <div class="ws-recent-name">${escHtml(r.name || r.path.split('/').pop())}</div>
            <div class="ws-recent-path" title="${escHtml(r.path)}">${escHtml(r.path)}${ago ? ` · ${ago}` : ''}</div>
          </div>
          <button class="ws-recent-remove" title="Remove from recents" aria-label="Remove">
            <i class="fa-solid fa-xmark" aria-hidden="true"></i>
          </button>`;
        item.addEventListener('click', e => {
          if (e.target.closest('.ws-recent-remove')) return;
          modal.style.display = 'none';
          loadWorkspace(r.path);
        });
        item.querySelector('.ws-recent-remove').addEventListener('click', async e => {
          e.stopPropagation();
          const s = await api('/api/settings');
          s.recent_workspaces = (s.recent_workspaces || []).filter(w => w.path !== r.path);
          await api('/api/settings', { method: 'POST', body: JSON.stringify(s) });
          item.remove();
          if (!recentEl.children.length) recentLbl.style.display = 'none';
        });
        recentEl.appendChild(item);
      }
    } else {
      recentLbl.style.display = 'none';
    }

    $('wsCustomPath').value = '';
  } catch (e) { toast(`Modal error: ${e.message}`, 'error'); }
}

function _timeAgo(isoString) {
  try {
    const diff = Date.now() - new Date(isoString).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)  return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch { return ''; }
}

$('wsModalClose').addEventListener('click',   () => { $('wsModal').style.display = 'none'; });
dom.workspacePill.addEventListener('click',   openWorkspaceModal);
$('btnOpenFolder').addEventListener('click',  openWorkspaceModal);
$('wsCustomOpen').addEventListener('click',   () => {
  const p = $('wsCustomPath').value.trim();
  if (p) { $('wsModal').style.display = 'none'; loadWorkspace(p); }
});
$('wsCustomPath').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    const p = $('wsCustomPath').value.trim();
    if (p) { $('wsModal').style.display = 'none'; loadWorkspace(p); }
  }
});
$('wsBrowse').addEventListener('click', async () => {
  try {
    const res = await api('/api/fs/browse', { method: 'POST' });
    if (res.path) {
      $('wsCustomPath').value = res.path;
    }
  } catch (e) { toast(`Browse failed: ${e.message}`, 'warn'); }
});
$('wsModal').addEventListener('click', e => { if (e.target === $('wsModal')) $('wsModal').style.display = 'none'; });

// ── AI Chat ───────────────────────────────────────────────────────────────────
function addChatMessage(role, content = '', streaming = false) {
  const wrap = document.createElement('div');
  wrap.className = `chat-msg ${role}`;
  const label = document.createElement('div');
  label.className = 'chat-label';
  label.textContent = role === 'user' ? 'You' : 'AI';
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble' + (streaming ? ' streaming-cursor' : '');
  bubble.innerHTML = role === 'assistant' ? renderMarkdown(content) : escHtml(content);
  wrap.appendChild(label);
  wrap.appendChild(bubble);
  dom.chatMessages.appendChild(wrap);
  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
  return bubble;
}

/** Apply a code string to the active editor (replaces selection or full content). */
function applyCodeToEditor(code) {
  if (!state.editor) return toast('No file open', 'warn');
  const sel = state.editor.getSelection();
  if (sel && !sel.isEmpty()) {
    state.editor.executeEdits('ai-apply', [{ range: sel, text: code }]);
  } else {
    state.editor.setValue(code);
  }
  if (state.activeTab) markDirty(state.activeTab);
  toast('Applied to editor', 'success', 1800);
}

/** Copy code block content to clipboard. Called via inline onclick. */
function copyCodeBlock(btn) {
  const code = btn.closest('.code-block-wrap').querySelector('code').textContent;
  navigator.clipboard.writeText(code).then(() => toast('Copied', 'success', 1400));
}

/** Apply code block to active editor. Called via inline onclick. */
function applyCodeBlock(btn) {
  const code = btn.closest('.code-block-wrap').querySelector('code').textContent;
  applyCodeToEditor(code);
}

// ── File Write Card (FWC) helpers ─────────────────────────────────────────────

/** Toggle expand / collapse of a file write card. */
function toggleFwc(el) {
  el.closest('.fwc').classList.toggle('fwc-open');
}

/** Copy FWC code content to clipboard. */
function copyFwc(btn) {
  const code = btn.closest('.fwc').querySelector('code').textContent;
  navigator.clipboard.writeText(code).then(() => toast('Copied', 'success', 1400));
}

/** Apply FWC code to the active editor. */
function applyFwc(btn) {
  const code = btn.closest('.fwc').querySelector('code').textContent;
  applyCodeToEditor(code);
}

/** Markdown renderer with copy/apply buttons on code blocks. */
function renderMarkdown(text) {
  // Two-pass approach: extract special blocks first (before HTML-encoding),
  // then encode the remainder and apply markdown transforms.

  // Step 0: extract python-exec blocks → exec-card placeholders
  const execPlaceholders = [];
  let processed = text.replace(
    /```python-exec\n([\s\S]*?)```/gi,
    (_, code) => {
      const idx = execPlaceholders.length;
      const encoded = code.trimEnd()
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      execPlaceholders.push(
        `<div class="exec-card" data-exec-idx="${idx}">` +
        `<div class="exec-header">` +
        `<i class="fa-solid fa-terminal exec-icon" aria-hidden="true"></i>` +
        `<span class="exec-lang">python</span>` +
        `<span class="exec-status exec-pending"><i class="fa-solid fa-clock" aria-hidden="true"></i> Queued</span>` +
        `</div>` +
        `<pre class="exec-code"><code>${encoded}</code></pre>` +
        `<div class="exec-output" style="display:none"></div>` +
        `</div>`
      );
      return `\x00EXEC_BLOCK_${idx}\x00`;
    }
  );

  // Step 1: extract ### FILE: blocks before HTML-encoding so we can render them as
  // collapsed File Write Cards (FWC) — compact by default, expand on click.
  const filePlaceholders = [];
  processed = processed.replace(
    /(?:#{1,4}\s*)?FILE:\s*`?([^\n`*]+)`?\s*\n```([^\n]*)\n([\s\S]*?)```/gi,
    (_, fname, lang, code) => {
      const idx = filePlaceholders.length;
      const safeName = fname.trim();
      const safeLang = (lang || 'text').trim();
      const lineCount = code.trimEnd().split('\n').length;
      const encodedCode = code.trimEnd()
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      const safeNameHtml = safeName.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      const safeLangHtml = safeLang.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      // Determine if this file already exists in the workspace tree
      let resolvedPath = safeName;
      if (!resolvedPath.includes(':') && !resolvedPath.startsWith('/')) {
        resolvedPath = (state.workspace + '/' + resolvedPath).replace(/\\/g, '/');
      }
      resolvedPath = resolvedPath.replace(/\\/g, '/');
      const exists = state.treeFiles.has(resolvedPath);
      const statusClass = exists ? 'fwc-changed' : 'fwc-added';
      const statusLabel = exists ? 'Changed' : 'Added';
      const safeResolvedHtml = resolvedPath.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      filePlaceholders.push(
        `<div class="fwc" data-filename="${safeNameHtml}" data-filepath="${safeResolvedHtml}">` +
        `<div class="fwc-header" onclick="toggleFwc(this)">` +
        `<i class="fa-solid fa-chevron-right fwc-chevron" aria-hidden="true"></i>` +
        `<i class="fa-solid fa-file-code fwc-icon" aria-hidden="true"></i>` +
        `<span class="fwc-name">${safeNameHtml}</span>` +
        `<span class="fwc-lang">${safeLangHtml}</span>` +
        `<span class="fwc-lines">${lineCount} line${lineCount !== 1 ? 's' : ''}</span>` +
        `<span class="fwc-status ${statusClass}">${statusLabel}</span>` +
        `<div class="fwc-actions" onclick="event.stopPropagation()">` +
        `<button class="cb-btn" onclick="copyFwc(this)" title="Copy code"><i class="fa-solid fa-copy" aria-hidden="true"></i> Copy</button>` +
        `<button class="cb-btn cb-apply" onclick="applyFwc(this)" title="Apply to active file"><i class="fa-solid fa-file-import" aria-hidden="true"></i> Apply</button>` +
        `</div></div>` +
        `<div class="fwc-body"><pre><code>${encodedCode}</code></pre></div>` +
        `</div>`
      );
      return `\x00FILE_BLOCK_${idx}\x00`;
    }
  );

  // Step 2: HTML-encode the remainder and apply normal markdown transforms
  processed = processed
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<div class="code-block-wrap">` +
      `<div class="code-block-header">` +
      `<span class="code-lang">${lang || 'text'}</span>` +
      `<div class="code-block-actions">` +
      `<button class="cb-btn" onclick="copyCodeBlock(this)" title="Copy to clipboard"><i class="fa-solid fa-copy" aria-hidden="true"></i> Copy</button>` +
      `<button class="cb-btn cb-apply" onclick="applyCodeBlock(this)" title="Apply to active file"><i class="fa-solid fa-file-import" aria-hidden="true"></i> Apply</button>` +
      `</div></div>` +
      `<pre><code>${code.trimEnd()}</code></pre></div>`)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^#{1,3} (.+)$/gm, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');

  // Step 3: strip <br> tags adjacent to placeholders (they come from surrounding newlines
  // in the raw AI text and would leave blank lines above/below each card)
  processed = processed.replace(/(?:<br>\s*)+(\x00FILE_BLOCK_\d+\x00)/g, '$1');
  processed = processed.replace(/(\x00FILE_BLOCK_\d+\x00)(?:\s*<br>)+/g, '$1');

  // Step 4: restore file block placeholders
  filePlaceholders.forEach((html, idx) => {
    processed = processed.replace(`\x00FILE_BLOCK_${idx}\x00`, html);
  });

  // Step 4b: restore exec block placeholders (strip adjacent <br> first)
  processed = processed.replace(/(?:<br>\s*)+(\x00EXEC_BLOCK_\d+\x00)/g, '$1');
  processed = processed.replace(/(\x00EXEC_BLOCK_\d+\x00)(?:\s*<br>)+/g, '$1');
  execPlaceholders.forEach((html, idx) => {
    processed = processed.replace(`\x00EXEC_BLOCK_${idx}\x00`, html);
  });

  // Step 5: render agent continuation dividers (injected between passes)
  processed = processed.replace(
    /(?:<br>)*\x00AGENT_CONTINUE\x00(?:<br>)*/g,
    '<div class="agent-continue-divider"><i class="fa-solid fa-rotate" aria-hidden="true"></i> continued</div>'
  );

  return processed;
}

// ── Auto file writer ──────────────────────────────────────────────────────────
/**
 * Scan AI response text for ### FILE: markers and write those files.
 * Format expected:
 *   ### FILE: /path/to/file.ext
 *   ```lang
 *   ...contents...
 *   ```
 */
async function autoWriteFiles(text) {
  // Match many AI output styles:
  //   ### FILE: path/to/file.ext   FILE: path/to/file.ext   **FILE: ...**   #### FILE: ...
  const filePattern = /(?:#{1,4}\s*|\*{1,2})?FILE:\s*\*{0,2}`?([^\n`*]+)`?\*{0,2}\s*\n```[^\n]*\n([\s\S]*?)```/gi;
  const files = [];
  let match;
  while ((match = filePattern.exec(text)) !== null) {
    let filePath = match[1].trim();
    const content = match[2];
    if (filePath.startsWith('/')) {
      filePath = state.workspace + filePath;
    } else if (!filePath.includes(':') && !filePath.startsWith(state.workspace)) {
      filePath = state.workspace + '/' + filePath;
    }
    filePath = filePath.replace(/\\/g, '/');
    const isNew = !state.treeFiles.has(filePath); // true = file didn't exist → Added
    files.push({ path: filePath, content, isNew });
  }
  if (files.length === 0) return;

  let written = 0;
  for (const { path, content, isNew } of files) {
    try {
      await api('/api/fs/write', { method: 'POST', body: JSON.stringify({ path, content }) });
      written++;
      // Live-refresh any open tab for this file
      const openTab = state.tabs.find(t => t.path.replace(/\\/g, '/') === path);
      if (openTab) {
        const model = state.monacoModels.get(openTab.path);
        if (model) {
          model.setValue(content);
          markClean(openTab.path);
        }
      }
      // Update the matching FWC card in the chat UI
      const shortName = path.split('/').pop();
      let card = null;
      for (const c of document.querySelectorAll('.fwc')) {
        if (c.dataset.filepath === path) { card = c; break; }
        if (!card && c.dataset.filename === shortName) card = c;
      }
      if (card) {
        const badge = card.querySelector('.fwc-status');
        if (badge) {
          badge.className = 'fwc-status fwc-written';
          badge.innerHTML = `<i class="fa-solid fa-check" aria-hidden="true"></i> ${isNew ? 'Added' : 'Changed'}`;
        }
      }
    } catch (e) {
      toast(`Failed to write ${path.split('/').pop()}: ${e.message}`, 'error');
    }
  }

  if (written > 0) {
    await refreshTree();
    const names = files.slice(0, 3).map(f => f.path.split('/').pop()).join(', ');
    const extra = files.length > 3 ? ` +${files.length - 3} more` : '';
    toast(`Wrote ${written} file${written !== 1 ? 's' : ''}: ${names}${extra}`, 'success', 4000);
    if (files[0]) openFile(files[0].path);
  }

  // ── MOVE directives: ### MOVE: src → dst_dir/ (### prefix optional, → or -> accepted)
  const movePattern = /(?:#{1,4}\s*)?MOVE:\s*([^\n→\-]+?)\s*(?:→|->)\s*([^\n]+)/gi;
  let moveMatch;
  while ((moveMatch = movePattern.exec(text)) !== null) {
    let src = moveMatch[1].trim();
    let dstDir = moveMatch[2].trim();
    // Resolve relative paths against workspace
    if (!src.includes(':') && !src.startsWith('/')) src = state.workspace + '/' + src;
    if (!dstDir.includes(':') && !dstDir.startsWith('/')) dstDir = state.workspace + '/' + dstDir;
    src = src.replace(/\\/g, '/');
    dstDir = dstDir.replace(/\\/g, '/').replace(/\/$/, ''); // strip trailing slash
    try {
      const r = await api('/api/fs/move', { method: 'POST', body: JSON.stringify({ src, dst_dir: dstDir }) });
      // If the source was open in a tab, close old path and open new
      const oldTab = state.tabs.find(t => t.path.replace(/\\/g, '/') === src);
      if (oldTab) { closeTab(oldTab.path); openFile(r.new_path); }
      await refreshTree();
      const name = src.split('/').pop();
      toast(`Moved "${name}" → ${dstDir.split('/').pop()}`, 'success', 3000);
    } catch (e) {
      toast(`Move failed (${moveMatch[1].trim()}): ${e.message}`, 'error');
    }
  }

  // ── DELETE directives: ### DELETE: path (### prefix optional)
  const deletePattern = /(?:#{1,4}\s*)?DELETE:\s*([^\n]+)/gi;
  let deleteMatch;
  while ((deleteMatch = deletePattern.exec(text)) !== null) {
    let delPath = deleteMatch[1].trim();
    if (!delPath.includes(':') && !delPath.startsWith('/')) delPath = state.workspace + '/' + delPath;
    delPath = delPath.replace(/\\/g, '/');
    try {
      await api('/api/fs/delete', { method: 'DELETE', body: JSON.stringify({ path: delPath }) });
      closeTab(delPath);
      await refreshTree();
      toast(`Deleted "${delPath.split('/').pop()}"`, 'warn', 3000);
    } catch (e) {
      toast(`Delete failed (${deleteMatch[1].trim()}): ${e.message}`, 'error');
    }
  }
}

/**
 * Execute all python-exec blocks found in `text`.
 * Updates the matching exec-card inside `bubble` with live status + output.
 */
async function autoExecBlocks(text, bubble) {
  const pattern = /```python-exec\n([\s\S]*?)```/gi;
  let match;
  let idx = 0;
  while ((match = pattern.exec(text)) !== null) {
    const code = match[1];
    const card     = bubble?.querySelector(`.exec-card[data-exec-idx="${idx}"]`);
    const statusEl = card?.querySelector('.exec-status');
    const outputEl = card?.querySelector('.exec-output');

    if (statusEl) {
      statusEl.className = 'exec-status exec-running';
      statusEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Running…';
    }

    try {
      const res = await api('/api/fs/exec', {
        method: 'POST',
        body: JSON.stringify({ code, workspace: state.workspace }),
      });

      const out = (res.stdout || '').trimEnd();
      const err = (res.stderr || '').trimEnd();

      if (statusEl) {
        if (res.returncode === 0) {
          statusEl.className = 'exec-status exec-done';
          statusEl.innerHTML = '<i class="fa-solid fa-check" aria-hidden="true"></i> Done';
        } else {
          statusEl.className = 'exec-status exec-error';
          statusEl.innerHTML = '<i class="fa-solid fa-xmark" aria-hidden="true"></i> Error';
        }
      }
      if (outputEl && (out || err)) {
        outputEl.style.display = '';
        outputEl.className = 'exec-output' + (err && !out ? ' exec-output-err' : '');
        outputEl.textContent = out || err;
      }
      await refreshTree();
    } catch (e) {
      if (statusEl) {
        statusEl.className = 'exec-status exec-error';
        statusEl.innerHTML = `<i class="fa-solid fa-xmark" aria-hidden="true"></i> ${e.message}`;
      }
    }
    idx++;
  }
}

/**
 * Detect if an AI response was cut off before completing its task.
 * True when: (a) the response has an unclosed code fence, or
 *            (b) it ends with the explicit ### CONTINUE signal.
 */
function _isTruncated(text) {
  const t = text.trimEnd();
  if (/###\s*CONTINUE\s*$/i.test(t)) return true;
  const fences = (t.match(/```/g) || []).length;
  return fences % 2 !== 0; // odd = unclosed fence
}

/**
 * Agent loop: stream a chat response, detect truncation, and automatically
 * continue into the same bubble until the task is complete (max 8 passes).
 */
async function sendChat(text) {
  if (!text.trim()) return;
  dom.chatInput.value = '';
  state.chatHistory.push({ role: 'user', content: text });
  addChatMessage('user', text);
  const bubble = addChatMessage('assistant', '', true);

  let full = '';          // cumulative text rendered in bubble (all passes)
  let pass  = 0;
  const MAX_PASS = 8;

  try {
    while (pass <= MAX_PASS) {
      // Build messages for this pass (history already contains prior turns)
      const msgs = state.chatHistory.map(m => ({ role: m.role, content: m.content }));

      // Stream this pass; onChunk accumulates into outer `full`
      const passText = await streamSSE('/api/ai/chat', {
        messages:  msgs,
        model:     state.selectedModel || undefined,
        workspace: state.workspace || undefined,
      }, chunk => {
        full += chunk;
        bubble.innerHTML = renderMarkdown(full);
        bubble.classList.add('streaming-cursor');
        dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
      });

      bubble.classList.remove('streaming-cursor');

      // Push this pass's assistant text to history
      state.chatHistory.push({ role: 'assistant', content: passText });

      if (_isTruncated(passText) && pass < MAX_PASS) {
        // Strip the ### CONTINUE marker from display, add a visual divider
        full = full.replace(/\n?###\s*CONTINUE\s*$/i, '').trimEnd();
        full += '\n\n\x00AGENT_CONTINUE\x00\n\n';
        pass++;
        // Inject 'continue' into history so the next call resumes correctly
        state.chatHistory.push({ role: 'user', content: 'continue' });
        toast(`Task continues… (part ${pass + 1})`, 'info', 1800);
        bubble.classList.add('streaming-cursor'); // keep cursor while we loop
      } else {
        // All done — strip any stray ### CONTINUE at end
        full = full.replace(/\n?###\s*CONTINUE\s*$/i, '').trimEnd();
        break;
      }
    }

    bubble.innerHTML = renderMarkdown(full);
    saveCurrentThread();
    await autoWriteFiles(full);
    await autoExecBlocks(full, bubble);
  } catch (e) {
    bubble.classList.remove('streaming-cursor');
    bubble.innerHTML = `<span style="color:var(--error)">${escHtml(e.message)}</span>`;
  }
  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

async function explainSelection() {
  if (!state.editor) return toast('No file open', 'warn');
  const sel = state.editor.getModel()?.getValueInRange(state.editor.getSelection());
  const code = sel?.trim() || state.editor.getValue();
  if (!code) return;
  const tab = state.tabs.find(t => t.path === state.activeTab);
  const lang = tab?.language || 'code';
  const prompt = `Explain this ${lang} code:\n\`\`\`${lang}\n${code}\n\`\`\``;
  state.chatHistory.push({ role: 'user', content: prompt });
  addChatMessage('user', `Explain ${sel ? 'selection' : 'current file'} (${lang})`);
  const bubble = addChatMessage('assistant', '', true);
  let full = '';
  try {
    full = await streamSSE('/api/ai/explain', { code, language: lang, model: state.selectedModel || undefined },
      chunk => {
        full += chunk;
        bubble.innerHTML = renderMarkdown(full);
        dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
      });
    bubble.classList.remove('streaming-cursor');
    bubble.innerHTML = renderMarkdown(full);
    state.chatHistory.push({ role: 'assistant', content: full });
    saveCurrentThread();
  } catch (e) {
    bubble.classList.remove('streaming-cursor');
    bubble.innerHTML = `<span style="color:var(--error)">${escHtml(e.message)}</span>`;
  }
}

async function fixWithError() {
  if (!state.editor) return toast('No file open', 'warn');
  const code  = state.editor.getValue();
  const error = state.lastError || (await promptUser('Paste the error message:') || '');
  if (!error) return;
  const tab = state.tabs.find(t => t.path === state.activeTab);
  const lang = tab?.language || 'python';
  addChatMessage('user', `Fix this ${lang} error:\n\`\`\`\n${error}\n\`\`\``);
  const bubble = addChatMessage('assistant', '', true);
  let full = '';
  try {
    full = await streamSSE('/api/ai/fix', { code, error, language: lang, model: state.selectedModel || undefined },
      chunk => {
        full += chunk;
        bubble.innerHTML = renderMarkdown(full);
        dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
      });
    bubble.classList.remove('streaming-cursor');
    bubble.innerHTML = renderMarkdown(full);
    state.chatHistory.push({ role: 'assistant', content: full });
    saveCurrentThread();
  } catch (e) {
    bubble.classList.remove('streaming-cursor');
    bubble.innerHTML = `<span style="color:var(--error)">${escHtml(e.message)}</span>`;
  }
}

async function completeAtCursor() {
  if (!state.editor) return;
  const model = state.editor.getModel();
  if (!model) return;
  const pos    = state.editor.getPosition();
  const offset = model.getOffsetAt(pos);
  const full   = model.getValue();
  const before = full.slice(0, offset);
  const after  = full.slice(offset);
  const tab    = state.tabs.find(t => t.path === state.activeTab);
  const lang   = tab?.language || 'python';
  try {
    const result = await api('/api/ai/complete', {
      method: 'POST',
      body:   JSON.stringify({ code_before: before, code_after: after, language: lang, model: state.selectedModel || undefined }),
    });
    if (result.completion) {
      state.editor.executeEdits('ai-complete', [{
        range: new window.monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
        text:  result.completion,
      }]);
      toast('Completion inserted', 'success', 1500);
    }
  } catch (e) { toast(e.message, 'error'); }
}

async function refactorSelection() {
  if (!state.editor) return toast('No file open', 'warn');
  const sel  = state.editor.getModel()?.getValueInRange(state.editor.getSelection());
  const code = sel?.trim() || state.editor.getValue();
  if (!code) return;

  // Show refactor instructions modal
  const modal = $('refactorModal');
  modal.style.display = 'flex';
  $('refactorInstructions').focus();

  await new Promise(resolve => {
    const confirm = async () => {
      const instructions = $('refactorInstructions').value.trim();
      if (!instructions) { toast('Enter instructions', 'warn'); return; }
      modal.style.display = 'none';
      resolve(instructions);
      $('refactorConfirm').removeEventListener('click', confirm);
      $('refactorCancel').removeEventListener('click', cancel);
    };
    const cancel = () => {
      modal.style.display = 'none';
      resolve(null);
      $('refactorConfirm').removeEventListener('click', confirm);
      $('refactorCancel').removeEventListener('click', cancel);
    };
    $('refactorConfirm').addEventListener('click', confirm);
    $('refactorCancel').addEventListener('click', cancel);
    $('refactorModalClose').addEventListener('click', cancel, { once: true });
  }).then(async instructions => {
    if (!instructions) return;
    const tab  = state.tabs.find(t => t.path === state.activeTab);
    const lang = tab?.language || 'python';
    addChatMessage('user', `Refactor (${lang}): ${instructions}`);
    const bubble = addChatMessage('assistant', '', true);
    let full = '';
    try {
      full = await streamSSE('/api/ai/refactor', { code, instructions, language: lang, model: state.selectedModel || undefined },
        chunk => {
          full += chunk;
          bubble.innerHTML = renderMarkdown(full);
          dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
        });
      bubble.classList.remove('streaming-cursor');
      bubble.innerHTML = renderMarkdown(full);
      state.chatHistory.push({ role: 'assistant', content: full });
      saveCurrentThread();
    } catch (e) {
      bubble.classList.remove('streaming-cursor');
      bubble.innerHTML = `<span style="color:var(--error)">${escHtml(e.message)}</span>`;
    }
  });
}

function promptUser(msg) {
  return new Promise(resolve => resolve(window.prompt(msg) || null));
}

// ── File palette (Ctrl+P) ─────────────────────────────────────────────────────
let _paletteFiles = [];
let _paletteActive = 0;

function _buildPaletteIndex() {
  const files = [];
  function walk(node) {
    if (!node) return;
    if (node.type === 'file') {
      const rel = node.path.replace(state.workspace, '').replace(/^[/\\]/, '').replace(/\\/g, '/');
      files.push({ path: node.path, name: node.name, rel });
    } else if (node.children) {
      node.children.forEach(walk);
    }
  }
  walk(state.treeData);
  _paletteFiles = files;
}

function _fuzzyMatch(str, query) {
  if (!query) return { match: true, score: 100 };
  const s = str.toLowerCase();
  const q = query.toLowerCase();
  // exact substring gets highest score
  if (s.includes(q)) return { match: true, score: 200 + (s.length - q.length) * -1 };
  let si = 0, qi = 0, score = 0;
  while (si < s.length && qi < q.length) {
    if (s[si] === q[qi]) { score++; qi++; }
    si++;
  }
  return { match: qi === q.length, score };
}

function openFilePalette() {
  _buildPaletteIndex();
  const el = $('filePalette');
  el.style.display = 'flex';
  const input = $('paletteInput');
  input.value = '';
  _paletteActive = 0;
  _renderPaletteResults('');
  input.focus();
}

function closeFilePalette() {
  $('filePalette').style.display = 'none';
}

function _renderPaletteResults(query) {
  const container = $('paletteResults');
  const results = _paletteFiles
    .map(f => ({ ...f, ..._fuzzyMatch(f.rel || f.name, query) }))
    .filter(f => f.match)
    .sort((a, b) => b.score - a.score)
    .slice(0, 30);

  if (!results.length) {
    container.innerHTML = `<div class="palette-empty">${query ? 'No files match' : 'No files in workspace'}</div>`;
    return;
  }
  container.innerHTML = '';
  results.forEach((f, i) => {
    const item = document.createElement('div');
    item.className = `palette-item${i === 0 ? ' active' : ''}`;
    item.dataset.path = f.path;
    item.setAttribute('role', 'option');
    item.innerHTML =
      `<i class="fa-solid ${fileIcon(f.name)} ti-icon palette-item-icon" aria-hidden="true"></i>` +
      `<span class="palette-item-name">${escHtml(f.name)}</span>` +
      `<span class="palette-item-path">${escHtml(f.rel || '')}</span>`;
    item.addEventListener('click', () => { closeFilePalette(); openFile(f.path); });
    item.addEventListener('mouseenter', () => {
      container.querySelectorAll('.palette-item').forEach((el, j) => el.classList.toggle('active', j === i));
      _paletteActive = i;
    });
    container.appendChild(item);
  });
  _paletteActive = 0;
}

$('paletteInput').addEventListener('input', e => _renderPaletteResults(e.target.value));
$('paletteInput').addEventListener('keydown', e => {
  const items = $('paletteResults').querySelectorAll('.palette-item');
  if (!items.length) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _paletteActive = Math.min(_paletteActive + 1, items.length - 1);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _paletteActive = Math.max(_paletteActive - 1, 0);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const active = items[_paletteActive];
    if (active) { closeFilePalette(); openFile(active.dataset.path); }
    return;
  } else if (e.key === 'Escape') {
    e.preventDefault(); closeFilePalette(); return;
  } else return;
  items.forEach((el, i) => el.classList.toggle('active', i === _paletteActive));
  items[_paletteActive]?.scrollIntoView({ block: 'nearest' });
});
$('filePalette').addEventListener('click', e => { if (e.target === $('filePalette')) closeFilePalette(); });

// ── Status bar ────────────────────────────────────────────────────────────────
function updateStatusBar() {
  if (!state.editor) return;
  const pos = state.editor.getPosition();
  if (pos) $('sbPos').textContent = `Ln ${pos.lineNumber}, Col ${pos.column}`;
  const tab = state.tabs.find(t => t.path === state.activeTab);
  const lang = tab?.language || '';
  $('sbLang').textContent = lang ? (lang.charAt(0).toUpperCase() + lang.slice(1)) : '—';
  $('sbDirty').style.display = tab?.dirty ? '' : 'none';
}

async function updateGitBranch() {
  try {
    const data = await api(`/api/git/branch?workspace=${encodeURIComponent(state.workspace || '')}`);
    const branch = data.branch;
    $('sbBranchText').textContent = branch || 'detached';
    $('sbBranch').style.display = branch ? '' : 'none';
  } catch {
    $('sbBranch').style.display = 'none';
  }
}

// ── Project context notes ─────────────────────────────────────────────────────
async function loadContextNotes() {
  if (!state.workspace) return;
  try {
    const proj = await api(`/api/project?workspace=${encodeURIComponent(state.workspace)}`);
    $('contextNotes').value = proj.ai_context || '';
  } catch { /* best-effort */ }
}

async function saveContextNotes() {
  if (!state.workspace) return;
  try {
    await api('/api/project', {
      method: 'POST',
      body: JSON.stringify({ workspace: state.workspace, ai_context: $('contextNotes').value.trim() }),
    });
    toast('Notes saved', 'success', 1500);
  } catch (e) { toast(`Save failed: ${e.message}`, 'error'); }
}

$('btnToggleContext').addEventListener('click', () => {
  const body = $('contextBody');
  const chevron = $('contextChevron');
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  chevron.classList.toggle('open', !open);
  $('btnToggleContext').setAttribute('aria-expanded', String(!open));
});
$('btnSaveContext').addEventListener('click', saveContextNotes);
$('contextNotes').addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); saveContextNotes(); }
});

// ── Chat threads ──────────────────────────────────────────────────────────────
function _threadWs() { return encodeURIComponent(state.workspace || ''); }

/** Render thread list into #threadList. */
function _renderThreadList(threads) {
  const container = $('threadList');
  if (!threads.length) {
    container.innerHTML = '<div class="thread-empty">No threads yet</div>';
    return;
  }
  container.innerHTML = '';
  threads.forEach(t => {
    const item = document.createElement('div');
    item.className = `thread-item${t.id === state.currentThreadId ? ' active' : ''}`;
    item.dataset.id = t.id;
    item.setAttribute('role', 'option');
    item.setAttribute('aria-selected', String(t.id === state.currentThreadId));

    const dateStr = t.updated_at ? _timeAgo(t.updated_at) : '';
    item.innerHTML =
      `<i class="fa-solid fa-comments" aria-hidden="true"></i>` +
      `<span class="thread-item-name" title="${escHtml(t.name)}">${escHtml(t.name)}</span>` +
      `<span class="thread-item-count">${t.message_count || 0}</span>` +
      (dateStr ? `<span class="thread-date">${dateStr}</span>` : '') +
      `<button class="thread-delete" data-id="${t.id}" title="Delete thread" aria-label="Delete thread">` +
        `<i class="fa-solid fa-trash" aria-hidden="true"></i></button>`;

    // Switch to this thread on click
    item.addEventListener('click', async e => {
      if (e.target.closest('.thread-delete')) return;
      await switchThread(t.id);
      closeThreadList();
    });
    // Double-click name → inline rename
    item.querySelector('.thread-item-name').addEventListener('dblclick', e => {
      e.stopPropagation();
      _startThreadRename(t.id, item.querySelector('.thread-item-name'));
    });
    // Delete button
    item.querySelector('.thread-delete').addEventListener('click', async e => {
      e.stopPropagation();
      await deleteThread(t.id);
    });
    container.appendChild(item);
  });
}

/** Load thread list from server (returns array). */
async function _fetchThreads() {
  try {
    const data = await api(`/api/threads?workspace=${_threadWs()}`);
    return data.threads || [];
  } catch { return []; }
}

/** Refresh thread list UI without switching thread. */
async function refreshThreadList() {
  const threads = await _fetchThreads();
  _renderThreadList(threads);
  return threads;
}

/** Open thread list dropdown. */
function openThreadList() {
  $('threadList').style.display = '';
  $('threadChevron').classList.add('open');
  refreshThreadList();
}

function closeThreadList() {
  $('threadList').style.display = 'none';
  $('threadChevron').classList.remove('open');
}

function toggleThreadList() {
  $('threadList').style.display === 'none' ? openThreadList() : closeThreadList();
}

/** Load messages from a thread into the chat panel. */
async function loadThread(id) {
  try {
    const data = await api(`/api/threads/${id}?workspace=${_threadWs()}`);
    state.currentThreadId = id;
    $('threadName').textContent = data.name || 'Untitled';
    dom.chatMessages.innerHTML = '';
    state.chatHistory = [];
    for (const msg of (data.messages || [])) {
      const bubble = addChatMessage(msg.role, '', false);
      bubble.innerHTML = msg.role === 'assistant'
        ? renderMarkdown(msg.content)
        : escHtml(msg.content);
      state.chatHistory.push({ role: msg.role, content: msg.content });
    }
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    // Update highlight in open list
    document.querySelectorAll('.thread-item').forEach(el =>
      el.classList.toggle('active', el.dataset.id === id));
  } catch (e) { toast(`Failed to load thread: ${e.message}`, 'error'); }
}

/** Save current chat history to the active thread (silently). */
async function saveCurrentThread() {
  if (!state.currentThreadId || !state.workspace) return;
  try {
    await api('/api/threads', {
      method: 'POST',
      body: JSON.stringify({
        workspace: state.workspace,
        id:        state.currentThreadId,
        messages:  state.chatHistory,
      }),
    });
    // Refresh count in open list
    if ($('threadList').style.display !== 'none') refreshThreadList();
  } catch { /* best-effort */ }
}

/** Create a new thread and switch to it. */
async function createThread(name = 'New Chat') {
  try {
    const data = await api('/api/threads', {
      method: 'POST',
      body: JSON.stringify({ workspace: state.workspace, name, messages: [] }),
    });
    state.currentThreadId = data.id;
    $('threadName').textContent = data.name;
    dom.chatMessages.innerHTML = '';
    state.chatHistory = [];
    closeThreadList();
    toast(`Thread "${data.name}" created`, 'success', 1800);
  } catch (e) { toast(`Could not create thread: ${e.message}`, 'error'); }
}

/** Switch to an existing thread (saves current first). */
async function switchThread(id) {
  if (id === state.currentThreadId) return;
  await saveCurrentThread();
  await loadThread(id);
}

/** Delete a thread. If it was active, switch to another or create fresh. */
async function deleteThread(id) {
  if (!confirm('Delete this thread? This cannot be undone.')) return;
  await api(`/api/threads/${id}?workspace=${_threadWs()}`, { method: 'DELETE' });
  if (id === state.currentThreadId) {
    state.currentThreadId = null;
    dom.chatMessages.innerHTML = '';
    state.chatHistory = [];
    $('threadName').textContent = '—';
    const threads = await _fetchThreads();
    if (threads.length) await loadThread(threads[0].id);
    else await createThread('General');
  }
  await refreshThreadList();
}

/** Inline rename for a thread item. */
function _startThreadRename(id, nameEl) {
  const prev = nameEl.textContent;
  const input = document.createElement('input');
  input.className = 'thread-rename-input';
  input.value = prev;
  nameEl.replaceWith(input);
  input.focus(); input.select();

  const commit = async () => {
    const name = input.value.trim() || prev;
    try {
      await api('/api/threads', {
        method: 'POST',
        body: JSON.stringify({ workspace: state.workspace, id, name }),
      });
      if (id === state.currentThreadId) $('threadName').textContent = name;
    } catch { /* ignore */ }
    await refreshThreadList();
  };
  input.addEventListener('blur', commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.replaceWith(nameEl); }
  });
}

/** Called once when workspace loads — ensure there's always at least one thread. */
async function initThreads() {
  const threads = await _fetchThreads();
  _renderThreadList(threads);
  if (threads.length) {
    await loadThread(threads[0].id);
  } else {
    await createThread('General');
  }
}

// Thread bar wiring
$('btnThreadPicker').addEventListener('click', toggleThreadList);
$('btnNewThread').addEventListener('click', async () => {
  const name = window.prompt('Thread name:', 'New Chat');
  if (name !== null) await createThread(name.trim() || 'New Chat');
});
// Close thread list when clicking outside
document.addEventListener('click', e => {
  if (!$('threadBar').contains(e.target) && !$('threadList').contains(e.target)) {
    closeThreadList();
  }
});

// ── Sidebar toggles ───────────────────────────────────────────────────────────
function toggleFileTree() {
  dom.fileTree.classList.toggle('collapsed');
  $('btnToggleTree').classList.toggle('active', !dom.fileTree.classList.contains('collapsed'));
}

function toggleAIPanel() {
  dom.aiPanel.classList.toggle('collapsed');
  $('btnToggleAI').classList.toggle('active', !dom.aiPanel.classList.contains('collapsed'));
}

// ── Toolbar buttons ───────────────────────────────────────────────────────────
$('btnToggleTree').addEventListener('click', toggleFileTree);
$('btnToggleAI').addEventListener('click',   toggleAIPanel);
$('btnCloseAI').addEventListener('click',    () => { dom.aiPanel.classList.add('collapsed'); $('btnToggleAI').classList.remove('active'); });
$('btnRefreshTree').addEventListener('click',() => refreshTree());
$('btnClearChat').addEventListener('click',  () => { dom.chatMessages.innerHTML = ''; state.chatHistory = []; });
$('btnClearOutput').addEventListener('click',() => { dom.outputPre.innerHTML = ''; });
$('btnToggleBottom').addEventListener('click', toggleBottomPanel);
$('btnRun').addEventListener('click',   runActiveFile);
$('btnStop').addEventListener('click',  stopRun);
$('btnNewTab').addEventListener('click', () => { $('wsModal').style.display = 'flex'; });
$('btnNewFileWelcome').addEventListener('click', async () => {
  const name = window.prompt('File name:', 'untitled.py');
  if (!name) return;
  const path = state.workspace + '/' + name;
  try {
    await api('/api/fs/write', { method: 'POST', body: JSON.stringify({ path, content: '' }) });
    await refreshTree();
    openFile(path);
  } catch (e) { toast(e.message, 'error'); }
});
$('btnNewFile').addEventListener('click', async () => {
  const name = window.prompt('File name:', 'untitled.py');
  if (!name) return;
  const path = state.workspace + '/' + name;
  try {
    await api('/api/fs/write', { method: 'POST', body: JSON.stringify({ path, content: '' }) });
    await refreshTree();
    openFile(path);
  } catch (e) { toast(e.message, 'error'); }
});
$('btnNewFolder').addEventListener('click', async () => {
  const name = window.prompt('Folder name:');
  if (!name) return;
  try {
    await api('/api/fs/mkdir', { method: 'POST', body: JSON.stringify({ path: state.workspace + '/' + name }) });
    await refreshTree();
  } catch (e) { toast(e.message, 'error'); }
});

$('btnExplain').addEventListener('click',  explainSelection);
$('btnFix').addEventListener('click',      fixWithError);
$('btnComplete').addEventListener('click', completeAtCursor);
$('btnRefactor').addEventListener('click', refactorSelection);

// Chat send
$('btnSendChat').addEventListener('click', () => sendChat(dom.chatInput.value));
dom.chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(dom.chatInput.value); }
});

// Bottom tabs
document.querySelectorAll('.btab').forEach(b => b.addEventListener('click', () => switchBtab(b.dataset.btab)));

// Model selector — save selection to localStorage
dom.modelSel.addEventListener('change', () => { state.selectedModel = dom.modelSel.value; saveSettings(); });

// Refactor modal close
$('refactorModalClose').addEventListener('click', () => { $('refactorModal').style.display = 'none'; });
$('refactorModal').addEventListener('click', e => { if (e.target === $('refactorModal')) $('refactorModal').style.display = 'none'; });
$('refactorInstructions').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); $('refactorConfirm').click(); } });

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;

  if (e.ctrlKey || e.metaKey) {
    switch (e.key) {
      case 's':  e.preventDefault(); saveActiveFile();  break;
      case 'Enter': e.preventDefault(); runActiveFile(); break;
      case '/':  e.preventDefault(); toggleAIPanel();   break;
      case 'b':  e.preventDefault(); toggleFileTree();  break;
      case 'k':  e.preventDefault(); dom.chatInput.focus(); break;
      case 'p':  e.preventDefault(); openFilePalette(); break;
      case 'w':  e.preventDefault(); if (state.activeTab) closeTab(state.activeTab); break;
      case 'Tab':
        if (state.tabs.length > 1) {
          e.preventDefault();
          const idx  = state.tabs.findIndex(t => t.path === state.activeTab);
          const next = state.tabs[(idx + 1) % state.tabs.length];
          activateTab(next.path);
        }
        break;
    }
    if (e.shiftKey) {
      switch (e.key) {
        case 'E': e.preventDefault(); explainSelection();  break;
        case 'F': e.preventDefault(); fixWithError();      break;
      }
    }
  }
});

// ── Resize handles ────────────────────────────────────────────────────────────
function makeResizable(handle, getEl, getCssVar, dir) {
  let dragging = false, start = 0, startW = 0;
  handle.addEventListener('mousedown', e => {
    dragging = true; start = e.clientX; startW = getEl().offsetWidth;
    handle.classList.add('dragging');
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const delta = dir === 'left' ? e.clientX - start : start - e.clientX;
    const newW  = Math.max(120, Math.min(500, startW + delta));
    document.documentElement.style.setProperty(getCssVar(), newW + 'px');
    if (state.editor) state.editor.layout();
  });
  document.addEventListener('mouseup', () => {
    if (dragging) { dragging = false; handle.classList.remove('dragging'); }
  });
}
makeResizable($('resizeLeft'),  () => dom.fileTree, () => '--filetree-w', 'left');
makeResizable($('resizeRight'), () => dom.aiPanel,  () => '--aipanel-w',  'right');

// Bottom panel resize
let bottomDragging = false, bottomStart = 0, bottomStartH = 0;
document.querySelector('.bottom-tabs').addEventListener('mousedown', e => {
  if (e.target.closest('button')) return;
  bottomDragging = true; bottomStart = e.clientY; bottomStartH = dom.bottomPanel.offsetHeight;
  e.preventDefault();
});
document.addEventListener('mousemove', e => {
  if (!bottomDragging) return;
  const newH = Math.max(32, Math.min(600, bottomStartH - (e.clientY - bottomStart)));
  document.documentElement.style.setProperty('--bottom-h', newH + 'px');
  if (state.editor) state.editor.layout();
});
document.addEventListener('mouseup', () => { bottomDragging = false; });

// ── Monaco Editor init ────────────────────────────────────────────────────────
function initMonaco() {
  return new Promise(resolve => {
    window.require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' } });
    window.require(['vs/editor/editor.main'], () => {
      const monaco = window.monaco;

      monaco.editor.defineTheme('aethvion-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [
          { token: '',                   background: '09090b', foreground: 'f8fafc' },
          { token: 'comment',            foreground: '52525b', fontStyle: 'italic' },
          { token: 'keyword',            foreground: '818cf8' },
          { token: 'string',             foreground: 'a3e635' },
          { token: 'number',             foreground: 'fb923c' },
          { token: 'type',               foreground: '67e8f9' },
          { token: 'function',           foreground: 'fbbf24' },
          { token: 'variable',           foreground: 'f8fafc' },
          { token: 'delimiter',          foreground: 'a1a1aa' },
        ],
        colors: {
          'editor.background':             '#09090b',
          'editor.foreground':             '#f8fafc',
          'editor.lineHighlightBackground':'#18181b',
          'editor.selectionBackground':    '#6366f133',
          'editorLineNumber.foreground':   '#3f3f46',
          'editorLineNumber.activeForeground': '#a1a1aa',
          'editorCursor.foreground':       '#818cf8',
          'editorIndentGuide.background':  '#27272a',
          'editorIndentGuide.activeBackground': '#3f3f46',
          'editor.findMatchBackground':    '#6366f150',
          'editor.findMatchHighlightBackground': '#6366f125',
          'editorWidget.background':       '#0f0f13',
          'editorWidget.border':           '#27272a',
          'editorSuggestWidget.background':'#0f0f13',
          'editorSuggestWidget.border':    '#3f3f46',
          'editorSuggestWidget.selectedBackground': '#6366f133',
          'input.background':              '#18181b',
          'input.border':                  '#3f3f46',
          'scrollbarSlider.background':    '#3f3f4680',
          'scrollbarSlider.hoverBackground':'#6366f160',
        },
      });

      const editor = monaco.editor.create(dom.monacoContainer, {
        theme:               'aethvion-dark',
        fontSize:            13,
        fontFamily:          "'JetBrains Mono', 'Consolas', monospace",
        fontLigatures:       true,
        lineNumbers:         'on',
        minimap:             { enabled: true, scale: 1 },
        scrollBeyondLastLine: false,
        wordWrap:            'off',
        tabSize:             4,
        insertSpaces:        true,
        renderWhitespace:    'selection',
        smoothScrolling:     true,
        cursorBlinking:      'smooth',
        cursorSmoothCaretAnimation: 'on',
        bracketPairColorization: { enabled: true },
        formatOnPaste:       true,
        suggest:             { showMethods: true, showFunctions: true, showKeywords: true },
        quickSuggestions:    true,
        padding:             { top: 8, bottom: 8 },
      });

      state.editor = editor;
      window._editor = editor;

      // Ctrl+S inside Monaco
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveActiveFile);
      // Ctrl+Enter inside Monaco
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, runActiveFile);
      // Ctrl+Space → AI complete
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Space, completeAtCursor);
      // Ctrl+P → file palette (override Monaco's default command palette)
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyP, openFilePalette);

      // Update status bar on cursor move
      editor.onDidChangeCursorPosition(() => updateStatusBar());

      // Layout on container resize
      new ResizeObserver(() => editor.layout()).observe(dom.monacoContainer);

      resolve(editor);
    });
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  await initMonaco();
  // Load providers and last workspace in parallel; loadWorkspace() reads /api/fs/roots
  // which now returns the persisted last_workspace
  await Promise.all([loadProviders(), loadWorkspace()]);
  toast('Aethvion Code ready', 'success', 2000);
})();

// Save on page unload (tab close / navigation)
window.addEventListener('beforeunload', () => { saveProjectState(); });

// ── Expose inline-onclick handlers to global scope (required for type="module") ──
// Functions used in innerHTML-injected onclick attributes must be on window.
Object.assign(window, {
  toggleFwc, copyFwc, applyFwc,
  copyCodeBlock, applyCodeBlock,
});
