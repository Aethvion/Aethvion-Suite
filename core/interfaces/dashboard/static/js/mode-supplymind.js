(function () {
    'use strict';

    const API = '/api/dashboard/supplymind';
    let _graphData = null;
    let _network = null;
    let _activeId = null;
    let _activeNode = null;
    let _searchTimer = null;
    let _simulatedRisk = false;

    // Utility: get element by id
    const $ = id => document.getElementById(id);

    // ── Tab switching ─────────────────────────────────────────────────────────
    function switchTab(tabId) {
        document.querySelectorAll('.sm-nav-tab').forEach(btn => {
            if (btn.dataset.smTab === tabId) btn.classList.add('active');
            else btn.classList.remove('active');
        });

        document.querySelectorAll('.sm-pane').forEach(pane => {
            if (pane.id === `sm-pane-${tabId}`) pane.classList.add('active');
            else pane.classList.remove('active');
        });

        if (tabId === 'graph') {
            if (!_network) loadGraph();
        }
    }

    // ── Data Loading ──────────────────────────────────────────────────────────
    async function loadData() {
        const scroll = $('sm-list-scroll');
        if (scroll) scroll.innerHTML = '<div class="sm-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

        try {
            const res = await fetch(`${API}/graph`);
            _graphData = await res.json();
            
            // Update stats
            const nodes = _graphData.nodes || [];
            const edges = _graphData.edges || [];
            const risks = _graphData.risks || [];
            if ($('sm-stat-count')) $('sm-stat-count').textContent = nodes.length;
            if ($('sm-stat-links')) $('sm-stat-links').textContent = edges.length;
            if ($('sm-stat-risks')) $('sm-stat-risks').textContent = risks.length;

            renderList(nodes);
            
            if (_activeId) {
                await selectNode(_activeId);
            }
            
            // Auto reload graph if rendered
            if (_network) {
                loadGraph();
            }

        } catch (err) {
            console.error('Failed to load SupplyMind data', err);
            if (scroll) scroll.innerHTML = '<div class="sm-list-empty"><i class="fas fa-triangle-exclamation"></i><p>Failed to connect to SupplyMind backend.</p></div>';
        }
    }

    // ── List Rendering ────────────────────────────────────────────────────────
    function renderList(nodes, filterText = '') {
        const scroll = $('sm-list-scroll');
        if (!scroll) return;

        if (!nodes || nodes.length === 0) {
            scroll.innerHTML = '<div class="sm-list-empty"><i class="fas fa-network-wired"></i><p>No graph nodes found.</p></div>';
            return;
        }

        let filtered = nodes;
        if (filterText) {
            const text = filterText.toLowerCase();
            filtered = nodes.filter(n => 
                (n.title && n.title.toLowerCase().includes(text)) ||
                (n.type && n.type.toLowerCase().includes(text))
            );
        }

        if (filtered.length === 0) {
            scroll.innerHTML = '<div class="sm-list-empty"><i class="fas fa-magnifying-glass"></i><p>No nodes match your search.</p></div>';
            return;
        }

        let html = '';
        for (const d of filtered) {
            let icon = 'fa-box';
            let color = '#a78bfa'; // Component
            if (d.group === 'finished_good') { icon = 'fa-box-open'; color = '#60a5fa'; }
            if (d.group === 'raw_material') { icon = 'fa-cubes'; color = '#34d399'; }
            if (d.group === 'facility') { icon = 'fa-industry'; color = '#fbbf24'; }

            html += `
                <div class="sm-artifact-card ${_activeId === d.id ? 'active' : ''}" data-node-id="${d.id}">
                    <div class="sm-card-title">${d.title}</div>
                    <div class="sm-card-meta">
                        <span><i class="fas ${icon}" style="color:${color}"></i> ${d.type}</span>
                    </div>
                </div>
            `;
        }

        scroll.innerHTML = html;

        // Attach clicks
        scroll.querySelectorAll('.sm-artifact-card').forEach(card => {
            card.addEventListener('click', () => {
                selectNode(card.dataset.nodeId);
            });
        });
    }

    function applySearch(text) {
        if (!_graphData) return;
        renderList(_graphData.nodes, text);
    }

    // ── Node Selection & Detail ───────────────────────────────────────────────
    async function selectNode(id) {
        _activeId = id;
        
        // Update list UI
        document.querySelectorAll('.sm-artifact-card').forEach(c => {
            if (c.dataset.nodeId === id) c.classList.add('active');
            else c.classList.remove('active');
        });

        const empty   = $('sm-detail-empty');
        const content = $('sm-detail-content');
        
        if (!_graphData) return;
        _activeNode = _graphData.nodes.find(n => n.id === id);
        if (!_activeNode) return;

        if (empty)   empty.style.display   = 'none';
        if (content) content.style.display = 'block';

        // Unlock Ask
        const textarea = $('sm-ask-textarea');
        const sendBtn  = $('sm-ask-send-btn');
        if (textarea) textarea.disabled = false;
        if (sendBtn)  sendBtn.disabled  = false;
        if ($('sm-ask-placeholder')) $('sm-ask-placeholder').style.display = 'none';

        // Find dependencies
        const upstream = _graphData.edges.filter(e => e.to === id).map(e => {
            const n = _graphData.nodes.find(n => n.id === e.from);
            return { node: n, edge: e };
        });
        const downstream = _graphData.edges.filter(e => e.from === id).map(e => {
            const n = _graphData.nodes.find(n => n.id === e.to);
            return { node: n, edge: e };
        });
        const risks = _graphData.risks.filter(r => r.target_id === id);

        // Build HTML
        let html = `
            <div class="sm-detail-header">
                <div class="sm-detail-title">${_activeNode.title}</div>
                <div class="sm-detail-meta" style="margin-bottom:20px;">
                    <span class="sm-detail-tag"><i class="fas fa-tag"></i> ${_activeNode.type}</span>
                    <span class="sm-detail-tag"><i class="fas fa-layer-group"></i> ${_activeNode.group.replace('_', ' ').toUpperCase()}</span>
                </div>
            </div>
            
            <div class="sm-detail-section" style="margin-top:20px; padding:0 24px;">
        `;
        
        if (risks.length > 0) {
            html += `<h3 style="color:#ef4444; font-size:13px; text-transform:uppercase; margin-bottom:10px;"><i class="fas fa-triangle-exclamation"></i> Active Risks</h3>`;
            html += `<div style="display:flex; flex-direction:column; gap:8px; margin-bottom:24px;">`;
            risks.forEach(r => {
                html += `
                    <div style="background:rgba(239, 68, 68, 0.1); border:1px solid rgba(239, 68, 68, 0.3); padding:10px; border-radius:6px; font-size:13px; display:flex; align-items:center; gap:10px;">
                        <i class="fas fa-bolt" style="color:#ef4444;"></i>
                        <span style="color:#fca5a5; font-weight:600;">${r.severity.toUpperCase()}</span>
                        <span>${r.title}</span>
                    </div>
                `;
            });
            html += `</div>`;
        }

        if (upstream.length > 0) {
            html += `<h3 style="color:#a78bfa; font-size:13px; text-transform:uppercase; margin-bottom:10px;"><i class="fas fa-arrow-down-short-wide"></i> Upstream Dependencies (Suppliers)</h3>`;
            html += `<div style="display:flex; flex-direction:column; gap:8px; margin-bottom:24px;">`;
            upstream.forEach(u => {
                html += `
                    <div class="sm-artifact-card" data-linked-id="${u.node?.id}" style="margin:0; border:1px solid rgba(255,255,255,0.05); background:rgba(255,255,255,0.02);">
                        <div style="font-size:13px; font-weight:600; margin-bottom:4px;">${u.node?.title || 'Unknown'}</div>
                        <div style="font-size:11px; color:#9ca3af; display:flex; gap:10px;">
                            <span><i class="fas fa-link"></i> ${u.edge.label}</span>
                            ${u.edge.lead_time_days ? `<span><i class="fas fa-clock"></i> Lead time: ${u.edge.lead_time_days} days</span>` : ''}
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        if (downstream.length > 0) {
            html += `<h3 style="color:#60a5fa; font-size:13px; text-transform:uppercase; margin-bottom:10px;"><i class="fas fa-arrow-up-right-dots"></i> Downstream Impact (Supplies To)</h3>`;
            html += `<div style="display:flex; flex-direction:column; gap:8px; margin-bottom:24px;">`;
            downstream.forEach(d => {
                html += `
                    <div class="sm-artifact-card" data-linked-id="${d.node?.id}" style="margin:0; border:1px solid rgba(255,255,255,0.05); background:rgba(255,255,255,0.02);">
                        <div style="font-size:13px; font-weight:600; margin-bottom:4px;">${d.node?.title || 'Unknown'}</div>
                        <div style="font-size:11px; color:#9ca3af; display:flex; gap:10px;">
                            <span><i class="fas fa-link"></i> ${d.edge.label}</span>
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        }
        
        if (upstream.length === 0 && downstream.length === 0) {
            html += `<div style="color:#6b7280; font-size:13px; padding:20px 0;">No direct dependencies found in graph.</div>`;
        }

        html += `</div>`;
        content.innerHTML = html;
    }

    // ── Ask (streaming) ───────────────────────────────────────────────────────
    async function sendAsk() {
        if (!_activeId) return;
        const textarea = $('sm-ask-textarea');
        const sendBtn  = $('sm-ask-send-btn');
        const output   = $('sm-ask-output');
        const modelSel = $('sm-ask-model');

        const question = textarea?.value.trim();
        if (!question) return;

        if (sendBtn) { sendBtn.disabled = true; sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }
        if (textarea) { textarea.disabled = true; }

        if (output) {
            output.innerHTML = `<div id="sm-ask-response" style="white-space:pre-wrap; font-size:13px; line-height:1.6;"></div><span class="sm-cursor"></span>`;
        }

        const model = modelSel?.value || 'auto';

        try {
            const res = await fetch(`${API}/${_activeId}/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question, model_id: model }),
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const reader  = res.body.getReader();
            const decoder = new TextDecoder();
            const respEl  = $('sm-ask-response');
            let buffer    = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const parts = buffer.split('\n\n');
                buffer = parts.pop();

                for (const part of parts) {
                    const line = part.replace(/^data: /, '').trim();
                    if (!line) continue;
                    try {
                        const msg = JSON.parse(line);
                        if (msg.token && respEl) {
                            respEl.textContent += msg.token;
                            if (output) output.scrollTop = output.scrollHeight;
                        }
                        if (msg.error) {
                            if (respEl) respEl.textContent = `Error: ${msg.error}`;
                        }
                    } catch (e) {}
                }
            }
        } catch (err) {
            const respEl = $('sm-ask-response');
            if (respEl) respEl.textContent = 'Failed to connect to the AI service.';
        } finally {
            if (sendBtn) { sendBtn.disabled = false; sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Ask'; }
            if (textarea) {
                textarea.disabled = false;
                textarea.value = '';
                textarea.focus();
            }
        }
    }

    // ── Graph rendering ───────────────────────────────────────────────────────
    async function loadGraph() {
        const canvas = $('sm-graph-canvas');
        if (!canvas) return;
        
        if (!_graphData) await loadData();
        if (!_graphData) return;

        try {
            // Find transitive risk paths if simulated risk is on
            let riskNodeIds = new Set();
            let riskEdgeIds = new Set();
            
            if (_simulatedRisk && _graphData.risks) {
                // BFS to find all downstream nodes affected by any risk
                let q = [];
                _graphData.risks.forEach(r => {
                    q.push(r.target_id);
                    riskNodeIds.add(r.target_id);
                });
                
                while(q.length > 0) {
                    const curr = q.shift();
                    // find downstream edges (from curr)
                    _graphData.edges.forEach(e => {
                        if (e.from === curr) {
                            riskEdgeIds.add(e.id);
                            if (!riskNodeIds.has(e.to)) {
                                riskNodeIds.add(e.to);
                                q.push(e.to);
                            }
                        }
                    });
                }
            }

            // Transform for VisJS
            const visNodes = _graphData.nodes.map(n => {
                let color, icon;
                const group = n.group;
                if (group === 'finished_good') {
                    color = '#3b82f6'; // blue
                    icon = '\uf466'; // box-open
                } else if (group === 'raw_material') {
                    color = '#10b981'; // green
                    icon = '\uf1b3'; // cubes
                } else if (group === 'facility') {
                    color = '#f59e0b'; // amber
                    icon = '\uf275'; // industry
                } else {
                    color = '#8b5cf6'; // purple (Component)
                    icon = '\uf468'; // box
                }
                
                let isRisk = _simulatedRisk && riskNodeIds.has(n.id);
                if (isRisk) {
                    color = '#ef4444'; // Red
                }

                return {
                    id: n.id,
                    label: n.title,
                    shape: 'icon',
                    level: group === 'finished_good' ? 1 : (group === 'component' ? 2 : (group === 'facility' ? 3 : 4)),
                    icon: {
                        face: '"Font Awesome 6 Free"',
                        code: icon,
                        size: 40,
                        color: color,
                        weight: 900
                    },
                    font: { color: isRisk ? '#ef4444' : '#e2e8f0', size: 12, face: 'Inter', background: isRisk ? 'rgba(239, 68, 68, 0.1)' : 'transparent' }
                };
            });
            
            // Add Risk nodes explicitly if simulated risk is on
            if (_simulatedRisk && _graphData.risks) {
                _graphData.risks.forEach(r => {
                    visNodes.push({
                        id: r.id,
                        label: r.title,
                        shape: 'icon',
                        level: 4,
                        icon: {
                            face: '"Font Awesome 6 Free"',
                            code: '\uf0e7', // bolt
                            size: 30,
                            color: '#ef4444',
                            weight: 900
                        },
                        font: { color: '#ef4444', size: 10, face: 'Inter' }
                    });
                });
            }

            const visEdges = _graphData.edges.map(e => {
                let isRisk = _simulatedRisk && riskEdgeIds.has(e.id);
                return {
                    id: e.id,
                    from: e.from,
                    to: e.to,
                    label: e.label,
                    font: { color: isRisk ? '#ef4444' : '#9ca3af', size: 10, align: 'middle' },
                    arrows: { to: { enabled: true, scaleFactor: 0.6 } },
                    color: { color: isRisk ? '#ef4444' : 'rgba(255,255,255,0.15)', highlight: isRisk ? '#f87171' : '#8b5cf6' },
                    smooth: { type: 'cubicBezier' },
                    width: isRisk ? 3 : 1.5,
                    dashes: isRisk ? [5,5] : false
                };
            });
            
            // Add Risk edges explicitly
            if (_simulatedRisk && _graphData.risks) {
                _graphData.risks.forEach(r => {
                    visEdges.push({
                        from: r.id,
                        to: r.target_id,
                        label: 'affects',
                        font: { color: '#ef4444', size: 10, align: 'middle' },
                        arrows: { to: { enabled: true, scaleFactor: 0.6 } },
                        color: { color: '#ef4444' },
                        width: 2
                    });
                });
            }

            const dsNodes = new vis.DataSet(visNodes);
            const dsEdges = new vis.DataSet(visEdges);

            const options = {
                nodes: { shadow: true },
                edges: { shadow: true },
                layout: {
                    hierarchical: {
                        direction: 'RL', // Right to Left (Finished Good on Left, Raw Materials on Right)
                        sortMethod: 'directed',
                        levelSeparation: 250,
                        nodeSpacing: 100
                    }
                },
                physics: {
                    enabled: false // disable physics for hierarchical layout to prevent jumping
                },
                interaction: { hover: true, tooltipDelay: 200 }
            };

            if (_network) {
                _network.destroy();
            }

            _network = new vis.Network(canvas, { nodes: dsNodes, edges: dsEdges }, options);

            _network.on('click', (params) => {
                if (params.nodes.length) {
                    const id = params.nodes[0];
                    if (!id.startsWith('risk_')) {
                        switchTab('artifacts');
                        selectNode(id);
                    }
                }
            });

        } catch (err) {
            canvas.innerHTML = '<div style="color:#ef4444;padding:20px;">Failed to render SupplyMind graph.</div>';
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        // Register info content for the ExpInfo overlay
        if (window.ExpInfo) {
            window.ExpInfo.register('supplymind', {
                icon:    'fas fa-network-wired',
                name:    'SupplyMind',
                color:   'linear-gradient(135deg, #10b981, #059669)',
                tagline: 'Supply Chain Dependency Intelligence — Transitive Risk Traversal.',
                status:  'Experimental',
                concepts: [
                    {
                        icon:  'fas fa-boxes-stacked',
                        label: 'Multi-Tier Graph Mapping',
                        desc:  'Most companies only see Tier 1 suppliers. SupplyMind maps N-tier dependencies explicitly as a graph.',
                    },
                    {
                        icon:  'fas fa-bolt',
                        label: 'Transitive Risk Propagation',
                        desc:  'A failure at a Tier 4 supplier instantly highlights all downstream finished products at risk.',
                    },
                    {
                        icon:  'fas fa-user-tie',
                        label: 'AI Supply Analyst',
                        desc:  'Ask the AI questions about risk impact. It uses the explicitly computed risk paths to answer deterministically.',
                    },
                ],
                how: 'Supply chains are ingested into AethvionDB as typed nodes (Products, Facilities, Companies) and directed edges (manufactures, sources_from). When a Risk Event occurs, the graph deterministically traverses downstream edges to locate impacted finished goods and compute lead-time impacts. This explicit structure is passed to the LLM to provide analytical context.',
                vision: 'Global supply chains fail silently until they collapse. SupplyMind provides real-time visibility into deep-tier dependencies, replacing manual supply auditing with instantaneous graph risk assessment.',
                pitch: {
                    problem: 'Supply chains are 4-6 layers deep, but visibility stops at Tier 1. The 2021 chip shortage proved that a $2 component from a Tier 4 fab can halt production of a $40,000 vehicle. Current systems cannot compute transitive risk quickly.',
                    solution: 'SupplyMind maps BOMs and suppliers as a traversable graph. A single API call traverses transitive dependencies to instantly identify all products impacted by an upstream node failure.',
                    tam: '$19B+ Supply Chain Risk Management market. Target customers: Manufacturing, Automotive, Defense, Pharmaceuticals.',
                    tactics: [
                        'Start with BOM ingestion plugins for existing ERPs (SAP/Oracle).',
                        'Sell "Supply Visibility" pilots to automotive and electronics manufacturers.',
                        'Integrate real-time global news API to automatically spawn RiskEvent nodes.'
                    ]
                }
            });
        }

        // Info button
        $('sm-info-btn')?.addEventListener('click', () => {
            if (window.ExpInfo) window.ExpInfo.show('supplymind');
        });

        // Tab switcher
        document.querySelectorAll('.sm-nav-tab').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.smTab));
        });

        // Search
        const searchInput = $('sm-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(_searchTimer);
                _searchTimer = setTimeout(() => applySearch(searchInput.value), 180);
            });
        }

        // Simulate Risk Event button
        const riskBtn = $('sm-simulate-risk-btn');
        if (riskBtn) {
            riskBtn.addEventListener('click', () => {
                _simulatedRisk = !_simulatedRisk;
                riskBtn.style.boxShadow = _simulatedRisk ? '0 0 15px rgba(239,68,68,0.8)' : 'none';
                riskBtn.innerHTML = _simulatedRisk ? '<i class="fas fa-bolt"></i> Risk: ON' : '<i class="fas fa-bolt"></i> Risk';
                if (_network) loadGraph();
                
                // If a node is active, reload its detail view to show/hide risks
                if (_activeId) selectNode(_activeId);
            });
        }

        // Ask panel
        const sendBtn  = $('sm-ask-send-btn');
        const textarea = $('sm-ask-textarea');
        if (sendBtn)  sendBtn.addEventListener('click', sendAsk);
        if (textarea) textarea.addEventListener('keydown', e => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                sendAsk();
            }
        });

        // Graph refresh
        $('sm-graph-refresh')?.addEventListener('click', loadGraph);

        // Linked artifact click → navigate
        document.addEventListener('click', e => {
            const chip = e.target.closest('[data-linked-id]');
            if (chip) selectNode(chip.dataset.linkedId);
        });

        // Initial load
        loadData();
    }

    // Wait for DOM to be ready (panelLoaded event or DOMContentLoaded)
    if (document.getElementById('sm-root')) {
        init();
    } else {
        document.addEventListener('panelLoaded', function handler(e) {
            if (e.detail?.tabName === 'supplymind') {
                document.removeEventListener('panelLoaded', handler);
                init();
            }
        });
    }

})();
