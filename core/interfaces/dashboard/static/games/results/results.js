(function () {
    const elements = {
        totalGames: 'res-total-games',
        winRate: 'res-win-rate',
        totalWins: 'res-total-wins',
        totalLosses: 'res-total-losses',
        historyBody: 'res-history-body',
        refreshBtn: 'results-refresh-btn'
    };

    async function loadStats() {
        try {
            const resp = await fetch('/api/games/stats');
            const data = await resp.json();

            if (data.success) {
                updateUI(data);
            }
        } catch (err) {
            console.error("Failed to load game stats:", err);
        }
    }

    async function clearHistory(gameType) {
        if (!confirm(`Are you sure you want to clear history for ${gameType}?`)) return;

        try {
            const resp = await fetch(`/api/games/stats/${gameType}`, { method: 'DELETE' });
            const data = await resp.json();
            if (data.success) {
                loadStats();
            } else {
                alert("Error: " + data.error);
            }
        } catch (err) {
            console.error("Clear failed:", err);
        }
    }

    function updateUI(data) {
        const stats = data.stats;
        document.getElementById(elements.totalGames).textContent = stats.total_games;
        document.getElementById(elements.totalWins).textContent = stats.wins;
        document.getElementById(elements.totalLosses).textContent = stats.losses;

        const rate = stats.total_games > 0 ? ((stats.wins / stats.total_games) * 100).toFixed(1) : 0;
        document.getElementById(elements.winRate).textContent = `${rate}%`;

        // Update Breakdown
        const breakdown = document.getElementById('res-breakdown');
        if (breakdown) {
            breakdown.innerHTML = '';
            for (const [gameType, gameStats] of Object.entries(stats.game_types)) {
                const total = gameStats.total || 0;
                const winRatio = total > 0 ? ((gameStats.wins / total) * 100).toFixed(1) : 0;
                const card = document.createElement('div');
                card.className = 'game-type-card';
                card.innerHTML = `
                    <h3>${gameType.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}</h3>
                    <div class="type-stat-row">
                        <span class="type-stat-lbl">Played</span>
                        <span class="type-stat-val">${total}</span>
                    </div>
                    <div class="type-stat-row">
                        <span class="type-stat-lbl">Wins</span>
                        <span class="type-stat-val">${gameStats.wins}</span>
                    </div>
                    <div class="type-stat-row">
                        <span class="type-stat-lbl">Losses</span>
                        <span class="type-stat-val">${gameStats.losses}</span>
                    </div>
                    <div class="type-stat-row">
                        <span class="type-stat-lbl">Win Rate</span>
                        <span class="type-stat-val">${winRatio}%</span>
                    </div>
                `;

                const clearBtn = document.createElement('button');
                clearBtn.className = 'clear-hist-btn';
                clearBtn.textContent = 'Clear History';
                clearBtn.onclick = () => clearHistory(gameType);

                card.appendChild(clearBtn);
                breakdown.appendChild(card);
            }
        }

        // Update Table
        const body = document.getElementById(elements.historyBody);
        body.innerHTML = '';

        data.recent.forEach(game => {
            const row = document.createElement('tr');
            const date = new Date(game.date).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });

            row.innerHTML = `
                <td>#${game.id}</td>
                <td>${game.type}</td>
                <td><span class="result-badge result-${game.result}">${game.result}</span></td>
                <td>${game.score}</td>
                <td>${date}</td>
            `;
            body.appendChild(row);
        });
    }

    // Register with framework
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById(elements.refreshBtn)?.addEventListener('click', loadStats);

        registerGame('game-results', {
            onTabSwitch: () => {
                loadStats();
            }
        });
    });

    window.refreshGameStats = loadStats;
})();
