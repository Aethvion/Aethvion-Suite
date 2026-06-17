/**
 * Aethvion Suite — Experimental Info Panel
 * A shared, reusable info overlay for Experimental-category tabs.
 *
 * Usage (in each experimental mode's JS):
 *   window.ExpInfo.register('my-tab', {
 *     icon:    'fas fa-my-icon',
 *     name:    'Tool Name',
 *     tagline: 'One-line description.',
 *     how:     'How it works — markdown-free paragraph.',
 *     vision:  'The long-term vision for this tool.',
 *     status:  'Alpha' | 'Beta' | 'Experimental' | 'Prototype',
 *     concepts: [                  // Optional: key concept pills
 *       { icon: 'fas fa-x', label: 'Concept Name', desc: 'Short explanation.' },
 *     ],
 *   });
 *
 *   // Then, call from your info button:
 *   window.ExpInfo.show('my-tab');
 */
(function () {
    'use strict';

    const _registry = {};   // tabId → info object
    let   _overlay  = null; // cached DOM element

    // ── Build the modal DOM once ───────────────────────────────────────────────
    function _ensureModal() {
        if (_overlay) return _overlay;

        _overlay = document.createElement('div');
        _overlay.id        = 'exp-info-overlay';
        _overlay.className = 'exp-info-overlay';
        _overlay.innerHTML = `
            <div class="exp-info-modal" id="exp-info-modal" role="dialog" aria-modal="true" aria-labelledby="exp-info-title">
                <div class="exp-info-modal-bg"></div>

                <div class="exp-info-header">
                    <div class="exp-info-identity">
                        <div class="exp-info-icon-wrap" id="exp-info-icon-wrap">
                            <i class="fas fa-flask-vial" id="exp-info-icon"></i>
                        </div>
                        <div>
                            <div class="exp-info-name" id="exp-info-title">Experimental Tool</div>
                            <div class="exp-info-badges">
                                <span class="exp-info-badge exp-badge-experimental" id="exp-info-status">Experimental</span>
                                <span class="exp-info-badge exp-badge-category">
                                    <i class="fas fa-flask-vial"></i> Experimental Category
                                </span>
                            </div>
                        </div>
                    </div>
                    <button class="exp-info-close" id="exp-info-close" aria-label="Close">
                        <i class="fas fa-xmark"></i>
                    </button>
                </div>

                <div class="exp-info-tagline" id="exp-info-tagline"></div>

                <div class="exp-info-body">

                    <div class="exp-info-section" id="exp-info-concepts-wrap">
                        <div class="exp-info-section-label">
                            <i class="fas fa-circle-nodes"></i> Key Concepts
                        </div>
                        <div class="exp-info-concepts" id="exp-info-concepts"></div>
                    </div>

                    <div class="exp-info-section">
                        <div class="exp-info-section-label">
                            <i class="fas fa-gears"></i> How It Works
                        </div>
                        <div class="exp-info-text" id="exp-info-how"></div>
                    </div>

                    <div class="exp-info-section">
                        <div class="exp-info-section-label">
                            <i class="fas fa-rocket"></i> The Vision
                        </div>
                        <div class="exp-info-text" id="exp-info-vision"></div>
                    </div>

                </div>

                <div class="exp-info-footer">
                    <div class="exp-info-footer-note">
                        <i class="fas fa-flask-vial"></i>
                        This tool is being validated in the Aethvion Suite workshop before
                        potentially becoming its own standalone product.
                    </div>
                    <button class="exp-info-close-btn" id="exp-info-close-btn">
                        Got it
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(_overlay);

        // Close handlers
        document.getElementById('exp-info-close')?.addEventListener('click',     _hide);
        document.getElementById('exp-info-close-btn')?.addEventListener('click', _hide);
        _overlay.addEventListener('click', e => {
            if (e.target === _overlay) _hide();
        });

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && _overlay.classList.contains('open')) _hide();
        });

        return _overlay;
    }

    // ── Public API ─────────────────────────────────────────────────────────────
    function register(tabId, info) {
        _registry[tabId] = info;
    }

    function show(tabId) {
        const info = _registry[tabId];
        if (!info) {
            console.warn('[ExpInfo] No info registered for tab:', tabId);
            return;
        }

        const overlay = _ensureModal();

        // Populate fields
        const icon   = document.getElementById('exp-info-icon');
        const wrap   = document.getElementById('exp-info-icon-wrap');
        const title  = document.getElementById('exp-info-title');
        const status = document.getElementById('exp-info-status');
        const tagEl  = document.getElementById('exp-info-tagline');
        const howEl  = document.getElementById('exp-info-how');
        const visEl  = document.getElementById('exp-info-vision');
        const conWrap = document.getElementById('exp-info-concepts-wrap');
        const conEl  = document.getElementById('exp-info-concepts');

        if (icon)   icon.className  = info.icon || 'fas fa-flask-vial';
        if (wrap)   wrap.style.background = info.color || 'linear-gradient(135deg,#6366f1,#7c3aed)';
        if (title)  title.textContent     = info.name    || 'Experimental Tool';
        if (tagEl)  tagEl.textContent     = info.tagline || '';
        if (howEl)  howEl.textContent     = info.how     || '';
        if (visEl)  visEl.textContent     = info.vision  || '';

        // Status badge
        if (status) {
            status.textContent  = info.status || 'Experimental';
            status.className    = 'exp-info-badge exp-badge-' + (info.status || 'Experimental').toLowerCase().replace(/\s+/g, '-');
        }

        // Concept pills
        if (conEl && conWrap) {
            if (info.concepts?.length) {
                conEl.innerHTML = info.concepts.map(c => `
                    <div class="exp-info-concept">
                        <div class="exp-info-concept-icon"><i class="${_esc(c.icon || 'fas fa-circle')}"></i></div>
                        <div>
                            <div class="exp-info-concept-label">${_esc(c.label)}</div>
                            <div class="exp-info-concept-desc">${_esc(c.desc || '')}</div>
                        </div>
                    </div>
                `).join('');
                conWrap.style.display = '';
            } else {
                conWrap.style.display = 'none';
            }
        }

        overlay.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    function _hide() {
        if (_overlay) _overlay.classList.remove('open');
        document.body.style.overflow = '';
    }

    function _esc(s) {
        return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    window.ExpInfo = { register, show };
})();
