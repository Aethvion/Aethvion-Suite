(function () {
    'use strict';

    const API = '/api/dashboard/clinicaltrace';
    let _graphData = null;
    let _network = null;
    let _activeId = null;
    let _activeNode = null;
    let _searchTimer = null;
    let _showContradictions = false;

    // Utility: get element by id
    const $ = id => document.getElementById(id);

    // ── Tab switching ─────────────────────────────────────────────────────────
    function switchTab(tabId) {
        document.querySelectorAll('.ct-nav-tab').forEach(btn => {
            if (btn.dataset.ctTab === tabId) btn.classList.add('active');
            else btn.classList.remove('active');
        });

        document.querySelectorAll('.ct-pane').forEach(pane => {
            if (pane.id === `ct-pane-${tabId}`) pane.classList.add('active');
            else pane.classList.remove('active');
        });

        if (tabId === 'graph') {
            if (!_network) loadGraph();
        }
    }

    // ── Data Loading ──────────────────────────────────────────────────────────
    async function loadData() {
        const scroll = $('ct-list-scroll');
        if (scroll) scroll.innerHTML = '<div class="ct-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

        try {
            const res = await fetch(`${API}/graph`);
            _graphData = await res.json();
            
            // Update stats
            const nodes = _graphData.nodes || [];
            const edges = _graphData.edges || [];
            const contradictions = _graphData.contradictions || [];
            if ($('ct-stat-count')) $('ct-stat-count').textContent = nodes.length;
            if ($('ct-stat-links')) $('ct-stat-links').textContent = edges.length;
            if ($('ct-stat-risks')) $('ct-stat-risks').textContent = contradictions.length;

            renderList(nodes);
            
            if (_activeId) {
                await selectNode(_activeId);
            }
            
            // Auto reload graph if rendered
            if (_network) {
                loadGraph();
            }

        } catch (err) {
            console.error('Failed to load ClinicalTrace data', err);
            if (scroll) scroll.innerHTML = '<div class="ct-list-empty"><i class="fas fa-triangle-exclamation"></i><p>Failed to connect to ClinicalTrace backend.</p></div>';
        }
    }

    // ── List Rendering ────────────────────────────────────────────────────────
    function renderList(nodes, filterText = '') {
        const scroll = $('ct-list-scroll');
        if (!scroll) return;

        if (!nodes || nodes.length === 0) {
            scroll.innerHTML = '<div class="ct-list-empty"><i class="fas fa-stethoscope"></i><p>No graph nodes found.</p></div>';
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
            scroll.innerHTML = '<div class="ct-list-empty"><i class="fas fa-magnifying-glass"></i><p>No nodes match your search.</p></div>';
            return;
        }

        let html = '';
        for (const d of filtered) {
            let icon = 'fa-file-medical';
            let color = '#3b82f6'; // Trial
            if (d.group === 'intervention') { icon = 'fa-capsules'; color = '#8b5cf6'; }
            if (d.group === 'population') { icon = 'fa-users'; color = '#f59e0b'; }
            if (d.group === 'outcome') { icon = 'fa-chart-line'; color = '#10b981'; }

            html += `
                <div class="ct-artifact-card ${_activeId === d.id ? 'active' : ''}" data-node-id="${d.id}">
                    <div class="ct-card-title">${d.title}</div>
                    <div class="ct-card-meta">
                        <span><i class="fas ${icon}" style="color:${color}"></i> ${d.type}</span>
                    </div>
                </div>
            `;
        }

        scroll.innerHTML = html;

        // Attach clicks
        scroll.querySelectorAll('.ct-artifact-card').forEach(card => {
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
        document.querySelectorAll('.ct-artifact-card').forEach(c => {
            if (c.dataset.nodeId === id) c.classList.add('active');
            else c.classList.remove('active');
        });

        const empty   = $('ct-detail-empty');
        const content = $('ct-detail-content');
        
        if (!_graphData) return;
        _activeNode = _graphData.nodes.find(n => n.id === id);
        if (!_activeNode) return;

        if (empty)   empty.style.display   = 'none';
        if (content) content.style.display = 'block';

        // Unlock Ask
        const textarea = $('ct-ask-textarea');
        const sendBtn  = $('ct-ask-send-btn');
        if (textarea) textarea.disabled = false;
        if (sendBtn)  sendBtn.disabled  = false;
        if ($('ct-ask-placeholder')) $('ct-ask-placeholder').style.display = 'none';

        // Find dependencies
        const upstream = _graphData.edges.filter(e => e.to === id).map(e => {
            const n = _graphData.nodes.find(n => n.id === e.from);
            return { node: n, edge: e };
        });
        const downstream = _graphData.edges.filter(e => e.from === id).map(e => {
            const n = _graphData.nodes.find(n => n.id === e.to);
            return { node: n, edge: e };
        });
        const contradictions = _graphData.contradictions.filter(c => c.from_trial === id || c.to_trial === id);

        // Build HTML
        let html = `
            <div class="ct-detail-header">
                <div class="ct-detail-title">${_activeNode.title}</div>
                <div class="ct-detail-meta" style="margin-bottom:20px;">
                    <span class="ct-detail-tag"><i class="fas fa-tag"></i> ${_activeNode.type}</span>
                </div>
            </div>
            
            <div class="ct-detail-section" style="margin-top:20px; padding:0 24px;">
        `;
        
        if (contradictions.length > 0) {
            html += `<h3 style="color:#ef4444; font-size:13px; text-transform:uppercase; margin-bottom:10px;"><i class="fas fa-not-equal"></i> Contradictions</h3>`;
            html += `<div style="display:flex; flex-direction:column; gap:8px; margin-bottom:24px;">`;
            contradictions.forEach(c => {
                const otherId = c.from_trial === id ? c.to_trial : c.from_trial;
                const otherNode = _graphData.nodes.find(n => n.id === otherId);
                
                html += `
                    <div style="background:rgba(239, 68, 68, 0.1); border:1px solid rgba(239, 68, 68, 0.3); padding:10px; border-radius:6px; font-size:13px; display:flex; flex-direction:column; gap:4px;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <i class="fas fa-bolt" style="color:#ef4444;"></i>
                            <span style="color:#fca5a5; font-weight:600;">Conflicts with:</span>
                            <span class="ct-linked-node" data-linked-id="${otherId}" style="cursor:pointer; text-decoration:underline;">${otherNode?.title || 'Unknown'}</span>
                        </div>
                        <div style="color:#e5e7eb; padding-left:22px;">Topic: ${c.topic} (Severity: ${c.severity})</div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        if (upstream.length > 0) {
            html += `<h3 style="color:#8b5cf6; font-size:13px; text-transform:uppercase; margin-bottom:10px;"><i class="fas fa-arrow-down-short-wide"></i> Incoming Links</h3>`;
            html += `<div style="display:flex; flex-direction:column; gap:8px; margin-bottom:24px;">`;
            upstream.forEach(u => {
                html += `
                    <div class="ct-artifact-card" data-linked-id="${u.node?.id}" style="margin:0; border:1px solid rgba(255,255,255,0.05); background:rgba(255,255,255,0.02);">
                        <div style="font-size:13px; font-weight:600; margin-bottom:4px;">${u.node?.title || 'Unknown'}</div>
                        <div style="font-size:11px; color:#9ca3af; display:flex; gap:10px;">
                            <span><i class="fas fa-link"></i> ${u.edge.label}</span>
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        if (downstream.length > 0) {
            html += `<h3 style="color:#10b981; font-size:13px; text-transform:uppercase; margin-bottom:10px;"><i class="fas fa-arrow-up-right-dots"></i> Outgoing Links</h3>`;
            html += `<div style="display:flex; flex-direction:column; gap:8px; margin-bottom:24px;">`;
            downstream.forEach(d => {
                html += `
                    <div class="ct-artifact-card" data-linked-id="${d.node?.id}" style="margin:0; border:1px solid rgba(255,255,255,0.05); background:rgba(255,255,255,0.02);">
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
            html += `<div style="color:#6b7280; font-size:13px; padding:20px 0;">No direct relationships found in graph.</div>`;
        }

        html += `</div>`;
        content.innerHTML = html;
    }

    // ── Ask (streaming) ───────────────────────────────────────────────────────
    async function sendAsk() {
        if (!_activeId) return;
        const textarea = $('ct-ask-textarea');
        const sendBtn  = $('ct-ask-send-btn');
        const output   = $('ct-ask-output');
        const modelSel = $('ct-ask-model');

        const question = textarea?.value.trim();
        if (!question) return;

        if (sendBtn) { sendBtn.disabled = true; sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }
        if (textarea) { textarea.disabled = true; }

        if (output) {
            output.innerHTML = `<div id="ct-ask-response" style="white-space:pre-wrap; font-size:13px; line-height:1.6;"></div><span class="ct-cursor"></span>`;
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
            const respEl  = $('ct-ask-response');
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
            const respEl = $('ct-ask-response');
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
        const canvas = $('ct-graph-canvas');
        if (!canvas) return;
        
        if (!_graphData) await loadData();
        if (!_graphData) return;

        try {
            // Find contradiction nodes to highlight them if toggle is on
            let conflictNodeIds = new Set();
            
            if (_showContradictions && _graphData.contradictions) {
                _graphData.contradictions.forEach(c => {
                    conflictNodeIds.add(c.from_trial);
                    conflictNodeIds.add(c.to_trial);
                });
            }

            // Transform for VisJS
            const visNodes = _graphData.nodes.map(n => {
                let color, icon;
                const group = n.group;
                if (group === 'trial') {
                    color = '#3b82f6'; // blue
                    icon = '\uf477'; // file-medical
                } else if (group === 'outcome') {
                    color = '#10b981'; // green
                    icon = '\uf201'; // chart-line
                } else if (group === 'population') {
                    color = '#f59e0b'; // amber
                    icon = '\uf0c0'; // users
                } else {
                    color = '#8b5cf6'; // purple (Intervention)
                    icon = '\uf46b'; // capsules
                }
                
                let isConflict = _showContradictions && conflictNodeIds.has(n.id);
                if (isConflict) {
                    color = '#ef4444'; // Red
                }

                return {
                    id: n.id,
                    label: n.title,
                    shape: 'icon',
                    level: group === 'trial' ? 2 : (group === 'intervention' ? 1 : (group === 'population' ? 3 : 4)),
                    icon: {
                        face: '"Font Awesome 6 Free"',
                        code: icon,
                        size: 40,
                        color: color,
                        weight: 900
                    },
                    font: { color: isConflict ? '#ef4444' : '#e2e8f0', size: 12, face: 'Inter', background: isConflict ? 'rgba(239, 68, 68, 0.1)' : 'transparent' }
                };
            });
            
            const visEdges = _graphData.edges.map(e => {
                return {
                    id: e.id,
                    from: e.from,
                    to: e.to,
                    label: e.label,
                    font: { color: '#9ca3af', size: 10, align: 'middle' },
                    arrows: { to: { enabled: true, scaleFactor: 0.6 } },
                    color: { color: 'rgba(255,255,255,0.15)', highlight: '#8b5cf6' },
                    smooth: { type: 'cubicBezier' },
                    width: 1.5
                };
            });
            
            // Add Contradiction edges explicitly if toggle is on
            if (_showContradictions && _graphData.contradictions) {
                _graphData.contradictions.forEach(c => {
                    visEdges.push({
                        from: c.from_trial,
                        to: c.to_trial,
                        label: 'CONTRADICTS',
                        font: { color: '#ef4444', size: 10, align: 'middle', background: 'rgba(0,0,0,0.8)' },
                        arrows: { to: { enabled: true, scaleFactor: 0.6 }, from: { enabled: true, scaleFactor: 0.6 } },
                        color: { color: '#ef4444' },
                        width: 2,
                        dashes: [5, 5]
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
                        direction: 'LR', // Left to Right
                        sortMethod: 'directed',
                        levelSeparation: 250,
                        nodeSpacing: 100
                    }
                },
                physics: {
                    enabled: false
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
            canvas.innerHTML = '<div style="color:#ef4444;padding:20px;">Failed to render ClinicalTrace graph.</div>';
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        // Register info content for the ExpInfo overlay
        if (window.ExpInfo) {
            window.ExpInfo.register('clinicaltrace', {
                icon:    'fas fa-stethoscope',
                name:    'ClinicalTrace',
                color:   'linear-gradient(135deg, #f43f5e, #be123c)',
                tagline: 'Structured Clinical Evidence Graph — Instantly traverse medical contradictions.',
                status:  'Experimental',
                concepts: [
                    {
                        icon:  'fas fa-vial',
                        label: 'Typed Trial Mapping',
                        desc:  'Papers are converted into an explicit graph of Trials, Interventions, Populations, and Outcomes.',
                    },
                    {
                        icon:  'fas fa-not-equal',
                        label: 'Contradiction Surface',
                        desc:  'The graph deterministically flags trials with conflicting outcomes for the exact same population and intervention.',
                    },
                    {
                        icon:  'fas fa-user-doctor',
                        label: 'AI Medical Analyst',
                        desc:  'Ask the AI questions about evidence quality. It uses the explicitly computed graph relationships rather than blindly searching text.',
                    },
                ],
                how: 'Medical abstracts and full-texts are ingested and structured into nodes (Trial, Intervention, Population, Outcome) and directed edges (tests, enrolls, produces, contradicts). When you analyze an intervention, the system instantly gathers all upstream and downstream nodes, identifying conflicting evidence. This exact topological context is passed to the LLM to provide deterministic analysis.',
                vision: 'Medical researchers currently spend months manually cross-referencing trials to find true contradictions. ClinicalTrace turns literature review from a reading task into an instantaneous graph query.',
                pitch: {
                    problem: 'Clinical evidence is trapped in prose. Determining the actual consensus on an intervention requires reading hundreds of trials and manually mapping their exact population constraints and outcomes. Contradictions are easily missed.',
                    solution: 'ClinicalTrace structures evidence as a typed graph. You can instantly filter trials by precise sub-populations or surface contradictory findings deterministically.',
                    tam: '$71B+ Drug Discovery Market. Target customers: Pharma R&D, Clinical Research Organizations (CROs), and Academic Centers.',
                    tactics: [
                        'Start with ingestion of open-access PubMed abstracts.',
                        'Build a domain-specific ontology for a high-value therapeutic area (e.g., Oncology or Diabetes) to serve as a proof-of-concept.',
                        'Position as a research aggregation tool to avoid medical device regulatory hurdles.'
                    ]
                }
            });
        }

        // Info button
        $('ct-info-btn')?.addEventListener('click', () => {
            if (window.ExpInfo) window.ExpInfo.show('clinicaltrace');
        });

        // Tab switcher
        document.querySelectorAll('.ct-nav-tab').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.ctTab));
        });

        // Search
        const searchInput = $('ct-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(_searchTimer);
                _searchTimer = setTimeout(() => applySearch(searchInput.value), 180);
            });
        }

        // Simulate Risk Event button -> now "Verify Contradictions"
        const riskBtn = $('ct-simulate-risk-btn');
        if (riskBtn) {
            riskBtn.addEventListener('click', () => {
                _showContradictions = !_showContradictions;
                riskBtn.style.boxShadow = _showContradictions ? '0 0 15px rgba(239,68,68,0.8)' : 'none';
                riskBtn.innerHTML = _showContradictions ? '<i class="fas fa-not-equal"></i> Contradictions: ON' : '<i class="fas fa-not-equal"></i> Verify';
                if (_network) loadGraph();
                
                // If a node is active, reload its detail view to show/hide risks
                if (_activeId) selectNode(_activeId);
            });
        }

        // Ask panel
        const sendBtn  = $('ct-ask-send-btn');
        const textarea = $('ct-ask-textarea');
        if (sendBtn)  sendBtn.addEventListener('click', sendAsk);
        if (textarea) textarea.addEventListener('keydown', e => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                sendAsk();
            }
        });

        // Graph refresh
        $('ct-graph-refresh')?.addEventListener('click', loadGraph);

        // Linked artifact click → navigate
        document.addEventListener('click', e => {
            const chip = e.target.closest('[data-linked-id]');
            if (chip && chip.classList.contains('ct-linked-node') || chip?.classList.contains('ct-artifact-card')) {
                selectNode(chip.dataset.linkedId);
            }
        });

        // Initial load
        loadData();
    }

    // Wait for DOM to be ready (panelLoaded event or DOMContentLoaded)
    if (document.getElementById('ct-root')) {
        init();
    } else {
        document.addEventListener('panelLoaded', function handler(e) {
            if (e.detail?.tabName === 'clinicaltrace') {
                document.removeEventListener('panelLoaded', handler);
                init();
            }
        });
    }

})();
