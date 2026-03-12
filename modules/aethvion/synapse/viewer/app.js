const WS_URL = `ws://${window.location.host}/ws/tracking`;
const API_BASE = `http://${window.location.host}/api/trackers`;

let ws = null;

// DOM Elements
const selectTracker = document.getElementById("tracker-select");
const selectSource = document.getElementById("source-select");
const btnStart = document.getElementById("btn-start");
const btnStop = document.getElementById("btn-stop");
const btnPreview = document.getElementById("btn-preview");
const statusText = document.getElementById("status-text");
const dataOutput = document.getElementById("data-output");
const videoFeed = document.getElementById("video-feed");

let isPreviewing = false;

async function fetchStatus() {
    try {
        const res = await fetch(API_BASE);
        const data = await res.json();
        
        // Populate options
        selectTracker.innerHTML = "";
        data.available.forEach(t => {
            const opt = document.createElement("option");
            opt.value = t;
            opt.innerText = t;
            if (t === data.active) opt.selected = true;
            selectTracker.appendChild(opt);
        });

        updateUIState(data.is_running);
    } catch (e) {
        console.error("Failed to fetch tracker status:", e);
        dataOutput.innerText = "Error connecting to Synapse backend.";
    }
}

function updateUIState(isRunning) {
    if (isRunning) {
        statusText.innerText = "Tracking Online";
        statusText.className = "status-online";
        btnStart.disabled = true;
        btnStop.disabled = false;
        selectTracker.disabled = true;
        selectSource.disabled = true;
        connectWebSocket();
        videoFeed.src = "/video_feed?" + new Date().getTime();
    } else {
        statusText.innerText = isPreviewing ? "Preview Active" : "Offline";
        statusText.className = isPreviewing ? "status-online" : "status-offline";
        btnStart.disabled = false;
        btnStop.disabled = true;
        selectTracker.disabled = false;
        if (selectSource) selectSource.disabled = isPreviewing; 
        disconnectWebSocket();
        dataOutput.innerText = "Waiting for data stream...";
        if (!isRunning && !isPreviewing) videoFeed.src = "";
    }
}

async function togglePreview() {
    isPreviewing = !isPreviewing;
    const source = selectSource.value;
    const endpoint = isPreviewing ? "/api/preview/start" : "/api/preview/stop";
    
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: source })
        });
        
        if (res.ok) {
            btnPreview.innerText = isPreviewing ? "Stop Preview" : "Show Preview";
            btnPreview.className = isPreviewing ? "btn danger" : "btn secondary";
            if (isPreviewing) {
                videoFeed.src = "/video_feed?" + new Date().getTime();
            }
            updateUIState(false);
        } else {
            isPreviewing = !isPreviewing; // Revert
            alert("Failed to toggle preview.");
        }
    } catch (e) {
        isPreviewing = !isPreviewing;
        console.error("Preview toggle failed:", e);
    }
}

async function startTracker() {
    const tracker = selectTracker.value;
    const source = selectSource.value;
    if (!tracker) return;
    
    try {
        const res = await fetch(`${API_BASE}/start/${tracker}`, { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: source })
        });
        if (res.ok) {
            updateUIState(true);
        } else {
            const err = await res.json();
            alert("Failed to start: " + err.message);
        }
    } catch (e) {
        console.error("Start failed:", e);
    }
}

async function stopTracker() {
    try {
        await fetch(`${API_BASE}/stop`, { method: 'POST' });
        updateUIState(false);
    } catch (e) {
        console.error("Stop failed:", e);
    }
}

function connectWebSocket() {
    if (ws) return;
    
    ws = new WebSocket(WS_URL);
    ws.onopen = () => console.log("WebSocket Connected");
    
    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "params") {
                // Pretty print the JSON stream live
                dataOutput.innerText = JSON.stringify(msg.params, null, 2);
            }
        } catch (e) {
            console.error("WS parse error:", e);
        }
    };
    
    ws.onclose = () => {
        console.log("WebSocket Disconnected");
        ws = null;
    };
}

function disconnectWebSocket() {
    if (ws) {
        ws.close();
        ws = null;
    }
}

// Event Listeners
btnStart.addEventListener("click", startTracker);
btnStop.addEventListener("click", stopTracker);
btnPreview.addEventListener("click", togglePreview);

// Init
fetchStatus();
