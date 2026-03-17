/* =============================================================
   Aethvion Drive Info — Frontend
   Squarified treemap + directory tree, mirrors WinDirStat.
   ============================================================= */
(function () {

/* ── DOM refs ─────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const overlay       = $("di-overlay");
const ovTitle       = $("ov-title");
const ovPath        = $("ov-path");
const ovFill        = $("ov-fill");
const ovStats       = $("ov-stats");
const btnCancel     = $("btn-cancel");
const driveSelect   = $("drive-select");
const scanPathInput = $("scan-path");
const btnScan       = $("btn-scan");
const savedSelect   = $("saved-select");
const btnDelScan    = $("btn-del-scan");
const breadcrumb    = $("di-breadcrumb");
const treeBody      = $("tree-body");
const canvas        = $("di-canvas");
const tooltip       = $("di-tooltip");
const legend        = $("di-legend");
const statusBar     = $("di-status");
const diLeft        = $("di-left");
const diResizer     = $("di-resizer");
const diRight       = $("di-right");
const ctx           = canvas.getContext("2d");

/* ── State ────────────────────────────────────────────────────── */
let currentScan  = null;   // full .eathscan payload
let navStack     = [];     // breadcrumb node history
let hitCells     = [];     // [{node, x,y,w,h}] for mouse hit-testing
let sortBy       = "size"; // "size" | "name" | "count"
let pollTimer    = null;
let hoveredNode  = null;   // node currently under mouse (tree or canvas)
let searchTimer  = null;

/* ── Extension colour map ─────────────────────────────────────── */
const EXT_COLORS_NAMED = {
    ".exe":"#e05252", ".dll":"#e07a52", ".sys":"#e05252",
    ".bat":"#e0a052", ".cmd":"#e0a052", ".ps1":"#5b7ce0",
    ".py" :"#4ec9b0", ".js" :"#f7df1e", ".ts" :"#2f74c0",
    ".html":"#e06c52",".css":"#5bc0e0", ".json":"#f0c060",
    ".xml":"#a0c070", ".yaml":"#a0c070",".yml":"#a0c070",
    ".mp3":"#c04ec9", ".mp4":"#7b4ec9", ".wav":"#c04ec9",
    ".flac":"#c04ec9",".mkv":"#7b4ec9", ".avi":"#7b4ec9",
    ".jpg":"#4ec94e", ".jpeg":"#4ec94e",".png":"#60c0a0",
    ".gif":"#80e060", ".svg":"#80e0c0", ".webp":"#60c0a0",
    ".pdf":"#e06060", ".doc":"#3a7bd5", ".docx":"#3a7bd5",
    ".xls":"#1d7830", ".xlsx":"#1d7830",".pptx":"#c94e4e",
    ".zip":"#c0a030", ".rar":"#c0a030", ".7z":"#c0a030",
    ".tar":"#c0a030", ".gz":"#c0a030",
    ".txt":"#aaaaaa", ".log":"#888888", ".ini":"#888888",
    ".iso":"#e07060", ".img":"#e07060",
    ".db" :"#5080c0", ".sqlite":"#5080c0",
};

function extColor(ext) {
    if (EXT_COLORS_NAMED[ext]) return EXT_COLORS_NAMED[ext];
    // deterministic hash → hsl
    let h = 5381;
    for (let i = 0; i < ext.length; i++) h = ((h << 5) + h) ^ ext.charCodeAt(i);
    return `hsl(${Math.abs(h) % 360},55%,48%)`;
}

/* ── Utilities ────────────────────────────────────────────────── */
function fmtBytes(b) {
    if (b == null) return "–";
    const units = ["B","KB","MB","GB","TB"];
    let i = 0; let v = b;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}
function fmtNum(n) { return n == null ? "–" : n.toLocaleString(); }
function escHtml(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

/* ── Squarified treemap layout ────────────────────────────────── */
/* Returns items with ._x ._y ._w ._h set (in-place). */
function squarify(items, x, y, w, h) {
    if (!items.length || w < 1 || h < 1) return;
    const total = items.reduce((s, it) => s + it.size, 0);
    if (!total) return;
    const sorted = [...items].sort((a, b) => b.size - a.size);
    _sq(sorted, x, y, w, h, total);
}

function _sq(items, x, y, w, h, total) {
    if (!items.length || total <= 0 || w < 1 || h < 1) return;
    const horiz   = w >= h;
    const strip   = horiz ? h : w;   // dimension along the strip
    const band    = horiz ? w : h;   // dimension of remaining block

    let row = [], rowSum = 0;
    let i   = 0;

    for (; i < items.length; i++) {
        const cand    = [...row, items[i]];
        const candSum = rowSum + items[i].size;
        const sw      = band * candSum / total;
        if (row.length && _worst(cand, candSum, strip, sw) > _worst(row, rowSum, strip, band * rowSum / total)) {
            break;
        }
        row.push(items[i]);
        rowSum += items[i].size;
    }

    // lay out the accepted row as a strip
    const sw  = band * rowSum / total;
    let   pos = horiz ? y : x;
    for (const it of row) {
        const len = Math.max(0, strip * it.size / rowSum);
        if (horiz) { it._x = x;   it._y = pos; it._w = sw;  it._h = len; }
        else       { it._x = pos; it._y = y;   it._w = len; it._h = sw;  }
        pos += len;
    }

    // recurse on remaining items
    const rest = items.slice(i);
    if (rest.length) {
        const rTotal = total - rowSum;
        if (horiz) _sq(rest, x + sw, y, w - sw, h, rTotal);
        else       _sq(rest, x, y + sw, w, h - sw, rTotal);
    }
}

function _worst(row, rowSum, strip, sw) {
    if (!rowSum || !sw || !strip) return Infinity;
    let w = 0;
    for (const it of row) {
        const len = strip * it.size / rowSum;
        if (!len) continue;
        w = Math.max(w, Math.max(sw / len, len / sw));
    }
    return w;
}

/* ── Treemap rendering ────────────────────────────────────────── */
const DPR       = window.devicePixelRatio || 1;
const DIR_HDR_H = 16;   // px — directory label bar height
const MIN_LABEL = 32;   // min rect size to draw a label
const MIN_CHILD = 3;    // min rect size to recurse into children

function resizeCanvas() {
    const rect = diRight.getBoundingClientRect();
    canvas.width  = Math.round(rect.width  * DPR);
    canvas.height = Math.round(rect.height * DPR);
    canvas.style.width  = rect.width  + "px";
    canvas.style.height = rect.height + "px";
}

function renderTreemap() {
    resizeCanvas();
    hitCells = [];
    const node = navStack.length ? navStack[navStack.length - 1] : null;
    if (!node) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#0d0d10";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        return;
    }
    ctx.fillStyle = "#0d0d10";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const W = canvas.width / DPR;
    const H = canvas.height / DPR;
    _renderNode(node, 2, 2, W - 4, H - 4, 0);

    // Draw highlight for hoveredNode if it's within the current view
    if (hoveredNode) {
        const cell = hitCells.find(c => c.node.path === hoveredNode.path);
        if (cell) {
            ctx.save();
            ctx.strokeStyle = "#fff";
            ctx.lineWidth = 2 * DPR;
            ctx.setLineDash([5 * DPR, 5 * DPR]);
            ctx.strokeRect(cell.x * DPR, cell.y * DPR, cell.w * DPR, cell.h * DPR);
            ctx.restore();
        }
    }
}

function _renderNode(node, x, y, w, h, depth) {
    if (w < 2 || h < 2) return;

    const children = (node.children || []).filter(c => c.size > 0);
    if (!children.length) return;

    squarify(children, x, y, w, h);

    for (const child of children) {
        const cx = child._x, cy = child._y;
        const cw = child._w, ch = child._h;
        if (cw < 1 || ch < 1) continue;

        if (child.type === "file") {
            _drawFile(child, cx, cy, cw, ch);
        } else {
            _drawDir(child, cx, cy, cw, ch, depth);
        }
    }
}

function _drawFile(node, x, y, w, h) {
    const color = extColor(node.ext || "");
    const cx = x * DPR, cy = y * DPR, cw = w * DPR, ch = h * DPR;

    // Fill
    ctx.fillStyle = color + "cc";
    ctx.fillRect(cx, cy, cw, ch);

    // 1px dark border
    ctx.strokeStyle = "rgba(0,0,0,.55)";
    ctx.lineWidth   = 1;
    ctx.strokeRect(cx + .5, cy + .5, cw - 1, ch - 1);

    // Label if large enough
    if (w > MIN_LABEL && h > MIN_LABEL) {
        _drawLabel(node.name, cx + 3, cy + 3, cw - 6, ch - 6, "#fff", 10);
    }

    hitCells.push({ node, x, y, w, h });
}

function _drawDir(node, x, y, w, h, depth) {
    const cx = x * DPR, cy = y * DPR, cw = w * DPR, ch = h * DPR;

    // Directory background
    let dirColor = "#14141e";
    if (depth > 0) {
        // Variation based on name hash for sectioning
        let h = 0;
        const n = node.name || "";
        for(let i=0; i<n.length; i++) h = ((h << 5) - h) + n.charCodeAt(i);
        const hue = Math.abs(h % 360);
        dirColor = `hsla(${hue}, 20%, 15%, 0.8)`;
    }
    ctx.fillStyle = depth === 0 ? "#0f0f16" : dirColor;
    ctx.fillRect(cx, cy, cw, ch);

    // Title bar
    const hdrH = Math.min(DIR_HDR_H, h);
    ctx.fillStyle = "#1c1c2e";
    ctx.fillRect(cx, cy, cw, hdrH * DPR);

    // Border
    ctx.strokeStyle = "#2a2a3a";
    ctx.lineWidth   = 1;
    ctx.strokeRect(cx + .5, cy + .5, cw - 1, ch - 1);

    // Directory label
    if (w > 20) {
        _drawLabel(node.name, cx + 4, cy + 2, cw - 8, hdrH * DPR - 4, "#ccc", 10);
    }

    hitCells.push({ node, x, y, w, h });

    // Recurse into children if enough space remains
    const innerY = y + hdrH;
    const innerH = h - hdrH - 1;
    if (cw > MIN_CHILD && innerH > MIN_CHILD) {
        _renderNode(node, x + 1, innerY, w - 2, innerH, depth + 1);
    }
}

function _drawLabel(text, cx, cy, maxW, maxH, color, size) {
    if (maxW < 8 || maxH < 8) return;
    ctx.save();
    ctx.fillStyle   = color;
    ctx.font        = `${size * DPR}px "Segoe UI",sans-serif`;
    ctx.textBaseline = "top";
    ctx.textAlign   = "left";
    // clip to rect
    ctx.beginPath();
    ctx.rect(cx, cy, maxW, maxH);
    ctx.clip();
    ctx.fillText(text, cx, cy);
    ctx.restore();
}

/* ── Hit-testing ──────────────────────────────────────────────── */
function hitTest(mouseX, mouseY) {
    // Search in reverse (topmost drawn = last in array = files on top)
    for (let i = hitCells.length - 1; i >= 0; i--) {
        const c = hitCells[i];
        if (mouseX >= c.x && mouseX <= c.x + c.w &&
            mouseY >= c.y && mouseY <= c.y + c.h) {
            return c.node;
        }
    }
    return null;
}

/* ── Tooltip ──────────────────────────────────────────────────── */
function showTooltip(node, mouseX, mouseY) {
    let html = `<b>${escHtml(node.name)}</b><br>`;
    html += `Size: <b>${fmtBytes(node.size)}</b><br>`;
    if (node.type === "dir") {
        html += `Files: ${fmtNum(node.file_count)}<br>`;
        html += `Dirs:  ${fmtNum(node.dir_count)}<br>`;
    } else {
        html += `Type: ${escHtml(node.ext || "(none)")}`;
    }
    tooltip.innerHTML = html;
    tooltip.classList.remove("di-hidden");
    positionTooltip(mouseX, mouseY);
}

function positionTooltip(mx, my) {
    const bRect = diRight.getBoundingClientRect();
    const tw = tooltip.offsetWidth + 16;
    const th = tooltip.offsetHeight + 16;
    let lx = mx + 14, ly = my + 14;
    if (lx + tw > bRect.width)  lx = mx - tw + 14;
    if (ly + th > bRect.height) ly = my - th + 14;
    tooltip.style.left = lx + "px";
    tooltip.style.top  = ly + "px";
}

/* ── Breadcrumb ───────────────────────────────────────────────── */
function renderBreadcrumb() {
    breadcrumb.innerHTML = "";
    navStack.forEach((node, idx) => {
        if (idx > 0) {
            const sep = document.createElement("span");
            sep.className = "di-crumb-sep";
            sep.textContent = "›";
            breadcrumb.appendChild(sep);
        }
        const crumb = document.createElement("span");
        crumb.className = "di-crumb" + (idx === navStack.length - 1 ? " active" : "");
        crumb.innerHTML = idx === 0
            ? `<i class="fas fa-home"></i> ${escHtml(node.name || node.path)}`
            : escHtml(node.name);
        crumb.addEventListener("click", () => {
            navStack = navStack.slice(0, idx + 1);
            renderBreadcrumb();
            renderTreemap();
            highlightTreeRow(node.path);
        });
        breadcrumb.appendChild(crumb);
    });
}

/* ── Tree view ────────────────────────────────────────────────── */
function buildSortedChildren(node) {
    const dirs  = (node.children || []).filter(c => c.type === "dir");
    const files = (node.children || []).filter(c => c.type === "file");
    if (sortBy === "name") {
        dirs.sort( (a,b) => a.name.localeCompare(b.name));
        files.sort((a,b) => a.name.localeCompare(b.name));
    } else if (sortBy === "count") {
        dirs.sort( (a,b) => (b.file_count||0) - (a.file_count||0));
        files.sort((a,b) => b.size - a.size);
    } else {
        dirs.sort( (a,b) => b.size - a.size);
        files.sort((a,b) => b.size - a.size);
    }
    return [...dirs, ...files];
}

function renderTree(root) {
    treeBody.innerHTML = "";
    const topSize = root.size || 1;
    appendTreeNode(root, treeBody, 0, topSize, true);
}

function appendTreeNode(node, container, depth, topSize, expanded) {
    const isDir = node.type === "dir";

    const row = document.createElement("div");
    row.className        = "di-tree-row";
    row.dataset.path     = node.path;
    row.style.paddingLeft = (8 + depth * 14) + "px";

    const arrow = document.createElement("span");
    arrow.className = "di-tree-arrow";
    arrow.innerHTML = isDir ? '<i class="fas fa-chevron-right"></i>' : "";
    row.appendChild(arrow);

    const icon = document.createElement("span");
    icon.className = "di-tree-icon";
    if (isDir) {
        icon.style.color = "#f0c060";
        icon.innerHTML   = '<i class="fas fa-folder"></i>';
    } else {
        icon.style.color = extColor(node.ext || "");
        icon.innerHTML   = '<i class="fas fa-file"></i>';
    }
    row.appendChild(icon);

    const name = document.createElement("span");
    name.className   = "di-tree-name";
    name.textContent = node.name;
    row.appendChild(name);

    const sizeEl = document.createElement("span");
    sizeEl.className   = "di-tree-size";
    sizeEl.textContent = fmtBytes(node.size);
    row.appendChild(sizeEl);

    const barWrap = document.createElement("span");
    barWrap.className = "di-tree-bar-wrap";
    const bar = document.createElement("span");
    bar.className = "di-tree-bar";
    bar.style.width = Math.min(100, (node.size / topSize) * 100) + "%";
    barWrap.appendChild(bar);
    row.appendChild(barWrap);

    container.appendChild(row);

    // Children container (for dirs)
    let childrenEl = null;
    if (isDir && node.children && node.children.length) {
        childrenEl = document.createElement("div");
        childrenEl.className = "di-tree-children" + (expanded ? " open" : "");
        container.appendChild(childrenEl);

        if (expanded) {
            const sorted = buildSortedChildren(node);
            for (const child of sorted.slice(0, 200)) {  // limit for performance
                appendTreeNode(child, childrenEl, depth + 1, topSize, false);
            }
        }

        arrow.className = "di-tree-arrow" + (expanded ? " open" : "");

        // Toggle expand on click
        row.addEventListener("click", e => {
            const open = childrenEl.classList.toggle("open");
            arrow.className = "di-tree-arrow" + (open ? " open" : "");
            if (open && !childrenEl.children.length) {
                const sorted = buildSortedChildren(node);
                for (const child of sorted.slice(0, 200)) {
                    appendTreeNode(child, childrenEl, depth + 1, topSize, false);
                }
            }
            // Navigate treemap to this directory
            navigateTo(node);
        });
    } else {
        row.addEventListener("click", () => navigateTo(node.type === "dir" ? node : getParent(node)));
    }

    // Hover sync
    row.addEventListener("mouseenter", () => {
        hoveredNode = node;
        renderTreemap();
    });
    row.addEventListener("mouseleave", () => {
        if (hoveredNode === node) {
            hoveredNode = null;
            renderTreemap();
        }
    });

    return row;
}

/* Navigate treemap to a given directory node */
function navigateTo(node) {
    if (!node) return;
    // Build nav stack: find path from root
    const root = currentScan.tree;
    const stack = findPathToNode(root, node.path);
    if (stack) {
        navStack = stack;
        renderBreadcrumb();
        renderTreemap();
    }
    highlightTreeRow(node.path);
}

function findPathToNode(root, targetPath) {
    if (root.path === targetPath) return [root];
    for (const child of root.children || []) {
        const found = findPathToNode(child, targetPath);
        if (found) return [root, ...found];
    }
    return null;
}

function getParent(node) {
    return findParentNode(currentScan.tree, node.path);
}
function findParentNode(root, targetPath) {
    for (const child of root.children || []) {
        if (child.path === targetPath) return root;
        const found = findParentNode(child, targetPath);
        if (found) return found;
    }
    return null;
}

function highlightTreeRow(path) {
    treeBody.querySelectorAll(".di-tree-row.hovered").forEach(r => r.classList.remove("hovered"));
    treeBody.querySelectorAll(".di-tree-row.active").forEach(r => r.classList.remove("active"));
    const row = treeBody.querySelector(`[data-path="${CSS.escape(path)}"]`);
    if (row) {
        row.classList.add("active");
        row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
}

function syncHoverToTree(path) {
    treeBody.querySelectorAll(".di-tree-row.hovered").forEach(r => r.classList.remove("hovered"));
    if (!path) return;
    const row = treeBody.querySelector(`[data-path="${CSS.escape(path)}"]`);
    if (row) {
        row.classList.add("hovered");
    }
}

/* ── Extension legend ─────────────────────────────────────────── */
function renderLegend(extensions) {
    legend.innerHTML = "";
    const entries = Object.entries(extensions).slice(0, 20);
    for (const [ext, info] of entries) {
        const item = document.createElement("span");
        item.className = "di-legend-item";
        item.innerHTML = `
            <span class="di-legend-dot" style="background:${extColor(ext)}"></span>
            <span class="di-legend-label">${escHtml(ext || "(none)")}</span>
            <span class="di-legend-size">${fmtBytes(info.size)}</span>`;
        legend.appendChild(item);
    }
}

/* ── Load & display a scan ────────────────────────────────────── */
function displayScan(scan) {
    currentScan = scan;
    navStack    = [scan.tree];
    renderBreadcrumb();
    renderTree(scan.tree);
    renderTreemap();
    renderLegend(scan.extensions || {});

    const m = scan.meta || {};
    statusBar.textContent =
        `${fmtNum(m.total_files)} files  ·  ${fmtNum(m.total_dirs)} dirs  ·  `
        + `${fmtBytes(m.total_size)}  ·  Scanned: ${m.root_path}`;
}

/* ── Saved scans dropdown ─────────────────────────────────────── */
async function loadSavedScans() {
    try {
        const res = await fetch("/api/scans");
        if (!res.ok) return;
        const list = await res.json();
        savedSelect.innerHTML = '<option value="">Load saved scan…</option>';
        for (const s of list) {
            const opt = document.createElement("option");
            opt.value = s.filename;
            const meta = s.meta || {};
            const date = meta.scan_date ? meta.scan_date.slice(0, 10) : "";
            opt.textContent = `${meta.root_path || s.filename}  (${date})`;
            savedSelect.appendChild(opt);
        }
    } catch (e) {
        console.warn("loadSavedScans failed:", e);
    }
}

/* ── Drive list ───────────────────────────────────────────────── */
async function loadDrives() {
    try {
        const drives = await fetch("/api/drives").then(r => r.json());
        driveSelect.innerHTML = '<option value="">Drive…</option>';
        for (const d of drives) {
            const opt = document.createElement("option");
            opt.value = d.path;
            const pct = d.total > 0 ? Math.round(d.used / d.total * 100) : 0;
            opt.textContent = `${d.label}  ${fmtBytes(d.free)} free  (${pct}% used)`;
            driveSelect.appendChild(opt);
        }
    } catch (_) {}
}

/* ── Scan flow ────────────────────────────────────────────────── */
async function startScan(path) {
    if (!path.trim()) return;

    overlay.classList.remove("hidden");
    ovTitle.textContent = "Starting scan…";
    ovPath.textContent  = path;
    ovFill.style.width  = "0%";
    ovStats.textContent = "";

    try {
        const res = await fetch("/api/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path }),
        });
        if (!res.ok) {
            const err = await res.json();
            alert("Could not start scan: " + (err.detail || res.status));
            overlay.classList.add("hidden");
            return;
        }
    } catch (e) {
        alert("Network error: " + e.message);
        overlay.classList.add("hidden");
        return;
    }

    pollTimer = setInterval(pollScan, 400);
}

async function pollScan() {
    try {
        const r  = await fetch("/api/scan/status");
        if (!r.ok) { clearInterval(pollTimer); overlay.classList.add("hidden"); return; }
        const st = await r.json();

        ovTitle.textContent = st.cancelled ? "Cancelled"
                            : st.done      ? "Saving…"
                            : "Scanning…";
        ovPath.textContent  = st.current_path || "";
        ovStats.textContent =
            `${fmtNum(st.files)} files  ·  ${fmtNum(st.dirs)} dirs  `
            + `·  ${fmtBytes(st.bytes_total)}  ·  ${(st.elapsed || 0).toFixed(0)}s`;

        /* Scan finished with an error */
        if (!st.running && st.error) {
            clearInterval(pollTimer);
            overlay.classList.add("hidden");
            alert("Scan error: " + st.error);
            return;
        }

        /* Scan finished successfully */
        if (st.done) {
            clearInterval(pollTimer);
            /* Keep overlay visible while loading (large scans can take a moment) */
            ovTitle.textContent = "Loading results…";
            ovPath.textContent  = "Parsing scan data…";
            try {
                const res = await fetch("/api/scan/result");
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const result = await res.json();
                displayScan(result);
                await loadSavedScans();
            } catch (e) {
                alert("Failed to load scan result: " + e.message);
            } finally {
                overlay.classList.add("hidden");
            }
        }
    } catch (e) {
        clearInterval(pollTimer);
        overlay.classList.add("hidden");
    }
}

/* ── Sort buttons ─────────────────────────────────────────────── */
document.querySelectorAll(".di-sort-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".di-sort-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        sortBy = btn.dataset.sort;
        if (currentScan) renderTree(currentScan.tree);
    });
});

/* ── Mouse interaction on canvas ─────────────────────────────── */
canvas.addEventListener("mousemove", e => {
    const rect = canvas.getBoundingClientRect();
    const mx   = e.clientX - rect.left;
    const my   = e.clientY - rect.top;
    const node = hitTest(mx, my);
    if (node) {
        showTooltip(node, mx, my);
        canvas.style.cursor = "pointer";
        if (hoveredNode !== node) {
            hoveredNode = node;
            syncHoverToTree(node.path);
            renderTreemap(); // Draw highlight
        }
    } else {
        tooltip.classList.add("di-hidden");
        canvas.style.cursor = "default";
        if (hoveredNode) {
            hoveredNode = null;
            syncHoverToTree(null);
            renderTreemap();
        }
    }
});

canvas.addEventListener("mouseleave", () => {
    tooltip.classList.add("di-hidden");
    hoveredNode = null;
    syncHoverToTree(null);
    renderTreemap();
});

canvas.addEventListener("click", e => {
    const rect = canvas.getBoundingClientRect();
    const mx   = e.clientX - rect.left;
    const my   = e.clientY - rect.top;
    const node = hitTest(mx, my);
    if (!node) return;
    if (node.type === "dir") {
        navStack.push(node);
        renderBreadcrumb();
        renderTreemap();
        highlightTreeRow(node.path);
    } else {
        // Click file → highlight its parent dir in tree
        const parent = getParent(node);
        if (parent) highlightTreeRow(parent.path);
    }
});

/* Double-click to zoom back out one level */
canvas.addEventListener("dblclick", () => {
    if (navStack.length > 1) {
        navStack.pop();
        renderBreadcrumb();
        renderTreemap();
    }
});

/* ── Header controls ──────────────────────────────────────────── */
driveSelect.addEventListener("change", () => {
    if (driveSelect.value) scanPathInput.value = driveSelect.value;
});

btnScan.addEventListener("click", () => startScan(scanPathInput.value));
scanPathInput.addEventListener("keydown", e => {
    if (e.key === "Enter") startScan(scanPathInput.value);
});

btnCancel.addEventListener("click", async () => {
    await fetch("/api/scan/cancel", { method: "POST" });
    clearInterval(pollTimer);
    overlay.classList.add("hidden");
});

savedSelect.addEventListener("change", async () => {
    const fn = savedSelect.value;
    if (!fn) { btnDelScan.classList.add("di-hidden"); return; }
    btnDelScan.classList.remove("di-hidden");

    /* Show loading overlay while streaming (large scans take a moment) */
    overlay.classList.remove("hidden");
    ovTitle.textContent = "Loading scan…";
    ovPath.textContent  = fn;
    ovFill.style.width  = "0%";
    ovStats.textContent = "";

    try {
        const res = await fetch(`/api/scans/${encodeURIComponent(fn)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status} — ${(await res.json().catch(()=>({}))).detail || ""}`);
        const scan = await res.json();
        displayScan(scan);
    } catch (e) {
        alert("Failed to load scan: " + e.message);
    } finally {
        overlay.classList.add("hidden");
    }
});

btnDelScan.addEventListener("click", async () => {
    const fn = savedSelect.value;
    if (!fn) return;
    if (!confirm(`Delete scan "${fn}"?`)) return;
    await fetch(`/api/scans/${encodeURIComponent(fn)}`, { method: "DELETE" });
    btnDelScan.classList.add("di-hidden");
    await loadSavedScans();
});

/* ── Resize handle (left/right split) ────────────────────────── */
let resizing = false, resizeStartX = 0, resizeStartW = 0;

diResizer.addEventListener("mousedown", e => {
    resizing    = true;
    resizeStartX = e.clientX;
    resizeStartW = diLeft.offsetWidth;
    diResizer.classList.add("dragging");
    e.preventDefault();
});

document.addEventListener("mousemove", e => {
    if (!resizing) return;
    const newW = Math.max(160, Math.min(600, resizeStartW + e.clientX - resizeStartX));
    diLeft.style.width = newW + "px";
    renderTreemap();
});

document.addEventListener("mouseup", () => {
    if (resizing) {
        resizing = false;
        diResizer.classList.remove("dragging");
    }
});

/* ── Window resize ────────────────────────────────────────────── */
window.addEventListener("resize", () => renderTreemap());

/* ── Search Logic ────────────────────────────────────────────── */
const treeSearchInput = $("tree-search");
const btnClearSearch  = $("btn-clear-search");
const searchResults   = $("search-results");

if (treeSearchInput && btnClearSearch && searchResults) {
    treeSearchInput.addEventListener("input", () => {
        const q = treeSearchInput.value.trim().toLowerCase();
        btnClearSearch.classList.toggle("di-hidden", !q);
        
        clearTimeout(searchTimer);
        if (!q) {
            searchResults.classList.add("di-hidden");
            return;
        }

        searchTimer = setTimeout(() => {
            const matches = [];
            _searchRecursive(currentScan.tree, q, matches, 50);
            renderSearchResults(matches);
        }, 300);
    });

    btnClearSearch.addEventListener("click", () => {
        treeSearchInput.value = "";
        btnClearSearch.classList.add("di-hidden");
        searchResults.classList.add("di-hidden");
    });
}

function _searchRecursive(node, q, matches, limit) {
    if (matches.length >= limit) return;
    if (node.name.toLowerCase().includes(q)) {
        matches.push(node);
    }
    for (const child of node.children || []) {
        _searchRecursive(child, q, matches, limit);
    }
}

function renderSearchResults(matches) {
    if (!matches.length) {
        searchResults.innerHTML = '<div class="di-search-item" style="cursor:default;opacity:0.5;">No results found</div>';
    } else {
        searchResults.innerHTML = matches.map(m => `
            <div class="di-search-item" data-path="${escHtml(m.path)}">
                <span class="name">${escHtml(m.name)}</span>
                <span class="path">${escHtml(m.path)}</span>
            </div>
        `).join("");
    }
    searchResults.classList.remove("di-hidden");
    
    searchResults.querySelectorAll(".di-search-item[data-path]").forEach(item => {
        item.addEventListener("click", () => {
            const path = item.dataset.path;
            const node = findNodeByPath(currentScan.tree, path);
            if (node) {
                navigateTo(node);
                searchResults.classList.add("di-hidden");
            }
        });
    });
}

function findNodeByPath(root, path) {
    if (root.path === path) return root;
    for (const child of root.children || []) {
        const f = findNodeByPath(child, path);
        if (f) return f;
    }
    return null;
}

/* ── Init ─────────────────────────────────────────────────────── */
loadDrives();
loadSavedScans();
renderTreemap();   // draws empty state

// Hide search results on outside click
document.addEventListener("click", e => {
    if (!treeSearchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.classList.add("di-hidden");
    }
});

})(); // end IIFE
