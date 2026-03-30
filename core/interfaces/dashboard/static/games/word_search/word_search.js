/**
 * Aethvion Suite — Word Search (JS)
 * Fully Client-Side with optional AI-powered theme generation.
 */

class WordSearchGame {
    constructor() {
        this.boardSize = 15;
        this.grid = [];
        this.wordsToFind = [];
        this.wordsFound = new Set();

        // Interaction state
        this.isSelecting = false;
        this.startCell = null;
        this.currentSelection = [];

        // AI state
        this.currentTopic = null;   // null = classic mode, string = AI topic
        this.isGenerating = false;  // loading guard

        this.vocabulary = [
            "ALGORITHM", "NEURAL", "NETWORK", "SYNAPSE", "CYBERNETIC",
            "QUANTUM", "TENSOR", "DATASET", "COMPUTE", "MACHINE",
            "LEARNING", "COGNITIVE", "LOGIC", "HEURISTIC", "ROUTING",
            "CIPHER", "ENCRYPTION", "BANDWIDTH", "SERVER", "CLIENT",
            "VIRTUAL", "REALITY", "AUGMENTED", "HOLOGRAPHIC", "SYSTEM",
            "KERNEL", "MEMORY", "PROCESSOR", "GRAPHICS", "INTERFACE",
            "MISAKA", "PROXY", "FIREWALL", "GATEWAY", "PROTOCOL",
            "SYNTAX", "VARIABLE", "FUNCTION", "ITERATION", "RECURSION"
        ];
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        const restartBtn  = document.getElementById('ws-restart-btn');
        const sizeSelect  = document.getElementById('ws-size-select');
        const aiBtn       = document.getElementById('ws-ai-btn');
        const topicInput  = document.getElementById('ws-topic');

        if (restartBtn) {
            restartBtn.addEventListener('click', () => {
                const s = parseInt(sizeSelect.value, 10);
                this.currentTopic = null;
                this.startGame(s);
            });
        }

        if (aiBtn) {
            aiBtn.addEventListener('click', () => {
                const topic = topicInput ? topicInput.value.trim() : '';
                if (!topic) {
                    topicInput && topicInput.focus();
                    topicInput && topicInput.classList.add('ws-input-error');
                    setTimeout(() => topicInput && topicInput.classList.remove('ws-input-error'), 1200);
                    return;
                }
                const s = parseInt(sizeSelect.value, 10);
                this.generateAIPuzzle(topic, s);
            });
        }

        if (topicInput) {
            topicInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    aiBtn && aiBtn.click();
                }
            });
        }

        // Global mouse/touch up to cancel selection
        document.addEventListener('mouseup',  () => this.endSelection());
        document.addEventListener('touchend', () => this.endSelection());
    }

    onLoad() {
        // Populate model dropdown (same helper used by Logic Quest / Blackjack)
        if (typeof loadGameModels === 'function') {
            loadGameModels(document.getElementById('ws-model-select'));
        }
        this.startGame(15);
    }

    onTabSwitch() {
        // Handle layout adjustments if necessary when tab becomes active
    }

    // ── Standard puzzle start ──────────────────────────────────────────────────

    startGame(size, customWords = null) {
        this.boardSize = size;
        this.grid = Array(size).fill(null).map(() => Array(size).fill(''));
        this.wordsFound.clear();
        this.currentSelection = [];
        this.isSelecting  = false;
        this.startCell    = null;

        this.generatePuzzle(customWords);
        this.renderBoard();
        this.renderWordList();
        this.updateScore();
        this.hideOverlay();
        this._renderTopicBadge();
    }

    generatePuzzle(customWords = null) {
        const source  = customWords || this.vocabulary;
        let numWords  = Math.floor(this.boardSize * 1.2);
        let shuffled  = [...source].sort(() => 0.5 - Math.random());
        let candidates = shuffled.slice(0, numWords * 2);

        this.wordsToFind = [];

        const directions = [
            [0,  1],  // right
            [1,  0],  // down
            [1,  1],  // diagonal down-right
            [-1, 1],  // diagonal up-right
            [0, -1],  // left
            [-1, 0],  // up
            [-1,-1],  // diagonal up-left
            [1, -1]   // diagonal down-left
        ];

        for (const word of candidates) {
            if (this.wordsToFind.length >= numWords) break;

            let placed   = false;
            let attempts = 0;

            while (!placed && attempts < 100) {
                attempts++;
                const dir = directions[Math.floor(Math.random() * directions.length)];
                const row = Math.floor(Math.random() * this.boardSize);
                const col = Math.floor(Math.random() * this.boardSize);

                if (this.canPlaceWord(word, row, col, dir)) {
                    this.placeWord(word, row, col, dir);
                    this.wordsToFind.push(word);
                    placed = true;
                }
            }
        }

        // Sort alphabetically for the UI
        this.wordsToFind.sort();

        // Fill empty cells with random letters
        const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        for (let r = 0; r < this.boardSize; r++) {
            for (let c = 0; c < this.boardSize; c++) {
                if (this.grid[r][c] === '') {
                    this.grid[r][c] = letters.charAt(Math.floor(Math.random() * letters.length));
                }
            }
        }
    }

    canPlaceWord(word, row, col, dir) {
        const [dr, dc] = dir;
        const endRow   = row + dr * (word.length - 1);
        const endCol   = col + dc * (word.length - 1);

        if (endRow < 0 || endRow >= this.boardSize || endCol < 0 || endCol >= this.boardSize) return false;

        for (let i = 0; i < word.length; i++) {
            const cr = row + dr * i;
            const cc = col + dc * i;
            if (this.grid[cr][cc] !== '' && this.grid[cr][cc] !== word[i]) return false;
        }
        return true;
    }

    placeWord(word, row, col, dir) {
        const [dr, dc] = dir;
        for (let i = 0; i < word.length; i++) {
            this.grid[row + dr * i][col + dc * i] = word[i];
        }
    }

    // ── AI Puzzle Generation ───────────────────────────────────────────────────

    async generateAIPuzzle(topic, size) {
        if (this.isGenerating) return;
        this.isGenerating = true;

        const aiBtn      = document.getElementById('ws-ai-btn');
        const topicInput = document.getElementById('ws-topic');
        const sizeSelect = document.getElementById('ws-size-select');
        const boardEl    = document.getElementById('ws-grid');

        // Disable controls while generating
        if (aiBtn)      { aiBtn.disabled = true;   aiBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating…'; }
        if (topicInput) topicInput.disabled = true;
        if (sizeSelect) sizeSelect.disabled = true;

        // Show a skeleton loading state on the grid
        if (boardEl)    boardEl.classList.add('ws-loading');

        const numWords = Math.max(8, Math.floor(size * 1.2));
        const model = document.getElementById('ws-model-select')?.value || 'auto';

        try {
            const res = await fetch('/api/games/word-search/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic, count: numWords, model })
            });

            const data = await res.json();

            if (!res.ok || !data.success) {
                this._showAIError(data.detail || data.error || 'AI generation failed.');
                return;
            }

            // Start the game with the AI-generated word list
            this.currentTopic = data.topic || topic;
            this.startGame(size, data.words);

        } catch (err) {
            this._showAIError('Could not reach the server. Is Aethvion running?');
            console.error('[WordSearch AI]', err);
        } finally {
            this.isGenerating = false;

            if (aiBtn)      { aiBtn.disabled = false; aiBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> AI Puzzle'; }
            if (topicInput) topicInput.disabled = false;
            if (sizeSelect) sizeSelect.disabled = false;
            if (boardEl)    boardEl.classList.remove('ws-loading');
        }
    }

    _showAIError(message) {
        const container = document.getElementById('ws-ai-error');
        if (!container) return;
        container.textContent = message;
        container.style.display = 'block';
        clearTimeout(this._errorTimer);
        this._errorTimer = setTimeout(() => { container.style.display = 'none'; }, 12000);
    }

    // ── Rendering ─────────────────────────────────────────────────────────────

    _renderTopicBadge() {
        const badge = document.getElementById('ws-topic-badge');
        if (!badge) return;
        if (this.currentTopic) {
            badge.textContent = `Topic: ${this.currentTopic}`;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    renderBoard() {
        const boardEl = document.getElementById('ws-grid');
        if (!boardEl) return;

        boardEl.innerHTML = '';
        boardEl.style.gridTemplateColumns = `repeat(${this.boardSize}, 1fr)`;
        boardEl.dataset.size = this.boardSize;

        for (let r = 0; r < this.boardSize; r++) {
            for (let c = 0; c < this.boardSize; c++) {
                const cell = document.createElement('div');
                cell.className    = 'ws-cell';
                cell.textContent  = this.grid[r][c];
                cell.dataset.row  = r;
                cell.dataset.col  = c;

                cell.addEventListener('mousedown',  (e) => this.startSelection(r, c, e));
                cell.addEventListener('mouseenter', ()  => this.updateSelection(r, c));

                cell.addEventListener('touchstart', (e) => {
                    e.preventDefault();
                    this.startSelection(r, c);
                });
                cell.addEventListener('touchmove', (e) => {
                    e.preventDefault();
                    const touch   = e.touches[0];
                    const element = document.elementFromPoint(touch.clientX, touch.clientY);
                    if (element && element.classList.contains('ws-cell')) {
                        this.updateSelection(parseInt(element.dataset.row), parseInt(element.dataset.col));
                    }
                });

                boardEl.appendChild(cell);
            }
        }
    }

    renderWordList() {
        const listEl = document.getElementById('ws-words-list');
        if (!listEl) return;

        listEl.innerHTML = '';
        for (const word of this.wordsToFind) {
            const item = document.createElement('div');
            item.className = 'ws-word-item';
            item.id        = `ws-word-${word}`;
            item.textContent = word;
            if (this.wordsFound.has(word)) item.classList.add('found');
            listEl.appendChild(item);
        }
    }

    // ── Interaction Logic ──────────────────────────────────────────────────────

    startSelection(r, c, e) {
        if (e && e.button !== 0) return;
        this.isSelecting      = true;
        this.startCell        = { r, c };
        this.currentSelection = [this.startCell];
        this.drawSelection();
    }

    updateSelection(r, c) {
        if (!this.isSelecting || !this.startCell) return;

        let dr = Math.sign(r - this.startCell.r);
        let dc = Math.sign(c - this.startCell.c);

        const rowDiff = Math.abs(r - this.startCell.r);
        const colDiff = Math.abs(c - this.startCell.c);

        let steps = 0;
        if      (dr === 0)           steps = colDiff;
        else if (dc === 0)           steps = rowDiff;
        else if (rowDiff === colDiff) steps = rowDiff;
        else {
            if (rowDiff > colDiff) { dc = 0; steps = rowDiff; }
            else                   { dr = 0; steps = colDiff; }
        }

        this.currentSelection = [];
        for (let i = 0; i <= steps; i++) {
            this.currentSelection.push({
                r: this.startCell.r + (dr * i),
                c: this.startCell.c + (dc * i)
            });
        }

        this.drawSelection();
    }

    drawSelection() {
        document.querySelectorAll('.ws-cell.selected').forEach(cell => cell.classList.remove('selected'));
        for (const pos of this.currentSelection) {
            const cell = document.querySelector(`.ws-cell[data-row="${pos.r}"][data-col="${pos.c}"]`);
            if (cell) cell.classList.add('selected');
        }
    }

    endSelection() {
        if (!this.isSelecting) return;
        this.isSelecting = false;

        if (this.currentSelection.length > 1) this.checkWord();

        document.querySelectorAll('.ws-cell.selected').forEach(cell => cell.classList.remove('selected'));
        this.currentSelection = [];
    }

    checkWord() {
        let str = '';
        for (const pos of this.currentSelection) str += this.grid[pos.r][pos.c];
        const revStr = str.split('').reverse().join('');

        let foundWord = null;
        if (this.wordsToFind.includes(str)    && !this.wordsFound.has(str))    foundWord = str;
        else if (this.wordsToFind.includes(revStr) && !this.wordsFound.has(revStr)) foundWord = revStr;

        if (foundWord) {
            this.wordsFound.add(foundWord);

            for (const pos of this.currentSelection) {
                const cell = document.querySelector(`.ws-cell[data-row="${pos.r}"][data-col="${pos.c}"]`);
                if (cell) cell.classList.add('found');
            }

            const listItem = document.getElementById(`ws-word-${foundWord}`);
            if (listItem) listItem.classList.add('found');

            this.updateScore();

            if (this.wordsFound.size === this.wordsToFind.length) this.showWin();
        }
    }

    updateScore() {
        const foundEl = document.getElementById('ws-found-count');
        const totalEl = document.getElementById('ws-total-count');
        const bar     = document.getElementById('ws-progress-bar');

        if (foundEl) foundEl.textContent = this.wordsFound.size;
        if (totalEl) totalEl.textContent = this.wordsToFind.length;

        if (bar && this.wordsToFind.length > 0) {
            bar.style.width = `${(this.wordsFound.size / this.wordsToFind.length) * 100}%`;
        }
    }

    showWin() {
        const overlay = document.getElementById('game-overlay-word-search');
        if (overlay) overlay.style.display = 'flex';
    }

    hideOverlay() {
        const overlay = document.getElementById('game-overlay-word-search');
        if (overlay) overlay.style.display = 'none';
    }
}

// Ensure registry functions are available
if (typeof registerGame === 'function') {
    const wsGame = new WordSearchGame();
    registerGame('word-search', {
        onLoad:       () => wsGame.init(),
        onTabSwitch:  () => wsGame.onTabSwitch()
    });

    document.addEventListener('DOMContentLoaded', () => {
        wsGame.init();
        wsGame.onLoad();
    });
}
