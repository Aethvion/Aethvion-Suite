/**
 * mode-chembio-lab.js
 * Chemistry & Biology Lab — RDKit cheminformatics + Biopython bioinformatics,
 * with an optional AI interpret layer.
 *
 * API prefix: /api/chembio
 */
(function () {
    'use strict';

    const API = '/api/chembio';
    const $ = id => document.getElementById(id);
    let _lastContext = '';

    function esc(s) {
        return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function emptyState(icon, msg) {
        return `<div class="cb-empty"><i class="fas fa-${icon}"></i><span>${esc(msg)}</span></div>`;
    }
    const loading = msg => `<div class="cb-loading"><i class="fas fa-spinner fa-spin"></i> ${esc(msg)}</div>`;
    const errorBox = msg => `<div class="cb-error"><i class="fas fa-triangle-exclamation"></i><span>${esc(msg || 'Error')}</span></div>`;

    async function post(endpoint, body) {
        const res = await fetch(`${API}/${endpoint}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        return res.json();
    }

    function switchTab(tabId) {
        document.querySelectorAll('.cb-nav-tab').forEach(b => b.classList.toggle('active', b.dataset.cbTab === tabId));
        ['molecule', 'similarity', 'sequence', 'align'].forEach(id => {
            const el = $(`cb-pane-${id}`);
            if (el) el.classList.toggle('active', id === tabId);
        });
    }

    // ── Molecule ──────────────────────────────────────────────────────────────
    async function runMolecule() {
        const out = $('cb-mol-result');
        const smi = $('cb-mol-smiles').value.trim();
        if (!smi) { out.innerHTML = emptyState('atom', 'Enter a SMILES string.'); return; }
        out.innerHTML = loading('Analyzing…');
        const data = await post('molecule', { smiles: smi });
        if (!data.ok) { out.innerHTML = errorBox(data.error); return; }

        const p = data.properties;
        const rows = [
            ['Formula', p.formula, true], ['Mol. weight', p.mol_weight + ' g/mol'],
            ['logP', p.logp], ['TPSA', p.tpsa + ' Å²'],
            ['H-donors', p.h_donors], ['H-acceptors', p.h_acceptors],
            ['Rotatable', p.rotatable_bonds], ['Rings', p.rings],
            ['Aromatic rings', p.aromatic_rings], ['Heavy atoms', p.heavy_atoms],
            ['Fraction Csp³', p.fraction_csp3],
        ];
        let html = '';
        if (data.image) html += `<img src="${data.image}" class="cb-mol-img" alt="structure">`;
        html += '<div class="cb-prop-grid">' + rows.map(([k, v, a]) =>
            `<div class="cb-prop"><div class="cb-prop-label">${esc(k)}</div>`
            + `<div class="cb-prop-value ${a ? 'accent' : ''}">${esc(v)}</div></div>`).join('') + '</div>';
        const li = data.lipinski;
        html += `<div class="cb-badge ${li.passes ? 'pass' : 'fail'}">`
            + `<i class="fas fa-${li.passes ? 'circle-check' : 'triangle-exclamation'}"></i>`
            + `Lipinski Ro5: ${li.violations} violation${li.violations === 1 ? '' : 's'} — ${li.passes ? 'drug-like' : 'flagged'}</div>`;
        html += `<div class="cb-canonical"><b>Canonical:</b> ${esc(data.canonical_smiles)}</div>`;
        out.innerHTML = html;

        _lastContext = `Molecule ${data.canonical_smiles}: ${JSON.stringify(p)}. `
            + `Lipinski violations ${li.violations} (${li.passes ? 'drug-like' : 'flagged'}).`;
    }

    // ── Similarity ────────────────────────────────────────────────────────────
    async function runSimilarity() {
        const out = $('cb-sim-result');
        const a = $('cb-sim-a').value.trim(), b = $('cb-sim-b').value.trim();
        if (!a || !b) { out.innerHTML = emptyState('code-compare', 'Enter both molecules.'); return; }
        out.innerHTML = loading('Comparing…');
        const data = await post('similarity', { smiles_a: a, smiles_b: b });
        if (!data.ok) { out.innerHTML = errorBox(data.error); return; }

        const pct = Math.round(data.tanimoto * 100);
        let html = `<div class="cb-sim-score"><div class="cb-sim-big">${data.tanimoto}</div>`
            + `<div class="cb-sim-cap">Tanimoto similarity · ${pct}%</div>`
            + `<div class="cb-sim-dice">Dice ${data.dice}</div></div>`;
        html += '<div class="cb-sim-mols">'
            + (data.image_a ? `<figure><img src="${data.image_a}" alt="A"><figcaption>Molecule A</figcaption></figure>` : '')
            + (data.image_b ? `<figure><img src="${data.image_b}" alt="B"><figcaption>Molecule B</figcaption></figure>` : '')
            + '</div>';
        out.innerHTML = html;
        _lastContext = `Tanimoto similarity ${data.tanimoto} (Dice ${data.dice}) between ${a} and ${b}.`;
    }

    // ── Sequence ──────────────────────────────────────────────────────────────
    async function runSequence() {
        const out = $('cb-seq-result');
        const seq = $('cb-seq-input').value.trim();
        if (!seq) { out.innerHTML = emptyState('dna', 'Paste a sequence.'); return; }
        out.innerHTML = loading('Analyzing…');
        const data = await post('sequence', { sequence: seq, seq_type: $('cb-seq-type').value });
        if (!data.ok) { out.innerHTML = errorBox(data.error); return; }

        const typeLabel = { dna: 'DNA', rna: 'RNA', protein: 'Protein' }[data.seq_type] || data.seq_type;
        let html = '<div class="cb-seq-badges">';
        html += `<span class="cb-chip alt"><i class="fas fa-dna"></i> ${typeLabel}</span>`;
        html += `<span class="cb-chip"><i class="fas fa-ruler"></i> ${data.length} ${data.seq_type === 'protein' ? 'residues' : 'bases'}</span>`;
        if (data.gc_percent !== undefined) html += `<span class="cb-chip"><i class="fas fa-percent"></i> GC ${data.gc_percent}%</span>`;
        if (data.mol_weight !== undefined) html += `<span class="cb-chip"><i class="fas fa-weight-hanging"></i> ${data.mol_weight} Da</span>`;
        if (data.isoelectric_point !== undefined) html += `<span class="cb-chip"><i class="fas fa-bolt"></i> pI ${data.isoelectric_point}</span>`;
        if (data.gravy !== undefined) html += `<span class="cb-chip"><i class="fas fa-droplet"></i> GRAVY ${data.gravy}</span>`;
        if (data.instability_index !== undefined) html += `<span class="cb-chip"><i class="fas fa-gauge"></i> instability ${data.instability_index}</span>`;
        html += '</div>';

        if (data.transcribed_rna) html += seqBlock('Transcribed RNA', data.transcribed_rna);
        if (data.protein) html += seqBlock('Translation (protein)', data.protein, 'protein');
        if (data.reverse_complement) html += seqBlock('Reverse complement', data.reverse_complement);

        if (data.composition) {
            const comp = Object.entries(data.composition)
                .map(([k, v]) => `<span class="cb-comp"><b>${esc(k)}</b> ${v}${data.seq_type === 'protein' ? '%' : ''}</span>`).join('');
            html += `<div class="cb-seq-block"><div class="k">${data.seq_type === 'protein' ? 'Amino-acid composition' : 'Base composition'}</div>`
                + `<div class="cb-comp-bar">${comp}</div></div>`;
        }
        out.innerHTML = html;

        _lastContext = `${typeLabel} sequence, length ${data.length}. ` + JSON.stringify(
            Object.fromEntries(Object.entries(data).filter(([k]) =>
                ['gc_percent', 'mol_weight', 'isoelectric_point', 'gravy', 'instability_index', 'aromaticity', 'protein', 'stop_codons'].includes(k))));
    }
    function seqBlock(label, val, cls = '') {
        return `<div class="cb-seq-block"><div class="k">${esc(label)}</div>`
            + `<div class="cb-seq-mono ${cls}">${esc(val)}</div></div>`;
    }

    // ── Alignment ─────────────────────────────────────────────────────────────
    async function runAlign() {
        const out = $('cb-align-result');
        const a = $('cb-align-a').value.trim(), b = $('cb-align-b').value.trim();
        if (!a || !b) { out.innerHTML = emptyState('align-left', 'Enter both sequences.'); return; }
        out.innerHTML = loading('Aligning…');
        const data = await post('align', { seq_a: a, seq_b: b, mode: $('cb-align-mode').value });
        if (!data.ok) { out.innerHTML = errorBox(data.error); return; }

        out.innerHTML = '<div class="cb-align-out">'
            + '<div class="cb-align-meta">'
            + `<span class="cb-chip"><i class="fas fa-star"></i> score ${data.score}</span>`
            + `<span class="cb-chip"><i class="fas fa-equals"></i> identity ${data.identity_percent}%</span>`
            + `<span class="cb-chip alt"><i class="fas fa-gears"></i> ${data.mode}</span>`
            + '</div>'
            + `<div class="cb-align-text">${esc(data.alignment)}</div></div>`;
        _lastContext = `Pairwise ${data.mode} alignment: score ${data.score}, identity ${data.identity_percent}%.`;
    }

    // ── AI interpret (streaming) ──────────────────────────────────────────────
    async function aiInterpret() {
        const out = $('cb-ai-output');
        if (!_lastContext) {
            out.classList.remove('cb-hide');
            out.textContent = 'Run an analysis first — then I can interpret it.';
            return;
        }
        out.classList.remove('cb-hide');
        out.innerHTML = '<span id="cb-ai-text"></span><span class="cb-ai-cursor"></span>';
        const textEl = $('cb-ai-text');
        try {
            const res = await fetch(`${API}/interpret`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ context: _lastContext, model_id: $('cb-ai-model').value || 'auto' }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n'); buffer = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    const s = line.slice(5).trim(); if (!s) continue;
                    let msg; try { msg = JSON.parse(s); } catch (_) { continue; }
                    if (msg.token) textEl.textContent += msg.token;
                    else if (msg.error) textEl.textContent += `\n[error] ${msg.error}`;
                }
            }
        } catch (err) {
            textEl.textContent += `\n[error] ${err.message}`;
        } finally {
            const cursor = out.querySelector('.cb-ai-cursor');
            if (cursor) cursor.remove();
        }
    }

    async function loadModels() {
        const sel = $('cb-ai-model');
        if (!sel) return;
        try {
            const res = await fetch('/api/registry/models/chat');
            if (!res.ok) return;
            const data = await res.json();
            (data.models || data.data || []).forEach(m => {
                const id = m.id || m.model_id || m.name; if (!id) return;
                const opt = document.createElement('option');
                opt.value = id; opt.textContent = m.name || id; sel.appendChild(opt);
            });
        } catch (_) { /* auto stays */ }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        document.querySelectorAll('.cb-nav-tab').forEach(b =>
            b.addEventListener('click', () => switchTab(b.dataset.cbTab)));

        $('cb-mol-btn').addEventListener('click', runMolecule);
        $('cb-sim-btn').addEventListener('click', runSimilarity);
        $('cb-seq-btn').addEventListener('click', runSequence);
        $('cb-align-btn').addEventListener('click', runAlign);
        $('cb-ai-interpret').addEventListener('click', aiInterpret);

        document.querySelectorAll('.cb-preset[data-smiles]').forEach(b =>
            b.addEventListener('click', () => { $('cb-mol-smiles').value = b.dataset.smiles; runMolecule(); }));
        document.querySelectorAll('.cb-preset[data-seq]').forEach(b =>
            b.addEventListener('click', () => { $('cb-seq-input').value = b.dataset.seq; runSequence(); }));

        registerInfo();
        loadModels();
        runMolecule();  // show aspirin by default so the tool isn't empty
    }

    function registerInfo() {
        if (!window.ExpInfo) return;
        window.ExpInfo.register('chembio-lab', {
            icon: 'fas fa-flask',
            name: 'Chemistry & Biology Lab',
            color: 'linear-gradient(135deg, #22d3ee, #a78bfa)',
            tagline: 'Bench-grade cheminformatics and bioinformatics — the same engines real labs use, wrapped in an AI that explains them.',
            status: 'Experimental',
            concepts: [
                { icon: 'fas fa-atom', label: 'Molecular analysis (RDKit)',
                  desc: 'Parse any SMILES to a 2D structure and real descriptors — MW, logP, TPSA, H-bonding — plus Lipinski drug-likeness and Tanimoto similarity.' },
                { icon: 'fas fa-dna', label: 'Sequence & alignment (Biopython)',
                  desc: 'Auto-detect DNA/RNA/protein, transcribe and translate, compute GC content or protein pI/GRAVY, and run Needleman–Wunsch / Smith–Waterman alignment.' },
                { icon: 'fas fa-wand-magic-sparkles', label: 'AI that reads the result',
                  desc: 'Every property, score and alignment can be explained by the AI in context — what it implies for drug-likeness, function or homology.' },
            ],
            how: 'Chemistry runs on RDKit, biology on Biopython — the exact open-source toolkits used in pharma and academic labs, executing locally. The Molecule pane renders a structure and computes descriptors with a Lipinski rule-of-five check; Similarity compares two molecules by Morgan-fingerprint Tanimoto and Dice; Sequence detects the biopolymer type and reports GC content, transcription, translation, or protein physicochemistry and composition; Alignment does global or local pairwise alignment with score and % identity. The AI never fabricates chemistry or biology — it interprets values the engines produced.',
            vision: 'Cheminformatics and bioinformatics power is normally locked behind scripting: you cannot explore a molecule or a sequence without writing RDKit or Biopython code. This tool makes those engines interactive and pairs them with an AI that explains what the results mean — bridging the gap between "I have a SMILES/sequence" and "I understand it." The long-term vision is an approachable life-sciences bench: add substructure search, reaction prediction, BLAST-style database queries and structure viewers, so students, educators and early-stage researchers get real computational biology without the coding barrier.',
            pitch: {
                problem: 'The gold-standard tools for chemistry and biology (RDKit, Biopython) are libraries, not products — using them means writing code. Meanwhile, LLMs will happily state a molecule\'s properties or a sequence\'s translation and get them subtly, dangerously wrong. There is no accessible, trustworthy middle.',
                solution: 'An interactive front-end over the real scientific engines, with an AI layer that interprets rather than computes. You get authoritative RDKit/Biopython results without writing a line of code, explained in context.',
                tam: 'Life-sciences R&D software & bioinformatics: $40B+ and growing with the AI-in-drug-discovery wave. Target: chem/bio education, biotech startups, and researchers who need quick computational answers without engineering support.',
                tactics: [
                    'Enter through education and self-learners, where the coding barrier is highest and stakes are low.',
                    'Anchor trust on using the field-standard engines (RDKit/Biopython) — not a black-box model.',
                    'Layer toward discovery workflows (substructure/BLAST search, property filtering) to reach biotech teams.',
                ],
            },
        });
        $('cb-info-btn')?.addEventListener('click', () => window.ExpInfo.show('chembio-lab'));
    }

    if ($('cb-root')) {
        init();
    } else {
        document.addEventListener('panelLoaded', function handler(e) {
            if (e.detail?.tabName === 'chembio-lab') {
                document.removeEventListener('panelLoaded', handler);
                init();
            }
        });
    }
})();
