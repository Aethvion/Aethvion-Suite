const WS_URL = `ws://${window.location.host}/ws/tracking`;
const API_BASE = `http://${window.location.host}/api/trackers`;

let ws = null;

// DOM Elements
const selectTracker = document.getElementById("tracker-select");
const btnStart = document.getElementById("btn-start");
const btnStop = document.getElementById("btn-stop");
const statusText = document.getElementById("status-text");
const dataOutput = document.getElementById("data-output");

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
        statusText.innerText = "Online";
        statusText.className = "status-online";
        btnStart.disabled = true;
        btnStop.disabled = false;
        selectTracker.disabled = true;
        connectWebSocket();
    } else {
        statusText.innerText = "Offline";
        statusText.className = "status-offline";
        btnStart.disabled = false;
        btnStop.disabled = true;
        selectTracker.disabled = false;
        disconnectWebSocket();
        dataOutput.innerText = "Waiting for data stream...";
    }
}

async function startTracker() {
    const tracker = selectTracker.value;
    if (!tracker) return;
    
    try {
        const res = await fetch(`${API_BASE}/start/${tracker}`, { method: 'POST' });
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

// Init
fetchStatus();
