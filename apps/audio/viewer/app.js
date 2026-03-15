/* =============================================================
   Aethvion Audio Editor — Multi-Track Frontend
   ============================================================= */

"use strict";

/* ── Constants ─────────────────────────────────────────────── */
const RULER_H   = 26;    // px  (matches CSS --ruler-h)
const TRACK_H   = 82;    // px  (matches CSS --track-h)
const MIN_PX_MS = 0.02;
const MAX_PX_MS = 2.0;

/* ── State ─────────────────────────────────────────────────── */
let state = {
    session:      null,     // full /api/session payload
    pxPerMs:      0.10,     // zoom level (pixels per millisecond)
    selectedId:   null,     // currently selected track_id
    playing:      false,
    playheadMs:   0,        // current playhead position in ms (seek target for new tracks)
};

/* ── DOM refs ──────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const headersBody    = $("headers-body");
const rowsBody       = $("rows-body");
const timelineInner  = $("timeline-inner");
const timelineScroll = $("timeline-scroll");
const ruler          = $("ruler");
const playhead       = $("playhead");
const fxChips        = $("fx-chips");
const fxEmpty        = $("fx-empty");
const fxTrackName    = $("fx-track-name");
const addFxForm      = $("add-fx-form");
const fxOpSelect     = $("fx-op-select");
const fxParamInputs  = $("fx-param-inputs");
const btnApplyFx     = $("btn-apply-fx");
const mixAudio       = $("mix-audio");
const mixCur         = $("mix-cur");
const mixDur         = $("mix-dur");
const mixProgressFill= $("mix-progress-fill");
const mixProgressWrap= $("mix-progress-wrap");
const mixVol         = $("mix-vol");
const hdrTracks      = $("hdr-tracks");
const hdrWorkspace   = $("hdr-workspace");
const workspaceInput = $("workspace-input");
const fileInput      = $("file-input");
const loading        = $("ae-loading");
const loadMsg        = $("ae-load-msg");
const notifications  = $("ae-notifications");
const timelineEmpty  = $("timeline-empty");
const btnPlayMix     = $("btn-play-mix");
const btnStopMix     = $("btn-stop-mix");
const btnRewind      = $("btn-rewind");
const btnAddTrack    = $("btn-add-track");
const btnAddTrackRow = $("btn-add-track-row");
const btnZoomIn      = $("btn-zoom-in");
const btnZoomOut     = $("btn-zoom-out");
const btnExportWav   = $("btn-export-wav");
const btnExportMp3   = $("btn-export-mp3");
const mixPlayIcon    = $("mix-play-icon");
const mixPlayLabel   = $("mix-play-label");

/* ── Utility ───────────────────────────────────────────────── */
function fmtMs(ms) {
    const total = ms / 1000;
    const m = Math.floor(total / 60);
    const s = (total % 60).toFixed(1).padStart(4, "0");
    return `${m}:${s}`;
}

function notify(msg, type = "info") {
    const el = document.createElement("div");
    el.className = `ae-notif ae-notif-${type}`;
    el.textContent = msg;
    notifications.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

function showLoading(msg = "PROCESSING...") {
    loadMsg.textContent = msg;
    loading.style.display = "flex";
}

function hideLoading() {
    loading.style.display = "none";
}

function escHtml(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

/* ── API helpers ───────────────────────────────────────────── */
async function api(path, opts = {}) {
    const r = await fetch(path, opts);
    if (!r.ok) {
        let msg = `HTTP ${r.status}`;
        try { const j = await r.json(); msg = j.detail || j.error || msg; } catch {}
        throw new Error(msg);
    }
    return r.json();
}

/* ── Session load / full re-render ─────────────────────────── */
async function loadSession() {
    try {
        state.session = await api("/api/session");
        render();
    } catch (e) {
        notify("Failed to load session: " + e.message, "error");
    }
}

function render() {
    const { session, pxPerMs } = state;
    if (!session) return;

    const hasTracks = session.tracks.length > 0;
    const workMs    = session.workspace_ms || 30000;
    const totalPx   = Math.max(workMs * pxPerMs, timelineScroll.clientWidth - 4);

    /* header badges */
    hdrTracks.textContent    = `${session.tracks.length} track${session.tracks.length !== 1 ? "s" : ""}`;
    hdrWorkspace.textContent = fmtMs(workMs);
    workspaceInput.value     = Math.round(workMs / 1000);

    /* toolbar buttons */
    btnPlayMix.disabled   = !hasTracks;
    btnStopMix.disabled   = !hasTracks;
    btnRewind.disabled    = !hasTracks;
    btnExportWav.disabled = !hasTracks;
    btnExportMp3.disabled = !hasTracks;

    /* empty state */
    timelineEmpty.style.display = hasTracks ? "none" : "flex";

    /* timeline width */
    timelineInner.style.width = totalPx + "px";

    renderRuler(workMs, totalPx);
    renderHeaders(session.tracks);
    renderRows(session.tracks, totalPx);
    renderFxPanel();
    syncPlayheadHeight();
}

/* ── Ruler ─────────────────────────────────────────────────── */
function renderRuler(workMs, totalPx) {
    ruler.width  = totalPx;
    ruler.height = RULER_H;
    const ctx = ruler.getContext("2d");
    ctx.clearRect(0, 0, totalPx, RULER_H);

    ctx.fillStyle = "#0d0d10";
    ctx.fillRect(0, 0, totalPx, RULER_H);

    const targetTicks = totalPx / 80;
    const msPerTick   = niceInterval(workMs / targetTicks);

    ctx.strokeStyle  = "#444";
    ctx.fillStyle    = "#aaa";
    ctx.font         = "10px monospace";
    ctx.textBaseline = "top";

    for (let t = 0; t <= workMs + msPerTick; t += msPerTick) {
        const x = t * state.pxPerMs;
        if (x > totalPx + 2) break;
        ctx.beginPath();
        ctx.moveTo(x, RULER_H * 0.5);
        ctx.lineTo(x, RULER_H);
        ctx.stroke();
        if (x > 2) ctx.fillText(fmtMs(t), x + 2, 2);
    }

    /* minor ticks */
    ctx.strokeStyle = "#2a2a2e";
    const minorMs   = msPerTick / 5;
    for (let t = 0; t <= workMs; t += minorMs) {
        const x = t * state.pxPerMs;
        if (x > totalPx + 2) break;
        if (Math.abs(t % msPerTick) > 1) {
            ctx.beginPath();
            ctx.moveTo(x, RULER_H * 0.75);
            ctx.lineTo(x, RULER_H);
            ctx.stroke();
        }
    }
}

function niceInterval(ms) {
    const candidates = [100, 250, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000];
    return candidates.find(c => c >= ms) || 600000;
}

/* Click on the ruler to seek to that position. */
ruler.addEventListener("click", e => {
    const rect = ruler.getBoundingClientRect();
    /* ruler scrolls with the timeline, so scrollLeft is already baked into rect.left */
    const x  = e.clientX - rect.left;
    const ms = x / state.pxPerMs;
    seekToMs(ms);
});

/* ── Track headers (left column) ───────────────────────────── */
function renderHeaders(tracks) {
    headersBody.innerHTML = "";
    tracks.forEach(t => {
        const div = document.createElement("div");
        div.className = "ae-track-header"
            + (t.muted ? " muted" : "")
            + (t.track_id === state.selectedId ? " selected" : "");
        div.dataset.id = t.track_id;
        div.innerHTML = `
            <div class="ae-th-color" style="background:${t.color}"></div>
            <div class="ae-th-body">
                <div class="ae-th-name" contenteditable="true" spellcheck="false"
                     data-id="${t.track_id}">${escHtml(t.name)}</div>
                <div class="ae-th-meta">${fmtMs(t.duration_ms)} &bull; ${Math.round(t.sample_rate / 1000)}kHz</div>
                <div class="ae-th-btns">
                    <button class="ae-icon-btn mute-btn" title="Mute" data-id="${t.track_id}">
                        <i class="fas ${t.muted ? "fa-volume-mute" : "fa-volume-up"}"></i>
                    </button>
                    <button class="ae-icon-btn del-btn" title="Delete track" data-id="${t.track_id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>`;
        headersBody.appendChild(div);

        div.addEventListener("click", e => {
            if (e.target.closest(".ae-icon-btn")) return;
            selectTrack(t.track_id);
        });

        const nameEl = div.querySelector(".ae-th-name");
        nameEl.addEventListener("keydown", e => {
            if (e.key === "Enter") { e.preventDefault(); e.target.blur(); }
        });
        nameEl.addEventListener("blur", async e => {
            const newName = e.target.textContent.trim() || t.name;
            if (newName !== t.name) await patchTrack(t.track_id, { name: newName });
        });

        div.querySelector(".mute-btn").addEventListener("click", e => {
            e.stopPropagation();
            patchTrack(t.track_id, { muted: !t.muted });
        });

        div.querySelector(".del-btn").addEventListener("click", e => {
            e.stopPropagation();
            deleteTrack(t.track_id);
        });
    });
}

/* ── Track rows (timeline) ─────────────────────────────────── */
function renderRows(tracks, totalPx) {
    rowsBody.innerHTML = "";
    tracks.forEach(t => {
        const row = document.createElement("div");
        row.className  = "ae-track-row";
        row.dataset.id = t.track_id;
        row.style.width = totalPx + "px";

        const clipLeft  = t.start_ms * state.pxPerMs;
        const clipWidth = Math.max(2, t.duration_ms * state.pxPerMs);

        const clip = document.createElement("div");
        clip.className = "ae-clip"
            + (t.muted ? " muted" : "")
            + (t.track_id === state.selectedId ? " selected" : "");
        clip.style.left        = clipLeft + "px";
        clip.style.width       = clipWidth + "px";
        clip.style.borderColor = t.color;

        clip.innerHTML = `
            <div class="ae-clip-label">${escHtml(t.name)}</div>
            <canvas class="ae-clip-canvas" height="${TRACK_H - 22}"></canvas>`;

        row.appendChild(clip);
        rowsBody.appendChild(row);

        const canvas = clip.querySelector(".ae-clip-canvas");
        canvas.width = Math.max(2, Math.ceil(clipWidth));
        drawWaveform(canvas, t.waveform || [], t.color, t.muted);

        makeDraggable(clip, t.track_id, t.start_ms);

        row.addEventListener("click", e => {
            if (e.target.closest(".ae-clip")) selectTrack(t.track_id);
        });
    });
}

function drawWaveform(canvas, waveform, color, muted) {
    if (!waveform || !waveform.length) return;
    const ctx = canvas.getContext("2d");
    const w   = canvas.width;
    const h   = canvas.height;
    const mid = h / 2;
    ctx.clearRect(0, 0, w, h);

    const alpha      = muted ? 0.3 : 0.75;
    const alphaHex   = Math.round(alpha * 255).toString(16).padStart(2, "0");
    ctx.strokeStyle  = color + alphaHex;
    ctx.lineWidth    = 1;
    ctx.beginPath();

    const step = waveform.length / w;
    for (let px = 0; px < w; px++) {
        const idx = Math.min(waveform.length - 1, Math.floor(px * step));
        const amp = (waveform[idx] || 0) * mid * 0.9;
        ctx.moveTo(px + 0.5, mid - amp);
        ctx.lineTo(px + 0.5, mid + amp);
    }
    ctx.stroke();
}

/* ── Clip drag-to-reposition ─────────────────────────────────── */
function makeDraggable(clipEl, trackId, startMs) {
    let dragging = false;
    let startX   = 0;
    let origMs   = startMs;

    clipEl.addEventListener("mousedown", e => {
        if (e.button !== 0) return;
        dragging = true;
        startX   = e.clientX;
        origMs   = state.session.tracks.find(t => t.track_id === trackId)?.start_ms ?? 0;
        e.preventDefault();
    });

    document.addEventListener("mousemove", e => {
        if (!dragging) return;
        const dx    = e.clientX - startX;
        const newMs = Math.max(0, origMs + dx / state.pxPerMs);
        clipEl.style.left = (newMs * state.pxPerMs) + "px";
    });

    document.addEventListener("mouseup", async e => {
        if (!dragging) return;
        dragging = false;
        const dx = e.clientX - startX;
        if (Math.abs(dx) < 2) return;
        const newMs = Math.max(0, origMs + dx / state.pxPerMs);
        await patchTrack(trackId, { start_ms: newMs });
    });
}

/* ── FX panel ──────────────────────────────────────────────── */
function renderFxPanel() {
    const track = state.session?.tracks.find(t => t.track_id === state.selectedId);

    if (!track) {
        fxTrackName.textContent = "select a track";
        fxEmpty.style.display   = "block";
        fxChips.innerHTML       = "";
        addFxForm.style.display = "none";
        btnApplyFx.disabled     = true;
        return;
    }

    fxTrackName.textContent = track.name;
    fxEmpty.style.display   = "none";
    addFxForm.style.display = "flex";
    btnApplyFx.disabled     = false;

    fxChips.innerHTML = "";
    (track.effects || []).forEach(fx => {
        const chip = document.createElement("div");
        chip.className = "ae-fx-chip" + (fx.enabled ? "" : " disabled");
        chip.innerHTML = `
            <span class="ae-fx-chip-name">${fxLabel(fx.op)}</span>
            <span class="ae-fx-chip-params">${fmtParams(fx)}</span>
            <button class="ae-fx-chip-toggle" title="${fx.enabled ? "Disable" : "Enable"}" data-id="${fx.effect_id}">
                <i class="fas ${fx.enabled ? "fa-eye" : "fa-eye-slash"}"></i>
            </button>
            <button class="ae-fx-chip-remove" title="Remove" data-id="${fx.effect_id}">
                <i class="fas fa-times"></i>
            </button>`;
        fxChips.appendChild(chip);

        chip.querySelector(".ae-fx-chip-toggle").addEventListener("click", () =>
            toggleEffect(track.track_id, fx.effect_id, !fx.enabled));
        chip.querySelector(".ae-fx-chip-remove").addEventListener("click", () =>
            removeEffect(track.track_id, fx.effect_id));
    });

    renderFxParams();
}

function fxLabel(op) {
    const map = {
        fade_in: "Fade In", fade_out: "Fade Out", normalize: "Normalize",
        volume: "Gain", speed: "Speed", reverse: "Reverse",
        crop_silence: "Crop Silence", trim: "Trim",
    };
    return map[op] || op;
}

function fmtParams(fx) {
    const p = fx.params || {};
    if (fx.op === "fade_in" || fx.op === "fade_out") return `${(p.duration_ms || 1000) / 1000}s`;
    if (fx.op === "volume")  return `${p.db >= 0 ? "+" : ""}${p.db || 0}dB`;
    if (fx.op === "speed")   return `×${p.rate || 1}`;
    if (fx.op === "crop_silence") return `${p.threshold_db || -50}dB`;
    return "";
}

/* ── FX param inputs (dynamic) ─────────────────────────────── */
const FX_PARAMS = {
    fade_in:      [{ key: "duration_ms", label: "Duration (ms)", default: 1000, min: 10, max: 10000 }],
    fade_out:     [{ key: "duration_ms", label: "Duration (ms)", default: 1000, min: 10, max: 10000 }],
    normalize:    [],
    volume:       [{ key: "db",          label: "dB",            default: 0,    min: -30, max: 30 }],
    speed:        [{ key: "rate",        label: "Rate",          default: 1.0,  min: 0.25, max: 4.0, step: 0.05 }],
    reverse:      [],
    crop_silence: [{ key: "threshold_db", label: "Threshold dB", default: -50, min: -80, max: -10 }],
    trim:         [
        { key: "start_ms", label: "Start (ms)", default: 0,    min: 0 },
        { key: "end_ms",   label: "End (ms)",   default: 5000, min: 1 },
    ],
};

function renderFxParams() {
    fxParamInputs.innerHTML = "";
    const defs = FX_PARAMS[fxOpSelect.value] || [];
    defs.forEach(def => {
        const label = document.createElement("label");
        label.className   = "ae-fx-param-label";
        label.textContent = def.label;
        const input = document.createElement("input");
        input.type        = "number";
        input.className   = "ae-num-input";
        input.value       = def.default;
        input.min         = def.min ?? "";
        input.max         = def.max ?? "";
        input.step        = def.step ?? 1;
        input.dataset.key = def.key;
        fxParamInputs.appendChild(label);
        fxParamInputs.appendChild(input);
    });
}

/* ── Track actions ─────────────────────────────────────────── */
function selectTrack(id) {
    state.selectedId = id;
    render();
}

async function deleteTrack(id) {
    showLoading("REMOVING...");
    try {
        await api(`/api/tracks/${id}`, { method: "DELETE" });
        if (state.selectedId === id) state.selectedId = null;
        await loadSession();
        stopMix();
        notify("Track removed", "info");
    } catch (e) {
        notify("Delete failed: " + e.message, "error");
    } finally {
        hideLoading();
    }
}

async function patchTrack(id, body) {
    try {
        const resp = await api(`/api/tracks/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        state.session = resp.session;
        render();
        /* live reload when mute toggled or position changed while playing */
        if ("muted" in body || "start_ms" in body) {
            reloadMixLive();
        }
    } catch (e) {
        notify("Update failed: " + e.message, "error");
    }
}

/* ── Effect actions ────────────────────────────────────────── */
async function addEffect() {
    if (!state.selectedId) return;
    const op     = fxOpSelect.value;
    const params = {};
    fxParamInputs.querySelectorAll("input[data-key]").forEach(inp => {
        params[inp.dataset.key] = parseFloat(inp.value);
    });
    showLoading("ADDING EFFECT...");
    try {
        const resp = await api(`/api/tracks/${state.selectedId}/effects`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ op, params }),
        });
        const idx = state.session.tracks.findIndex(t => t.track_id === state.selectedId);
        if (idx !== -1) state.session.tracks[idx] = resp.track;
        render();
        notify(`${fxLabel(op)} added`, "success");
    } catch (e) {
        notify("Add effect failed: " + e.message, "error");
    } finally {
        hideLoading();
    }
}

async function toggleEffect(trackId, effectId, enabled) {
    try {
        const resp = await api(`/api/tracks/${trackId}/effects/${effectId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled }),
        });
        const idx = state.session.tracks.findIndex(t => t.track_id === trackId);
        if (idx !== -1) state.session.tracks[idx] = resp.track;
        render();
    } catch (e) {
        notify("Toggle effect failed: " + e.message, "error");
    }
}

async function removeEffect(trackId, effectId) {
    try {
        const resp = await api(`/api/tracks/${trackId}/effects/${effectId}`, { method: "DELETE" });
        const idx = state.session.tracks.findIndex(t => t.track_id === trackId);
        if (idx !== -1) state.session.tracks[idx] = resp.track;
        render();
        notify("Effect removed", "info");
    } catch (e) {
        notify("Remove effect failed: " + e.message, "error");
    }
}

/* ── File upload ─────────────────────────────────────────────── */
async function uploadFiles(files) {
    if (!files || files.length === 0) return;
    showLoading(`UPLOADING ${files.length > 1 ? files.length + " FILES" : "FILE"}...`);
    /* place tracks starting at the current playhead, stacking sequentially */
    let nextStartMs = state.playheadMs;
    try {
        for (const file of files) {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("start_ms", String(nextStartMs));
            const resp = await fetch("/api/tracks/upload", { method: "POST", body: fd });
            if (!resp.ok) {
                const j = await resp.json().catch(() => ({}));
                throw new Error(j.error || `HTTP ${resp.status}`);
            }
            const data = await resp.json();
            state.session = data.session;
            /* advance cursor to end of just-added track so multiple files stack */
            const added = data.track;
            if (added) nextStartMs = added.start_ms + added.duration_ms;
        }
        render();
        notify(`${files.length} track${files.length !== 1 ? "s" : ""} added`, "success");
    } catch (e) {
        notify("Upload failed: " + e.message, "error");
    } finally {
        hideLoading();
        fileInput.value = "";
    }
}

/* ── Live mix reload (re-render and resume at current position) ── */
async function reloadMixLive() {
    if (!state.playing && !mixAudio.src) return;
    const savedSec  = mixAudio.currentTime;
    const wasPlaying = state.playing;
    try {
        const resp = await fetch("/api/preview");
        if (!resp.ok) return;
        const blob = await resp.blob();
        const url  = URL.createObjectURL(blob);
        mixAudio.pause();
        mixAudio.src = url;
        await new Promise(res => mixAudio.addEventListener("loadedmetadata", res, { once: true }));
        mixAudio.currentTime = savedSec;
        if (wasPlaying) await mixAudio.play();
    } catch { /* silent — playback will just continue with stale mix */ }
}

/* ── Mix playback ────────────────────────────────────────────── */
async function playMix() {
    const startMs = state.playheadMs; // remember seek position before stopMix resets it
    const hadSrc  = !!mixAudio.src;
    mixAudio.pause();
    state.playing = false;
    updatePlayBtn(false);

    showLoading("RENDERING MIX...");
    try {
        const resp = await fetch("/api/preview");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        const url  = URL.createObjectURL(blob);
        mixAudio.src    = url;
        mixAudio.volume = parseFloat(mixVol.value);
        await new Promise(res => mixAudio.addEventListener("loadedmetadata", res, { once: true }));
        mixAudio.currentTime = startMs / 1000;
        await mixAudio.play();
        state.playing = true;
        updatePlayBtn(true);
    } catch (e) {
        notify("Playback failed: " + e.message, "error");
    } finally {
        hideLoading();
    }
}

function stopMix() {
    mixAudio.pause();
    mixAudio.currentTime = 0;
    state.playing    = false;
    state.playheadMs = 0;
    updatePlayBtn(false);
    setPlayhead(0);
}

function updatePlayBtn(isPlaying) {
    mixPlayIcon.className    = isPlaying ? "fas fa-pause" : "fas fa-play";
    mixPlayLabel.textContent = isPlaying ? "PAUSE" : "PLAY MIX";
}

function setPlayhead(px) {
    playhead.style.left = px + "px";
    state.playheadMs = px / state.pxPerMs;
}

/* Seek both the audio element and the visual playhead to a given ms position. */
function seekToMs(ms) {
    state.playheadMs = Math.max(0, ms);
    setPlayhead(state.playheadMs * state.pxPerMs);
    if (mixAudio.readyState >= 1) {
        mixAudio.currentTime = state.playheadMs / 1000;
    }
    mixCur.textContent = fmtMs(state.playheadMs);
}

function syncPlayheadHeight() {
    const total = RULER_H + (state.session?.tracks.length || 0) * TRACK_H;
    playhead.style.height = total + "px";
}

/* ── Playhead animation ─────────────────────────────────────── */
mixAudio.addEventListener("timeupdate", () => {
    const cur = mixAudio.currentTime;
    const dur = mixAudio.duration || 0;
    mixCur.textContent = fmtMs(cur * 1000);
    mixDur.textContent = fmtMs(dur * 1000);
    mixProgressFill.style.width = dur ? (cur / dur * 100) + "%" : "0%";
    setPlayhead((cur * 1000) * state.pxPerMs);
});

mixAudio.addEventListener("ended", () => {
    state.playing = false;
    updatePlayBtn(false);
});

mixAudio.addEventListener("play",  () => updatePlayBtn(true));
mixAudio.addEventListener("pause", () => updatePlayBtn(false));

/* progress bar seek */
mixProgressWrap.addEventListener("click", e => {
    if (!mixAudio.duration) return;
    const rect  = mixProgressWrap.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const ms    = ratio * mixAudio.duration * 1000;
    seekToMs(ms);
});

/* ── Export ──────────────────────────────────────────────────── */
async function exportMix(fmt) {
    showLoading(`EXPORTING ${fmt.toUpperCase()}...`);
    try {
        const resp = await fetch(`/api/export?format=${fmt}`);
        if (!resp.ok) {
            const j = await resp.json().catch(() => ({}));
            throw new Error(j.detail || `HTTP ${resp.status}`);
        }
        const blob = await resp.blob();
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement("a");
        a.href     = url;
        a.download = `mix.${fmt}`;
        a.click();
        URL.revokeObjectURL(url);
        notify(`Exported mix.${fmt}`, "success");
    } catch (e) {
        notify("Export failed: " + e.message, "error");
    } finally {
        hideLoading();
    }
}

/* ── Workspace ───────────────────────────────────────────────── */
async function setWorkspace(sec) {
    const ms = Math.max(1, sec) * 1000;
    try {
        await api("/api/session/workspace", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ workspace_ms: ms }),
        });
        await loadSession();
    } catch (e) {
        notify("Workspace update failed: " + e.message, "error");
    }
}

/* ── Zoom ────────────────────────────────────────────────────── */
function zoom(factor) {
    state.pxPerMs = Math.min(MAX_PX_MS, Math.max(MIN_PX_MS, state.pxPerMs * factor));
    render();
}

/* ── Drag-and-drop onto app ──────────────────────────────────── */
const dropTarget = document.getElementById("app");
dropTarget.addEventListener("dragover", e => e.preventDefault());
dropTarget.addEventListener("drop", e => {
    e.preventDefault();
    const files = [...e.dataTransfer.files].filter(f =>
        f.type.startsWith("audio/") ||
        /\.(wav|mp3|ogg|flac|aac|m4a|opus)$/i.test(f.name)
    );
    if (files.length) uploadFiles(files);
});

/* ── Event wiring ────────────────────────────────────────────── */
btnAddTrack.addEventListener("click",    () => fileInput.click());
btnAddTrackRow.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", e => uploadFiles([...e.target.files]));

btnPlayMix.addEventListener("click", () => {
    if (state.playing) { mixAudio.pause(); }
    else playMix();
});

btnStopMix.addEventListener("click", stopMix);

btnRewind.addEventListener("click", () => seekToMs(0));

btnZoomIn.addEventListener("click",  () => zoom(1.5));
btnZoomOut.addEventListener("click", () => zoom(1 / 1.5));

workspaceInput.addEventListener("change", e => setWorkspace(parseFloat(e.target.value) || 30));

btnExportWav.addEventListener("click", () => exportMix("wav"));
btnExportMp3.addEventListener("click", () => exportMix("mp3"));

mixVol.addEventListener("input", () => { mixAudio.volume = parseFloat(mixVol.value); });

fxOpSelect.addEventListener("change", renderFxParams);
btnApplyFx.addEventListener("click", addEffect);

/* keep headers and timeline vertically in sync */
timelineScroll.addEventListener("scroll", () => {
    headersBody.parentElement.scrollTop = timelineScroll.scrollTop;
});

/* ── Init ─────────────────────────────────────────────────────── */
loadSession();
