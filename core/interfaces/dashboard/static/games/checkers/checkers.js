/**
 * Misaka Cipher — Checkers (JS)
 * Fully Client-Side Implementation with Minimax AI
 */

const PLAYER = 1;      // Human (Cyan) moving UP (decreasing row)
const AI = 2;          // AI (Red) moving DOWN (increasing row)
const EMPTY = 0;

class CheckersGame {
    constructor() {
        this.boardSize = 8;
        this.board = []; // 2D array: { player: int, king: bool } or null
        this.turn = PLAYER;

        this.selectedSquare = null; // {r, c}
        this.validMoves = [];       // array of move objects for selected piece

        this.mustJumpSq = null;     // {r, c} if a piece just jumped and must multi-jump
        this.gameOver = false;

        this.aiDifficulty = 3; // depth for minimax
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        const restartBtn = document.getElementById('chk-restart-btn');
        const diffSelect = document.getElementById('chk-difficulty-select');

        if (restartBtn) {
            restartBtn.addEventListener('click', () => {
                if (diffSelect) {
                    let diffMap = { 'easy': 2, 'medium': 4, 'hard': 6 };
                    this.aiDifficulty = diffMap[diffSelect.value] || 4;
                }
                this.startGame();
            });
        }
    }

    onLoad() {
        this.startGame();
    }

    onTabSwitch() {
        // Handle layuot
    }

    startGame() {
        this.board = Array(8).fill(null).map(() => Array(8).fill(null));
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                if ((r + c) % 2 === 1) { // Dark squares only
                    if (r < 3) this.board[r][c] = { player: AI, king: false };
                    else if (r > 4) this.board[r][c] = { player: PLAYER, king: false };
                    else this.board[r][c] = { player: EMPTY, king: false };
                } else {
                    this.board[r][c] = null; // Light squares not playable
                }
            }
        }

        this.turn = PLAYER;
        this.selectedSquare = null;
        this.validMoves = [];
        this.mustJumpSq = null;
        this.gameOver = false;

        this.hideOverlay();
        this.updateStatus("Your Turn (Blue)");
        this.renderBoard();
        this.updatePlayerCards();
    }

    renderBoard() {
        const boardEl = document.getElementById('chk-board');
        if (!boardEl) return;

        boardEl.innerHTML = '';

        // Find all mandatory jumps for current player to enforce jumping rules
        let jumpingMoves = this.getAllJumpsForPlayer(this.board, this.turn);
        let hasJumps = jumpingMoves.length > 0;

        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                const sq = document.createElement('div');
                sq.className = 'chk-square';

                if ((r + c) % 2 === 1) {
                    sq.classList.add('dark');
                    sq.dataset.row = r;
                    sq.dataset.col = c;

                    let pieceState = this.board[r][c];

                    if (pieceState && pieceState.player !== EMPTY) {
                        const piece = document.createElement('div');
                        piece.className = 'chk-piece';
                        piece.classList.add(pieceState.player === PLAYER ? 'player' : 'opponent');
                        if (pieceState.king) piece.classList.add('king');
                        sq.appendChild(piece);

                        // Highlight interactivity for player
                        if (pieceState.player === PLAYER && this.turn === PLAYER && !this.gameOver) {
                            // If locked into multi-jump
                            if (this.mustJumpSq) {
                                if (r === this.mustJumpSq.r && c === this.mustJumpSq.c) sq.classList.add('playable');
                            } else {
                                // Enforce must-jump rule visually
                                if (hasJumps) {
                                    let pieceHasJump = jumpingMoves.some(m => m.fromR === r && m.fromC === c);
                                    if (pieceHasJump) sq.classList.add('playable');
                                } else {
                                    sq.classList.add('playable');
                                }
                            }
                        }
                    }

                    // Selection state
                    if (this.selectedSquare && this.selectedSquare.r === r && this.selectedSquare.c === c) {
                        sq.classList.add('selected');
                    }

                    // valid move targets
                    let moveTarget = this.validMoves.find(m => m.toR === r && m.toC === c);
                    if (moveTarget) {
                        sq.classList.add('valid-move');
                    }

                    sq.addEventListener('click', () => this.handleSquareClick(r, c));

                } else {
                    sq.classList.add('light');
                }

                boardEl.appendChild(sq);
            }
        }
    }

    handleSquareClick(r, c) {
        if (this.turn !== PLAYER || this.gameOver) return;

        let pieceState = this.board[r][c];

        // If clicking a valid move target
        let moveTo = this.validMoves.find(m => m.toR === r && m.toC === c);
        if (moveTo) {
            this.executeMove(moveTo);
            return;
        }

        // If clicking own piece
        if (pieceState && pieceState.player === PLAYER) {

            if (this.mustJumpSq) {
                // Cannot select another piece during multi-jump
                if (r !== this.mustJumpSq.r || c !== this.mustJumpSq.c) return;
            }

            let allJumps = this.getAllJumpsForPlayer(this.board, PLAYER);
            let hasJumps = allJumps.length > 0;

            if (hasJumps) {
                let myJumps = allJumps.filter(m => m.fromR === r && m.fromC === c);
                if (myJumps.length === 0) return; // Must jump if possible

                this.selectedSquare = { r, c };
                this.validMoves = myJumps;
            } else {
                let standardMoves = this.getStandardMovesForPiece(this.board, r, c);
                this.selectedSquare = { r, c };
                this.validMoves = standardMoves;
            }

            this.renderBoard();
        } else {
            // Deselect
            if (!this.mustJumpSq) {
                this.selectedSquare = null;
                this.validMoves = [];
                this.renderBoard();
            }
        }
    }

    executeMove(move) {
        // Apply move to board state
        let movingPiece = this.board[move.fromR][move.fromC];
        this.board[move.toR][move.toC] = movingPiece;
        this.board[move.fromR][move.fromC] = { player: EMPTY, king: false };

        let didJump = move.jumpR !== null;
        if (didJump) {
            this.board[move.jumpR][move.jumpC] = { player: EMPTY, king: false };
        }

        // King promotion
        let promoted = false;
        if (movingPiece.player === PLAYER && move.toR === 0 && !movingPiece.king) {
            movingPiece.king = true; promoted = true;
        } else if (movingPiece.player === AI && move.toR === 7 && !movingPiece.king) {
            movingPiece.king = true; promoted = true;
        }

        this.selectedSquare = null;
        this.validMoves = [];

        // Handle multi-jump
        if (didJump && !promoted) {
            let subsequentJumps = this.getJumpsForPiece(this.board, move.toR, move.toC);
            if (subsequentJumps.length > 0) {
                this.mustJumpSq = { r: move.toR, c: move.toC };
                if (this.turn === PLAYER) {
                    this.selectedSquare = this.mustJumpSq;
                    this.validMoves = subsequentJumps;
                    this.renderBoard();
                } else {
                    // AI multi-jump is handled instantly conceptually by passing control back to AI turn loop
                    this.renderBoard();
                    setTimeout(() => this.executeAIMove(), 500);
                }
                return;
            }
        }

        // End of turn
        this.mustJumpSq = null;
        this.switchTurn();
    }

    switchTurn() {
        this.turn = (this.turn === PLAYER) ? AI : PLAYER;

        let pCount = 0, aCount = 0;
        let pMoves = this.getAllMovesForPlayer(this.board, PLAYER).length;
        let aMoves = this.getAllMovesForPlayer(this.board, AI).length;

        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                if (this.board[r][c] && this.board[r][c].player === PLAYER) pCount++;
                if (this.board[r][c] && this.board[r][c].player === AI) aCount++;
            }
        }

        if (pCount === 0 || pMoves === 0) {
            this.endGame(AI);
            return;
        }
        if (aCount === 0 || aMoves === 0) {
            this.endGame(PLAYER);
            return;
        }

        if (this.turn === PLAYER) {
            this.updateStatus("Your Turn (Blue)");
            this.updatePlayerCards();
            this.renderBoard();
        } else {
            this.updateStatus("Nexus AI is thinking...");
            this.updatePlayerCards();
            this.renderBoard();
            setTimeout(() => this.executeAIMove(), 100); // Async to allow UI draw
        }
    }

    updateStatus(msg) {
        const el = document.getElementById('chk-status-bar');
        if (el) el.textContent = msg;
    }

    updatePlayerCards() {
        const pCard = document.getElementById('chk-player1-card');
        const aCard = document.getElementById('chk-player2-card');
        if (pCard && aCard) {
            if (this.turn === PLAYER) {
                pCard.classList.add('active'); aCard.classList.remove('active');
            } else {
                aCard.classList.add('active'); pCard.classList.remove('active');
            }
        }
    }

    // --- Move Generation Logic ---

    getAllMovesForPlayer(boardState, player) {
        let jumps = this.getAllJumpsForPlayer(boardState, player);
        if (jumps.length > 0) return jumps; // Must jump

        let moves = [];
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                if (boardState[r][c] && boardState[r][c].player === player) {
                    moves.push(...this.getStandardMovesForPiece(boardState, r, c));
                }
            }
        }
        return moves;
    }

    getAllJumpsForPlayer(boardState, player) {
        let jumps = [];
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                if (boardState[r][c] && boardState[r][c].player === player) {
                    jumps.push(...this.getJumpsForPiece(boardState, r, c));
                }
            }
        }
        return jumps;
    }

    getStandardMovesForPiece(boardState, r, c) {
        let moves = [];
        let piece = boardState[r][c];
        let dirs = [];

        if (piece.king) dirs = [[-1, -1], [-1, 1], [1, -1], [1, 1]];
        else if (piece.player === PLAYER) dirs = [[-1, -1], [-1, 1]]; // Player moves UP (-1)
        else dirs = [[1, -1], [1, 1]]; // AI moves DOWN (+1)

        for (let d of dirs) {
            let nr = r + d[0], nc = c + d[1];
            if (nr >= 0 && nr < 8 && nc >= 0 && nc < 8) {
                if (boardState[nr][nc].player === EMPTY) {
                    moves.push({ fromR: r, fromC: c, toR: nr, toC: nc, jumpR: null, jumpC: null });
                }
            }
        }
        return moves;
    }

    getJumpsForPiece(boardState, r, c) {
        let jumps = [];
        let piece = boardState[r][c];
        let opponent = piece.player === PLAYER ? AI : PLAYER;
        let dirs = [];

        if (piece.king) dirs = [[-1, -1], [-1, 1], [1, -1], [1, 1]];
        else if (piece.player === PLAYER) dirs = [[-1, -1], [-1, 1]];
        else dirs = [[1, -1], [1, 1]];

        for (let d of dirs) {
            let nr = r + d[0], nc = c + d[1];             // Square with opponent
            let nnr = r + d[0] * 2, nnc = c + d[1] * 2;       // Destination square

            if (nnr >= 0 && nnr < 8 && nnc >= 0 && nnc < 8) {
                if (boardState[nr][nc].player === opponent && boardState[nnr][nnc].player === EMPTY) {
                    jumps.push({ fromR: r, fromC: c, toR: nnr, toC: nnc, jumpR: nr, jumpC: nc });
                }
            }
        }
        return jumps;
    }

    // --- Minimax AI ---

    executeAIMove() {
        if (this.gameOver) return;

        // If locked into multi-jump sequence
        if (this.mustJumpSq) {
            let jumps = this.getJumpsForPiece(this.board, this.mustJumpSq.r, this.mustJumpSq.c);
            if (jumps.length > 0) {
                // Randomly pick a jump if multiple, or just 0
                let move = jumps[Math.floor(Math.random() * jumps.length)];
                this.executeMove(move);
            } else {
                this.mustJumpSq = null;
                this.switchTurn();
            }
            return;
        }

        // Standard Turn: Minimax
        let bestMove = this.getBestMoveMinimax(this.board, this.aiDifficulty);
        if (bestMove) {
            this.executeMove(bestMove);
        } else {
            console.log("AI forfeited");
            this.endGame(PLAYER);
        }
    }

    // Clone board state
    cloneBoard(b) {
        let nb = Array(8).fill(null).map(() => Array(8).fill(null));
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                if (b[r][c] !== null) {
                    nb[r][c] = { player: b[r][c].player, king: b[r][c].king };
                }
            }
        }
        return nb;
    }

    // Evaluate heuristic score (Positive favors AI, Negative favors Player)
    evaluateBoard(b) {
        let score = 0;
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                let piece = b[r][c];
                if (piece && piece.player !== EMPTY) {
                    let val = piece.king ? 3 : 1;

                    // Positional advantage (pieces further along board are better)
                    if (piece.player === AI) {
                        score += val;
                        if (!piece.king) score += (r * 0.1); // Incentive to move forward
                    } else {
                        score -= val;
                        if (!piece.king) score -= ((7 - r) * 0.1);
                    }
                }
            }
        }
        return score;
    }

    // Simple apply move returning new state (no multi-jump sim for simplicity, handles basic depth)
    simulateMove(b, move) {
        let nb = this.cloneBoard(b);
        let movingPiece = nb[move.fromR][move.fromC];
        nb[move.toR][move.toC] = movingPiece;
        nb[move.fromR][move.fromC] = { player: EMPTY, king: false };
        if (move.jumpR !== null) nb[move.jumpR][move.jumpC] = { player: EMPTY, king: false };

        if (movingPiece.player === PLAYER && move.toR === 0) movingPiece.king = true;
        if (movingPiece.player === AI && move.toR === 7) movingPiece.king = true;
        return nb;
    }

    minimax(position, depth, maxPlayer, alpha, beta) {
        if (depth === 0) {
            return { eval: this.evaluateBoard(position), move: null };
        }

        let playerToCheck = maxPlayer ? AI : PLAYER;
        let moves = this.getAllMovesForPlayer(position, playerToCheck);

        if (moves.length === 0) {
            return { eval: maxPlayer ? -Infinity : Infinity, move: null };
        }

        if (maxPlayer) {
            let maxEval = -Infinity;
            let bestMove = moves[0];
            for (let move of moves) {
                let evalState = this.minimax(this.simulateMove(position, move), depth - 1, false, alpha, beta).eval;
                if (evalState > maxEval) {
                    maxEval = evalState;
                    bestMove = move;
                }
                alpha = Math.max(alpha, evalState);
                if (beta <= alpha) break;
            }
            return { eval: maxEval, move: bestMove };
        } else {
            let minEval = Infinity;
            let bestMove = moves[0];
            for (let move of moves) {
                let evalState = this.minimax(this.simulateMove(position, move), depth - 1, true, alpha, beta).eval;
                if (evalState < minEval) {
                    minEval = evalState;
                    bestMove = move;
                }
                beta = Math.min(beta, evalState);
                if (beta <= alpha) break;
            }
            return { eval: minEval, move: bestMove };
        }
    }

    getBestMoveMinimax(boardContext, depth) {
        // Shuffle to add variety if heuristic is tied
        let moves = this.getAllMovesForPlayer(boardContext, AI);
        if (moves.length <= 1) return moves[0]; // Optimization

        // Minor randomization tie breaker implemented external to minimax core
        let result = this.minimax(boardContext, depth, true, -Infinity, Infinity);
        return result.move || moves[Math.floor(Math.random() * moves.length)];
    }

    endGame(winner) {
        this.gameOver = true;
        this.updateStatus("Game Over");

        const overlay = document.getElementById('game-overlay-checkers');
        const title = document.getElementById('chk-win-title');
        if (overlay && title) {
            title.textContent = winner === PLAYER ? "YOU WIN" : "AI WINS";
            title.style.color = winner === PLAYER ? "var(--primary)" : "#ff4757";
            overlay.style.display = 'flex';
        }
    }

    hideOverlay() {
        const overlay = document.getElementById('game-overlay-checkers');
        if (overlay) overlay.style.display = 'none';
    }
}

// Ensure registry functions are available
if (typeof registerGame === 'function') {
    const chkGame = new CheckersGame();
    registerGame('checkers', {
        onLoad: () => chkGame.init(),
        onTabSwitch: () => chkGame.onTabSwitch()
    });

    // Auto-init when DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        chkGame.init();
        chkGame.onLoad();
    });
}
