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
    const _loadedScripts = new Set(); // script paths fully loaded

    const SCRIPT_MAP = {
        'chat':             ['/static/js/mode-chat.js'],
        'agents':           ['/static/js/mode-agents.js'],
        'schedule':         ['/static/js/mode-schedule.js'],
        'agent-corp':       ['/static/js/mode-agentcorp.js'],
        'arena':            ['/static/js/mode-arena.js'],
        'logs':             ['/static/js/view-logs.js'],
        'aiconv':           ['/static/js/mode-aiconv.js'],
        'advaiconv':        ['/static/js/mode-adv-aiconv.js'],
        'researchboard':    ['/static/js/mode-research-board.js'],
        'explained':        ['/static/js/mode-explained.js'],
        'misaka-cipher':    ['/static/js/mode-misakacipher.js'],
        'axiom':            ['/static/js/mode-axiom.js'],
        'lyra':             ['/static/js/mode-lyra.js'],
        'companion-creator':['/static/js/companion-creator.js'],
        'files':            ['/static/js/view-files.js'],
        'memory':           ['/static/js/view-memory.js'],
        'companion-memory': ['/static/js/companion-memory.js'],
        'persistent-memory':['/static/js/view-persistent-memory.js'],
        'photo':            ['/static/js/mode-photo.js'],
        'audio':            ['/static/js/mode-audio.js'],
        'usage':            ['/static/js/view-usage.js'],
        'settings':         ['/static/js/view-settings.js'],
        'ports':            ['/static/js/view-ports.js'],
        'documentation':    ['/static/js/view-documentation.js'],
        'status':           ['/static/js/view-status.js'],
        'local-models':     ['/static/js/view-models.js'],
        'image-models':     ['/static/js/view-models.js'],
        'audio-models':     ['/static/js/view-audio-models.js'],
        'api-providers':    ['/static/js/view-api-providers.js'],
        '3d-models':        ['/static/js/view-3d-models.js'],
        '3d-gen':           ['/static/js/particle-sphere.js', '/static/js/mode-3d-gen.js'],
        'games-center':     ['/static/games/common/games-shared.js'],
        'game-logic-quest': ['/static/games/common/games-shared.js', '/static/games/logic-quest/logic-quest.js'],
        'game-blackjack':   ['/static/games/common/games-shared.js', '/static/games/blackjack/blackjack.js'],
        'game-results':     ['/static/games/common/games-shared.js', '/static/games/results/results.js'],
        'game-word-search': ['/static/games/common/games-shared.js', '/static/games/word_search/word_search.js'],
        'game-sudoku':      ['/static/games/common/games-shared.js', '/static/games/sudoku/sudoku.js'],
        'game-checkers':    ['/static/games/common/games-shared.js', '/static/games/checkers/checkers.js'],
        'game-smarter-than-ai': ['/static/games/common/games-shared.js', '/static/games/smarter_than_ai/smarter_than_ai.js']
    };

    /**
     * Resolve which DOM panel element to use for a given maintab name.
     */
    function _panelFor(tabName) {
        const panelId = FILE_TABS.has(tabName) ? 'files-panel' : `${tabName}-panel`;
        return { panelId, el: document.getElementById(panelId) };
    }

    /**
     * Lazy load script tags for a given tab.
     */
    function _loadScripts(tabName) {
        const scripts = SCRIPT_MAP[tabName] || [];
        const promises = scripts.map(src => {
            if (_loadedScripts.has(src)) return Promise.resolve();
            
            return new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = src + '?v=' + _initTs;
                if (src.includes('mode-3d-gen.js')) script.type = 'module';
                script.onload = () => {
                    _loadedScripts.add(src);
                    resolve();
                };
                script.onerror = reject;
                document.body.appendChild(script);
            });
        });
        return Promise.all(promises);
    }

    /**
     * Fetch and inject a partial if not already loaded.
     * Returns a Promise that resolves when the panel is ready.
     */
    function ensure(tabName) {
        const { panelId, el } = _panelFor(tabName);

        // Already loaded or panel has no partial attribute
        if (!el || !el.dataset.partial || _loaded.has(panelId)) return _loadScripts(tabName);

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
                
                // Lazy load scripts after HTML is in DOM
                return _loadScripts(tabName);
            })
            .then(function() {
                // Let JS modules know this panel is now in the DOM and scripts are loaded
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
