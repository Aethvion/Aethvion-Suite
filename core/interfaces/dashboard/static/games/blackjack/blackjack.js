/**
 * Playing Cards: AI Duel (Blackjack Variant)
 */

(function () {
    let session = null;
    let streak = 0;

    const elements = {
        panel: 'game-blackjack-panel',
        modelSelect: 'pc-model-select',
        difficultySelect: 'pc-difficulty-select',
        streakDisplay: 'pc-streak',
        deckDisplay: 'pc-deck-count',
        display: 'pc-display',
        aiHand: 'pc-ai-hand',
        playerHand: 'pc-player-hand',
        aiScore: 'pc-ai-score',
        playerScore: 'pc-player-score',
        hitBtn: 'pc-hit-btn',
        stayBtn: 'pc-stay-btn',
        hintBtn: 'pc-hint-btn',
        revealBtn: 'pc-reveal-btn',
        history: 'pc-history',
        overlay: 'game-overlay-playing-cards',
        overlayTitle: 'pc-overlay-title',
        overlayMsg: 'pc-overlay-msg'
    };

    /**
     * Start a new duel
     */
    async function startNewDuel() {
        const model = document.getElementById(elements.modelSelect)?.value || 'auto';
        const difficulty = document.getElementById(elements.difficultySelect)?.value || 'medium';

        setGameDisplay(document.getElementById(elements.display), 'Shuffling deck...', 'loading');
        hideOverlay();

        try {
            const data = await gameApiPost('new', {
                game_type: 'blackjack',
                difficulty: difficulty,
                model: model
            });

            if (data.success) {
                session = {
                    id: data.session_id,
                    deckCount: 48, // approximate after deal
                    history: []
                };

                updateUI(data);
                setGameDisplay(document.getElementById(elements.display), 'Cards dealt. Your move.');
            } else {
                setGameDisplay(document.getElementById(elements.display), `Error: ${data.error}`, 'error');
            }
        } catch (err) {
            setGameDisplay(document.getElementById(elements.display), 'Failed to start duel.', 'error');
        }
    }

    /**
     * Draw a card (Hit)
     */
    async function hit() {
        if (!session || session.completed) return;

        try {
            const data = await gameApiPost('action', {
                session_id: session.id,
                action: 'draw',
                data: { target: 'player' }
            });

            if (data.success) {
                updateUI(data);
                if (data.completed) handleGameOver(data);
            }
        } catch (err) { }
    }

    /**
     * Stand / Stay
     */
    async function stay() {
        if (!session || session.completed) return;

        try {
            const data = await gameApiPost('action', {
                session_id: session.id,
                action: 'stay',
                data: {}
            });

            if (data.success) {
                updateUI(data);
                handleGameOver(data);
            }
        } catch (err) { }
    }

    /**
     * Get AI Tip
     */
    async function getTip() {
        if (!session) return;
        try {
            const data = await gameApiPost('action', { session_id: session.id, action: 'hint', data: {} });
            if (data.success) {
                const tip = data.message || data.hint || "The dealer looks confident.";
                setGameDisplay(document.getElementById(elements.display), `AI Tip: ${tip}`);
            }
        } catch (err) { }
    }

    /**
     * Fold 
     */
    async function fold() {
        if (!session || session.completed) return;
        if (!confirm("Fold and lose this hand?")) return;

        try {
            const data = await gameApiPost('action', { session_id: session.id, action: 'reveal', data: {} });
            if (data.success) {
                updateUI(data);
                handleGameOver(data);
            }
        } catch (err) { }
    }

    /**
     * Update UI state
     */
    function updateUI(data) {
        console.log("[Blackjack] Updating UI with data:", data);
        // Update Hands
        if (data.player_hand) renderHand(document.getElementById(elements.playerHand), data.player_hand);
        if (data.ai_hand) renderHand(document.getElementById(elements.aiHand), data.ai_hand, data.hide_ai_card);

        // Update Scores
        if (data.player_score !== undefined) document.getElementById(elements.playerScore).textContent = data.player_score;
        if (data.ai_score !== undefined) document.getElementById(elements.aiScore).textContent = data.ai_score;

        // Update Deck
        if (data.deck_count !== undefined) document.getElementById(elements.deckDisplay).textContent = data.deck_count;

        // Update Display
        if (data.message) setGameDisplay(document.getElementById(elements.display), data.message);

        // Update History
        if (data.log) {
            const history = document.getElementById(elements.history);
            history.innerHTML = '';
            data.log.forEach(entry => {
                const item = document.createElement('div');
                item.className = 'history-item';
                item.textContent = entry;
                history.appendChild(item);
            });
            history.scrollTop = history.scrollHeight;
        }
    }

    /**
     * Render Cards
     */
    function renderHand(container, cards, hideHole = false) {
        container.innerHTML = '';

        const suitMap = {
            'Hearts': '♥', 'Diamonds': '♦', 'Clubs': '♣', 'Spades': '♠',
            'Heart': '♥', 'Diamond': '♦', 'Club': '♣', 'Spade': '♠',
            'H': '♥', 'D': '♦', 'C': '♣', 'S': '♠'
        };

        cards.forEach((card, idx) => {
            const div = document.createElement('div');

            if (hideHole && idx === 1) {
                div.className = 'pc-card back';
            } else {
                const suit = suitMap[card.suit] || card.suit;
                const isRed = suit === '♥' || suit === '♦';
                div.className = `pc-card ${isRed ? 'red' : ''}`;
                div.innerHTML = `
                    <div class="card-rank-top">${card.rank}</div>
                    <div class="card-suit-large">${suit}</div>
                    <div class="card-rank-bottom" style="transform: rotate(180deg)">${card.rank}</div>
                `;
            }
            container.appendChild(div);
        });
    }

    /**
     * Handle Duel End
     */
    function handleGameOver(data) {
        session.completed = true;

        const overlay = document.getElementById(elements.overlay);
        const title = document.getElementById(elements.overlayTitle);
        const msg = document.getElementById(elements.overlayMsg);

        if (data.result === 'win') {
            title.textContent = 'YOU WIN';
            title.style.color = 'var(--primary)';
            streak++;
        } else if (data.result === 'push') {
            title.textContent = 'PUSH';
            title.style.color = 'var(--text-muted)';
        } else {
            title.textContent = 'DEALER WINS';
            title.style.color = '#ff4444';
            streak = 0;
        }

        document.getElementById(elements.streakDisplay).textContent = streak;
        msg.textContent = data.message || 'Game Over.';
        overlay.style.display = 'flex';
    }

    function hideOverlay() {
        document.getElementById(elements.overlay).style.display = 'none';
    }

    // Register with framework
    document.addEventListener('DOMContentLoaded', () => {
        loadGameModels(document.getElementById(elements.modelSelect));

        document.getElementById(elements.hitBtn)?.addEventListener('click', hit);
        document.getElementById(elements.stayBtn)?.addEventListener('click', stay);
        document.getElementById(elements.hintBtn)?.addEventListener('click', getTip);
        document.getElementById(elements.revealBtn)?.addEventListener('click', fold);

        registerGame('blackjack', {
            onTabSwitch: () => {
                if (!session) startNewDuel();
            }
        });
    });

    window.startPlayingCards = startNewDuel;

})();
