/**
 * app.js — Aethvion VTuber main application entry point
 */
import { state, setMode, selectLayer, selectBone, resetParams, markDirty, markClean } from './state.js';
import * as api from './api.js';
import {
  initRenderer, loadModel, fitToScreen, setZoom, panBy,
  canvasToScreen, screenToCanvas, captureBoneBindPoses,
} from './engine/renderer.js';
import {
  meshToolActivate, meshToolDeactivate, setMeshTool, drawMesh,
} from './tools/mesh-tool.js';
import {
  boneToolActivate, boneToolDeactivate, setBoneTool, drawBones,
} from './tools/bone-tool.js';
import {
  weightToolActivate, weightToolDeactivate,
} from './tools/weight-tool.js';
import {
  renderLayerPanel, renderBonePanel, renderParamPanel, renderInspector,
  showLoading, hideLoading, toast, setStatus,
} from './ui/panels.js';

// ── Init ───────────────────────────────────────────────────────────
const canvas = document.getElementById('mainCanvas');
const overlaysvg = document.getElementById('overlaysvg');

const pixiApp = initRenderer(canvas);
window._pixiApp = pixiApp;

// Populate provider/model selectors
api.getProviders().then(data => {
  const chatSel = document.getElementById('chatModelSel');
  const imgSel  = document.getElementById('imageModelSel');
  for (const m of data.chat_models ?? []) {
    chatSel.innerHTML += `<option value="${m.id}">${m.id} (${m.provider})</option>`;
  }
  for (const m of data.image_models ?? []) {
    imgSel.innerHTML += `<option value="${m.id}">${m.id} (${m.provider})</option>`;
  }
}).catch(() => {});

// ── Mode switching ─────────────────────────────────────────────────
const modeToolbar = {
  generate: [],
  edit:    ['select', 'sep', 'move'],
  mesh:    ['select', 'add', 'delete', 'sep', 'move'],
  bones:   ['select', 'add', 'delete', 'sep', 'move'],
  weights: ['paint', 'smooth', 'erase'],
  physics: [],
  preview: ['play'],
  live:    [],
};

const toolIcons = {
  select: { icon: 'fa-arrow-pointer',      label: 'Select' },
  add:    { icon: 'fa-circle-plus',         label: 'Add' },
  delete: { icon: 'fa-circle-minus',        label: 'Delete' },
  move:   { icon: 'fa-up-down-left-right',  label: 'Move' },
  paint:  { icon: 'fa-paint-brush',         label: 'Paint' },
  smooth: { icon: 'fa-droplet',             label: 'Smooth' },
  erase:  { icon: 'fa-eraser',              label: 'Erase' },
  play:   { icon: 'fa-play',               label: 'Play' },
};

document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    switchMode(btn.dataset.mode);
  });
});

function switchMode(mode) {
  const prev = state.mode;
  setMode(mode);

  // Deactivate previous mode tools
  if (prev === 'mesh')    meshToolDeactivate();
  if (prev === 'bones')   boneToolDeactivate();
  if (prev === 'weights') weightToolDeactivate();

  // Clear overlay
  while (overlaysvg.firstChild) overlaysvg.removeChild(overlaysvg.firstChild);
  overlaysvg.classList.remove('interactive');

  // Update mode buttons
  document.querySelectorAll('.mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });

  // Show/hide generate panel
  const genPanel = document.getElementById('generatePanel');
  genPanel.classList.toggle('active', mode === 'generate');

  // Show/hide playback controls
  document.getElementById('playbackControls').style.display =
    (mode === 'preview' || mode === 'live') ? 'flex' : 'none';

  // Activate mode tools
  if (mode === 'mesh')    { meshToolActivate(overlaysvg); }
  if (mode === 'bones')   { boneToolActivate(overlaysvg); }
  if (mode === 'weights') { weightToolActivate(overlaysvg); }

  // Rebuild toolbar
  buildToolBar(mode);

  // Render inspector
  renderInspector();

  state.isPlaying = (mode === 'preview' || mode === 'live');
}

function buildToolBar(mode) {
  const bar = document.getElementById('toolBar');
  bar.innerHTML = '';

  const tools = modeToolbar[mode] ?? [];
  if (!tools.length) return;

  for (const tool of tools) {
    if (tool === 'sep') {
      const sep = document.createElement('div');
      sep.className = 'tool-separator';
      bar.appendChild(sep);
      continue;
    }
    const info = toolIcons[tool];
    const btn = document.createElement('button');
    btn.className = `tool-btn${state.activeTool === tool ? ' active' : ''}`;
    btn.title = info.label;
    btn.innerHTML = `<i class="fa-solid ${info.icon}"></i>`;
    btn.addEventListener('click', () => {
      state.activeTool = tool;
      bar.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      applyToolToMode(mode, tool);
    });
    bar.appendChild(btn);
  }

  // Auto-select first tool
  bar.querySelector('.tool-btn')?.click();
}

function applyToolToMode(mode, tool) {
  if (mode === 'mesh') {
    const m = tool === 'add' ? 'add' : tool === 'delete' ? 'delete' : 'select';
    setMeshTool(m);
  }
  if (mode === 'bones') {
    const m = tool === 'add' ? 'add' : tool === 'delete' ? 'delete' : 'select';
    setBoneTool(m);
  }
  if (mode === 'weights') {
    state.brushMode = tool === 'smooth' ? 'smooth' : tool === 'erase' ? 'subtract' : 'add';
    document.getElementById('brushMode').value = state.brushMode;
  }
}

// ── Viewport controls ──────────────────────────────────────────────
let isPanning = false;
let panStart = { x: 0, y: 0 };

const host = document.getElementById('canvasHost');

host.addEventListener('wheel', e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  setZoom(state.viewScale * factor);
  if (state.mode === 'mesh') drawMesh();
  if (state.mode === 'bones') drawBones();
}, { passive: false });

host.addEventListener('mousedown', e => {
  if (e.button === 1 || (e.button === 0 && e.altKey)) {
    isPanning = true;
    panStart = { x: e.clientX, y: e.clientY };
    e.preventDefault();
  }
});

window.addEventListener('mousemove', e => {
  if (isPanning) {
    panBy(e.clientX - panStart.x, e.clientY - panStart.y);
    panStart = { x: e.clientX, y: e.clientY };
    if (state.mode === 'mesh') drawMesh();
    if (state.mode === 'bones') drawBones();
  }
});

window.addEventListener('mouseup', e => {
  if (e.button === 1 || (e.button === 0 && e.altKey)) isPanning = false;
});

document.getElementById('btnZoomIn').addEventListener('click', () => setZoom(state.viewScale * 1.25));
document.getElementById('btnZoomOut').addEventListener('click', () => setZoom(state.viewScale * 0.8));
document.getElementById('btnZoomFit').addEventListener('click', fitToScreen);

// ── File operations ────────────────────────────────────────────────
document.getElementById('btnNewModel').addEventListener('click', async () => {
  const name = prompt('Model name:', 'Untitled') || 'Untitled';
  showLoading('Creating model...');
  try {
    const res = await api.createModel(name);
    await openModel(res.model_id, res.model);
    toast(`Model "${name}" created`, 'success');
  } catch (e) { toast(e.message, 'error'); }
  hideLoading();
});

document.getElementById('btnOpenModel').addEventListener('click', () => {
  document.getElementById('fileInput').accept = '.vtuber';
  document.getElementById('fileInput').click();
});

document.getElementById('btnSaveModel').addEventListener('click', saveCurrentModel);

document.getElementById('btnExport').addEventListener('click', async () => {
  if (!state.modelId) return toast('No model to export', 'error');
  await saveCurrentModel();
  showLoading('Exporting...');
  try {
    const blob = await api.exportModel(state.modelId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${state.modelId}.vtuber`; a.click();
    URL.revokeObjectURL(url);
    toast('Exported!', 'success');
  } catch (e) { toast(e.message, 'error'); }
  hideLoading();
});

document.getElementById('fileInput').addEventListener('change', async e => {
  const file = e.target.files?.[0];
  if (!file) return;
  e.target.value = '';

  if (file.name.endsWith('.vtuber')) {
    showLoading('Importing...');
    try {
      const res = await api.importModel(file);
      await openModel(res.model_id, res.model);
      toast('Model imported', 'success');
    } catch (ex) { toast(ex.message, 'error'); }
    hideLoading();
  } else {
    // Image → add as layer or start generate
    if (state.model && state.modelId) {
      showLoading('Adding layer...');
      try {
        const res = await api.addLayer(state.modelId, file, file.name.replace(/\.[^.]+$/, ''));
        state.model.layers.push(res.layer);
        await loadModel(state.model, state.modelId);
        renderLayerPanel();
        toast('Layer added', 'success');
      } catch (ex) { toast(ex.message, 'error'); }
      hideLoading();
    }
  }
});

async function saveCurrentModel() {
  if (!state.modelId || !state.model) return;
  showLoading('Saving...');
  try {
    await api.saveModel(state.modelId, state.model);
    markClean();
    toast('Saved', 'success');
  } catch (e) { toast(e.message, 'error'); }
  hideLoading();
}

// ── Add layer button ────────────────────────────────────────────────
document.getElementById('btnAddLayer').addEventListener('click', () => {
  if (!state.model) return toast('Create a model first', 'error');
  document.getElementById('fileInput').accept = 'image/*';
  document.getElementById('fileInput').click();
});

document.getElementById('btnDeleteLayer').addEventListener('click', () => {
  if (!state.selectedLayerId || !state.model) return;
  state.model.layers = state.model.layers.filter(l => l.id !== state.selectedLayerId);
  selectLayer(null);
  loadModel(state.model, state.modelId);
  renderLayerPanel();
  markDirty();
  toast('Layer deleted', 'info');
});

// ── Add bone button ────────────────────────────────────────────────
document.getElementById('btnAddBone').addEventListener('click', () => {
  if (!state.model) return toast('Create a model first', 'error');
  if (state.mode !== 'bones') switchMode('bones');
  setBoneTool('add');
  toast('Click on the canvas to place a bone', 'info');
});

document.getElementById('btnDeleteBone').addEventListener('click', () => {
  if (!state.selectedBoneId || !state.model) return;
  state.model.bones = state.model.bones.filter(b => b.id !== state.selectedBoneId);
  selectBone(null);
  renderBonePanel();
  drawBones();
  markDirty();
  toast('Bone deleted', 'info');
});

// ── Events from tools ──────────────────────────────────────────────
document.addEventListener('bonesChanged', () => {
  renderBonePanel();
  captureBoneBindPoses();
});

document.addEventListener('boneSelected', () => {
  renderBonePanel();
  renderInspector();
});

// ── Playback ───────────────────────────────────────────────────────
document.getElementById('btnPlayPause').addEventListener('click', () => {
  state.isPlaying = !state.isPlaying;
  state.animTime = state.isPlaying ? state.animTime : 0;
  const icon = document.querySelector('#btnPlayPause i');
  icon.className = `fa-solid fa-${state.isPlaying ? 'pause' : 'play'}`;
});

// ── Weight brush controls ──────────────────────────────────────────
document.getElementById('brushRadius').addEventListener('input', e => {
  state.brushRadius = parseInt(e.target.value);
});
document.getElementById('brushStrength').addEventListener('input', e => {
  state.brushStrength = parseInt(e.target.value) / 100;
});
document.getElementById('brushMode').addEventListener('change', e => {
  state.brushMode = e.target.value;
});

// ── Generate tab ───────────────────────────────────────────────────
const pipelinePills = document.querySelectorAll('#pipelinePills .pill');
pipelinePills.forEach(pill => {
  pill.addEventListener('click', () => {
    pipelinePills.forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    state.conceptPipeline = pill.dataset.val;
    const isUpload = pill.dataset.val === 'simple';
    document.getElementById('uploadPanel').style.display = isUpload ? 'flex' : 'none';
    document.getElementById('promptPanel').style.display = isUpload ? 'none' : 'flex';
  });
});

// Upload zone
const uploadZone = document.getElementById('uploadZone');
const uploadInput = document.getElementById('uploadImageInput');
const uploadPreview = document.getElementById('uploadPreview');

uploadZone.addEventListener('click', () => uploadInput.click());
uploadInput.addEventListener('change', e => {
  const file = e.target.files?.[0];
  if (!file) return;
  state.uploadedFile = file;
  const url = URL.createObjectURL(file);
  uploadPreview.src = url; uploadPreview.style.display = 'block';
});
uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.style.borderColor = 'var(--accent)'; });
uploadZone.addEventListener('dragleave', () => { uploadZone.style.borderColor = ''; });
uploadZone.addEventListener('drop', e => {
  e.preventDefault(); uploadZone.style.borderColor = '';
  const file = e.dataTransfer.files?.[0];
  if (file) { state.uploadedFile = file; const url = URL.createObjectURL(file); uploadPreview.src = url; uploadPreview.style.display = 'block'; }
});

document.getElementById('btnGenerateConcept').addEventListener('click', async () => {
  const pipeline = state.conceptPipeline;
  const chatModel = document.getElementById('chatModelSel').value;
  const imageModel = document.getElementById('imageModelSel').value;
  const instructions = document.getElementById('genInstructions').value;
  const meshDensity = document.getElementById('meshDensity').value;
  const boneStyle = document.getElementById('boneStyle').value;

  if (pipeline === 'simple') {
    // Upload mode: directly auto-rig
    if (!state.uploadedFile) return toast('Please upload an image first', 'error');
    showLoading('Auto-rigging from image...');
    try {
      const res = await api.generateFromUpload(state.uploadedFile, {
        chatModel, instructions, meshDensity, boneStyle,
      });
      await openModel(res.model_id, res.model);
      toast('Model generated!', 'success');
    } catch (e) { toast(e.message, 'error'); }
    hideLoading();
    return;
  }

  // Sheet / Local: generate concept first
  const prompt = document.getElementById('genPrompt').value.trim();
  if (!prompt) return toast('Enter a prompt first', 'error');

  showLoading('Generating concept...');
  try {
    const res = await api.generateConcept({ prompt, pipeline, imageModel, chatModel });
    state.conceptId = res.concept_id;

    const img = document.getElementById('conceptImg');
    img.src = res.concept_url;
    document.getElementById('conceptPreview').style.display = 'block';
    toast('Concept generated! Click "Rig It!" to continue.', 'success');
  } catch (e) { toast(e.message, 'error'); }
  hideLoading();
});

document.getElementById('btnRigConcept').addEventListener('click', async () => {
  if (!state.conceptId) return toast('Generate a concept first', 'error');
  const chatModel = document.getElementById('chatModelSel').value;
  const instructions = document.getElementById('genInstructions').value;
  const meshDensity = document.getElementById('meshDensity').value;
  const boneStyle = document.getElementById('boneStyle').value;
  const pipeline = state.conceptPipeline;

  showLoading('Rigging model...');
  try {
    const res = await api.generateRig({
      conceptId: state.conceptId,
      pipeline, chatModel, instructions, meshDensity, boneStyle,
    });
    await openModel(res.model_id, res.model);
    document.getElementById('conceptPreview').style.display = 'none';
    toast('Model rigged successfully!', 'success');
  } catch (e) { toast(e.message, 'error'); }
  hideLoading();
});

// ── Open a model ───────────────────────────────────────────────────
async function openModel(modelId, model) {
  state.modelId = modelId;
  state.model = model;
  state.isDirty = false;
  markClean();

  resetParams();
  captureBoneBindPoses();

  await loadModel(model, modelId);

  renderLayerPanel();
  renderBonePanel();
  renderParamPanel();
  renderInspector();

  document.title = `Aethvion VTuber — ${model.name || 'Untitled'}`;
  setStatus(`Model "${model.name}" loaded (${model.layers?.length ?? 0} layers, ${model.bones?.length ?? 0} bones)`);

  // Switch to edit mode
  switchMode('edit');
}

// ── Keyboard shortcuts ────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

  if (e.ctrlKey || e.metaKey) {
    if (e.key === 's') { e.preventDefault(); saveCurrentModel(); return; }
    if (e.key === 'z') { e.preventDefault(); toast('Undo not yet implemented', 'info'); return; }
  }

  switch (e.key) {
    case 'g': switchMode('generate'); break;
    case 'e': switchMode('edit'); break;
    case 'm': switchMode('mesh'); break;
    case 'b': switchMode('bones'); break;
    case 'w': switchMode('weights'); break;
    case 'p': switchMode('preview'); break;
    case 'f': fitToScreen(); break;
    case 'Delete':
    case 'Backspace':
      if (state.mode === 'bones' && state.selectedBoneId) {
        state.model.bones = state.model.bones.filter(b => b.id !== state.selectedBoneId);
        selectBone(null); renderBonePanel(); drawBones(); markDirty();
      }
      break;
  }
});

// ── Start in generate mode ────────────────────────────────────────
switchMode('generate');
setStatus('Ready — Create a new model or generate a character to get started.');
