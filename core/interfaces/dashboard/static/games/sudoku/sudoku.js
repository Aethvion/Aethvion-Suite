/**
 * Aethvion Suite — Sudoku (JS)
 * Fully Client-Side Implementation
 */

class SudokuGame {
    constructor() {
        this.board = Array(9).fill(null).map(() => Array(9).fill(0));
        this.solution = Array(9).fill(null).map(() => Array(9).fill(0));
        this.fixed = Array(9).fill(null).map(() => Array(9).fill(false));

        this.selectedCell = null; // {r, c}
        this.history = []; // For undo
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        const restartBtn = document.getElementById('su-restart-btn');
        const diffSelect = document.getElementById('su-difficulty-select');
        const undoBtn = document.getElementById('su-undo-btn');
        const hintBtn = document.getElementById('su-hint-btn');

        if (restartBtn) {
            restartBtn.addEventListener('click', () => {
                const diff = diffSelect ? diffSelect.value : 'easy';
                this.startGame(diff);
            });
        }

        if (undoBtn) {
            undoBtn.addEventListener('click', () => this.undo());
        }

        if (hintBtn) {
            hintBtn.addEventListener('click', () => this.giveHint());
        }

        // Global keydown for number input
        document.addEventListener('keydown', (e) => {
            // Only capture if a sudoku cell is selected and we're ostensibly on the sudoku tab
            const panel = document.getElementById('game-sudoku-panel');
            if (!this.selectedCell || !panel || !panel.classList.contains('active')) return;

            if (e.key >= '1' && e.key <= '9') {
                this.setCellValue(parseInt(e.key));
            } else if (e.key === 'Backspace' || e.key === 'Delete' || e.key === '0') {
                this.setCellValue(0);
            } else if (e.key === 'ArrowUp') {
                this.moveSelection(-1, 0); e.preventDefault();
            } else if (e.key === 'ArrowDown') {
                this.moveSelection(1, 0); e.preventDefault();
            } else if (e.key === 'ArrowLeft') {
                this.moveSelection(0, -1); e.preventDefault();
            } else if (e.key === 'ArrowRight') {
                this.moveSelection(0, 1); e.preventDefault();
            }
        });

        // Keypad binding
        document.querySelectorAll('.su-key').forEach(key => {
            key.addEventListener('click', () => {
                if (key.dataset.val === 'clear') {
                    this.setCellValue(0);
                } else {
                    this.setCellValue(parseInt(key.dataset.val));
                }
            });
        });
    }

    onLoad() {
        this.startGame('easy');
    }

    onTabSwitch() {
        // Handle layout adjustments if necessary when tab becomes active
    }

    startGame(difficulty) {
        this.history = [];
        this.selectedCell = null;
        this.hideOverlay();

        // 1. Generate full valid board
        this.generateFullBoard();

        // 2. Remove items based on difficulty
        // Easy: 40 empty, Med: 50, Hard: 60
        let removeCount = 40;
        if (difficulty === 'medium') removeCount = 50;
        if (difficulty === 'hard') removeCount = 60;

        this.board = this.solution.map(arr => [...arr]);
        this.fixed = Array(9).fill(null).map(() => Array(9).fill(true));

        let removed = 0;
        while (removed < removeCount) {
            let r = Math.floor(Math.random() * 9);
            let c = Math.floor(Math.random() * 9);
            if (this.board[r][c] !== 0) {
                this.board[r][c] = 0;
                this.fixed[r][c] = false;
                removed++;
            }
        }

        this.renderBoard();
        this.checkErrors();
    }

    // --- Generation Logic ---

    generateFullBoard() {
        this.solution = Array(9).fill(null).map(() => Array(9).fill(0));
        this.fillDiagonal();
        this.fillRemaining(0, 3);
    }

    fillDiagonal() {
        for (let i = 0; i < 9; i = i + 3) {
            this.fillBox(i, i);
        }
    }

    fillBox(rowStart, colStart) {
        let num;
        for (let i = 0; i < 3; i++) {
            for (let j = 0; j < 3; j++) {
                do {
                    num = Math.floor(Math.random() * 9) + 1;
                } while (!this.unUsedInBox(rowStart, colStart, num));
                this.solution[rowStart + i][colStart + j] = num;
            }
        }
    }

    unUsedInBox(rowStart, colStart, num) {
        for (let i = 0; i < 3; i++) {
            for (let j = 0; j < 3; j++) {
                if (this.solution[rowStart + i][colStart + j] === num) return false;
            }
        }
        return true;
    }

    checkIfSafe(i, j, num) {
        return (this.unUsedInRow(i, num) &&
            this.unUsedInCol(j, num) &&
            this.unUsedInBox(i - i % 3, j - j % 3, num));
    }

    unUsedInRow(i, num) {
        for (let j = 0; j < 9; j++)
            if (this.solution[i][j] === num) return false;
        return true;
    }

    unUsedInCol(j, num) {
        for (let i = 0; i < 9; i++)
            if (this.solution[i][j] === num) return false;
        return true;
    }

    fillRemaining(i, j) {
        if (j >= 9 && i < 8) {
            i = i + 1;
            j = 0;
        }
        if (i >= 9 && j >= 9) return true;

        if (i < 3) {
            if (j < 3) j = 3;
        } else if (i < 6) {
            if (j === Math.floor(i / 3) * 3) j = j + 3;
        } else {
            if (j === 6) {
                i = i + 1;
                j = 0;
                if (i >= 9) return true;
            }
        }

        for (let num = 1; num <= 9; num++) {
            if (this.checkIfSafe(i, j, num)) {
                this.solution[i][j] = num;
                if (this.fillRemaining(i, j + 1)) return true;
                this.solution[i][j] = 0;
            }
        }
        return false;
    }

    // --- UI Logic ---

    renderBoard() {
        const boardEl = document.getElementById('su-grid');
        if (!boardEl) return;

        boardEl.innerHTML = '';

        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                const cell = document.createElement('div');
                cell.className = 'su-cell';
                if (this.fixed[r][c]) cell.classList.add('fixed');

                cell.dataset.row = r;
                cell.dataset.col = c;

                if (this.board[r][c] !== 0) {
                    cell.textContent = this.board[r][c];
                }

                cell.addEventListener('mousedown', () => this.selectCell(r, c));
                cell.addEventListener('touchstart', (e) => {
                    e.preventDefault();
                    this.selectCell(r, c);
                });

                boardEl.appendChild(cell);
            }
        }
    }

    selectCell(r, c) {
        this.selectedCell = { r, c };
        this.updateHighlights();
    }

    moveSelection(dr, dc) {
        if (!this.selectedCell) return;
        let nr = this.selectedCell.r + dr;
        let nc = this.selectedCell.c + dc;

        if (nr >= 0 && nr < 9 && nc >= 0 && nc < 9) {
            this.selectCell(nr, nc);
        }
    }

    updateHighlights() {
        // Clear old
        document.querySelectorAll('.su-cell').forEach(cell => {
            cell.classList.remove('selected', 'highlight', 'highlight-same');
        });

        if (!this.selectedCell) return;

        let sr = this.selectedCell.r;
        let sc = this.selectedCell.c;
        let selectedVal = this.board[sr][sc];

        let selectedEl = document.querySelector(`.su-cell[data-row="${sr}"][data-col="${sc}"]`);
        if (selectedEl) selectedEl.classList.add('selected');

        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                if (r === sr && c === sc) continue;
                let cell = document.querySelector(`.su-cell[data-row="${r}"][data-col="${c}"]`);
                if (!cell) continue;

                // Highlight same row, col, box
                let br = Math.floor(sr / 3) * 3;
                let bc = Math.floor(sc / 3) * 3;
                let isSameBox = (r >= br && r < br + 3 && c >= bc && c < bc + 3);

                if (r === sr || c === sc || isSameBox) {
                    cell.classList.add('highlight');
                }

                // Highlight identical numbers
                if (selectedVal !== 0 && this.board[r][c] === selectedVal) {
                    cell.classList.add('highlight-same');
                }
            }
        }
    }

    setCellValue(val) {
        if (!this.selectedCell) return;
        let r = this.selectedCell.r;
        let c = this.selectedCell.c;

        if (this.fixed[r][c]) return;

        // Save history if value changed
        if (this.board[r][c] !== val) {
            this.history.push({ r, c, prev: this.board[r][c] });
            this.board[r][c] = val;

            let cell = document.querySelector(`.su-cell[data-row="${r}"][data-col="${c}"]`);
            if (cell) {
                cell.textContent = val === 0 ? '' : val;
            }

            this.checkErrors();
            this.updateHighlights();
            this.checkWin();
        }
    }

    undo() {
        if (this.history.length === 0) return;
        let lastAction = this.history.pop();

        this.board[lastAction.r][lastAction.c] = lastAction.prev;
        let cell = document.querySelector(`.su-cell[data-row="${lastAction.r}"][data-col="${lastAction.c}"]`);
        if (cell) {
            cell.textContent = lastAction.prev === 0 ? '' : lastAction.prev;
        }

        this.selectCell(lastAction.r, lastAction.c);
        this.checkErrors();
    }

    giveHint() {
        if (!this.selectedCell) return;
        let r = this.selectedCell.r;
        let c = this.selectedCell.c;
        if (this.fixed[r][c]) return;

        let correctVal = this.solution[r][c];
        this.setCellValue(correctVal);
    }

    checkErrors() {
        document.querySelectorAll('.su-cell').forEach(cell => cell.classList.remove('error'));

        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                if (this.board[r][c] === 0) continue;
                let val = this.board[r][c];
                let isError = false;

                // Check row
                for (let i = 0; i < 9; i++) if (i !== c && this.board[r][i] === val) isError = true;
                // Check col
                for (let i = 0; i < 9; i++) if (i !== r && this.board[i][c] === val) isError = true;
                // Check box
                let br = Math.floor(r / 3) * 3;
                let bc = Math.floor(c / 3) * 3;
                for (let i = 0; i < 3; i++) {
                    for (let j = 0; j < 3; j++) {
                        let cr = br + i; let cc = bc + j;
                        if ((cr !== r || cc !== c) && this.board[cr][cc] === val) isError = true;
                    }
                }

                if (isError) {
                    let cell = document.querySelector(`.su-cell[data-row="${r}"][data-col="${c}"]`);
                    if (cell) cell.classList.add('error');
                }
            }
        }
    }

    checkWin() {
        let isFull = true;
        let hasError = false;

        document.querySelectorAll('.su-cell').forEach(cell => {
            if (cell.textContent === '') isFull = false;
            if (cell.classList.contains('error')) hasError = true;
        });

        if (isFull && !hasError) {
            this.showWin();
        }
    }

    showWin() {
        const overlay = document.getElementById('game-overlay-sudoku');
        if (overlay) overlay.style.display = 'flex';
    }

    hideOverlay() {
        const overlay = document.getElementById('game-overlay-sudoku');
        if (overlay) overlay.style.display = 'none';
    }
}

// Ensure registry functions are available
if (typeof registerGame === 'function') {
    const suGame = new SudokuGame();
    registerGame('sudoku', {
        onLoad: () => suGame.init(),
        onTabSwitch: () => suGame.onTabSwitch()
    });
    // Init is triggered via games-shared.js panelLoaded handler
}
