/**
 * Aethvion Suite — Partial Loader
 *
 * Fetches panel HTML on first activation and injects it into the placeholder div.
 * Every main-tab-panel in index.html is an empty shell with data-partial="name".
 * The actual HTML lives in /static/partials/{name}.html.
 *
 * Usage (called by switchMainTab in core.js):
 *   await window._partialLoader.ensure('chat');
 */
(function () {
    // panels that share one DOM element (all map to files-panel)
    const FILE_TABS = new Set(['output', 'screenshots', 'camera', 'uploads']);

    const _loaded  = new Set();   // panelIds fully injected
    const _pending = new Map();   // panelId → Promise (in-flight)

    /**
     * Resolve which DOM panel element to use for a given maintab name.
     */
    function _panelFor(tabName) {
        const panelId = FILE_TABS.has(tabName) ? 'files-panel' : `${tabName}-panel`;
        return { panelId, el: document.getElementById(panelId) };
    }

    /**
     * Fetch and inject a partial if not already loaded.
     * Returns a Promise that resolves when the panel is ready.
     */
    function ensure(tabName) {
        const { panelId, el } = _panelFor(tabName);

        // Already loaded or panel has no partial attribute
        if (!el || !el.dataset.partial || _loaded.has(panelId)) return Promise.resolve();

        // Return the in-flight promise if already fetching
        if (_pending.has(panelId)) return _pending.get(panelId);

        const partial = el.dataset.partial;
        // Use BUILD_VERSION if available for cache-busting, otherwise a module-level timestamp
        const v = (typeof BUILD_VERSION !== 'undefined' && BUILD_VERSION) || _initTs;

        const promise = fetch(`/static/partials/${partial}.html?v=${v}`)
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.text();
            })
            .then(function (html) {
                el.innerHTML = html;
                _loaded.add(panelId);
                _pending.delete(panelId);
                // Let JS modules know this panel is now in the DOM
                document.dispatchEvent(new CustomEvent('panelLoaded', {
                    detail: { tabName: tabName, panelId: panelId, el: el }
                }));
            })
            .catch(function (err) {
                console.error('[PartialLoader] Failed to load "' + partial + '":', err);
                el.innerHTML =
                    '<div style="display:flex;align-items:center;justify-content:center;height:200px;' +
                    'gap:10px;color:var(--text-tertiary,#888)">' +
                    '<i class="fas fa-exclamation-triangle"></i> Panel failed to load.</div>';
                _loaded.add(panelId);   // don't retry endlessly
                _pending.delete(panelId);
            });

        _pending.set(panelId, promise);
        return promise;
    }

    /**
     * True if the panel for tabName has already been injected.
     */
    function isLoaded(tabName) {
        const { panelId, el } = _panelFor(tabName);
        return !el || !el.dataset.partial || _loaded.has(panelId);
    }

    /**
     * Fire-and-forget background preload (useful for likely-next tabs).
     */
    function preload() {
        var tabs = Array.prototype.slice.call(arguments);
        tabs.forEach(function (t) { ensure(t); });
    }

    // Timestamp used as a cache-buster before BUILD_VERSION is available
    var _initTs = Date.now();

    window._partialLoader = { ensure: ensure, isLoaded: isLoaded, preload: preload };
})();
