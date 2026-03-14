/* Aethvion Audio Editor - Frontend Logic */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let wavesurfer = null;
let currentRegion = null;
let zoomLevel = 50;
const API = '';  // same origin

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

function notify(msg, type = 'info', duration = 3500) {
    const container = document.getElementById('ae-notifications');
    const el = document.createElement('div');
    el.className = `ae-notif ${type}`;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => el.remove(), duration);
}

// ---------------------------------------------------------------------------
// Loading overlay
// ---------------------------------------------------------------------------

function setLoading(active, msg = 'PROCESSING...') {
    const el = document.getElementById('ae-loading');
    const span = el.querySelector('span');
    if (span) span.textContent = msg;
    el.classList.toggle('active', active);
}

// ---------------------------------------------------------------------------
// WaveSurfer init
// ---------------------------------------------------------------------------

function initWaveSurfer() {
    if (wavesurfer) {
        wavesurfer.destroy();
        wavesurfer = null;
    }

    wavesurfer = WaveSurfer.create({
        container: '#waveform',
        waveColor: 'rgba(0, 217, 255, 0.5)',
        progressColor: 'rgba(0, 217, 255, 0.9)',
        cursorColor: '#ffffff',
        cursorWidth: 1,
        height: 120,
        normalize: true,
        responsive: true,
        interact: true,
        fillParent: true,
        backend: 'WebAudio',
        plugins: [
            WaveSurfer.timeline.create({
                container: '#wave-timeline',
                primaryColor: 'rgba(0,217,255,0.5)',
                secondaryColor: 'rgba(0,217,255,0.25)',
                primaryFontColor: 'rgba(255,255,255,0.5)',
                secondaryFontColor: 'rgba(255,255,255,0.3)',
                height: 18,
                fontSize: 10,
            }),
            WaveSurfer.regions.create({
                regionsMinLength: 0.01,
                dragSelection: { slop: 5 },
                color: 'rgba(0, 217, 255, 0.12)',
            }),
        ],
    });

    // Volume from master slider
    const volSlider = document.getElementById('master-vol');
    if (volSlider) wavesurfer.setVolume(parseFloat(volSlider.value));

    // Time updates
    wavesurfer.on('audioprocess', updateTime);
    wavesurfer.on('seek', updateTime);

    // Region events
    wavesurfer.on('region-created', (r) => {
        // Remove previous region
        if (currentRegion && currentRegion.id !== r.id) {
            currentRegion.remove();
        }
        currentRegion = r;
        updateRegionInfo();
    });

    wavesurfer.on('region-updated', (r) => {
        currentRegion = r;
        updateRegionInfo();
    });

    wavesurfer.on('region-removed', () => {
        currentRegion = null;
        document.getElementById('region-info').style.display = 'none';
        document.getElementById('btn-trim').disabled = true;
        document.getElementById('btn-silence').disabled = true;
    });

    // Play/pause state
    wavesurfer.on('play', () => {
        document.getElementById('play-icon').className = 'fas fa-pause';
        document.getElementById('btn-play').querySelector('.fas + span, .fas').nextSibling.textContent = ' PAUSE';
    });
    wavesurfer.on('pause', () => {
        document.getElementById('play-icon').className = 'fas fa-play';
    });
    wavesurfer.on('finish', () => {
        document.getElementById('play-icon').className = 'fas fa-play';
    });
}

function updateTime() {
    if (!wavesurfer) return;
    const cur = wavesurfer.getCurrentTime();
    const dur = wavesurfer.getDuration();
    document.getElementById('time-current').textContent = formatTime(cur);
    document.getElementById('time-total').textContent = formatTime(dur);
}

function updateRegionInfo() {
    if (!currentRegion) return;
    const ri = document.getElementById('region-info');
    ri.style.display = 'inline-flex';
    document.getElementById('region-start').textContent = currentRegion.start.toFixed(3);
    document.getElementById('region-end').textContent = currentRegion.end.toFixed(3);
    document.getElementById('btn-trim').disabled = false;
    document.getElementById('btn-silence').disabled = false;
}

function formatTime(sec) {
    if (isNaN(sec)) return '0:00.00';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toFixed(2).padStart(5, '0')}`;
}

// ---------------------------------------------------------------------------
// Load audio from server (after upload / operation)
// ---------------------------------------------------------------------------

async function reloadPreview(info, waveform) {
    updateHeader(info);
    enableControls(true);

    // Re-init WaveSurfer and load the preview stream
    initWaveSurfer();
    currentRegion = null;

    const url = `${API}/api/audio/preview?t=${Date.now()}`;
    wavesurfer.load(url);

    wavesurfer.on('ready', () => {
        document.getElementById('waveform-container').style.display = 'block';
        document.getElementById('timeline-container').style.display = 'block';
        document.getElementById('playbar').style.display = 'flex';
        document.getElementById('dropzone').style.display = 'none';
        updateTime();
    });

    wavesurfer.on('error', (e) => {
        notify('Waveform load error: ' + e, 'error');
    });
}

function updateHeader(info) {
    document.getElementById('file-info-bar').style.display = 'flex';
    document.getElementById('file-info-empty').style.display = 'none';
    document.getElementById('hdr-filename').textContent = info.filename || '—';

    const dur = info.duration_ms / 1000;
    const m = Math.floor(dur / 60);
    const s = (dur % 60).toFixed(1);
    document.getElementById('hdr-duration').textContent = `${m}:${s.padStart(4,'0')}`;
    document.getElementById('hdr-samplerate').textContent = `${info.sample_rate} Hz`;
    document.getElementById('hdr-channels').textContent = info.channels === 1 ? 'Mono' : 'Stereo';
    document.getElementById('hdr-bitdepth').textContent = `${info.bit_depth}-bit`;
}

function enableControls(on) {
    const ids = [
        'btn-play','btn-stop','btn-skip-back','btn-skip-fwd',
        'btn-zoom-in','btn-zoom-out','btn-zoom-fit',
        'btn-undo','btn-reset',
        'btn-export-wav','btn-export-mp3',
        'btn-fade-in','btn-fade-out','btn-normalize','btn-volume',
        'btn-speed','btn-reverse','btn-crop-silence',
        'btn-to-mono','btn-to-stereo','btn-resample',
    ];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = !on;
    });
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

async function uploadFile(file) {
    setLoading(true, 'LOADING AUDIO...');
    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch(`${API}/api/audio/upload`, { method: 'POST', body: fd });
        const data = await res.json();
        setLoading(false);
        if (data.success) {
            await reloadPreview(data.info, data.waveform);
            notify(`Loaded: ${data.info.filename}`, 'success');
        } else {
            notify(data.error || 'Upload failed', 'error');
        }
    } catch (e) {
        setLoading(false);
        notify('Upload error: ' + e.message, 'error');
    }
}

// ---------------------------------------------------------------------------
// Operations
// ---------------------------------------------------------------------------

async function applyOp(op, params = {}) {
    setLoading(true);
    try {
        const res = await fetch(`${API}/api/audio/operation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ op, params }),
        });
        const data = await res.json();
        setLoading(false);
        if (data.success) {
            await reloadPreview(data.info, data.waveform);
            notify(`Applied: ${op}`, 'success');
        } else {
            notify(data.error || 'Operation failed', 'error');
        }
    } catch (e) {
        setLoading(false);
        notify('Error: ' + e.message, 'error');
    }
}

async function undoOp() {
    setLoading(true, 'UNDOING...');
    try {
        const res = await fetch(`${API}/api/audio/undo`, { method: 'POST' });
        const data = await res.json();
        setLoading(false);
        if (data.success) {
            await reloadPreview(data.info, data.waveform);
            notify('Undone', 'info');
        } else {
            notify(data.error || 'Nothing to undo', 'warning');
        }
    } catch (e) {
        setLoading(false);
        notify('Undo error: ' + e.message, 'error');
    }
}

async function resetAudio() {
    if (!confirm('Reset to original? All edits will be lost.')) return;
    setLoading(true, 'RESETTING...');
    try {
        const res = await fetch(`${API}/api/audio/reset`, { method: 'POST' });
        const data = await res.json();
        setLoading(false);
        if (data.success) {
            await reloadPreview(data.info, data.waveform);
            notify('Reset to original', 'info');
        } else {
            notify(data.error || 'Reset failed', 'error');
        }
    } catch (e) {
        setLoading(false);
        notify('Reset error: ' + e.message, 'error');
    }
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

function exportAudio(fmt) {
    const url = `${API}/api/audio/export?format=${fmt}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    a.click();
    notify(`Exporting as ${fmt.toUpperCase()}...`, 'info');
}

// ---------------------------------------------------------------------------
// Drag & Drop
// ---------------------------------------------------------------------------

function initDropzone() {
    const dz = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');

    dz.addEventListener('dragover', (e) => {
        e.preventDefault();
        dz.classList.add('drag-over');
    });
    dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
    dz.addEventListener('drop', (e) => {
        e.preventDefault();
        dz.classList.remove('drag-over');
        const f = e.dataTransfer.files[0];
        if (f) uploadFile(f);
    });

    // Also allow dropping on the whole waveform area when file is loaded
    const wfPanel = document.querySelector('.ae-waveform-panel');
    wfPanel.addEventListener('dragover', (e) => {
        e.preventDefault();
        if (wavesurfer) {
            wfPanel.style.outline = '2px dashed var(--primary)';
        }
    });
    wfPanel.addEventListener('dragleave', () => {
        wfPanel.style.outline = '';
    });
    wfPanel.addEventListener('drop', (e) => {
        e.preventDefault();
        wfPanel.style.outline = '';
        const f = e.dataTransfer.files[0];
        if (f) uploadFile(f);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files[0]) uploadFile(e.target.files[0]);
        fileInput.value = '';
    });
}

// ---------------------------------------------------------------------------
// Slider value displays
// ---------------------------------------------------------------------------

function initSliders() {
    const defs = [
        ['fade-in-dur',   (v) => `${(v/1000).toFixed(1)}s`,  'fade-in-val'],
        ['fade-out-dur',  (v) => `${(v/1000).toFixed(1)}s`,  'fade-out-val'],
        ['vol-db',        (v) => `${v >= 0 ? '+' : ''}${v} dB`, 'vol-db-val'],
        ['speed-rate',    (v) => `${parseFloat(v).toFixed(2)}×`, 'speed-rate-val'],
        ['crop-thresh',   (v) => `${v} dB`,                   'crop-thresh-val'],
    ];
    defs.forEach(([inputId, fmt, displayId]) => {
        const inp = document.getElementById(inputId);
        const disp = document.getElementById(displayId);
        if (!inp || !disp) return;
        const update = () => disp.textContent = fmt(inp.value);
        inp.addEventListener('input', update);
        update();
    });
}

// ---------------------------------------------------------------------------
// Button wiring
// ---------------------------------------------------------------------------

function initButtons() {
    // File
    document.getElementById('btn-open').addEventListener('click', () => {
        document.getElementById('file-input').click();
    });

    // Playback
    document.getElementById('btn-play').addEventListener('click', () => {
        if (!wavesurfer) return;
        wavesurfer.playPause();
    });
    document.getElementById('btn-stop').addEventListener('click', () => {
        if (!wavesurfer) return;
        wavesurfer.stop();
    });
    document.getElementById('btn-skip-back').addEventListener('click', () => {
        if (!wavesurfer) return;
        wavesurfer.setCurrentTime(Math.max(0, wavesurfer.getCurrentTime() - 5));
    });
    document.getElementById('btn-skip-fwd').addEventListener('click', () => {
        if (!wavesurfer) return;
        wavesurfer.setCurrentTime(Math.min(wavesurfer.getDuration(), wavesurfer.getCurrentTime() + 5));
    });

    // Zoom
    document.getElementById('btn-zoom-in').addEventListener('click', () => {
        zoomLevel = Math.min(500, zoomLevel + 30);
        if (wavesurfer) wavesurfer.zoom(zoomLevel);
    });
    document.getElementById('btn-zoom-out').addEventListener('click', () => {
        zoomLevel = Math.max(10, zoomLevel - 30);
        if (wavesurfer) wavesurfer.zoom(zoomLevel);
    });
    document.getElementById('btn-zoom-fit').addEventListener('click', () => {
        zoomLevel = 50;
        if (wavesurfer) wavesurfer.zoom(zoomLevel);
    });

    // Volume
    document.getElementById('master-vol').addEventListener('input', (e) => {
        if (wavesurfer) wavesurfer.setVolume(parseFloat(e.target.value));
    });

    // Edit
    document.getElementById('btn-undo').addEventListener('click', undoOp);
    document.getElementById('btn-reset').addEventListener('click', resetAudio);

    // Export
    document.getElementById('btn-export-wav').addEventListener('click', () => exportAudio('wav'));
    document.getElementById('btn-export-mp3').addEventListener('click', () => exportAudio('mp3'));

    // Trim / Silence
    document.getElementById('btn-trim').addEventListener('click', () => {
        if (!currentRegion) { notify('Select a region first', 'warning'); return; }
        applyOp('trim', {
            start_ms: currentRegion.start * 1000,
            end_ms: currentRegion.end * 1000,
        });
    });
    document.getElementById('btn-silence').addEventListener('click', () => {
        if (!currentRegion) { notify('Select a region first', 'warning'); return; }
        applyOp('silence', {
            start_ms: currentRegion.start * 1000,
            end_ms: currentRegion.end * 1000,
        });
    });
    document.getElementById('btn-crop-silence').addEventListener('click', () => {
        applyOp('crop_silence', {
            threshold_db: parseFloat(document.getElementById('crop-thresh').value),
        });
    });

    // Fade
    document.getElementById('btn-fade-in').addEventListener('click', () => {
        applyOp('fade_in', { duration_ms: parseFloat(document.getElementById('fade-in-dur').value) });
    });
    document.getElementById('btn-fade-out').addEventListener('click', () => {
        applyOp('fade_out', { duration_ms: parseFloat(document.getElementById('fade-out-dur').value) });
    });

    // Dynamics
    document.getElementById('btn-normalize').addEventListener('click', () => applyOp('normalize'));
    document.getElementById('btn-volume').addEventListener('click', () => {
        applyOp('volume', { db: parseFloat(document.getElementById('vol-db').value) });
    });

    // Speed / Reverse
    document.getElementById('btn-speed').addEventListener('click', () => {
        applyOp('speed', { rate: parseFloat(document.getElementById('speed-rate').value) });
    });
    document.getElementById('btn-reverse').addEventListener('click', () => applyOp('reverse'));

    // Format
    document.getElementById('btn-to-mono').addEventListener('click', () => applyOp('stereo_to_mono'));
    document.getElementById('btn-to-stereo').addEventListener('click', () => applyOp('mono_to_stereo'));
    document.getElementById('btn-resample').addEventListener('click', () => {
        applyOp('resample', { sample_rate: parseInt(document.getElementById('resample-rate').value) });
    });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    initDropzone();
    initSliders();
    initButtons();
    enableControls(false);
});
