/**
 * AethvionLoops — Central registry for dashboard background polling loops.
 * Makes all registered setInterval loops inspectable, pausable/stoppable,
 * and configurable for "Start on Startup" (persisted in localStorage).
 */
(function (global) {
    'use strict';

    const PREFS_KEY = 'aethvion_loop_prefs_v1';
    const _loops = new Map();
    const _listeners = new Set();

    const CRIT_ORDER = { critical: 0, standard: 1, optional: 2 };

    function _loadPrefs() {
        try {
            return JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') || {};
        } catch {
            return {};
        }
    }

    function _savePrefs(prefs) {
        try {
            localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
        } catch {}
    }

    function _emit() {
        _listeners.forEach(cb => {
            try { cb(); } catch {}
        });
    }

    function _clearTimer(entry) {
        if (entry._timerId !== null) {
            clearInterval(entry._timerId);
            entry._timerId = null;
        }
    }

    async function _executeTick(entry, manual = false) {
        if (!entry || typeof entry.fn !== 'function') return;
        if (!manual && entry.pauseWhenHidden && typeof document !== 'undefined' && document.hidden) {
            entry.skippedHiddenCount += 1;
            return;
        }
        if (entry._inFlight) return;
        entry._inFlight = true;
        const started = performance.now();
        try {
            await entry.fn();
            entry.lastError = null;
        } catch (err) {
            entry.lastError = err?.message || String(err);
        } finally {
            entry._inFlight = false;
            entry.runCount += 1;
            entry.lastRunAt = Date.now();
            entry.lastDurationMs = Math.round(performance.now() - started);
            _emit();
        }
    }

    function _startTimer(entry) {
        _clearTimer(entry);
        const ms = Math.max(250, Number(entry.intervalMs) || 10000);
        entry._timerId = setInterval(() => _executeTick(entry, false), ms);
        entry.status = 'running';
    }

    function register(id, opts = {}) {
        if (!id || typeof opts.fn !== 'function') return null;

        const prefs = _loadPrefs();
        const savedPref = prefs[id];
        const defaultAutoStart = opts.defaultAutoStart !== undefined ? !!opts.defaultAutoStart : true;
        const autoStart = (savedPref && typeof savedPref.autoStart === 'boolean')
            ? savedPref.autoStart
            : defaultAutoStart;

        const existing = _loops.get(id);
        if (existing) _clearTimer(existing);

        const entry = {
            id,
            name: opts.name || id,
            category: opts.category || 'General',
            criticality: ['critical', 'standard', 'optional'].includes(opts.criticality) ? opts.criticality : 'standard',
            description: opts.description || '',
            intervalMs: Math.max(250, Number(opts.intervalMs) || 10000),
            fn: opts.fn,
            pauseWhenHidden: opts.pauseWhenHidden !== undefined ? !!opts.pauseWhenHidden : true,
            defaultAutoStart,
            autoStart,
            status: 'stopped',
            runCount: existing ? existing.runCount : 0,
            skippedHiddenCount: existing ? existing.skippedHiddenCount : 0,
            lastRunAt: existing ? existing.lastRunAt : null,
            lastDurationMs: existing ? existing.lastDurationMs : null,
            lastError: null,
            _timerId: null,
            _inFlight: false,
        };

        _loops.set(id, entry);

        // Respect startup preference unless caller explicitly forces startNow: false
        const shouldStart = opts.startNow !== undefined ? (!!opts.startNow && autoStart) : autoStart;
        if (shouldStart) {
            _startTimer(entry);
        }
        _emit();
        return id;
    }

    function start(id) {
        const entry = _loops.get(id);
        if (!entry) return false;
        _startTimer(entry);
        _emit();
        return true;
    }

    function pause(id) {
        const entry = _loops.get(id);
        if (!entry) return false;
        _clearTimer(entry);
        entry.status = 'paused';
        _emit();
        return true;
    }

    function stop(id) {
        const entry = _loops.get(id);
        if (!entry) return false;
        _clearTimer(entry);
        entry.status = 'stopped';
        _emit();
        return true;
    }

    async function runNow(id) {
        const entry = _loops.get(id);
        if (!entry) return false;
        await _executeTick(entry, true);
        return true;
    }

    function setAutoStart(id, enabled) {
        const entry = _loops.get(id);
        if (!entry) return false;
        entry.autoStart = !!enabled;
        const prefs = _loadPrefs();
        prefs[id] = { ...(prefs[id] || {}), autoStart: entry.autoStart };
        _savePrefs(prefs);
        _emit();
        return true;
    }

    function setOptionalAutoStart(enabled, applyNow = true) {
        const prefs = _loadPrefs();
        _loops.forEach(entry => {
            if (entry.criticality === 'optional') {
                entry.autoStart = !!enabled;
                prefs[entry.id] = { ...(prefs[entry.id] || {}), autoStart: entry.autoStart };
                if (applyNow) {
                    if (enabled && entry.status !== 'running') _startTimer(entry);
                    if (!enabled && entry.status === 'running') {
                        _clearTimer(entry);
                        entry.status = 'stopped';
                    }
                }
            }
        });
        _savePrefs(prefs);
        _emit();
    }

    function setCategoryAutoStart(category, enabled, applyNow = true) {
        const prefs = _loadPrefs();
        _loops.forEach(entry => {
            if (entry.category.toLowerCase() === String(category || '').toLowerCase()) {
                entry.autoStart = !!enabled;
                prefs[entry.id] = { ...(prefs[entry.id] || {}), autoStart: entry.autoStart };
                if (applyNow) {
                    if (enabled && entry.status !== 'running') _startTimer(entry);
                    if (!enabled && entry.status === 'running') {
                        _clearTimer(entry);
                        entry.status = 'stopped';
                    }
                }
            }
        });
        _savePrefs(prefs);
        _emit();
    }

    function list() {
        return Array.from(_loops.values())
            .map(e => ({
                id: e.id,
                name: e.name,
                category: e.category,
                criticality: e.criticality,
                description: e.description,
                intervalMs: e.intervalMs,
                pauseWhenHidden: e.pauseWhenHidden,
                defaultAutoStart: e.defaultAutoStart,
                autoStart: e.autoStart,
                status: e.status,
                runCount: e.runCount,
                skippedHiddenCount: e.skippedHiddenCount,
                lastRunAt: e.lastRunAt,
                lastDurationMs: e.lastDurationMs,
                lastError: e.lastError,
            }))
            .sort((a, b) => {
                const ca = CRIT_ORDER[a.criticality] ?? 9;
                const cb = CRIT_ORDER[b.criticality] ?? 9;
                if (ca !== cb) return ca - cb;
                return a.name.localeCompare(b.name);
            });
    }

    function getSummary() {
        let running = 0, paused = 0, stopped = 0, critical = 0, optional = 0;
        _loops.forEach(e => {
            if (e.status === 'running') running += 1;
            else if (e.status === 'paused') paused += 1;
            else stopped += 1;
            if (e.criticality === 'critical') critical += 1;
            if (e.criticality === 'optional') optional += 1;
        });
        return { total: _loops.size, running, paused, stopped, critical, optional };
    }

    function onChange(cb) {
        if (typeof cb !== 'function') return () => {};
        _listeners.add(cb);
        return () => _listeners.delete(cb);
    }

    global.AethvionLoops = {
        register,
        start,
        pause,
        stop,
        runNow,
        setAutoStart,
        setOptionalAutoStart,
        setCategoryAutoStart,
        list,
        getSummary,
        onChange,
    };
})(window);
