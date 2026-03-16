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
  selectedModel:    '',
  isRunning:        false,
  lastError:        '',       // last stderr output (used by Fix)
  treeExpanded:     new Set(),
  contextTarget:    null,     // {path, isDir, el}
  treeData:         null,
  abortCtrl:        null,     // for cancelling run
  bottomCollapsed:  false,
  editor:           null,
};

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
async function loadProviders() {
  try {
    const data = await api('/api/providers');
    dom.modelSel.innerHTML = '';
    if (!data.available || !data.models.length) {
      dom.modelSel.innerHTML = '<option value="">No AI providers</option>';
      return;
    }
    for (const m of data.models) {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = `${m.id} (${m.provider})`;
      dom.modelSel.appendChild(opt);
    }
    state.selectedModel = data.models[0].id;
  } catch { dom.modelSel.innerHTML = '<option value="">No providers</option>'; }
}

// ── Workspace ─────────────────────────────────────────────────────────────────
async function loadWorkspace(path = '') {
  try {
    if (!path) {
      const roots = await api('/api/fs/roots');
      path = roots.workspace;
    }
    state.workspace = path;
    const short = path.split(/[\\/]/).slice(-2).join('/');
    dom.workspaceLabel.textContent = short;
    dom.workspaceLabel.title = path;
    await refreshTree(path);
  } catch (e) { toast(`Workspace error: ${e.message}`, 'error'); }
}

// ── File tree ─────────────────────────────────────────────────────────────────
async function refreshTree(path = state.workspace) {
  try {
    const data = await api(`/api/fs/tree?path=${encodeURIComponent(path)}`);
    state.treeData = data;
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
function openFile(path) {
  const existing = state.tabs.find(t => t.path === path);
  if (existing) {
    activateTab(path);
    return;
  }
  fetch(`/api/fs/read?path=${encodeURIComponent(path)}`)
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
      activateTab(data.path);
      highlightTreeItem(data.path);
    })
    .catch(e => toast(`Cannot open file: ${e.message}`, 'error'));
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
}

function markDirty(path) {
  const tab = state.tabs.find(t => t.path === path);
  if (tab && !tab.dirty) { tab.dirty = true; renderTabs(); }
}

function markClean(path) {
  const tab = state.tabs.find(t => t.path === path);
  if (tab) { tab.dirty = false; renderTabs(); }
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

// ── Run code ──────────────────────────────────────────────────────────────────
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

  try {
    const result = await api('/api/code/run', {
      method: 'POST',
      body: JSON.stringify({ path: tab.path, language: tab.language }),
    });

    if (result.stdout) appendOutput(`<span class="out-stdout">${escHtml(result.stdout)}</span>`);
    if (result.stderr) {
      appendOutput(`<span class="out-stderr">${escHtml(result.stderr)}</span>`);
      state.lastError = result.stderr;
    }
    const ok = result.returncode === 0;
    appendOutput(`<span class="${ok ? 'out-ok' : 'out-err'}">${ok ? '✓' : '✗'} Exit ${result.returncode} · ${result.elapsed}s</span>\n`);
  } catch (e) {
    appendOutput(`<span class="out-err">Error: ${escHtml(e.message)}</span>\n`);
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
  $('ctx-open').style.display = isDir ? 'none' : '';
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
  const rootsEl = $('wsRoots');
  rootsEl.innerHTML = '';
  try {
    const data = await api('/api/fs/roots');
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
    $('wsCustomPath').value = data.workspace;
  } catch {}
}

$('wsModalClose').addEventListener('click',   () => { $('wsModal').style.display = 'none'; });
dom.workspacePill.addEventListener('click',   openWorkspaceModal);
$('btnOpenFolder').addEventListener('click',  openWorkspaceModal);
$('wsCustomOpen').addEventListener('click',   () => {
  const p = $('wsCustomPath').value.trim();
  if (p) { $('wsModal').style.display = 'none'; loadWorkspace(p); }
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

/** Minimal markdown renderer (code blocks, inline code, bold, italic, headings) */
function renderMarkdown(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_,lang,code) =>
      `<pre><code>${code.trimEnd()}</code></pre>`)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^#{1,3} (.+)$/gm, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

async function sendChat(text) {
  if (!text.trim()) return;
  dom.chatInput.value = '';
  state.chatHistory.push({ role: 'user', content: text });
  addChatMessage('user', text);
  const bubble = addChatMessage('assistant', '', true);
  let full = '';
  try {
    full = await streamSSE('/api/ai/chat', {
      messages: state.chatHistory.map(m => ({ role: m.role, content: m.content })),
      model: state.selectedModel || undefined,
    }, chunk => {
      full += chunk;
      bubble.innerHTML = renderMarkdown(full);
      bubble.classList.add('streaming-cursor');
      dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    });
    bubble.classList.remove('streaming-cursor');
    bubble.innerHTML = renderMarkdown(full);
    state.chatHistory.push({ role: 'assistant', content: full });
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
    } catch (e) {
      bubble.classList.remove('streaming-cursor');
      bubble.innerHTML = `<span style="color:var(--error)">${escHtml(e.message)}</span>`;
    }
  });
}

function promptUser(msg) {
  return new Promise(resolve => resolve(window.prompt(msg) || null));
}

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

// Model selector
dom.modelSel.addEventListener('change', () => { state.selectedModel = dom.modelSel.value; });

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

      // Layout on container resize
      new ResizeObserver(() => editor.layout()).observe(dom.monacoContainer);

      resolve(editor);
    });
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  await initMonaco();
  await Promise.all([loadProviders(), loadWorkspace()]);
  toast('Aethvion Code ready', 'success', 2000);
})();
