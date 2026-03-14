/**
 * api.js — HTTP API client for Aethvion VTuber backend
 */

const BASE = '';  // Same origin

async function request(method, path, body = null, formData = null) {
  const opts = { method, headers: {} };
  if (formData) {
    opts.body = formData;
  } else if (body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.detail || err.message || `HTTP ${res.status}`);
  }
  const ct = res.headers.get('Content-Type') || '';
  if (ct.includes('application/json')) return res.json();
  if (ct.includes('application/octet-stream') || ct.includes('image/')) return res.blob();
  return res.text();
}

// ── Providers ─────────────────────────────────────────────────────
export async function getProviders() {
  return request('GET', '/api/providers');
}

// ── Models ────────────────────────────────────────────────────────
export async function listModels() {
  return request('GET', '/api/models');
}

export async function getModel(modelId) {
  return request('GET', `/api/model/${modelId}`);
}

export async function createModel(name = 'Untitled') {
  const fd = new FormData();
  fd.append('name', name);
  return request('POST', '/api/model/new', null, fd);
}

export async function saveModel(modelId, model) {
  return request('POST', `/api/model/${modelId}/save`, { model });
}

export async function deleteModel(modelId) {
  return request('DELETE', `/api/model/${modelId}`);
}

export async function exportModel(modelId) {
  const blob = await request('GET', `/api/model/${modelId}/export`);
  return blob;
}

export async function importModel(file) {
  const fd = new FormData();
  fd.append('file', file);
  return request('POST', '/api/import', null, fd);
}

// ── Layers ────────────────────────────────────────────────────────
export async function addLayer(modelId, file, layerName = '') {
  const fd = new FormData();
  fd.append('file', file);
  if (layerName) fd.append('layer_name', layerName);
  return request('POST', `/api/model/${modelId}/add-layer`, null, fd);
}

export async function removeLayerBg(modelId, layerId) {
  return request('POST', `/api/model/${modelId}/layer/${layerId}/remove-bg`);
}

export async function restoreLayerBg(modelId, layerId) {
  return request('POST', `/api/model/${modelId}/layer/${layerId}/restore-bg`);
}

// ── Generation ────────────────────────────────────────────────────
export async function generateConcept({ prompt, pipeline, imageModel, chatModel }) {
  return request('POST', '/api/generate/concept', {
    prompt, pipeline,
    image_model: imageModel || undefined,
    chat_model: chatModel || undefined,
  });
}

export async function generateRig({ conceptId, pipeline, chatModel, instructions,
                                    meshDensity, boneStyle }) {
  return request('POST', '/api/generate/rig', {
    concept_id: conceptId,
    pipeline,
    chat_model: chatModel || undefined,
    instructions: instructions || undefined,
    mesh_density: meshDensity || 'medium',
    bone_style: boneStyle || 'humanoid',
    auto_weights: true,
  });
}

export async function generateFromUpload(file, { chatModel, instructions, meshDensity, boneStyle }) {
  const fd = new FormData();
  fd.append('file', file);
  if (chatModel) fd.append('chat_model', chatModel);
  if (instructions) fd.append('instructions', instructions);
  fd.append('mesh_density', meshDensity || 'medium');
  fd.append('bone_style', boneStyle || 'humanoid');
  return request('POST', '/api/generate/from-upload', null, fd);
}

// ── AI Rigging ────────────────────────────────────────────────────
export async function autoMesh(modelId, layerId, density = 'medium', chatModel = '') {
  return request('POST', '/api/rig/auto-mesh', {
    model_id: modelId, layer_id: layerId,
    density, chat_model: chatModel || undefined,
  });
}

export async function autoBones(modelId, style = 'humanoid', chatModel = '') {
  return request('POST', '/api/rig/auto-bones', {
    model_id: modelId, style, chat_model: chatModel || undefined,
  });
}

export async function autoWeights(modelId, smooth = true) {
  return request('POST', '/api/rig/auto-weights', { model_id: modelId, smooth });
}

export async function autoRigAll(modelId, { meshDensity, boneStyle, chatModel }) {
  return request('POST', '/api/rig/auto-all', {
    model_id: modelId,
    mesh_density: meshDensity || 'medium',
    bone_style: boneStyle || 'humanoid',
    chat_model: chatModel || undefined,
  });
}

// ── Texture URL helpers ───────────────────────────────────────────
export function textureUrl(modelId, texRel) {
  return `/api/model/${modelId}/texture/${texRel.replace('textures/', '')}`;
}
