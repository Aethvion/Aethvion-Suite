const WS_URL   = `ws://${window.location.host}/ws/tracking`;
const API_BASE = `http://${window.location.host}/api/trackers`;

let ws                  = null;
let isPreviewing        = false;
let debugInterval       = null;
let osfLivenessInterval = null;
let isPinned            = false;
let isCollapsed         = false;

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
    if (osf) { syncOsfPort(); fetchOsfStatus(); }
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

// Forward declarations so updateUIState can call them before they are defined below
function stopOsfLiveness() { if (osfLivenessInterval) { clearInterval(osfLivenessInterval); osfLivenessInterval = null; } }

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
        stopOsfLiveness();
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

// ── OSF Process manager ───────────────────────────────────────────────────────

const osfMgrDot       = document.getElementById("osf-mgr-dot");
const osfMgrLabel     = document.getElementById("osf-mgr-label");
const osfInstallSec   = document.getElementById("osf-install-section");
const osfLaunchSec    = document.getElementById("osf-launch-section");
const osfInstallProg  = document.getElementById("osf-install-progress");
const osfProgFill     = document.getElementById("osf-prog-fill");
const osfProgMsg      = document.getElementById("osf-prog-msg");
const btnOsfInstall   = document.getElementById("btn-osf-install");
const btnOsfLaunch    = document.getElementById("btn-osf-launch");
const btnOsfKill      = document.getElementById("btn-osf-kill");
const osfCameraInput  = document.getElementById("osf-camera");

function setOsfMgrState(state) {
    // state: "checking" | "not-installed" | "installed" | "running" | "installing"
    const map = {
        "checking":      ["",        "Checking…"],
        "not-installed": ["",        "Not Installed"],
        "installed":     ["ready",   "Installed — not running"],
        "running":       ["online",  "Process Running"],
        "installing":    ["busy",    "Installing…"],
    };
    const [cls, text] = map[state] || ["", state];
    if (osfMgrDot)   osfMgrDot.className    = "osf-mgr-dot" + (cls ? " " + cls : "");
    if (osfMgrLabel) osfMgrLabel.textContent = text;

    const notInstalled = state === "not-installed" || state === "installing";
    const installed    = state === "installed" || state === "running";
    const running      = state === "running";

    if (osfInstallSec) osfInstallSec.style.display = notInstalled ? "" : "none";
    if (osfLaunchSec)  osfLaunchSec.style.display  = installed    ? "" : "none";
    if (btnOsfLaunch)  btnOsfLaunch.disabled        = running;
    if (btnOsfKill)    btnOsfKill.disabled           = !running;
}

async function fetchOsfStatus() {
    try {
        const res  = await fetch("/api/osf/status");
        const data = await res.json();
        if (data.running)        setOsfMgrState("running");
        else if (data.installed) setOsfMgrState("installed");
        else                     setOsfMgrState("not-installed");
    } catch (_) {
        setOsfMgrState("not-installed");
    }
}

async function installOsf() {
    if (btnOsfInstall) btnOsfInstall.disabled = true;
    setOsfMgrState("installing");
    if (osfInstallProg) osfInstallProg.style.display = "";
    if (osfProgMsg)     osfProgMsg.textContent = "Connecting…";
    if (osfProgFill)  { osfProgFill.style.width = "0%"; osfProgFill.style.background = ""; }

    try {
        const res    = await fetch("/api/osf/install", { method: "POST" });
        const reader = res.body.getReader();
        const dec    = new TextDecoder();
        let   buf    = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });

            const lines = buf.split("\n");
            buf = lines.pop();

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                try {
                    const evt = JSON.parse(line.slice(6));
                    if (osfProgMsg)  osfProgMsg.textContent = evt.msg || "…";
                    if (osfProgFill && evt.pct != null) osfProgFill.style.width = evt.pct + "%";

                    if (evt.step === "done") {
                        if (osfProgFill) osfProgFill.style.width = "100%";
                        await fetchOsfStatus();
                        setTimeout(() => { if (osfInstallProg) osfInstallProg.style.display = "none"; }, 2500);
                    } else if (evt.step === "error") {
                        if (osfProgFill) osfProgFill.style.background = "var(--danger)";
                        if (btnOsfInstall) btnOsfInstall.disabled = false;
                        setOsfMgrState("not-installed");
                    }
                } catch (_) {}
            }
        }
    } catch (e) {
        console.error("OSF install failed:", e);
        if (osfProgMsg) osfProgMsg.textContent = "Network error — try again.";
        if (btnOsfInstall) btnOsfInstall.disabled = false;
        setOsfMgrState("not-installed");
    }
}

async function launchOsf() {
    const port   = osfPortInput   ? parseInt(osfPortInput.value)   || 11573 : 11573;
    const camera = osfCameraInput ? parseInt(osfCameraInput.value) || 0     : 0;
    try {
        if (btnOsfLaunch) btnOsfLaunch.disabled = true;
        if (osfMgrLabel)  osfMgrLabel.textContent = "Starting…";

        const res  = await fetch("/api/osf/launch", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ camera_index: camera, port, host: "127.0.0.1" }),
        });
        const data = await res.json();
        if (data.success) {
            setOsfMgrState("running");
            syncOsfPort();
            startOsfLiveness();

            // Give facetracker ~1.5 s to initialize, then auto-start the Synapse tracker
            // Also verify it's still alive — if it crashed we skip startTracker and show the error
            setTimeout(async () => {
                const checkRes  = await fetch("/api/osf/status");
                const checkData = await checkRes.json();
                if (checkData.running) {
                    if (isOSF()) startTracker();
                } else {
                    stopOsfLiveness();
                    setOsfMgrState("installed");
                    showOsfCrashDiag(await diagnoseOsfCrash());
                }
            }, 1500);
        } else {
            if (btnOsfLaunch) btnOsfLaunch.disabled = false;
            alert("Could not launch OSF: " + (data.error || "unknown error"));
        }
    } catch (e) {
        if (btnOsfLaunch) btnOsfLaunch.disabled = false;
        console.error("OSF launch failed:", e);
    }
}

async function stopOsfProcess() {
    try {
        stopOsfLiveness();
        await fetch("/api/osf/stop-process", { method: "POST" });
        setOsfMgrState("installed");
    } catch (e) {
        console.error("OSF stop failed:", e);
    }
}

/** Analyse the crash log and return a user-friendly diagnosis object. */
async function diagnoseOsfCrash() {
    try {
        const lr    = await fetch("/api/osf/log");
        const ldata = await lr.json();
        const log   = ldata.log || "";

        if (/python\d+\.dll.*could not be found|LoadLibrary.*python/i.test(log)) {
            return {
                type:    "vcredist",
                summary: "Missing Visual C++ Redistributable",
                detail:  "facetracker.exe needs the Microsoft Visual C++ Runtime " +
                         "(2015–2022 x64) which is not installed on this machine.",
                action:  { label: "Download VC++ Redistributable",
                           url: "https://aka.ms/vs/17/release/vc_redist.x64.exe" },
                log,
            };
        }
        if (/no cameras found|cannot open camera|capture failed/i.test(log)) {
            return {
                type:    "camera",
                summary: "Camera not found",
                detail:  "OpenSeeFace could not open camera index " +
                         (osfCameraInput ? osfCameraInput.value : "0") +
                         ". Try a different camera index.",
                log,
            };
        }
        return { type: "unknown", summary: "Process exited", detail: "", log };
    } catch (_) {
        return { type: "unknown", summary: "Process exited", detail: "", log: "" };
    }
}

/** Poll /api/osf/status every 3 s to detect if facetracker crashes. */
function startOsfLiveness() {
    if (osfLivenessInterval) return;
    osfLivenessInterval = setInterval(async () => {
        try {
            const res  = await fetch("/api/osf/status");
            const data = await res.json();
            if (!data.running && data.installed) {
                stopOsfLiveness();
                setOsfMgrState("installed");

                const diag = await diagnoseOsfCrash();
                showOsfCrashDiag(diag);
            }
        } catch (_) {}
    }, 3000);
}

function showOsfCrashDiag(diag) {
    if (osfMgrLabel) osfMgrLabel.textContent = diag.summary;

    // Show progress area with red bar as error indicator
    if (osfInstallProg) osfInstallProg.style.display = "";
    if (osfProgFill)  { osfProgFill.style.width = "100%"; osfProgFill.style.background = "var(--danger)"; }
    if (osfProgMsg)     osfProgMsg.textContent = diag.detail || "See output below.";

    // If there's a fix action, inject a one-time link below the progress message
    const existingLink = document.getElementById("osf-fix-link");
    if (existingLink) existingLink.remove();
    if (diag.action) {
        const a = document.createElement("a");
        a.id        = "osf-fix-link";
        a.href      = diag.action.url;
        a.target    = "_blank";
        a.rel       = "noopener";
        a.className = "osf-link";
        a.style.display     = "block";
        a.style.marginTop   = "6px";
        a.textContent = diag.action.label + " ↗";
        osfProgMsg.insertAdjacentElement("afterend", a);
    }

    // Dump raw log to parameter panel
    if (diag.log) dataOutput.innerText = diag.log;
}


if (btnOsfInstall) btnOsfInstall.addEventListener("click", installOsf);
if (btnOsfLaunch)  btnOsfLaunch.addEventListener("click",  launchOsf);
if (btnOsfKill)    btnOsfKill.addEventListener("click",    stopOsfProcess);

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
