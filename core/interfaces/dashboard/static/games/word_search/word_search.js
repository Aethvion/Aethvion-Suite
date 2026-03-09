/**
 * Misaka Cipher — Word Search (JS)
 * Fully Client-Side Implementation
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
        const restartBtn = document.getElementById('ws-restart-btn');
        const sizeSelect = document.getElementById('ws-size-select');

        if (restartBtn) {
            restartBtn.addEventListener('click', () => {
                const s = parseInt(sizeSelect.value, 10);
                this.startGame(s);
            });
        }

        // Global mouse up to cancel selection
        document.addEventListener('mouseup', () => this.endSelection());
        document.addEventListener('touchend', () => this.endSelection());
    }

    onLoad() {
        this.startGame(15);
    }

    onTabSwitch() {
        // Handle layout adjustments if necessary when tab becomes active
    }

    startGame(size) {
        this.boardSize = size;
        this.grid = Array(size).fill(null).map(() => Array(size).fill(''));
        this.wordsFound.clear();
        this.currentSelection = [];
        this.isSelecting = false;
        this.startCell = null;

        this.generatePuzzle();
        this.renderBoard();
        this.renderWordList();
        this.updateScore();
        this.hideOverlay();
    }

    generatePuzzle() {
        // Select random words based on board size
        let numWords = Math.floor(this.boardSize * 1.2);
        let shuffledVocab = [...this.vocabulary].sort(() => 0.5 - Math.random());
        let candidates = shuffledVocab.slice(0, numWords * 2); // get extra in case some don't fit

        this.wordsToFind = [];

        // Directions: [dRow, dCol]
        const directions = [
            [0, 1],   // right
            [1, 0],   // down
            [1, 1],   // diagonal down-right
            [-1, 1],  // diagonal up-right
            [0, -1],  // left
            [-1, 0],  // up
            [-1, -1], // diagonal up-left
            [1, -1]   // diagonal down-left
        ];

        for (const word of candidates) {
            if (this.wordsToFind.length >= numWords) break;

            let placed = false;
            let attempts = 0;

            while (!placed && attempts < 100) {
                attempts++;
                let dir = directions[Math.floor(Math.random() * directions.length)];
                let row = Math.floor(Math.random() * this.boardSize);
                let col = Math.floor(Math.random() * this.boardSize);

                if (this.canPlaceWord(word, row, col, dir)) {
                    this.placeWord(word, row, col, dir);
                    this.wordsToFind.push(word);
                    placed = true;
                }
            }
        }

        // Sort for UI purely alphabetically
        this.wordsToFind.sort();

        // Fill empty spaces with random uppercase letters
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
        let [dr, dc] = dir;
        let endRow = row + dr * (word.length - 1);
        let endCol = col + dc * (word.length - 1);

        // Check bounds
        if (endRow < 0 || endRow >= this.boardSize || endCol < 0 || endCol >= this.boardSize) return false;

        // Check conflicts
        for (let i = 0; i < word.length; i++) {
            let cr = row + dr * i;
            let cc = col + dc * i;
            if (this.grid[cr][cc] !== '' && this.grid[cr][cc] !== word[i]) {
                return false;
            }
        }
        return true;
    }

    placeWord(word, row, col, dir) {
        let [dr, dc] = dir;
        for (let i = 0; i < word.length; i++) {
            let cr = row + dr * i;
            let cc = col + dc * i;
            this.grid[cr][cc] = word[i];
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
                cell.className = 'ws-cell';
                cell.textContent = this.grid[r][c];
                cell.dataset.row = r;
                cell.dataset.col = c;

                // Events
                cell.addEventListener('mousedown', (e) => this.startSelection(r, c, e));
                cell.addEventListener('mouseenter', () => this.updateSelection(r, c));

                // Touch events
                cell.addEventListener('touchstart', (e) => {
                    e.preventDefault();
                    this.startSelection(r, c);
                });
                cell.addEventListener('touchmove', (e) => {
                    e.preventDefault();
                    let touch = e.touches[0];
                    let element = document.elementFromPoint(touch.clientX, touch.clientY);
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
            item.id = `ws-word-${word}`;
            item.textContent = word;
            if (this.wordsFound.has(word)) {
                item.classList.add('found');
            }
            listEl.appendChild(item);
        }
    }

    // --- Interaction Logic ---

    startSelection(r, c, e) {
        if (e && e.button !== 0) return; // Only left click
        this.isSelecting = true;
        this.startCell = { r, c };
        this.currentSelection = [this.startCell];
        this.drawSelection();
    }

    updateSelection(r, c) {
        if (!this.isSelecting || !this.startCell) return;

        // Calculate direction vector
        let dr = Math.sign(r - this.startCell.r);
        let dc = Math.sign(c - this.startCell.c);

        // Calculate max steps to maintain straight line or diagonal (45 deg)
        let rowDiff = Math.abs(r - this.startCell.r);
        let colDiff = Math.abs(c - this.startCell.c);

        let steps = 0;
        if (dr === 0) steps = colDiff;
        else if (dc === 0) steps = rowDiff;
        else if (rowDiff === colDiff) steps = rowDiff;
        else {
            // Not a straight or 45 deg line, snap to nearest valid direction
            if (rowDiff > colDiff) {
                dc = 0;
                steps = rowDiff;
            } else {
                dr = 0;
                steps = colDiff;
            }
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
        // Clear old selection (excluding found words)
        document.querySelectorAll('.ws-cell.selected').forEach(cell => {
            cell.classList.remove('selected');
        });

        // Add to new
        for (const pos of this.currentSelection) {
            let cell = document.querySelector(`.ws-cell[data-row="${pos.r}"][data-col="${pos.c}"]`);
            if (cell) cell.classList.add('selected');
        }
    }

    endSelection() {
        if (!this.isSelecting) return;
        this.isSelecting = false;

        if (this.currentSelection.length > 1) {
            this.checkWord();
        }

        // Clear visual selection state that isn't actually "found" (handled in drawSelection on next start, or explicitly here)
        document.querySelectorAll('.ws-cell.selected').forEach(cell => {
            cell.classList.remove('selected');
        });

        this.currentSelection = [];
    }

    checkWord() {
        // Extract string from current selection (both forwards and backwards)
        let str = "";
        for (const pos of this.currentSelection) {
            str += this.grid[pos.r][pos.c];
        }
        let revStr = str.split('').reverse().join('');

        let foundWord = null;
        if (this.wordsToFind.includes(str) && !this.wordsFound.has(str)) foundWord = str;
        else if (this.wordsToFind.includes(revStr) && !this.wordsFound.has(revStr)) foundWord = revStr;

        if (foundWord) {
            this.wordsFound.add(foundWord);

            // Mark cells as found
            for (const pos of this.currentSelection) {
                let cell = document.querySelector(`.ws-cell[data-row="${pos.r}"][data-col="${pos.c}"]`);
                if (cell) cell.classList.add('found');
            }

            // Strike through list
            const listItem = document.getElementById(`ws-word-${foundWord}`);
            if (listItem) listItem.classList.add('found');

            this.updateScore();

            if (this.wordsFound.size === this.wordsToFind.length) {
                this.showWin();
            }
        }
    }

    updateScore() {
        const foundEl = document.getElementById('ws-found-count');
        const totalEl = document.getElementById('ws-total-count');
        const bar = document.getElementById('ws-progress-bar');

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
        onLoad: () => wsGame.init(),
        onTabSwitch: () => wsGame.onTabSwitch()
    });

    // Auto-init when DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        // Just call init right away, but defer actual start
        wsGame.init();
        wsGame.onLoad(); // generates first grid
    });
}
