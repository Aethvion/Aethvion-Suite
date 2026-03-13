const WS_URL   = `ws://${window.location.host}/ws/tracking`;
const API_BASE = `http://${window.location.host}/api/trackers`;

let ws            = null;
let isPreviewing  = false;
let debugInterval = null;
let isPinned      = false;
let isCollapsed   = false;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const selectTracker    = document.getElementById("tracker-select");
const selectSource     = document.getElementById("source-select");
const sourceGroup      = document.getElementById("source-group");
const previewGroup     = document.getElementById("preview-group");
const osfConfig        = document.getElementById("osf-config");
const osfPortInput     = document.getElementById("osf-port");
const osfPortDisplay   = document.getElementById("osf-port-display");
const osfCmdDisplay    = document.getElementById("osf-cmd-display");
const osfStats         = document.getElementById("osf-stats");
const btnStart         = document.getElementById("btn-start");
const btnStop          = document.getElementById("btn-stop");
const btnPreview       = document.getElementById("btn-preview");
const statusDot        = document.getElementById("status-dot");
const statusText       = document.getElementById("status-text");
const dataOutput       = document.getElementById("data-output");
const videoFeed        = document.getElementById("video-feed");
const videoPlaceholder = document.getElementById("video-placeholder");
const floatPanel       = document.getElementById("float-panel");
const floatDrag        = document.getElementById("float-drag");
const floatBody        = document.getElementById("float-body");
const btnCollapse      = document.getElementById("btn-collapse");
const btnPin           = document.getElementById("btn-pin");

// ── Tracker select ────────────────────────────────────────────────────────────

const TRACKER_LABELS = {
    mediapipe:   "MediaPipe  (built-in webcam / screen)",
    openseeface: "OpenSeeFace  (external process → UDP)",
};

function isOSF() {
    return selectTracker.value === "openseeface";
}

function onTrackerChange() {
    const osf = isOSF();
    sourceGroup.style.display  = osf ? "none" : "";
    previewGroup.style.display = osf ? "none" : "";
    osfConfig.style.display    = osf ? ""     : "none";
    if (osf) syncOsfPort();
}

function syncOsfPort() {
    const port = osfPortInput ? osfPortInput.value : "11573";
    if (osfPortDisplay) osfPortDisplay.textContent = port;
    if (osfCmdDisplay)  osfCmdDisplay.textContent  =
        `facetracker.exe -c 0 -P 1 --ip 127.0.0.1 --port ${port}`;
}

selectTracker.addEventListener("change", onTrackerChange);
if (osfPortInput) osfPortInput.addEventListener("input", syncOsfPort);

// ── Fetch current status & populate tracker list ──────────────────────────────

async function fetchStatus() {
    try {
        const res  = await fetch(API_BASE);
        const data = await res.json();

        selectTracker.innerHTML = "";
        data.available.forEach(t => {
            const opt     = document.createElement("option");
            opt.value     = t;
            opt.innerText = TRACKER_LABELS[t] || t;
            if (t === data.active) opt.selected = true;
            selectTracker.appendChild(opt);
        });

        onTrackerChange();
        updateUIState(data.is_running);
    } catch (e) {
        console.error("Failed to fetch tracker status:", e);
        dataOutput.innerText = "Error connecting to Synapse backend.";
    }
}

// ── UI state ──────────────────────────────────────────────────────────────────

function setStatusDot(state) {
    // state: "online" | "preview" | ""
    statusDot.className = "status-dot" + (state ? " " + state : "");
}

function updateUIState(isRunning) {
    const controls = [selectTracker, selectSource, osfPortInput].filter(Boolean);

    if (isRunning) {
        statusText.innerText = "Tracking Online";
        statusText.className = "status-online";
        setStatusDot("online");
        btnStart.disabled    = true;
        btnStop.disabled     = false;
        controls.forEach(el => el.disabled = true);
        connectWebSocket();
        showVideo();
        videoFeed.src = "/video_feed?" + Date.now();
        if (isOSF()) startDebugPolling();
    } else {
        statusText.innerText = isPreviewing ? "Preview Active" : "Offline";
        statusText.className = isPreviewing ? "status-online"  : "status-offline";
        setStatusDot(isPreviewing ? "preview" : "");
        btnStart.disabled    = false;
        btnStop.disabled     = true;
        controls.forEach(el => { el.disabled = isPreviewing && el !== osfPortInput; });
        disconnectWebSocket();
        stopDebugPolling();
        dataOutput.innerText = "Waiting for data stream…";
        if (!isPreviewing) {
            videoFeed.src = "";
            showPlaceholder();
        }
        if (osfStats) osfStats.style.display = "none";
    }
}

function showVideo() {
    if (videoPlaceholder) videoPlaceholder.style.display = "none";
    if (videoFeed)        videoFeed.style.display        = "";
}

function showPlaceholder() {
    if (videoFeed)        videoFeed.style.display        = "none";
    if (videoPlaceholder) videoPlaceholder.style.display = "";
}

// ── Tracker start / stop ──────────────────────────────────────────────────────

async function startTracker() {
    const tracker = selectTracker.value;
    if (!tracker) return;

    const body = {
        source:   isOSF() ? "none" : selectSource.value,
        osf_host: "127.0.0.1",
        osf_port: osfPortInput ? parseInt(osfPortInput.value) || 11573 : 11573,
    };

    try {
        const res = await fetch(`${API_BASE}/start/${tracker}`, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify(body),
        });
        if (res.ok) {
            updateUIState(true);
        } else {
            const err = await res.json();
            alert("Failed to start: " + (err.message || err.detail || "Unknown error"));
        }
    } catch (e) {
        console.error("Start failed:", e);
    }
}

async function stopTracker() {
    try {
        await fetch(`${API_BASE}/stop`, { method: "POST" });
        updateUIState(false);
    } catch (e) {
        console.error("Stop failed:", e);
    }
}

// ── Preview (MediaPipe / camera only) ─────────────────────────────────────────

async function togglePreview() {
    isPreviewing = !isPreviewing;
    const source   = selectSource.value;
    const endpoint = isPreviewing ? "/api/preview/start" : "/api/preview/stop";

    try {
        const res = await fetch(endpoint, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ source }),
        });

        if (res.ok) {
            btnPreview.innerText = isPreviewing ? "Stop Preview"            : "Show Preview";
            btnPreview.className = isPreviewing ? "btn danger full-width"   : "btn secondary full-width";
            if (isPreviewing) {
                videoFeed.src = "/video_feed?" + Date.now();
                showVideo();
            } else {
                showPlaceholder();
            }
            updateUIState(false);
        } else {
            isPreviewing = !isPreviewing;
            alert("Failed to toggle preview.");
        }
    } catch (e) {
        isPreviewing = !isPreviewing;
        console.error("Preview toggle failed:", e);
    }
}

// ── OSF debug stats polling ────────────────────────────────────────────────────

async function fetchDebugStats() {
    try {
        const res  = await fetch(`${API_BASE}/debug`);
        const data = await res.json();
        if (!data.active) return;

        const s = data.stats || {};
        document.getElementById("stat-rx").textContent  = s.packets_received ?? "0";
        document.getElementById("stat-ok").textContent  = s.packets_parsed   ?? "0";
        document.getElementById("stat-sz").textContent  = s.last_size        ?? "—";
        document.getElementById("stat-fmt").textContent = s.format           ?? "—";

        const errEl = document.getElementById("stat-err");
        if (s.last_error) {
            errEl.textContent   = s.last_error;
            errEl.style.display = "";
        } else {
            errEl.style.display = "none";
        }

        if (osfStats) osfStats.style.display = "";
    } catch (_) {
        // silent — backend may not yet be up
    }
}

function startDebugPolling() {
    if (debugInterval) return;
    debugInterval = setInterval(fetchDebugStats, 1000);
}

function stopDebugPolling() {
    if (debugInterval) { clearInterval(debugInterval); debugInterval = null; }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWebSocket() {
    if (ws) return;
    ws = new WebSocket(WS_URL);
    ws.onopen  = () => console.log("[Synapse WS] Connected");
    ws.onclose = () => { console.log("[Synapse WS] Disconnected"); ws = null; };
    ws.onerror = (e) => console.error("[Synapse WS] Error:", e);
    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "params") {
                dataOutput.innerText = JSON.stringify(msg.params, null, 2);
            }
        } catch (e) {
            console.error("[Synapse WS] Parse error:", e);
        }
    };
}

function disconnectWebSocket() {
    if (ws) { ws.close(); ws = null; }
}

// ── Floating panel: drag ──────────────────────────────────────────────────────

(function initFloatDrag() {
    if (!floatPanel || !floatDrag) return;

    let dragging = false;
    let startX, startY, origLeft, origBottom;

    floatDrag.addEventListener("mousedown", (e) => {
        if (isPinned) return;
        dragging = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = floatPanel.getBoundingClientRect();
        origLeft   = rect.left;
        origBottom = window.innerHeight - rect.bottom;
        floatDrag.style.cursor = "grabbing";
        e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
        if (!dragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        // Clamp so panel stays inside the viewport
        const panelW = floatPanel.offsetWidth;
        const panelH = floatPanel.offsetHeight;
        const newLeft   = Math.max(0, Math.min(window.innerWidth  - panelW, origLeft   + dx));
        const newBottom = Math.max(0, Math.min(window.innerHeight - panelH, origBottom - dy));
        floatPanel.style.left   = newLeft   + "px";
        floatPanel.style.bottom = newBottom + "px";
        floatPanel.style.right  = "auto";
    });

    document.addEventListener("mouseup", () => {
        if (dragging) { dragging = false; floatDrag.style.cursor = ""; }
    });
})();

// ── Floating panel: collapse / pin ────────────────────────────────────────────

if (btnCollapse) {
    btnCollapse.addEventListener("click", () => {
        isCollapsed              = !isCollapsed;
        floatBody.style.display  = isCollapsed ? "none" : "";
        btnCollapse.textContent  = isCollapsed ? "+"    : "−";
        btnCollapse.title        = isCollapsed ? "Expand" : "Collapse";
    });
}

if (btnPin) {
    btnPin.addEventListener("click", () => {
        isPinned               = !isPinned;
        floatDrag.style.cursor = isPinned ? "default" : "grab";
        btnPin.style.opacity   = isPinned ? "1"       : "0.5";
        btnPin.title           = isPinned ? "Unpin"   : "Pin";
    });
}

// ── Event listeners ───────────────────────────────────────────────────────────

btnStart.addEventListener("click", startTracker);
btnStop.addEventListener("click",  stopTracker);
if (btnPreview) btnPreview.addEventListener("click", togglePreview);

// ── Init ──────────────────────────────────────────────────────────────────────
showPlaceholder();
fetchStatus();
