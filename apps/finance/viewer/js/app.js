/**
 * Aethvion Finance — Complete Application Logic
 * Vanilla JS IIFE, no framework dependencies.
 */
(function () {
  'use strict';

  // ======================================================================
  // Constants
  // ======================================================================
  const CATEGORIES = [
    'Income', 'Housing', 'Food', 'Transport', 'Utilities',
    'Healthcare', 'Entertainment', 'Shopping', 'Services',
    'Education', 'Savings', 'Investment', 'Other'
  ];

  const CATEGORY_ICONS = {
    Income: '💰', Housing: '🏠', Food: '🍔', Transport: '🚗',
    Utilities: '💡', Healthcare: '🏥', Entertainment: '🎬',
    Shopping: '🛍️', Services: '⚙️', Education: '📚',
    Savings: '🏦', Investment: '📈', Other: '📌'
  };

  const ACCOUNT_ICONS = {
    checking: '💳', savings: '🏦', investment: '📈', cash: '💵'
  };

  const ACCENT_COLORS = [
    '#00d2ff', '#00f2ad', '#ff4b5c', '#ffb938',
    '#a855f7', '#f97316', '#06b6d4', '#84cc16'
  ];

  // ======================================================================
  // Core state
  // ======================================================================
  let state = { meta: {}, accounts: [], transactions: [], budgets: [], goals: [], holdings: [] };
  let activeView = 'dashboard';
  let charts = {};

  // Transactions filter
  let txFilter = {
    month: currentYearMonth(),
    category: '',
    type: '',
    search: ''
  };

  // Selected transaction row
  let selectedTxId = null;

  // Budget month navigator
  let budgetMonth = currentYearMonth();

  // ======================================================================
  // Utility helpers
  // ======================================================================

  /** Returns "YYYY-MM" for today */
  function currentYearMonth() {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
  }

  /** "YYYY-MM" → "March 2026" */
  function monthLabel(ym) {
    const [y, m] = ym.split('-');
    const d = new Date(+y, +m - 1, 1);
    return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  }

  /** Advance a "YYYY-MM" by delta months */
  function shiftMonth(ym, delta) {
    const [y, m] = ym.split('-').map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
  }

  /** Format ISO date string → "15 Mar 2026" */
  function fmtDate(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr + 'T00:00:00');
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  /** Format number as currency with state symbol */
  function fmtCurrency(n) {
    const sym = (state.meta && state.meta.currency) ? state.meta.currency : '€';
    const abs = Math.abs(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (n < 0 ? '-' : '') + sym + abs;
  }

  /** Format a plain number with 2 decimals and thousand separators */
  function fmt(n) {
    return Math.abs(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /** Get transactions for a "YYYY-MM" month */
  function getTxForMonth(ym) {
    return state.transactions.filter(t => t.date && t.date.startsWith(ym));
  }

  /** {category: total} for expenses in a transaction list */
  function getCategoryTotals(txList) {
    const totals = {};
    txList.filter(t => t.type === 'expense').forEach(t => {
      totals[t.category] = (totals[t.category] || 0) + Math.abs(t.amount);
    });
    return totals;
  }

  /**
   * Compute net worth history for last N months.
   * Strategy: sum account opening balances, then layer on transactions.
   */
  function getNetWorthHistory(months = 12) {
    const result = [];
    const today = new Date();
    // Running total starts from sum of account balances (current state)
    // We work backwards: current net worth is known, then subtract/add
    const currentNetWorth = state.accounts.reduce((s, a) => s + (a.balance || 0), 0);

    for (let i = 0; i < months; i++) {
      const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
      const ym = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
      result.unshift({ month: ym, label: d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }) });
    }

    // Compute a running balance per month cumulatively
    // Simplification: use currentNetWorth minus all future-month net flows
    let runningNW = currentNetWorth;
    const monthly = {};

    // Walk months oldest→newest computing net flow per month
    state.transactions.forEach(t => {
      if (!t.date) return;
      const ym = t.date.substring(0, 7);
      const signed = t.type === 'income' ? Math.abs(t.amount) : -Math.abs(t.amount);
      monthly[ym] = (monthly[ym] || 0) + signed;
    });

    // Start from current and subtract forward months
    const currentYM = currentYearMonth();
    for (let i = result.length - 1; i >= 0; i--) {
      const ym = result[i].month;
      result[i].netWorth = runningNW;
      // Subtract this month's contribution to go back
      runningNW -= (monthly[ym] || 0);
    }

    return result;
  }

  /** Show a toast notification */
  function notify(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.animation = 'toast-out 0.2s ease forwards';
      setTimeout(() => toast.remove(), 220);
    }, 3000);
  }

  /** Fetch wrapper — returns parsed JSON or throws */
  async function api(method, path, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' }
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const resp = await fetch(path, opts);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    return resp.json();
  }

  /** Destroy a chart instance if it exists */
  function destroyChart(key) {
    if (charts[key]) {
      charts[key].destroy();
      delete charts[key];
    }
  }

  // ======================================================================
  // State loading
  // ======================================================================
  async function loadState() {
    try {
      state = await api('GET', '/api/state');
      renderAll();
    } catch (e) {
      notify('Could not load state from server: ' + e.message, 'error');
    }
  }

  // ======================================================================
  // Navigation
  // ======================================================================
  function switchView(name) {
    // Hide all views
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    const viewEl = document.getElementById('view-' + name);
    const navEl  = document.getElementById('nav-' + name);
    if (viewEl) viewEl.classList.add('active');
    if (navEl)  navEl.classList.add('active');

    activeView = name;
    renderView(name);
  }

  function renderView(name) {
    switch (name) {
      case 'dashboard':    renderDashboard();    break;
      case 'transactions': renderTransactions(); break;
      case 'accounts':     renderAccounts();     break;
      case 'budget':       renderBudget();       break;
      case 'goals':        renderGoals();        break;
      case 'analytics':    renderAnalytics();    break;
      case 'portfolio':    renderPortfolio();    break;
    }
  }

  function renderAll() {
    updateHeaderMeta();
    renderView(activeView);
  }

  function updateHeaderMeta() {
    const nameEl = document.getElementById('meta-name');
    const currEl = document.getElementById('meta-currency');
    if (nameEl) nameEl.textContent = (state.meta && state.meta.name) ? state.meta.name : 'My Finances';
    if (currEl) currEl.textContent = (state.meta && state.meta.currency) ? state.meta.currency : '€';
  }

  // ======================================================================
  // Dashboard
  // ======================================================================
  function renderDashboard() {
    const ym = currentYearMonth();
    const monthTx = getTxForMonth(ym);
    const monthIncome   = monthTx.filter(t => t.type === 'income').reduce((s, t) => s + Math.abs(t.amount), 0);
    const monthExpenses = monthTx.filter(t => t.type === 'expense').reduce((s, t) => s + Math.abs(t.amount), 0);
    const netWorth      = state.accounts.reduce((s, a) => s + (a.balance || 0), 0);
    const savingsRate   = monthIncome > 0 ? ((monthIncome - monthExpenses) / monthIncome * 100) : 0;

    // KPIs
    setText('kpi-networth',  fmtCurrency(netWorth));
    setText('kpi-income',    fmtCurrency(monthIncome));
    setText('kpi-expenses',  fmtCurrency(monthExpenses));
    setText('kpi-savings',   savingsRate.toFixed(1) + '%');
    setText('dash-month-label', monthLabel(ym));

    // Net worth trend chart
    buildNetWorthChart();

    // Spending donut
    buildSpendingDonut(ym);

    // Recent transactions (last 5)
    renderRecentTx();

    // Goals progress
    renderGoalsMini();
  }

  function buildNetWorthChart() {
    destroyChart('netWorthTrend');
    const history = getNetWorthHistory(12);
    const canvas = document.getElementById('chart-networth-trend');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    charts['netWorthTrend'] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: history.map(h => h.label),
        datasets: [{
          label: 'Net Worth',
          data: history.map(h => h.netWorth),
          borderColor: '#00d2ff',
          backgroundColor: 'rgba(0,210,255,0.08)',
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: '#00d2ff'
        }]
      },
      options: darkChartOptions({ legend: false })
    });
  }

  function buildSpendingDonut(ym) {
    destroyChart('spendingDonut');
    const canvas = document.getElementById('chart-spending-donut');
    if (!canvas) return;
    const totals = getCategoryTotals(getTxForMonth(ym));
    const labels = Object.keys(totals);
    const data   = Object.values(totals);
    if (!labels.length) return;
    const ctx = canvas.getContext('2d');
    charts['spendingDonut'] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: ACCENT_COLORS.slice(0, labels.length),
          borderWidth: 2,
          borderColor: '#1c1f2b'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: {
            display: true,
            position: 'right',
            labels: { color: '#7a7f99', font: { family: 'Outfit', size: 11 }, boxWidth: 12 }
          }
        }
      }
    });
  }

  function renderRecentTx() {
    const el = document.getElementById('dash-recent-tx');
    if (!el) return;
    const sorted = [...state.transactions].sort((a, b) => (b.date || '').localeCompare(a.date || '')).slice(0, 5);
    if (!sorted.length) {
      el.innerHTML = '<div class="empty-state"><i class="fa-solid fa-receipt"></i><p>No transactions yet</p></div>';
      return;
    }
    el.innerHTML = sorted.map(t => {
      const icon = CATEGORY_ICONS[t.category] || '📌';
      const cls  = t.type === 'income' ? 'income' : 'expense';
      const sign = t.type === 'income' ? '+' : '-';
      const sym  = (state.meta && state.meta.currency) ? state.meta.currency : '€';
      return `<div class="recent-tx-item">
        <div class="tx-cat-badge" style="background:rgba(255,255,255,0.06)">${icon}</div>
        <div class="tx-info">
          <div class="tx-name">${esc(t.name)}</div>
          <div class="tx-date">${fmtDate(t.date)} · ${esc(t.category)}</div>
        </div>
        <div class="tx-amount ${cls}">${sign}${sym}${Math.abs(t.amount).toFixed(2)}</div>
      </div>`;
    }).join('');
  }

  function renderGoalsMini() {
    const el = document.getElementById('dash-goals');
    if (!el) return;
    if (!state.goals.length) {
      el.innerHTML = '<div class="empty-state"><i class="fa-solid fa-bullseye"></i><p>No goals set</p></div>';
      return;
    }
    el.innerHTML = state.goals.map(g => {
      const pct = g.target > 0 ? Math.min(100, (g.current / g.target) * 100) : 0;
      return `<div class="goal-mini-item">
        <div class="goal-mini-header">
          <span class="goal-mini-name">${esc(g.name)}</span>
          <span class="goal-mini-pct">${pct.toFixed(1)}%</span>
        </div>
        <div class="progress-bar-track">
          <div class="progress-bar-fill" style="width:${pct}%;background:${g.color || '#00d2ff'}"></div>
        </div>
      </div>`;
    }).join('');
  }

  // ======================================================================
  // Transactions
  // ======================================================================
  function renderTransactions() {
    // Populate category filter
    const catSel = document.getElementById('tx-filter-category');
    if (catSel) {
      const usedCats = [...new Set(state.transactions.map(t => t.category).filter(Boolean))].sort();
      const current = catSel.value;
      catSel.innerHTML = '<option value="">All Categories</option>' +
        usedCats.map(c => `<option value="${esc(c)}" ${c === current ? 'selected' : ''}>${esc(c)}</option>`).join('');
    }

    // Set filter UI values
    const monthEl  = document.getElementById('tx-filter-month');
    const typeEl   = document.getElementById('tx-filter-type');
    const searchEl = document.getElementById('tx-filter-search');
    if (monthEl  && !monthEl.dataset.bound)  monthEl.value  = txFilter.month;
    if (typeEl   && !typeEl.dataset.bound)   typeEl.value   = txFilter.type;
    if (searchEl && !searchEl.dataset.bound) searchEl.value = txFilter.search;

    // Apply filters
    let filtered = [...state.transactions];
    if (txFilter.month)    filtered = filtered.filter(t => t.date && t.date.startsWith(txFilter.month));
    if (txFilter.category) filtered = filtered.filter(t => t.category === txFilter.category);
    if (txFilter.type)     filtered = filtered.filter(t => t.type === txFilter.type);
    if (txFilter.search) {
      const q = txFilter.search.toLowerCase();
      filtered = filtered.filter(t => (t.name || '').toLowerCase().includes(q));
    }

    // Sort by date descending
    filtered.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    // Update count label
    const total = state.transactions.length;
    const shown = filtered.length;
    setText('tx-count-label', `${shown} of ${total} transactions`);

    // Render rows
    const tbody = document.getElementById('tx-table-body');
    if (!tbody) return;

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><i class="fa-solid fa-receipt"></i><p>No transactions match your filters</p></div></td></tr>`;
      return;
    }

    const accMap = {};
    state.accounts.forEach(a => { accMap[a.id] = a.name; });

    tbody.innerHTML = filtered.map(t => {
      const cls     = t.type === 'income' ? 'income' : 'expense';
      const sign    = t.type === 'income' ? '+' : '-';
      const sym     = (state.meta && state.meta.currency) ? state.meta.currency : '€';
      const accName = t.account_id ? (accMap[t.account_id] || '—') : '—';
      const sel     = t.id === selectedTxId ? 'selected' : '';
      return `<tr class="${sel}" data-id="${t.id}">
        <td>${fmtDate(t.date)}</td>
        <td>${esc(t.name)}</td>
        <td><span class="cat-chip">${esc(t.category || '—')}</span></td>
        <td class="text-muted">${esc(accName)}</td>
        <td class="tx-table-amount ${cls}">${sign}${sym}${Math.abs(t.amount).toFixed(2)}</td>
      </tr>`;
    }).join('');

    // Update action bar
    updateTxActionBar();
  }

  function updateTxActionBar() {
    const bar  = document.getElementById('tx-row-actions');
    const name = document.getElementById('tx-selected-name');
    if (!bar) return;
    if (selectedTxId) {
      const tx = state.transactions.find(t => t.id === selectedTxId);
      bar.classList.add('visible');
      if (name && tx) name.textContent = tx.name;
    } else {
      bar.classList.remove('visible');
      if (name) name.textContent = '';
    }
  }

  // ======================================================================
  // Accounts
  // ======================================================================
  function renderAccounts() {
    const grid     = document.getElementById('accounts-grid');
    const totalEl  = document.getElementById('accounts-total-balance');
    const subEl    = document.getElementById('accounts-subtitle');
    if (!grid) return;

    const total = state.accounts.reduce((s, a) => s + (a.balance || 0), 0);
    if (totalEl) totalEl.textContent = fmtCurrency(total);
    if (subEl)   subEl.textContent   = `${state.accounts.length} account${state.accounts.length !== 1 ? 's' : ''}`;

    if (!state.accounts.length) {
      grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1;">
        <i class="fa-solid fa-building-columns"></i>
        <p>No accounts yet. Add your first account to get started.</p>
      </div>`;
      return;
    }

    grid.innerHTML = state.accounts.map(a => {
      const color = a.color || '#00d2ff';
      const icon  = ACCOUNT_ICONS[a.type] || '💳';
      const bgHex = color + '22';
      return `<div class="account-card">
        <div class="acc-color-bar" style="background:${color}"></div>
        <div class="acc-header">
          <div class="acc-icon" style="background:${bgHex}">${icon}</div>
          <div class="acc-actions">
            <button class="btn-icon" title="Edit" onclick="openEditAccount('${a.id}')"><i class="fa-solid fa-pen"></i></button>
            <button class="btn-icon danger" title="Delete" onclick="confirmDeleteAccount('${a.id}')"><i class="fa-solid fa-trash"></i></button>
          </div>
        </div>
        <div class="acc-balance" style="color:${color}">${fmtCurrency(a.balance || 0)}</div>
        <div class="acc-name">${esc(a.name)}</div>
        <div class="acc-type">${esc(a.type)}</div>
      </div>`;
    }).join('');
  }

  // ======================================================================
  // Budget
  // ======================================================================
  function renderBudget() {
    setText('budget-month-label', monthLabel(budgetMonth));

    const list  = document.getElementById('budget-list');
    if (!list) return;

    const monthTx = getTxForMonth(budgetMonth);
    const sym     = (state.meta && state.meta.currency) ? state.meta.currency : '€';

    // Gather all categories that have a budget set
    const budgeted = {};
    state.budgets.forEach(b => { budgeted[b.category] = b; });

    // Gather categories with expenses this month (no budget)
    const catTotals = getCategoryTotals(monthTx);
    const unbudgeted = Object.keys(catTotals).filter(c => !budgeted[c]);

    const rows = [];

    // Budgeted rows
    state.budgets.forEach(b => {
      const spent = catTotals[b.category] || 0;
      const pct   = b.limit > 0 ? Math.min(100, (spent / b.limit) * 100) : 0;
      const over  = spent > b.limit;
      const rem   = b.limit - spent;
      const barColor = over ? '#ff4b5c' : pct > 80 ? '#ffb938' : '#00f2ad';
      rows.push(`<div class="budget-row">
        <div class="budget-cat-name">${esc(b.category)}</div>
        <div class="budget-bar-col">
          <div class="budget-bar-track">
            <div class="budget-bar-fill" style="width:${pct}%;background:${barColor}"></div>
          </div>
        </div>
        <div class="budget-amount-spent">${sym}${spent.toFixed(2)}</div>
        <div class="budget-amount-limit">${sym}${b.limit.toFixed(2)}</div>
        <div class="budget-remaining ${over ? 'over' : 'ok'}">${over ? '−' + sym + Math.abs(rem).toFixed(2) + ' over' : sym + rem.toFixed(2)}</div>
        <div style="display:flex;gap:4px;">
          <button class="btn-icon" title="Edit budget" onclick="openSetBudget('${esc(b.category)}')"><i class="fa-solid fa-pen"></i></button>
          <button class="btn-icon danger" title="Remove budget" onclick="confirmDeleteBudget('${esc(b.category)}')"><i class="fa-solid fa-trash"></i></button>
        </div>
      </div>`);
    });

    // Unbudgeted rows
    unbudgeted.forEach(cat => {
      const spent = catTotals[cat] || 0;
      rows.push(`<div class="budget-row">
        <div class="budget-cat-name">${esc(cat)}</div>
        <div class="budget-bar-col">
          <div class="budget-bar-track"><div class="budget-bar-fill" style="width:100%;background:#7a7f99;opacity:0.4"></div></div>
        </div>
        <div class="budget-amount-spent">${sym}${spent.toFixed(2)}</div>
        <div class="budget-amount-limit text-muted">No limit</div>
        <div><span class="unbudgeted-label">Unbudgeted</span></div>
        <div>
          <button class="btn-icon" title="Set budget" onclick="openSetBudget('${esc(cat)}')"><i class="fa-solid fa-plus"></i></button>
        </div>
      </div>`);
    });

    if (!rows.length) {
      list.innerHTML = `<div class="empty-state">
        <i class="fa-solid fa-clipboard-list"></i>
        <p>No budgets set and no expenses recorded for ${monthLabel(budgetMonth)}.</p>
      </div>`;
    } else {
      list.innerHTML = rows.join('');
    }
  }

  // ======================================================================
  // Goals
  // ======================================================================
  function renderGoals() {
    const grid = document.getElementById('goals-grid');
    if (!grid) return;

    if (!state.goals.length) {
      grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1;">
        <i class="fa-solid fa-bullseye"></i>
        <p>No goals yet. Set a financial goal to get started.</p>
      </div>`;
      return;
    }

    const today = new Date();
    const sym = (state.meta && state.meta.currency) ? state.meta.currency : '€';

    grid.innerHTML = state.goals.map(g => {
      const pct     = g.target > 0 ? Math.min(100, (g.current / g.target) * 100) : 0;
      const color   = g.color || '#00d2ff';
      const bgHex   = color + '18';

      let daysLeft = '—';
      let monthlyNeeded = '—';
      if (g.deadline) {
        const deadline = new Date(g.deadline);
        const diffMs   = deadline - today;
        const days     = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
        daysLeft = days > 0 ? `${days} days` : days === 0 ? 'Today' : 'Overdue';
        const months = Math.max(1, Math.ceil(days / 30));
        const needed = (g.target - g.current) / months;
        monthlyNeeded = needed > 0 ? sym + needed.toFixed(2) + '/mo' : 'Complete!';
      }

      return `<div class="goal-card">
        <div class="goal-color-bar" style="background:${color}"></div>
        <div class="goal-card-header">
          <div>
            <div class="goal-name">${esc(g.name)}</div>
            <div class="goal-deadline">${g.deadline ? 'Deadline: ' + fmtDate(g.deadline) : 'No deadline'}</div>
          </div>
          <div class="goal-actions">
            <button class="btn-icon" title="Edit" onclick="openEditGoal('${g.id}')"><i class="fa-solid fa-pen"></i></button>
            <button class="btn-icon danger" title="Delete" onclick="confirmDeleteGoal('${g.id}')"><i class="fa-solid fa-trash"></i></button>
          </div>
        </div>
        <div class="goal-amounts">
          <span class="goal-current" style="color:${color}">${fmtCurrency(g.current)}</span>
          <span class="goal-target">of ${fmtCurrency(g.target)}</span>
        </div>
        <div class="progress-bar-track">
          <div class="progress-bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <div class="goal-stats">
          <div class="goal-stat">
            <div class="stat-label">Progress</div>
            <div class="stat-value">${pct.toFixed(1)}%</div>
          </div>
          <div class="goal-stat">
            <div class="stat-label">Days Left</div>
            <div class="stat-value">${daysLeft}</div>
          </div>
          <div class="goal-stat" style="grid-column:1/-1">
            <div class="stat-label">Monthly needed</div>
            <div class="stat-value">${monthlyNeeded}</div>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  // ======================================================================
  // Analytics
  // ======================================================================
  function renderAnalytics() {
    buildIncomeExpensesChart();
    buildCatBarChart();
    buildCashflowChart();
    buildAccountsDonutChart();
  }

  function buildIncomeExpensesChart() {
    destroyChart('incomeExpenses');
    const canvas = document.getElementById('chart-income-expenses');
    if (!canvas) return;

    const months = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date();
      d.setMonth(d.getMonth() - i);
      const ym = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
      months.push({ ym, label: d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }) });
    }

    const incomeData   = months.map(m => getTxForMonth(m.ym).filter(t => t.type === 'income').reduce((s, t) => s + Math.abs(t.amount), 0));
    const expenseData  = months.map(m => getTxForMonth(m.ym).filter(t => t.type === 'expense').reduce((s, t) => s + Math.abs(t.amount), 0));

    const ctx = canvas.getContext('2d');
    charts['incomeExpenses'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: months.map(m => m.label),
        datasets: [
          { label: 'Income',   data: incomeData,  backgroundColor: 'rgba(0,242,173,0.7)',  borderRadius: 4 },
          { label: 'Expenses', data: expenseData, backgroundColor: 'rgba(255,75,92,0.7)',  borderRadius: 4 }
        ]
      },
      options: darkChartOptions({ legend: true })
    });
  }

  function buildCatBarChart() {
    destroyChart('catBar');
    const canvas = document.getElementById('chart-cat-bar');
    if (!canvas) return;

    const ym     = currentYearMonth();
    const totals = getCategoryTotals(getTxForMonth(ym));
    const sorted = Object.entries(totals).sort((a, b) => b[1] - a[1]);

    if (!sorted.length) return;

    const ctx = canvas.getContext('2d');
    charts['catBar'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: sorted.map(([k]) => k),
        datasets: [{
          label: 'Spending',
          data: sorted.map(([, v]) => v),
          backgroundColor: sorted.map((_, i) => ACCENT_COLORS[i % ACCENT_COLORS.length]),
          borderRadius: 4
        }]
      },
      options: {
        ...darkChartOptions({ legend: false }),
        indexAxis: 'y'
      }
    });
  }

  function buildCashflowChart() {
    destroyChart('cashflow');
    const canvas = document.getElementById('chart-cashflow');
    if (!canvas) return;

    const months = [];
    for (let i = 11; i >= 0; i--) {
      const d = new Date();
      d.setMonth(d.getMonth() - i);
      const ym = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
      months.push({ ym, label: d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }) });
    }

    const cfData = months.map(m => {
      const txs  = getTxForMonth(m.ym);
      const inc  = txs.filter(t => t.type === 'income').reduce((s, t) => s + Math.abs(t.amount), 0);
      const exp  = txs.filter(t => t.type === 'expense').reduce((s, t) => s + Math.abs(t.amount), 0);
      return inc - exp;
    });

    const ctx = canvas.getContext('2d');
    charts['cashflow'] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: months.map(m => m.label),
        datasets: [{
          label: 'Net Cash Flow',
          data: cfData,
          borderColor: '#00d2ff',
          backgroundColor: 'rgba(0,210,255,0.07)',
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 3
        }]
      },
      options: darkChartOptions({ legend: false })
    });
  }

  function buildAccountsDonutChart() {
    destroyChart('accountsDonut');
    const canvas = document.getElementById('chart-accounts-donut');
    if (!canvas) return;
    const positive = state.accounts.filter(a => (a.balance || 0) > 0);
    if (!positive.length) return;
    const ctx = canvas.getContext('2d');
    charts['accountsDonut'] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: positive.map(a => a.name),
        datasets: [{
          data: positive.map(a => a.balance),
          backgroundColor: positive.map((_, i) => ACCENT_COLORS[i % ACCENT_COLORS.length]),
          borderWidth: 2,
          borderColor: '#1c1f2b'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: {
            display: true,
            position: 'right',
            labels: { color: '#7a7f99', font: { family: 'Outfit', size: 11 }, boxWidth: 12 }
          }
        }
      }
    });
  }

  /** Standard dark Chart.js options */
  function darkChartOptions({ legend = false } = {}) {
    Chart.defaults.color        = '#a0a0a0';
    Chart.defaults.borderColor  = 'rgba(255,255,255,0.05)';
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {
          display: legend,
          labels: { color: '#7a7f99', font: { family: 'Outfit', size: 11 }, boxWidth: 12 }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#7a7f99', font: { family: 'Outfit' } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#7a7f99', font: { family: 'Outfit' } } }
      }
    };
  }

  // ======================================================================
  // Modal system
  // ======================================================================
  function openModal(title, bodyHTML, footerHTML, onSave) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML    = bodyHTML;
    document.getElementById('modal-footer').innerHTML  = footerHTML;
    document.getElementById('modal-overlay').classList.add('visible');

    // Wire save
    const saveBtn = document.getElementById('modal-save-btn');
    if (saveBtn && onSave) saveBtn.onclick = onSave;

    // Wire cancel / close
    const cancelBtn = document.getElementById('modal-cancel-btn');
    if (cancelBtn) cancelBtn.onclick = closeModal;
    document.getElementById('modal-close-btn').onclick = closeModal;
  }

  function closeModal() {
    document.getElementById('modal-overlay').classList.remove('visible');
  }

  function defaultFooter(showDelete, onDelete) {
    let del = '';
    if (showDelete) {
      del = `<button class="modal-delete-btn" id="modal-delete-btn"><i class="fa-solid fa-trash"></i> Delete</button>`;
    }
    return `${del}<span style="flex:1"></span>
      <button class="modal-cancel-btn" id="modal-cancel-btn">Cancel</button>
      <button class="modal-save-btn"   id="modal-save-btn">Save</button>`;
  }

  function wireDeleteBtn(handler) {
    const btn = document.getElementById('modal-delete-btn');
    if (btn) btn.onclick = handler;
  }

  // ======================================================================
  // Transaction modals
  // ======================================================================
  function openAddTransaction() {
    const today = new Date().toISOString().split('T')[0];
    const accOptions = state.accounts.map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join('');
    const catOptions = CATEGORIES.map(c => `<option value="${c}">${c}</option>`).join('');

    const body = `
      <div class="form-row">
        <div class="form-group">
          <label>Date</label>
          <input type="date" id="f-tx-date" value="${today}" />
        </div>
        <div class="form-group">
          <label>Type</label>
          <select id="f-tx-type">
            <option value="expense">Expense</option>
            <option value="income">Income</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>Description</label>
        <input type="text" id="f-tx-name" placeholder="e.g. Grocery run" />
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Amount</label>
          <input type="number" id="f-tx-amount" min="0" step="0.01" placeholder="0.00" />
        </div>
        <div class="form-group">
          <label>Category</label>
          <select id="f-tx-category">${catOptions}</select>
        </div>
      </div>
      <div class="form-group">
        <label>Account</label>
        <select id="f-tx-account">
          <option value="">— No account —</option>
          ${accOptions}
        </select>
      </div>
      <div class="form-group">
        <label>Note (optional)</label>
        <textarea id="f-tx-note" placeholder="Any notes…"></textarea>
      </div>`;

    openModal('Add Transaction', body, defaultFooter(false), async () => {
      const payload = {
        date:       getVal('f-tx-date'),
        type:       getVal('f-tx-type'),
        name:       getVal('f-tx-name'),
        amount:     parseFloat(getVal('f-tx-amount')) || 0,
        category:   getVal('f-tx-category'),
        account_id: getVal('f-tx-account'),
        note:       getVal('f-tx-note')
      };
      if (!payload.name)   { notify('Description is required', 'error'); return; }
      if (!payload.amount) { notify('Amount is required', 'error'); return; }
      try {
        await api('POST', '/api/transaction', payload);
        closeModal();
        await loadState();
        notify('Transaction added', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });
  }

  function openEditTransaction(id) {
    const tx = state.transactions.find(t => t.id === id);
    if (!tx) return;

    const accOptions = state.accounts.map(a =>
      `<option value="${a.id}" ${a.id === tx.account_id ? 'selected' : ''}>${esc(a.name)}</option>`).join('');
    const catOptions = CATEGORIES.map(c =>
      `<option value="${c}" ${c === tx.category ? 'selected' : ''}>${c}</option>`).join('');

    const body = `
      <div class="form-row">
        <div class="form-group">
          <label>Date</label>
          <input type="date" id="f-tx-date" value="${tx.date || ''}" />
        </div>
        <div class="form-group">
          <label>Type</label>
          <select id="f-tx-type">
            <option value="expense" ${tx.type === 'expense' ? 'selected' : ''}>Expense</option>
            <option value="income"  ${tx.type === 'income'  ? 'selected' : ''}>Income</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>Description</label>
        <input type="text" id="f-tx-name" value="${esc(tx.name)}" />
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Amount</label>
          <input type="number" id="f-tx-amount" value="${Math.abs(tx.amount)}" min="0" step="0.01" />
        </div>
        <div class="form-group">
          <label>Category</label>
          <select id="f-tx-category">${catOptions}</select>
        </div>
      </div>
      <div class="form-group">
        <label>Account</label>
        <select id="f-tx-account">
          <option value="">— No account —</option>
          ${accOptions}
        </select>
      </div>
      <div class="form-group">
        <label>Note (optional)</label>
        <textarea id="f-tx-note">${esc(tx.note || '')}</textarea>
      </div>`;

    openModal('Edit Transaction', body, defaultFooter(true), async () => {
      const payload = {
        date:       getVal('f-tx-date'),
        type:       getVal('f-tx-type'),
        name:       getVal('f-tx-name'),
        amount:     parseFloat(getVal('f-tx-amount')) || 0,
        category:   getVal('f-tx-category'),
        account_id: getVal('f-tx-account'),
        note:       getVal('f-tx-note')
      };
      try {
        await api('PUT', `/api/transaction/${id}`, payload);
        closeModal();
        selectedTxId = null;
        await loadState();
        notify('Transaction updated', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });

    wireDeleteBtn(async () => {
      if (!confirm('Delete this transaction?')) return;
      try {
        await api('DELETE', `/api/transaction/${id}`);
        closeModal();
        selectedTxId = null;
        await loadState();
        notify('Transaction deleted', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });
  }

  // ======================================================================
  // Account modals
  // ======================================================================
  function openAddAccount() {
    const body = `
      <div class="form-group">
        <label>Account Name</label>
        <input type="text" id="f-acc-name" placeholder="e.g. Main Checking" />
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Type</label>
          <select id="f-acc-type">
            <option value="checking">Checking</option>
            <option value="savings">Savings</option>
            <option value="investment">Investment</option>
            <option value="cash">Cash</option>
          </select>
        </div>
        <div class="form-group">
          <label>Opening Balance</label>
          <input type="number" id="f-acc-balance" value="0" step="0.01" />
        </div>
      </div>
      <div class="form-group">
        <label>Accent Color</label>
        <div class="color-input-row">
          <input type="color" id="f-acc-color-picker" value="#00d2ff" oninput="document.getElementById('f-acc-color').value=this.value" />
          <input type="text"  id="f-acc-color" value="#00d2ff" oninput="document.getElementById('f-acc-color-picker').value=this.value" />
        </div>
      </div>
      <div class="form-group">
        <label>Note (optional)</label>
        <textarea id="f-acc-note" placeholder="Optional note…"></textarea>
      </div>`;

    openModal('Add Account', body, defaultFooter(false), async () => {
      const payload = {
        name:    getVal('f-acc-name'),
        type:    getVal('f-acc-type'),
        balance: parseFloat(getVal('f-acc-balance')) || 0,
        color:   getVal('f-acc-color') || '#00d2ff',
        note:    getVal('f-acc-note')
      };
      if (!payload.name) { notify('Account name is required', 'error'); return; }
      try {
        await api('POST', '/api/account', payload);
        closeModal();
        await loadState();
        notify('Account added', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });
  }

  function openEditAccount(id) {
    const acc = state.accounts.find(a => a.id === id);
    if (!acc) return;

    const body = `
      <div class="form-group">
        <label>Account Name</label>
        <input type="text" id="f-acc-name" value="${esc(acc.name)}" />
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Type</label>
          <select id="f-acc-type">
            ${['checking','savings','investment','cash'].map(t =>
              `<option value="${t}" ${t === acc.type ? 'selected' : ''}>${t.charAt(0).toUpperCase()+t.slice(1)}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>Balance</label>
          <input type="number" id="f-acc-balance" value="${acc.balance || 0}" step="0.01" />
        </div>
      </div>
      <div class="form-group">
        <label>Accent Color</label>
        <div class="color-input-row">
          <input type="color" id="f-acc-color-picker" value="${acc.color || '#00d2ff'}" oninput="document.getElementById('f-acc-color').value=this.value" />
          <input type="text"  id="f-acc-color" value="${acc.color || '#00d2ff'}" oninput="document.getElementById('f-acc-color-picker').value=this.value" />
        </div>
      </div>
      <div class="form-group">
        <label>Note (optional)</label>
        <textarea id="f-acc-note">${esc(acc.note || '')}</textarea>
      </div>`;

    openModal('Edit Account', body, defaultFooter(true), async () => {
      const payload = {
        name:    getVal('f-acc-name'),
        type:    getVal('f-acc-type'),
        balance: parseFloat(getVal('f-acc-balance')) || 0,
        color:   getVal('f-acc-color') || '#00d2ff',
        note:    getVal('f-acc-note')
      };
      try {
        await api('PUT', `/api/account/${id}`, payload);
        closeModal();
        await loadState();
        notify('Account updated', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });

    wireDeleteBtn(() => confirmDeleteAccount(id));
  }

  function confirmDeleteAccount(id) {
    const acc = state.accounts.find(a => a.id === id);
    if (!acc) return;
    if (!confirm(`Delete account "${acc.name}"? This cannot be undone.`)) return;
    api('DELETE', `/api/account/${id}`)
      .then(() => { closeModal(); loadState(); notify('Account deleted', 'success'); })
      .catch(e => notify('Error: ' + e.message, 'error'));
  }

  // ======================================================================
  // Budget modals
  // ======================================================================
  function openSetBudget(preCategory) {
    const catOptions = CATEGORIES.map(c =>
      `<option value="${c}" ${c === preCategory ? 'selected' : ''}>${c}</option>`).join('');

    const existing = preCategory ? state.budgets.find(b => b.category === preCategory) : null;

    const body = `
      <div class="form-group">
        <label>Category</label>
        <select id="f-bud-category">${catOptions}</select>
      </div>
      <div class="form-group">
        <label>Monthly Limit</label>
        <input type="number" id="f-bud-limit" value="${existing ? existing.limit : ''}" min="0" step="0.01" placeholder="0.00" />
      </div>`;

    openModal(existing ? 'Edit Budget' : 'Set Budget', body, defaultFooter(false), async () => {
      const payload = {
        category: getVal('f-bud-category'),
        limit:    parseFloat(getVal('f-bud-limit')) || 0,
        period:   'monthly'
      };
      if (!payload.limit) { notify('Limit must be greater than 0', 'error'); return; }
      try {
        await api('POST', '/api/budget', payload);
        closeModal();
        await loadState();
        notify('Budget saved', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });
  }

  function confirmDeleteBudget(category) {
    if (!confirm(`Remove budget for "${category}"?`)) return;
    api('DELETE', `/api/budget/${encodeURIComponent(category)}`)
      .then(() => { loadState(); notify('Budget removed', 'success'); })
      .catch(e => notify('Error: ' + e.message, 'error'));
  }

  // ======================================================================
  // Goal modals
  // ======================================================================
  function openAddGoal() {
    const body = `
      <div class="form-group">
        <label>Goal Name</label>
        <input type="text" id="f-goal-name" placeholder="e.g. Emergency Fund" />
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Target Amount</label>
          <input type="number" id="f-goal-target" min="0" step="0.01" placeholder="0.00" />
        </div>
        <div class="form-group">
          <label>Current Saved</label>
          <input type="number" id="f-goal-current" value="0" min="0" step="0.01" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Deadline (optional)</label>
          <input type="date" id="f-goal-deadline" />
        </div>
        <div class="form-group">
          <label>Accent Color</label>
          <div class="color-input-row">
            <input type="color" id="f-goal-color-picker" value="#00d2ff" oninput="document.getElementById('f-goal-color').value=this.value" />
            <input type="text"  id="f-goal-color" value="#00d2ff" oninput="document.getElementById('f-goal-color-picker').value=this.value" />
          </div>
        </div>
      </div>
      <div class="form-group">
        <label>Note (optional)</label>
        <textarea id="f-goal-note" placeholder="Optional note…"></textarea>
      </div>`;

    openModal('Add Goal', body, defaultFooter(false), async () => {
      const payload = {
        name:     getVal('f-goal-name'),
        target:   parseFloat(getVal('f-goal-target')) || 0,
        current:  parseFloat(getVal('f-goal-current')) || 0,
        deadline: getVal('f-goal-deadline'),
        color:    getVal('f-goal-color') || '#00d2ff',
        note:     getVal('f-goal-note')
      };
      if (!payload.name)   { notify('Goal name is required', 'error'); return; }
      if (!payload.target) { notify('Target amount is required', 'error'); return; }
      try {
        await api('POST', '/api/goal', payload);
        closeModal();
        await loadState();
        notify('Goal added', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });
  }

  function openEditGoal(id) {
    const g = state.goals.find(x => x.id === id);
    if (!g) return;

    const body = `
      <div class="form-group">
        <label>Goal Name</label>
        <input type="text" id="f-goal-name" value="${esc(g.name)}" />
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Target Amount</label>
          <input type="number" id="f-goal-target" value="${g.target}" min="0" step="0.01" />
        </div>
        <div class="form-group">
          <label>Current Saved</label>
          <input type="number" id="f-goal-current" value="${g.current}" min="0" step="0.01" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Deadline (optional)</label>
          <input type="date" id="f-goal-deadline" value="${g.deadline || ''}" />
        </div>
        <div class="form-group">
          <label>Accent Color</label>
          <div class="color-input-row">
            <input type="color" id="f-goal-color-picker" value="${g.color || '#00d2ff'}" oninput="document.getElementById('f-goal-color').value=this.value" />
            <input type="text"  id="f-goal-color" value="${g.color || '#00d2ff'}" oninput="document.getElementById('f-goal-color-picker').value=this.value" />
          </div>
        </div>
      </div>
      <div class="form-group">
        <label>Note (optional)</label>
        <textarea id="f-goal-note">${esc(g.note || '')}</textarea>
      </div>`;

    openModal('Edit Goal', body, defaultFooter(true), async () => {
      const payload = {
        name:     getVal('f-goal-name'),
        target:   parseFloat(getVal('f-goal-target')) || 0,
        current:  parseFloat(getVal('f-goal-current')) || 0,
        deadline: getVal('f-goal-deadline'),
        color:    getVal('f-goal-color') || '#00d2ff',
        note:     getVal('f-goal-note')
      };
      try {
        await api('PUT', `/api/goal/${id}`, payload);
        closeModal();
        await loadState();
        notify('Goal updated', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });

    wireDeleteBtn(() => confirmDeleteGoal(id));
  }

  function confirmDeleteGoal(id) {
    const g = state.goals.find(x => x.id === id);
    if (!g) return;
    if (!confirm(`Delete goal "${g.name}"?`)) return;
    api('DELETE', `/api/goal/${id}`)
      .then(() => { closeModal(); loadState(); notify('Goal deleted', 'success'); })
      .catch(e => notify('Error: ' + e.message, 'error'));
  }

  // ======================================================================
  // Project Manager
  // ======================================================================
  async function openProjectManager() {
    document.getElementById('modal-title').textContent = 'Project Manager';
    document.getElementById('modal-body').innerHTML    = '<p class="text-muted" style="text-align:center;padding:20px;">Loading projects…</p>';
    document.getElementById('modal-footer').innerHTML  = `<span style="flex:1"></span><button class="modal-cancel-btn" id="modal-cancel-btn">Close</button>`;
    document.getElementById('modal-overlay').classList.add('visible');
    document.getElementById('modal-close-btn').onclick = closeModal;
    document.getElementById('modal-cancel-btn').onclick = closeModal;

    try {
      const data = await api('GET', '/api/projects');
      const projects = data.projects || [];

      const listHTML = projects.length
        ? projects.map(p => `<div class="project-item">
            <div class="project-item-info">
              <div class="project-item-name">${esc(p.name)}</div>
              <div class="project-item-meta">${esc(p.currency)} · ${p.modified ? p.modified.split('T')[0] : '—'}</div>
            </div>
            <div class="project-item-actions">
              <button class="proj-load-btn" data-file="${esc(p.filename)}"><i class="fa-solid fa-folder-open"></i> Load</button>
              <button class="proj-del-btn"  data-file="${esc(p.filename)}"><i class="fa-solid fa-trash"></i></button>
            </div>
          </div>`).join('')
        : '<p class="text-muted" style="text-align:center;padding:16px;">No saved projects yet.</p>';

      document.getElementById('modal-body').innerHTML = `
        <div class="proj-save-row">
          <input type="text" id="proj-save-name" placeholder="Project name to save…" value="${esc((state.meta && state.meta.name) ? state.meta.name : '')}" />
          <button class="btn-primary" id="proj-save-btn"><i class="fa-solid fa-floppy-disk"></i> Save</button>
        </div>
        <div class="project-list" id="project-list">${listHTML}</div>`;

      // Wire save button
      document.getElementById('proj-save-btn').onclick = async () => {
        const name = document.getElementById('proj-save-name').value.trim();
        if (!name) { notify('Enter a project name', 'error'); return; }
        try {
          await api('POST', '/api/save', { name });
          notify('Project saved: ' + name, 'success');
          openProjectManager(); // Refresh
        } catch (e) {
          notify('Save failed: ' + e.message, 'error');
        }
      };

      // Wire load/delete buttons
      document.getElementById('modal-body').querySelectorAll('.proj-load-btn').forEach(btn => {
        btn.onclick = async () => {
          const file = btn.dataset.file;
          try {
            await api('POST', `/api/load/${encodeURIComponent(file)}`);
            closeModal();
            await loadState();
            notify('Project loaded', 'success');
          } catch (e) {
            notify('Load failed: ' + e.message, 'error');
          }
        };
      });

      document.getElementById('modal-body').querySelectorAll('.proj-del-btn').forEach(btn => {
        btn.onclick = async () => {
          const file = btn.dataset.file;
          if (!confirm(`Delete project "${file}"?`)) return;
          try {
            await api('DELETE', `/api/projects/${encodeURIComponent(file)}`);
            notify('Project deleted', 'success');
            openProjectManager(); // Refresh
          } catch (e) {
            notify('Delete failed: ' + e.message, 'error');
          }
        };
      });

    } catch (e) {
      document.getElementById('modal-body').innerHTML =
        `<p class="text-danger" style="text-align:center;padding:20px;">Error: ${esc(e.message)}</p>`;
    }
  }

  // ======================================================================
  // Save inline controls
  // ======================================================================
  function showSaveInline() {
    const inline = document.getElementById('save-inline');
    const hdrBtns = document.querySelector('.header-actions');
    inline.classList.add('visible');
    hdrBtns.style.display = 'none';
    document.getElementById('save-name-input').value = (state.meta && state.meta.name) ? state.meta.name : '';
    document.getElementById('save-name-input').focus();
  }

  function hideSaveInline() {
    document.getElementById('save-inline').classList.remove('visible');
    document.querySelector('.header-actions').style.display = '';
  }

  async function doSave() {
    const name = document.getElementById('save-name-input').value.trim();
    if (!name) { notify('Enter a project name', 'error'); return; }
    try {
      await api('POST', '/api/save', { name });
      hideSaveInline();
      notify('Saved as "' + name + '"', 'success');
    } catch (e) {
      notify('Save failed: ' + e.message, 'error');
    }
  }

  // ======================================================================
  // DOM helpers
  // ======================================================================
  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value : '';
  }

  function esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ======================================================================
  // Event wiring
  // ======================================================================
  function wireEvents() {
    // Nav items
    document.querySelectorAll('.nav-item[data-view]').forEach(item => {
      item.addEventListener('click', () => switchView(item.dataset.view));
    });

    // Modal close on overlay click
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
      if (e.target === document.getElementById('modal-overlay')) closeModal();
    });

    // Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModal();
    });

    // Header: Save button
    document.getElementById('hdr-save-btn').addEventListener('click', showSaveInline);
    document.getElementById('save-confirm-btn').addEventListener('click', doSave);
    document.getElementById('save-cancel-btn').addEventListener('click', hideSaveInline);
    document.getElementById('save-name-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doSave();
      if (e.key === 'Escape') hideSaveInline();
    });

    // Header: Load button
    document.getElementById('hdr-load-btn').addEventListener('click', openProjectManager);

    // Add Transaction button
    document.getElementById('add-tx-btn').addEventListener('click', openAddTransaction);

    // Transaction table row clicks
    document.getElementById('tx-table-body').addEventListener('click', (e) => {
      const row = e.target.closest('tr[data-id]');
      if (!row) return;
      const id = row.dataset.id;
      if (selectedTxId === id) {
        selectedTxId = null;
      } else {
        selectedTxId = id;
      }
      // Refresh selection highlight
      document.querySelectorAll('#tx-table-body tr').forEach(r => r.classList.remove('selected'));
      if (selectedTxId) {
        document.querySelector(`#tx-table-body tr[data-id="${selectedTxId}"]`)?.classList.add('selected');
      }
      updateTxActionBar();
    });

    // Tx action bar buttons
    document.getElementById('tx-edit-btn').addEventListener('click', () => {
      if (selectedTxId) openEditTransaction(selectedTxId);
    });
    document.getElementById('tx-delete-btn').addEventListener('click', async () => {
      if (!selectedTxId) return;
      const tx = state.transactions.find(t => t.id === selectedTxId);
      if (!tx) return;
      if (!confirm(`Delete "${tx.name}"?`)) return;
      try {
        await api('DELETE', `/api/transaction/${selectedTxId}`);
        selectedTxId = null;
        await loadState();
        notify('Transaction deleted', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });

    // Transaction filters
    document.getElementById('tx-filter-month').addEventListener('change', (e) => {
      txFilter.month = e.target.value;
      renderTransactions();
    });
    document.getElementById('tx-filter-category').addEventListener('change', (e) => {
      txFilter.category = e.target.value;
      renderTransactions();
    });
    document.getElementById('tx-filter-type').addEventListener('change', (e) => {
      txFilter.type = e.target.value;
      renderTransactions();
    });
    document.getElementById('tx-filter-search').addEventListener('input', (e) => {
      txFilter.search = e.target.value;
      renderTransactions();
    });
    document.getElementById('tx-clear-filter-btn').addEventListener('click', () => {
      txFilter = { month: currentYearMonth(), category: '', type: '', search: '' };
      document.getElementById('tx-filter-month').value    = txFilter.month;
      document.getElementById('tx-filter-category').value = '';
      document.getElementById('tx-filter-type').value     = '';
      document.getElementById('tx-filter-search').value   = '';
      renderTransactions();
    });

    // Accounts
    document.getElementById('add-account-btn').addEventListener('click', openAddAccount);

    // Budget navigation
    document.getElementById('budget-prev-btn').addEventListener('click', () => {
      budgetMonth = shiftMonth(budgetMonth, -1);
      renderBudget();
    });
    document.getElementById('budget-next-btn').addEventListener('click', () => {
      budgetMonth = shiftMonth(budgetMonth, 1);
      renderBudget();
    });
    document.getElementById('add-budget-btn').addEventListener('click', () => openSetBudget(''));

    // Goals
    document.getElementById('add-goal-btn').addEventListener('click', openAddGoal);

    // Portfolio
    document.getElementById('add-holding-btn').addEventListener('click', openAddHolding);
    document.getElementById('portfolio-search').addEventListener('input', renderPortfolio);
    document.getElementById('refresh-prices-btn').addEventListener('click', refreshPrices);
  }

  // ======================================================================
  // Portfolio — live price refresh
  // ======================================================================
  async function refreshPrices() {
    const btn   = document.getElementById('refresh-prices-btn');
    const label = document.getElementById('refresh-prices-label');
    if (!btn) return;

    const holdings = state.holdings || [];
    if (!holdings.length) {
      notify('Add some holdings first before refreshing prices.', 'info');
      return;
    }

    // Loading state
    btn.disabled = true;
    const icon = btn.querySelector('i');
    if (icon) icon.className = 'fa-solid fa-rotate fa-spin';
    if (label) label.textContent = 'Refreshing…';

    try {
      const result = await api('POST', '/api/holdings/refresh-prices');

      // Merge updated holdings back into state so UI refreshes instantly
      // without a full round-trip loadState() for every holding
      if (result.holdings && result.holdings.length) {
        state.holdings = result.holdings;
      }

      renderPortfolio();

      // Summary toast
      const parts = [];
      if (result.updated > 0) parts.push(`${result.updated} price${result.updated !== 1 ? 's' : ''} updated`);
      if (result.skipped  > 0) parts.push(`${result.skipped} skipped`);
      if (result.errors && result.errors.length) {
        parts.push(`${result.errors.length} error${result.errors.length !== 1 ? 's' : ''}`);
        // Log individual errors to console for diagnostics
        result.errors.forEach(e => console.warn('[PriceRefresh]', e));
      }
      const type = result.errors && result.errors.length ? 'error' : 'success';
      notify(parts.join(' · ') || 'Prices refreshed', type);

    } catch (e) {
      notify('Price refresh failed: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
      if (icon) icon.className = 'fa-solid fa-rotate';
      if (label) label.textContent = 'Refresh Prices';
    }
  }

  // ======================================================================
  // Portfolio — rendering & charts
  // ======================================================================
  const ASSET_TYPES = ['Stock', 'ETF', 'Crypto', 'Bond', 'REIT', 'Fund', 'Cash', 'Other'];

  const ASSET_COLORS = {
    Stock:  '#00d2ff',
    ETF:    '#00f2ad',
    Crypto: '#f97316',
    Bond:   '#a855f7',
    REIT:   '#ffb938',
    Fund:   '#06b6d4',
    Cash:   '#84cc16',
    Other:  '#7a7f99',
  };

  function holdingPnl(h) {
    const cost  = h.shares * h.buy_price;
    const value = h.shares * h.current_price;
    const pnl   = value - cost;
    const pct   = cost > 0 ? (pnl / cost) * 100 : 0;
    return { cost, value, pnl, pct };
  }

  function renderPortfolio() {
    const holdings = state.holdings || [];
    const search   = (document.getElementById('portfolio-search')?.value || '').toLowerCase();
    const filtered = search
      ? holdings.filter(h => h.ticker.toLowerCase().includes(search) || h.name.toLowerCase().includes(search))
      : holdings;

    // ---- KPI totals ----
    let totalValue = 0, totalCost = 0;
    holdings.forEach(h => {
      const { cost, value } = holdingPnl(h);
      totalValue += value;
      totalCost  += cost;
    });
    const totalPnl = totalValue - totalCost;
    const totalPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;
    const cur = state.meta?.currency || '€';

    const kpiEl = document.getElementById('portfolio-kpis');
    if (kpiEl) {
      const pnlClass = totalPnl >= 0 ? 'success' : 'danger';
      kpiEl.innerHTML = `
        <div class="kpi-card" style="--kpi-color:var(--accent)">
          <div class="kpi-label">Portfolio Value</div>
          <div class="kpi-value">${cur}${fmt(totalValue)}</div>
        </div>
        <div class="kpi-card" style="--kpi-color:var(--text-muted)">
          <div class="kpi-label">Total Invested</div>
          <div class="kpi-value">${cur}${fmt(totalCost)}</div>
        </div>
        <div class="kpi-card" style="--kpi-color:var(--${pnlClass})">
          <div class="kpi-label">Total P&amp;L</div>
          <div class="kpi-value ${totalPnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
            ${totalPnl >= 0 ? '+' : ''}${cur}${fmt(Math.abs(totalPnl))}
          </div>
        </div>
        <div class="kpi-card" style="--kpi-color:var(--${pnlClass})">
          <div class="kpi-label">Return</div>
          <div class="kpi-value ${totalPct >= 0 ? 'pnl-positive' : 'pnl-negative'}">
            ${totalPct >= 0 ? '+' : ''}${totalPct.toFixed(2)}%
          </div>
        </div>
      `;
    }

    // ---- Holdings table ----
    const tbody = document.getElementById('holdings-tbody');
    if (tbody) {
      if (!filtered.length) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:40px;color:var(--text-muted);">
          ${search ? 'No holdings match your search.' : 'No holdings yet. Click <strong>Add Holding</strong> to get started.'}
        </td></tr>`;
      } else {
        tbody.innerHTML = filtered.map(h => {
          const { cost, value, pnl, pct } = holdingPnl(h);
          const sign = pnl >= 0 ? '+' : '';
          const cls  = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
          const type = (h.asset_type || 'other').charAt(0).toUpperCase() + (h.asset_type || 'other').slice(1);
          const color = ASSET_COLORS[type] || ASSET_COLORS.Other;
          return `<tr>
            <td><span class="holding-ticker">${esc(h.ticker)}</span></td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(h.name)}</td>
            <td><span class="asset-badge" style="color:${color};border:1px solid ${color}40">${type}</span></td>
            <td style="text-align:right">${h.shares.toLocaleString(undefined, {maximumFractionDigits:6})}</td>
            <td style="text-align:right">${cur}${fmt(h.buy_price)}</td>
            <td style="text-align:right">${cur}${fmt(h.current_price)}</td>
            <td style="text-align:right;font-weight:600">${cur}${fmt(value)}</td>
            <td style="text-align:right" class="${cls}">${sign}${cur}${fmt(Math.abs(pnl))}</td>
            <td style="text-align:right" class="${cls}">${sign}${pct.toFixed(2)}%</td>
            <td style="text-align:center">
              <button class="btn-icon" title="Edit" onclick="openEditHolding('${h.id}')"><i class="fa-solid fa-pen"></i></button>
              <button class="btn-icon danger" title="Delete" onclick="confirmDeleteHolding('${h.id}')"><i class="fa-solid fa-trash"></i></button>
            </td>
          </tr>`;
        }).join('');
      }
    }

    // ---- Charts ----
    buildPortfolioAllocChart(holdings);
    buildPortfolioPerfChart(filtered);
  }

  function buildPortfolioAllocChart(holdings) {
    destroyChart('portfolio-alloc');
    const canvas = document.getElementById('chart-portfolio-alloc');
    if (!canvas) return;

    // Group by asset type
    const groups = {};
    holdings.forEach(h => {
      const { value } = holdingPnl(h);
      const type = (h.asset_type || 'other').charAt(0).toUpperCase() + (h.asset_type || 'other').slice(1);
      groups[type] = (groups[type] || 0) + value;
    });
    const labels = Object.keys(groups);
    const data   = Object.values(groups);
    const colors = labels.map(l => ASSET_COLORS[l] || ASSET_COLORS.Other);

    if (!labels.length) return;

    charts['portfolio-alloc'] = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors.map(c => c + 'cc'),
          borderColor:     colors,
          borderWidth: 1.5,
          hoverOffset: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '62%',
        plugins: {
          legend: { position: 'right', labels: { boxWidth: 12, padding: 14, font: { size: 12 } } },
          tooltip: {
            callbacks: {
              label: ctx => {
                const cur = state.meta?.currency || '€';
                const pct = ((ctx.parsed / data.reduce((a,b) => a+b, 0)) * 100).toFixed(1);
                return ` ${cur}${fmt(ctx.parsed)}  (${pct}%)`;
              }
            }
          }
        }
      }
    });
  }

  function buildPortfolioPerfChart(holdings) {
    destroyChart('portfolio-perf');
    const canvas = document.getElementById('chart-portfolio-perf');
    if (!canvas || !holdings.length) return;

    const sorted = [...holdings].sort((a, b) => {
      const pa = holdingPnl(a).pnl, pb = holdingPnl(b).pnl;
      return pb - pa;
    }).slice(0, 12); // cap at 12 for readability

    const labels = sorted.map(h => h.ticker);
    const values = sorted.map(h => holdingPnl(h).pnl);
    const colors = values.map(v => v >= 0 ? 'rgba(0,242,173,0.8)' : 'rgba(255,75,92,0.8)');
    const borders = values.map(v => v >= 0 ? '#00f2ad' : '#ff4b5c');

    charts['portfolio-perf'] = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'P&L',
          data: values,
          backgroundColor: colors,
          borderColor:     borders,
          borderWidth: 1.5,
          borderRadius: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => {
                const cur = state.meta?.currency || '€';
                const v = ctx.parsed.y;
                return ` ${v >= 0 ? '+' : ''}${cur}${fmt(Math.abs(v))}`;
              }
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: {
              font: { size: 11 },
              callback: v => {
                const cur = state.meta?.currency || '€';
                return (v >= 0 ? '+' : '') + cur + fmt(Math.abs(v));
              }
            }
          }
        }
      }
    });
  }

  // ---- Holding modals ----
  function openAddHolding() {
    openModal('Add Holding', holdingForm({}), defaultFooter(false), async () => {
      const data = collectHoldingForm();
      if (!data) return;
      try {
        await api('POST', '/api/holding', data);
        closeModal();
        await loadState();
        notify('Holding added', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });
  }

  function openEditHolding(id) {
    const h = (state.holdings || []).find(x => x.id === id);
    if (!h) return;
    openModal('Edit Holding', holdingForm(h), defaultFooter(true), async () => {
      const data = collectHoldingForm();
      if (!data) return;
      try {
        await api('PUT', `/api/holding/${id}`, data);
        closeModal();
        await loadState();
        notify('Holding updated', 'success');
      } catch (e) {
        notify('Error: ' + e.message, 'error');
      }
    });
    wireDeleteBtn(() => confirmDeleteHolding(id));
  }

  function confirmDeleteHolding(id) {
    const h = (state.holdings || []).find(x => x.id === id);
    if (!h) return;
    if (!confirm(`Remove "${h.ticker} — ${h.name}" from your portfolio? This cannot be undone.`)) return;
    api('DELETE', `/api/holding/${id}`)
      .then(() => { closeModal(); loadState(); notify('Holding removed', 'success'); })
      .catch(e => notify('Error: ' + e.message, 'error'));
  }

  function holdingForm(h = {}) {
    const typeOptions = ASSET_TYPES.map(t =>
      `<option value="${t.toLowerCase()}" ${(h.asset_type || 'stock') === t.toLowerCase() ? 'selected' : ''}>${t}</option>`
    ).join('');
    return `
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">Ticker / Symbol *</label>
          <input id="hf-ticker" class="form-input" placeholder="e.g. AAPL" value="${esc(h.ticker || '')}" style="text-transform:uppercase" />
        </div>
        <div class="form-group">
          <label class="form-label">Name *</label>
          <input id="hf-name" class="form-input" placeholder="e.g. Apple Inc." value="${esc(h.name || '')}" />
        </div>
        <div class="form-group">
          <label class="form-label">Asset Type</label>
          <select id="hf-type" class="form-input">${typeOptions}</select>
        </div>
        <div class="form-group">
          <label class="form-label">Shares / Units *</label>
          <input id="hf-shares" type="number" step="any" min="0" class="form-input" placeholder="0" value="${h.shares ?? ''}" />
        </div>
        <div class="form-group">
          <label class="form-label">Buy Price (avg) *</label>
          <input id="hf-buy-price" type="number" step="any" min="0" class="form-input" placeholder="0.00" value="${h.buy_price ?? ''}" />
        </div>
        <div class="form-group">
          <label class="form-label">Current Price *</label>
          <input id="hf-current-price" type="number" step="any" min="0" class="form-input" placeholder="0.00" value="${h.current_price ?? ''}" />
        </div>
        <div class="form-group" style="grid-column:1/-1">
          <label class="form-label">Note</label>
          <input id="hf-note" class="form-input" placeholder="Optional note" value="${esc(h.note || '')}" />
        </div>
      </div>
    `;
  }

  function collectHoldingForm() {
    const ticker       = document.getElementById('hf-ticker')?.value.trim().toUpperCase();
    const name         = document.getElementById('hf-name')?.value.trim();
    const asset_type   = document.getElementById('hf-type')?.value;
    const shares       = parseFloat(document.getElementById('hf-shares')?.value);
    const buy_price    = parseFloat(document.getElementById('hf-buy-price')?.value);
    const current_price = parseFloat(document.getElementById('hf-current-price')?.value);
    const note         = document.getElementById('hf-note')?.value.trim();

    if (!ticker || !name || isNaN(shares) || isNaN(buy_price) || isNaN(current_price)) {
      notify('Please fill in all required fields.', 'error');
      return null;
    }
    if (shares < 0 || buy_price < 0 || current_price < 0) {
      notify('Values cannot be negative.', 'error');
      return null;
    }
    return { ticker, name, asset_type, shares, buy_price, current_price, note };
  }

  // Expose functions that are called from inline HTML onclick attributes
  window.openEditAccount     = openEditAccount;
  window.confirmDeleteAccount = confirmDeleteAccount;
  window.openEditGoal        = openEditGoal;
  window.confirmDeleteGoal   = confirmDeleteGoal;
  window.openSetBudget       = openSetBudget;
  window.confirmDeleteBudget = confirmDeleteBudget;
  window.openEditHolding     = openEditHolding;
  window.confirmDeleteHolding = confirmDeleteHolding;

  // ======================================================================
  // Boot
  // ======================================================================
  document.addEventListener('DOMContentLoaded', () => {
    // Set Chart.js global defaults
    Chart.defaults.color       = '#a0a0a0';
    Chart.defaults.borderColor = 'rgba(255,255,255,0.05)';
    Chart.defaults.font.family = 'Outfit';

    // Set initial filter month to current
    const monthEl = document.getElementById('tx-filter-month');
    if (monthEl) monthEl.value = txFilter.month;

    wireEvents();
    loadState();
  });

})();
