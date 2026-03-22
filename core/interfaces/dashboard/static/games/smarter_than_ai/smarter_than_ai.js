/**
 * Are You Smarter Than AI? — Gameshow Frontend
 * Vanilla JS, IIFE, no frameworks.
 */

(function () {

    // ── State ──────────────────────────────────────────────────────────────────
    let _show   = null;   // current show state from server
    let _timer  = null;   // countdown interval handle
    let _timeLeft = 0;    // seconds remaining
    let _humanPlayerId = null;  // id of the human player (first human found)
    let _humanAnswered = false;
    let _roundActive = false;
    let _isJudging   = false;   // guard against double-judge

    // AI answers received from server but hidden until reveal
    let _pendingAIAnswers = {};

    // Next-round auto-countdown
    let _nextRoundTimer = null;
    let _nextRoundCountdown = 0;

    // Track locally-configured players before show creation
    let _localPlayers = [];
    let _playerCounter = 0;

    // ── DOM helpers ────────────────────────────────────────────────────────────

    function el(id) { return document.getElementById(id); }

    // ── API helpers ────────────────────────────────────────────────────────────

    async function staPost(path, body) {
        const res = await fetch(`/api/smarter-than-ai/${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return await res.json();
    }

    async function staGet(path) {
        const res = await fetch(`/api/smarter-than-ai/${path}`);
        return await res.json();
    }

    // ── Initialise ─────────────────────────────────────────────────────────────

    function staInit() {
        _renderLobby();

        el('sta-add-human-btn')?.addEventListener('click', () => staAddPlayer('human'));
        el('sta-add-ai-btn')?.addEventListener('click',    () => staAddPlayer('ai'));
        el('sta-start-btn')?.addEventListener('click',     staStartShow);
        el('sta-next-round-btn')?.addEventListener('click', staNextRound);
        el('sta-judge-btn')?.addEventListener('click',     staJudgeRound);
        el('sta-play-again-btn')?.addEventListener('click', _resetToLobby);

        // Load models into GM selector
        loadGameModels(el('sta-gm-model-select'));
    }

    // ── Lobby ──────────────────────────────────────────────────────────────────

    function _renderLobby() {
        _show   = null;
        _timer  = null;
        _localPlayers = [];
        _playerCounter = 0;
        _humanPlayerId = null;

        _showScreen('sta-lobby-screen');
        _refreshPlayerList();
        staSetStatus('');
    }

    function _resetToLobby() {
        _stopTimer();
        _stopNextRoundCountdown();
        _renderLobby();
    }

    function staAddPlayer(type) {
        _playerCounter++;
        const defaultName = type === 'human'
            ? `Player ${_playerCounter}`
            : `AI-${_playerCounter}`;

        _localPlayers.push({
            _localId: 'lp_' + _playerCounter,
            name: defaultName,
            type: type,
            model: type === 'ai' ? 'auto' : null
        });
        _refreshPlayerList();
    }

    function staRemovePlayer(localId) {
        _localPlayers = _localPlayers.filter(p => p._localId !== localId);
        _refreshPlayerList();
    }

    function _refreshPlayerList() {
        const list = el('sta-player-list');
        if (!list) return;

        if (_localPlayers.length === 0) {
            list.innerHTML = '<div style="font-size:0.78rem;color:var(--text-muted);padding:0.5rem 0;">No players yet. Add at least one player to start.</div>';
        } else {
            list.innerHTML = _localPlayers.map(p => _buildPlayerCardHTML(p)).join('');

            // Attach AI model selects
            _localPlayers.forEach(p => {
                const nameInput = el(`sta-player-name-${p._localId}`);
                if (nameInput) {
                    nameInput.addEventListener('input', () => { p.name = nameInput.value; });
                }

                if (p.type === 'ai') {
                    const modelSel = el(`sta-player-model-${p._localId}`);
                    if (modelSel) {
                        loadGameModels(modelSel).then(() => {
                            if (p.model && p.model !== 'auto') {
                                modelSel.value = p.model;
                            }
                        });
                        modelSel.addEventListener('change', () => { p.model = modelSel.value; });
                    }
                }
            });
        }

        // Toggle start button
        const startBtn = el('sta-start-btn');
        if (startBtn) startBtn.disabled = _localPlayers.length === 0;
    }

    function _buildPlayerCardHTML(p) {
        const icon = p.type === 'human' ? '👤' : '🤖';
        const modelSelect = p.type === 'ai'
            ? `<select class="sta-player-model-select" id="sta-player-model-${p._localId}">
                 <option value="auto">⚡ Auto</option>
               </select>`
            : `<span class="sta-model-badge human">Human</span>`;

        return `
        <div class="sta-player-card ${p.type}" id="sta-pc-${p._localId}">
            <span class="sta-player-icon">${icon}</span>
            <input class="sta-player-name-input" id="sta-player-name-${p._localId}"
                   type="text" value="${_esc(p.name)}" placeholder="Name..." />
            ${modelSelect}
            <button class="sta-remove-btn" title="Remove" onclick="window._staRemovePlayer('${p._localId}')">✕</button>
        </div>`;
    }

    // ── Start show ─────────────────────────────────────────────────────────────

    async function staStartShow() {
        if (_localPlayers.length === 0) return;

        const gmModel    = el('sta-gm-model-select')?.value || 'auto';
        const totalRounds = parseInt(el('sta-rounds-select')?.value || '5', 10);
        const timeLimit  = parseInt(el('sta-time-select')?.value || '30', 10);

        const playerConfigs = _localPlayers.map(p => ({
            name: p.name || 'Unknown',
            type: p.type,
            model: p.type === 'ai' ? (p.model || 'auto') : null
        }));

        _setThinking('Setting up the show...');
        el('sta-start-btn').disabled = true;

        const data = await staPost('show', {
            game_master_model: gmModel,
            players: playerConfigs,
            total_rounds: totalRounds,
            time_limit_seconds: timeLimit
        });

        if (!data.success) {
            staSetStatus('Failed to create show: ' + (data.detail || data.error || 'Unknown error'));
            el('sta-start-btn').disabled = false;
            return;
        }

        _show = data.state;

        // Identify human player
        _humanPlayerId = (_show.players.find(p => p.type === 'human') || {}).id || null;

        _showScreen('sta-game-screen');
        _renderPodiums();
        staSetStatus('');
        _updateRoundIndicator();

        // Start first round immediately
        await staStartRound();
    }

    // ── Round lifecycle ────────────────────────────────────────────────────────

    async function staStartRound() {
        _stopNextRoundCountdown();
        _setThinking('The Game Master is preparing a question...');
        _setBtns({ judge: false, next: false });
        _humanAnswered = false;
        _roundActive = false;
        _isJudging   = false;
        _pendingAIAnswers = {};

        // Reset next-round button text
        const nextBtn = el('sta-next-round-btn');
        if (nextBtn) nextBtn.textContent = 'Next Round';

        el('sta-correct-reveal')?.classList.remove('visible');
        _clearAnswerBoxes();

        const data = await staPost('round/start', { show_id: _show.show_id });
        if (!data.success) {
            staSetStatus('Error starting round: ' + (data.detail || 'Unknown'));
            return;
        }

        if (data.finished) {
            _show = data.state;
            staShowFinal();
            return;
        }

        _show = data.state;
        const round = data.round;

        _updateRoundIndicator();
        _displayQuestion(round);
        _renderAnswerBoxes(round);
        staSetStatus('');
        _roundActive = true;

        // Start AI answering and timer concurrently
        _startTimer(_show.time_limit_seconds);
        _triggerAIAnswers();
    }

    function _displayQuestion(round) {
        const catBadge = el('sta-category-badge');
        const questionText = el('sta-question-text');
        if (catBadge)    catBadge.textContent   = round.category || 'General';
        if (questionText) questionText.textContent = round.question;

        const humanInput = el('sta-human-answer-input');
        const submitBtn  = el('sta-submit-answer-btn');
        if (humanInput) {
            humanInput.value = '';
            humanInput.disabled = _humanPlayerId === null;
        }
        if (submitBtn) submitBtn.disabled = _humanPlayerId === null;
    }

    function _renderAnswerBoxes(round) {
        const grid = el('sta-answers-grid');
        if (!grid) return;

        grid.innerHTML = _show.players.map(p => `
            <div class="sta-answer-box ${p.type === 'human' ? 'human-player' : 'ai-player'}"
                 id="sta-ab-${p.id}">
                <div class="sta-answer-player">
                    <div class="sta-answer-player-dot"></div>
                    ${_esc(p.name)}
                </div>
                <div class="sta-answer-text" id="sta-at-${p.id}">
                    ${p.type === 'ai'
                        ? '<em style="color:var(--text-muted)">🤔 Thinking...</em>'
                        : '<em style="color:var(--text-muted)">Waiting for your answer...</em>'}
                </div>
                <div class="sta-answer-status" id="sta-as-${p.id}"></div>
            </div>
        `).join('');
    }

    function _clearAnswerBoxes() {
        const grid = el('sta-answers-grid');
        if (grid) grid.innerHTML = '';
    }

    // ── AI answers (locked until reveal) ──────────────────────────────────────

    async function _triggerAIAnswers() {
        const hasAI = _show.players.some(p => p.type === 'ai');
        if (!hasAI) return;

        const data = await staPost('round/ai-answers', { show_id: _show.show_id });
        if (!data.success) return;

        // Store answers privately and show "locked" badge in UI
        const round = data.round;
        _show.players.filter(p => p.type === 'ai').forEach(p => {
            const ans = round.answers[p.id];
            if (ans) {
                _pendingAIAnswers[p.id] = ans;
                _setAnswerBoxLocked(p.id);
            }
        });

        _checkAllAnswered(round);
    }

    function _setAnswerBoxLocked(playerId) {
        const textEl = el(`sta-at-${playerId}`);
        if (textEl) {
            textEl.innerHTML = '<em style="color:var(--accent-gold,#f0b429)">🔒 Answer locked in</em>';
        }
    }

    /** Reveal pending AI answers in the UI (called just before judging). */
    function _revealAIAnswers() {
        Object.entries(_pendingAIAnswers).forEach(([playerId, answer]) => {
            const textEl = el(`sta-at-${playerId}`);
            if (textEl) textEl.textContent = answer;
        });
        _pendingAIAnswers = {};
    }

    function _setAnswerBox(playerId, answer) {
        const textEl = el(`sta-at-${playerId}`);
        if (textEl) textEl.textContent = answer;
    }

    // ── Human answer submission ────────────────────────────────────────────────

    async function staSubmitHumanAnswer() {
        if (!_humanPlayerId || _humanAnswered) return;

        const input = el('sta-human-answer-input');
        const answer = input?.value?.trim();
        if (!answer) return;

        _humanAnswered = true;
        input.disabled = true;
        el('sta-submit-answer-btn').disabled = true;

        _setAnswerBox(_humanPlayerId, answer);

        const data = await staPost('round/answer', {
            show_id: _show.show_id,
            player_id: _humanPlayerId,
            answer: answer
        });

        if (!data.success) {
            staSetStatus('Error submitting answer.');
            return;
        }

        _checkAllAnswered(data.round);
    }

    function _checkAllAnswered(round) {
        if (!_roundActive || _isJudging) return;

        const allIds     = _show.players.map(p => p.id);
        const answeredIds = Object.keys(round.answers || {});
        const allDone    = allIds.every(id => answeredIds.includes(id));

        if (allDone) {
            _stopTimer();
            staSetStatus('All players answered! Revealing...');
            _revealAIAnswers();
            // Small pause so the reveal is visible before judging
            setTimeout(() => staJudgeRound(), 700);
        }
    }

    // ── Timer ──────────────────────────────────────────────────────────────────

    function _startTimer(seconds) {
        _stopTimer();
        _timeLeft = seconds;
        _updateTimerUI();

        _timer = setInterval(() => {
            _timeLeft--;
            _updateTimerUI();

            if (_timeLeft <= 0) {
                _stopTimer();
                _onTimerExpire();
            }
        }, 1000);
    }

    function _stopTimer() {
        if (_timer) { clearInterval(_timer); _timer = null; }
    }

    function _updateTimerUI() {
        const numEl  = el('sta-timer-num');
        const circEl = el('sta-timer');
        const totalSecs = _show?.time_limit_seconds || 30;

        if (numEl) numEl.textContent = _timeLeft;

        const pct = (_timeLeft / totalSecs) * 100;
        if (circEl) {
            circEl.style.setProperty('--progress', pct + '%');
            if (_timeLeft <= 5) {
                circEl.classList.add('urgent');
            } else {
                circEl.classList.remove('urgent');
            }
        }
    }

    async function _onTimerExpire() {
        if (!_roundActive || _isJudging) return;

        // Reveal all AI answers that were locked
        _revealAIAnswers();

        staSetStatus("Time's up! Judging answers...");

        // Auto-submit blank for human if they didn't answer
        if (_humanPlayerId && !_humanAnswered) {
            _humanAnswered = true;
            const input = el('sta-human-answer-input');
            if (input) input.disabled = true;
            el('sta-submit-answer-btn').disabled = true;

            await staPost('round/answer', {
                show_id: _show.show_id,
                player_id: _humanPlayerId,
                answer: "(no answer)"
            });
            _setAnswerBox(_humanPlayerId, "(no answer)");
        }

        await staJudgeRound();
    }

    // ── Judging ────────────────────────────────────────────────────────────────

    async function staJudgeRound() {
        if (_isJudging) return;   // prevent double-fire
        _isJudging   = true;
        _roundActive = false;
        _stopTimer();
        _setBtns({ judge: false, next: false });
        _setThinking('The Game Master is judging all answers...');

        const data = await staPost('round/judge', { show_id: _show.show_id });

        if (!data.success) {
            staSetStatus('Error judging round: ' + (data.detail || 'Unknown'));
            _isJudging = false;
            return;
        }

        _show = data.state;

        // Show correct answer reveal
        const revealEl = el('sta-correct-reveal');
        if (revealEl) {
            el('sta-correct-answer-text').textContent = data.correct_answer || '(unknown)';
            el('sta-explanation-text').textContent    = data.explanation   || '';
            revealEl.classList.add('visible');
        }

        // Animate answer boxes with correct/wrong colours
        await staRevealAnswers(data.judgements || []);

        // Update podiums
        _renderPodiums();

        staSetStatus('');

        // Check if show finished
        if (_show.state === 'finished') {
            setTimeout(staShowFinal, 2000);
        } else {
            // Start 5-second auto-countdown to next round
            _startNextRoundCountdown();
        }
    }

    async function staRevealAnswers(judgements) {
        for (let i = 0; i < judgements.length; i++) {
            const j = judgements[i];
            const box = el(`sta-ab-${j.player_id}`);
            const statusEl = el(`sta-as-${j.player_id}`);

            await _delay(300 * i);

            if (box) {
                box.classList.remove('correct', 'wrong');
                box.classList.add(j.is_correct ? 'correct' : 'wrong');
            }
            if (statusEl) {
                statusEl.textContent = j.is_correct
                    ? `+${j.points} pts`
                    : '✗ Wrong';
            }
        }
    }

    // ── Next-round countdown ───────────────────────────────────────────────────

    function _startNextRoundCountdown() {
        _nextRoundCountdown = 5;
        _setBtns({ judge: false, next: true });
        _updateNextRoundBtn();

        _nextRoundTimer = setInterval(() => {
            _nextRoundCountdown--;
            _updateNextRoundBtn();

            if (_nextRoundCountdown <= 0) {
                _stopNextRoundCountdown();
                staStartRound();
            }
        }, 1000);
    }

    function _stopNextRoundCountdown() {
        if (_nextRoundTimer) { clearInterval(_nextRoundTimer); _nextRoundTimer = null; }
        _nextRoundCountdown = 0;
    }

    function _updateNextRoundBtn() {
        const nextBtn = el('sta-next-round-btn');
        if (!nextBtn) return;
        nextBtn.textContent = _nextRoundCountdown > 0
            ? `Next Round (${_nextRoundCountdown})`
            : 'Next Round';
        nextBtn.disabled = false;
    }

    // ── Next round ─────────────────────────────────────────────────────────────

    async function staNextRound() {
        _stopNextRoundCountdown();
        const nextBtn = el('sta-next-round-btn');
        if (nextBtn) nextBtn.textContent = 'Next Round';
        await staStartRound();
    }

    // ── Final screen ───────────────────────────────────────────────────────────

    function staShowFinal() {
        _stopTimer();
        _stopNextRoundCountdown();
        _showScreen('sta-final-screen');

        const players = [...(_show?.players || [])].sort((a, b) => b.score - a.score);
        const winner  = players[0];

        const trophyEl   = el('sta-final-trophy');
        const titleEl    = el('sta-final-title');
        const winnerEl   = el('sta-final-winner-name');
        const boardEl    = el('sta-final-leaderboard');

        if (trophyEl) trophyEl.textContent = winner?.type === 'ai' ? '🤖' : '🏆';
        if (titleEl)  titleEl.textContent  = winner ? `${_esc(winner.name)} Wins!` : 'Game Over!';
        if (winnerEl) winnerEl.textContent = winner ? `Final Score: ${winner.score} pts` : '';

        if (boardEl) {
            boardEl.innerHTML = players.map((p, i) => `
                <div class="sta-final-row" style="animation-delay:${0.05 + i * 0.06}s">
                    <div class="sta-final-rank">${['🥇','🥈','🥉'][i] || (i + 1)}</div>
                    <div class="sta-final-player-name">${_esc(p.name)}</div>
                    <span class="sta-final-type-badge ${p.type}">${p.type === 'human' ? 'Human' : 'AI'}</span>
                    <div class="sta-final-score">${p.score}</div>
                </div>
            `).join('');
        }
    }

    // ── Podiums ────────────────────────────────────────────────────────────────

    function _renderPodiums() {
        const container = el('sta-podiums');
        if (!container || !_show?.players) return;

        const maxScore = Math.max(..._show.players.map(p => p.score), 0);

        container.innerHTML = _show.players.map(p => {
            const isLeading = p.score > 0 && p.score === maxScore;
            return `
            <div class="sta-podium ${isLeading ? 'leading' : ''} ${p.type}-type" id="sta-pod-${p.id}">
                <div class="sta-podium-name" title="${_esc(p.name)}">${_esc(p.name.length > 9 ? p.name.slice(0, 8) + '…' : p.name)}</div>
                <div class="sta-podium-score" id="sta-pod-score-${p.id}">${p.score}</div>
            </div>`;
        }).join('');
    }

    // ── UI helpers ─────────────────────────────────────────────────────────────

    function _showScreen(screenId) {
        ['sta-lobby-screen', 'sta-game-screen', 'sta-final-screen'].forEach(id => {
            const screen = el(id);
            if (screen) screen.style.display = id === screenId ? '' : 'none';
        });

        // Show podiums + controls only during active game
        const inGame = screenId === 'sta-game-screen';
        const podiumsSection = el('sta-podiums-section');
        const controlsBar    = el('sta-controls-bar');
        if (podiumsSection) podiumsSection.style.display = inGame ? '' : 'none';
        if (controlsBar)    controlsBar.style.display    = inGame ? '' : 'none';
    }

    function staSetStatus(msg, isThinking = false) {
        const bar = el('sta-status-bar');
        if (!bar) return;
        bar.className = 'sta-status-bar' + (isThinking ? ' thinking' : '');
        if (isThinking) {
            bar.innerHTML = `<span>${_esc(msg)}</span><span class="sta-thinking-dots"></span>`;
        } else {
            bar.textContent = msg;
        }
    }

    function _setThinking(msg) {
        staSetStatus(msg, true);
    }

    function _setBtns(opts) {
        const judgeBtn = el('sta-judge-btn');
        const nextBtn  = el('sta-next-round-btn');
        if (judgeBtn) judgeBtn.disabled = !opts.judge;
        if (nextBtn)  nextBtn.disabled  = !opts.next;
    }

    function _updateRoundIndicator() {
        const ind = el('sta-round-indicator');
        if (!ind || !_show) return;
        const cur = _show.current_round_index + 1;
        const tot = _show.total_rounds;
        ind.textContent = cur > 0 && cur <= tot ? `Round ${cur} / ${tot}` : `${tot} Rounds`;
    }

    function _delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function _esc(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── Register ───────────────────────────────────────────────────────────────

    document.addEventListener('DOMContentLoaded', () => {
        staInit();

        // Human answer submit button
        el('sta-submit-answer-btn')?.addEventListener('click', staSubmitHumanAnswer);

        // Also submit on Enter key
        el('sta-human-answer-input')?.addEventListener('keydown', e => {
            if (e.key === 'Enter') staSubmitHumanAnswer();
        });

        if (typeof registerGame === 'function') {
            registerGame('smarter-than-ai', {
                onTabSwitch: () => {
                    // Nothing special needed on tab switch
                }
            });
        }
    });

    // Expose to inline onclick
    window._staRemovePlayer = function(localId) {
        staRemovePlayer(localId);
    };

})();
