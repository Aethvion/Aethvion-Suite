/**
 * Logic Quest: The Black Box
 * AI-powered deduction game logic.
 */

(function () {
    let session = null;

    // UI elements
    const elements = {
        panel: 'game-logic-quest-panel',
        modelSelect: 'lq-model-select',
        difficultySelect: 'lq-difficulty-select',
        attemptsDisplay: 'lq-attempts-display',
        scoreDisplay: 'lq-score-display',
        display: 'lq-display',
        testInput: 'lq-test-input',
        testBtn: 'lq-test-btn',
        guessInput: 'lq-guess-input',
        guessBtn: 'lq-guess-btn',
        history: 'lq-history',
        hintBadge: 'lq-hint-text',
        resetBtn: 'lq-reset-btn',
        hintBtn: 'lq-hint-btn',
        revealBtn: 'lq-reveal-btn',
        oracle: 'lq-oracle'
    };

    /**
     * Start a new game session
     */
    async function startNewGame() {
        const model = document.getElementById(elements.modelSelect)?.value || 'auto';
        const difficulty = document.getElementById(elements.difficultySelect)?.value || 'easy';

        // Visual feedback
        const oracle = document.getElementById(elements.oracle);
        if (oracle) oracle.classList.add('processing');
        setGameDisplay(document.getElementById(elements.display), 'Initializing AI Game Master...', 'loading');

        try {
            const data = await gameApiPost('new', {
                game_type: 'logic-quest',
                difficulty: difficulty,
                model: model
            });

            if (data.success) {
                session = {
                    id: data.session_id,
                    maxAttempts: data.max_attempts,
                    attempts: 0,
                    history: [],
                    hint: data.hint,
                    model: data.model_used
                };

                // Update UI
                document.getElementById(elements.attemptsDisplay).textContent = `0 / ${session.maxAttempts}`;
                document.getElementById(elements.scoreDisplay).textContent = '0';
                document.getElementById(elements.hintBadge).textContent = session.hint || 'Numbers or strings...';
                document.getElementById(elements.history).innerHTML = '<div class="placeholder-text">No tests yet</div>';
                setGameDisplay(document.getElementById(elements.display), 'The Oracle is ready. Enter a test input.');

                hideGameOverlay('logic-quest');
                
                const startOverlay = document.getElementById('game-overlay-logic-quest-start');
                if (startOverlay) startOverlay.style.display = 'none';

                // Clear inputs
                document.getElementById(elements.testInput).value = '';
                document.getElementById(elements.guessInput).value = '';

                console.log(`Logic Quest started with model: ${session.model}`);
            } else {
                setGameDisplay(document.getElementById(elements.display), `Error: ${data.error}`, 'error');
            }
        } catch (err) {
            console.error(err);
            setGameDisplay(document.getElementById(elements.display), 'Failed to connect to games server.', 'error');
        } finally {
            if (oracle) oracle.classList.remove('processing');
        }
    }

    /**
     * Test an input against the secret rule
     */
    async function testInput() {
        if (!session || session.completed) return;

        const inputVal = document.getElementById(elements.testInput).value.trim();
        if (!inputVal) return;

        const oracle = document.getElementById(elements.oracle);
        if (oracle) oracle.classList.add('processing');

        try {
            const data = await gameApiPost('action', {
                session_id: session.id,
                action: 'test',
                data: { input: inputVal }
            });

            if (data.success) {
                session.attempts = data.attempts;
                session.history = data.history;

                // Update UI
                document.getElementById(elements.attemptsDisplay).textContent = `${session.attempts} / ${session.maxAttempts}`;
                setGameDisplay(document.getElementById(elements.display), `IN: ${inputVal} → OUT: ${data.output}`);
                renderHistory(document.getElementById(elements.history), session.history);

                document.getElementById(elements.testInput).value = '';
                document.getElementById(elements.testInput).focus();
            } else {
                setGameDisplay(document.getElementById(elements.display), data.error || 'Test failed', 'error');
            }
        } catch (err) {
            setGameDisplay(document.getElementById(elements.display), 'Connection error during test', 'error');
        } finally {
            if (oracle) oracle.classList.remove('processing');
        }
    }

    /**
     * Guess the secret rule
     */
    async function submitGuess() {
        if (!session || session.completed) return;

        const guessVal = document.getElementById(elements.guessInput).value.trim();
        if (!guessVal) return;

        const oracle = document.getElementById(elements.oracle);
        if (oracle) oracle.classList.add('processing');

        try {
            const data = await gameApiPost('action', {
                session_id: session.id,
                action: 'guess',
                data: { guess: guessVal }
            });

            if (data.success) {
                session.attempts = data.attempts;
                document.getElementById(elements.attemptsDisplay).textContent = `${session.attempts} / ${session.maxAttempts}`;

                if (data.correct) {
                    session.completed = true;
                    setGameDisplay(document.getElementById(elements.display), 'Success! Rule deduced.', 'correct');
                    showGameOverlay('logic-quest', {
                        title: 'MYSTERY SOLVED',
                        subtitle: `The secret rule was: ${data.rule}\n\n${data.message}`,
                        score: data.score
                    });
                } else {
                    setGameDisplay(document.getElementById(elements.display), data.message || 'Incorrect guess.', 'error');
                    setTimeout(() => {
                        if (!session.completed) setGameDisplay(document.getElementById(elements.display), 'Keep testing inputs...');
                    }, 3000);
                }
            }
        } catch (err) {
            console.error(err);
        } finally {
            if (oracle) oracle.classList.remove('processing');
        }
    }

    /**
     * Request a hint from AI
     */
    async function requestHint() {
        if (!session || session.completed) return;

        try {
            const data = await gameApiPost('action', {
                session_id: session.id,
                action: 'hint',
                data: {}
            });
            if (data.success) {
                setGameDisplay(document.getElementById(elements.display), `Hint: ${data.hint}`);
            }
        } catch (err) { }
    }

    /**
     * Reveal the secret rule
     */
    async function revealAnswer() {
        if (!session || session.completed) return;

        if (!confirm("Are you sure you want to give up and see the answer?")) return;

        const oracle = document.getElementById(elements.oracle);
        if (oracle) oracle.classList.add('processing');

        try {
            const data = await gameApiPost('action', {
                session_id: session.id,
                action: 'reveal',
                data: {}
            });

            if (data.success) {
                session.completed = true;
                setGameDisplay(document.getElementById(elements.display), 'Game Over. Answer revealed.', 'error');
                showGameOverlay('logic-quest', {
                    title: 'GAVE UP',
                    subtitle: `The secret rule was: ${data.rule}\n\n${data.message}`,
                    score: 0
                });
            }
        } catch (err) {
            console.error(err);
        } finally {
            if (oracle) oracle.classList.remove('processing');
        }
    }

    // Initialize the module
    document.addEventListener('DOMContentLoaded', () => {
        // Models dropdown
        loadGameModels(document.getElementById(elements.modelSelect));

        // Event listeners
        document.getElementById(elements.testBtn)?.addEventListener('click', testInput);
        document.getElementById(elements.guessBtn)?.addEventListener('click', submitGuess);
        document.getElementById(elements.resetBtn)?.addEventListener('click', startNewGame);
        document.getElementById(elements.hintBtn)?.addEventListener('click', requestHint);
        document.getElementById(elements.revealBtn)?.addEventListener('click', revealAnswer);

        document.getElementById(elements.testInput)?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') testInput();
        });
        document.getElementById(elements.guessInput)?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') submitGuess();
        });

        // Register with framework
        registerGame('logic-quest', {
            onTabSwitch: () => {
                // If there is no active session, show the start overlay instead of auto-starting
                if (!session) {
                    const overlay = document.getElementById('game-overlay-logic-quest-start');
                    if (overlay) overlay.style.display = 'flex';
                }
            }
        });
    });

    // Expose start function for "Play Again" buttons
    window.startLogicQuest = startNewGame;

})();
