/**
 * Aethvion Kanban - Frontend (Standalone)
 * Streamlined & Professional Edition
 */

let boardData = {
    columns: []
};

let currentEditingTask = null;
let currentEditingColumnId = null;

// --- DOM Elements ---
const boardEl = document.getElementById('kb-board');
const btnAddColumn = document.getElementById('btn-add-column');
const btnSaveBoard = document.getElementById('btn-save');
const taskModal = document.getElementById('task-modal');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnCancelModal = document.getElementById('btn-cancel-modal');
const btnSaveTask = document.getElementById('btn-save-task');
const btnDeleteTask = document.getElementById('btn-delete-task');
const toaster = document.getElementById('kb-toaster');

const inputTaskName = document.getElementById('task-name');
const inputTaskDesc = document.getElementById('task-desc');
const inputTaskPriority = document.getElementById('task-priority');

// --- Initialization ---
async function init() {
    setupEventListeners();
    await loadBoard();
}

async function loadBoard() {
    try {
        const resp = await fetch('/api/board');
        if (!resp.ok) throw new Error('Network response was not ok');
        boardData = await resp.json();
        renderBoard();
    } catch (err) {
        console.error('Failed to load board:', err);
        showNotification('Failed to load board data', 'error');
        boardEl.innerHTML = `<div class="kb-error">Failed to load board. Check server connection.</div>`;
    }
}

async function saveBoard(silent = false) {
    try {
        await fetch('/api/board', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(boardData)
        });
        if (!silent) showNotification('Board synced to core');
    } catch (err) {
        console.error('Failed to save board:', err);
        showNotification('Sync failed', 'error');
    }
}

// --- Rendering ---
function renderBoard() {
    boardEl.innerHTML = '';
    
    if (boardData.columns.length === 0) {
        boardEl.innerHTML = `
            <div class="kb-empty-state" style="margin: auto; text-align: center; opacity: 0.5;">
                <i class="fas fa-layer-group" style="font-size: 3rem; margin-bottom: 1rem;"></i>
                <p>Your board is empty. Add a column to get started.</p>
            </div>
        `;
        return;
    }

    boardData.columns.forEach(col => {
        const colEl = document.createElement('div');
        colEl.className = 'kb-column';
        colEl.dataset.id = col.id;
        
        colEl.innerHTML = `
            <div class="kb-column-header">
                <span class="kb-column-title">${escapeHTML(col.title)}</span>
                <button class="kb-btn-icon btn-del-col" title="Delete Column"><i class="fas fa-trash-alt"></i></button>
            </div>
            <div class="kb-task-list" data-id="${col.id}"></div>
            <div class="kb-column-footer">
                <button class="kb-btn btn-add-task" data-id="${col.id}">
                    <i class="fas fa-plus"></i> Add New Task
                </button>
            </div>
        `;
        
        // Delete column functionality
        colEl.querySelector('.btn-del-col').onclick = () => deleteColumn(col.id);

        const taskListEl = colEl.querySelector('.kb-task-list');
        col.tasks.forEach(task => {
            const cardEl = createTaskCard(task, col.id);
            taskListEl.appendChild(cardEl);
        });
        
        // Drag & Drop events for column
        taskListEl.addEventListener('dragover', e => {
            e.preventDefault();
            taskListEl.classList.add('drag-over');
        });
        
        taskListEl.addEventListener('dragleave', () => {
            taskListEl.classList.remove('drag-over');
        });
        
        taskListEl.addEventListener('drop', e => {
            e.preventDefault();
            taskListEl.classList.remove('drag-over');
            const taskId = e.dataTransfer.getData('text/plain');
            const sourceColId = e.dataTransfer.getData('source-col');
            moveTask(taskId, sourceColId, col.id);
        });
        
        boardEl.appendChild(colEl);
    });
    
    // Wire up add task buttons
    boardEl.querySelectorAll('.btn-add-task').forEach(btn => {
        btn.onclick = () => openTaskModal(null, btn.dataset.id);
    });
}

function createTaskCard(task, colId) {
    const card = document.createElement('div');
    card.className = 'kb-card';
    card.draggable = true;
    card.dataset.id = task.id;
    
    const priorityLabels = { low: 'Low', medium: 'Med', high: 'High' };
    const descCount = task.description ? task.description.trim().length : 0;
    
    card.innerHTML = `
        <div class="kb-card-priority-pill p-${task.priority}">
            <i class="fas fa-circle" style="font-size: 0.5rem"></i>
            ${priorityLabels[task.priority]}
        </div>
        <div class="kb-card-title">${escapeHTML(task.title)}</div>
        <div class="kb-card-meta">
            <div><i class="fas fa-align-left"></i> ${descCount > 0 ? 'Details' : 'Empty'}</div>
            <span>#${task.id.split('-').pop().substring(0,4)}</span>
        </div>
    `;
    
    card.onclick = () => openTaskModal(task, colId);
    
    card.addEventListener('dragstart', e => {
        card.classList.add('dragging');
        e.dataTransfer.setData('text/plain', task.id);
        e.dataTransfer.setData('source-col', colId);
        // Add a nice drag image effect
        setTimeout(() => (card.style.display = 'none'), 0);
    });
    
    card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        card.style.display = 'block';
    });
    
    return card;
}

// --- Actions ---
function openTaskModal(task, colId) {
    currentEditingTask = task;
    currentEditingColumnId = colId;
    
    if (task) {
        document.getElementById('modal-title').innerText = 'Edit Task';
        inputTaskName.value = task.title;
        inputTaskDesc.value = task.description || '';
        inputTaskPriority.value = task.priority;
        btnDeleteTask.classList.remove('hidden');
    } else {
        document.getElementById('modal-title').innerText = 'New Task';
        inputTaskName.value = '';
        inputTaskDesc.value = '';
        inputTaskPriority.value = 'medium';
        btnDeleteTask.classList.add('hidden');
    }
    
    taskModal.classList.remove('hidden');
    inputTaskName.focus();
}

function closeTaskModal() {
    taskModal.classList.add('hidden');
    currentEditingTask = null;
    currentEditingColumnId = null;
}

function saveTask() {
    const title = inputTaskName.value.trim();
    if (!title) {
        showNotification('Task name cannot be empty', 'error');
        return;
    }
    
    const col = boardData.columns.find(c => c.id === currentEditingColumnId);
    if (!col) return;
    
    if (currentEditingTask) {
        // Update
        currentEditingTask.title = title;
        currentEditingTask.description = inputTaskDesc.value;
        currentEditingTask.priority = inputTaskPriority.value;
        showNotification('Task updated');
    } else {
        // Create
        const newTask = {
            id: 't-' + Date.now(),
            title: title,
            description: inputTaskDesc.value,
            priority: inputTaskPriority.value,
            tags: []
        };
        col.tasks.push(newTask);
        showNotification('Task created');
    }
    
    renderBoard();
    closeTaskModal();
    saveBoard(true);
}

function deleteTask() {
    if (!currentEditingTask) return;
    if (!confirm('Are you sure you want to delete this task?')) return;
    
    const col = boardData.columns.find(c => c.id === currentEditingColumnId);
    if (col) {
        col.tasks = col.tasks.filter(t => t.id !== currentEditingTask.id);
    }
    
    showNotification('Task removed');
    renderBoard();
    closeTaskModal();
    saveBoard(true);
}

function moveTask(taskId, fromColId, toColId) {
    if (fromColId === toColId) return;
    
    const fromCol = boardData.columns.find(c => c.id === fromColId);
    const toCol = boardData.columns.find(c => c.id === toColId);
    
    const taskIdx = fromCol.tasks.findIndex(t => t.id === taskId);
    if (taskIdx === -1) return;
    
    const [task] = fromCol.tasks.splice(taskIdx, 1);
    toCol.tasks.push(task);
    
    renderBoard();
    saveBoard(true);
}

function addColumn() {
    const title = prompt('Enter Column Title:');
    if (!title) return;
    
    const id = 'c-' + Date.now();
    boardData.columns.push({
        id: id,
        title: title,
        tasks: []
    });
    
    renderBoard();
    saveBoard(true);
    showNotification('Column added');
}

function deleteColumn(colId) {
    if (!confirm('Delete this column and all its tasks?')) return;
    
    boardData.columns = boardData.columns.filter(c => c.id !== colId);
    renderBoard();
    saveBoard(true);
    showNotification('Column deleted');
}

function setupEventListeners() {
    btnAddColumn.addEventListener('click', addColumn);
    btnSaveBoard.addEventListener('click', () => saveBoard(false));
    btnCloseModal.addEventListener('click', closeTaskModal);
    btnCancelModal.addEventListener('click', closeTaskModal);
    btnSaveTask.addEventListener('click', saveTask);
    btnDeleteTask.addEventListener('click', deleteTask);
    
    // Global keyboard shortcuts
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && !taskModal.classList.contains('hidden')) {
            closeTaskModal();
        }
    });

    window.onclick = (e) => {
        if (e.target === taskModal) closeTaskModal();
    };
}

// --- Utilities ---
function showNotification(msg, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `kb-toast kb-toast-${type}`;
    
    const icon = type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle';
    toast.innerHTML = `<i class="fas ${icon}"></i> <span>${msg}</span>`;
    
    toaster.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function escapeHTML(str) {
    const p = document.createElement('p');
    p.textContent = str;
    return p.innerHTML;
}

// Start
init();
