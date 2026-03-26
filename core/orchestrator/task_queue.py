"""
Misaka Cipher - Task Queue Manager
Manages async task execution with worker pool
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from pathlib import Path
from core.utils import get_logger, generate_trace_id
from core.tools.standard.file_ops import WORKSPACE_ROOT
from core.utils.paths import WS_PROJECTS, HISTORY_AGENTS
from .task_models import Task, TaskStatus, ChatThread

logger = get_logger(__name__)


class TaskWorker:
    """
    Worker that processes tasks from the queue.
    
    Each worker runs independently and can execute tasks in parallel.
    """
    
    def __init__(self, worker_id: str, queue: asyncio.Queue, tasks: Dict[str, Task], threads: Dict[str, ChatThread], orchestrator, save_callback=None):
        """
        Initialize task worker.
        
        Args:
            worker_id: Unique worker identifier
            queue: Shared task queue
            tasks: Shared tasks dictionary
            threads: Shared threads dictionary
            orchestrator: MasterOrchestrator instance
            save_callback: Function to call to persist task state
        """
        self.worker_id = worker_id
        self.queue = queue
        self.tasks = tasks
        self.threads = threads
        self.orchestrator = orchestrator
        self.save_callback = save_callback
        self.running = False
        self.current_task: Optional[Task] = None
        logger.info(f"Worker {worker_id} initialized")
    
    async def run(self):
        """Main worker loop - processes tasks from queue."""
        self.running = True
        logger.info(f"Worker {self.worker_id} started")
        
        while self.running:
            try:
                # Get task from queue (blocks until available)
                task = await self.queue.get()
                
                # Check if this is a specialized task for another worker (e.g. Discord)
                if task.metadata.get('task_type') == 'DISCORD_SEND':
                    # Put it back or just ignore it because we assume DiscordWorker is polling the same tasks dict
                    # Actually, if it's in the queue, it WILL be picked up by a TaskWorker.
                    # We should prevent Discord tasks from entering this general queue, 
                    # OR we make this worker ignore it and the DiscordWorker pulls it.
                    # Best: DiscordWorker doesn't use the queue.put(), it just watches the tasks dict.
                    # Wait, submit_task calls queue.put(task).
                    # I'll update submit_task to NOT queue DISCORD_SEND tasks.
                    self.queue.task_done()
                    continue

                self.current_task = task
                
                logger.info(f"Worker {self.worker_id} picked up task {task.id}")
                
                # Update task status
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                task.worker_id = self.worker_id
                
                # Save task state (started)
                # We need to access the manager to save, but worker only has orchestrator
                # So we'll access it via the shared tasks dict which is owned by manager,
                # but better yet, let's add a save callback or reference.
                # For now, let's assume we can't save from here easily without a ref.
                # Actually, the queue manager pass 'self' as well? No.
                # Let's check init: __init__(self, worker_id: str, queue: asyncio.Queue, tasks: Dict[str, Task], orchestrator)
                # We can't reach _save_task easily.
                # Let's Modify TaskWorker init to accept manager or save_callback.
                # For now, I'll update the worker logic in a separate step or just skip intermediate saving? 
                # No, intermediate saving is good for crash recovery.
                # I'll stick to updating the queue manager to save when it can, but worker does the work.
                # Wait, I can pass a callback to the worker.
                # Let's do that in a minute.
                
                # Actually, I can just update the code to pass the callback.
                try:
                    # Execute task via orchestrator in executor (it's synchronous)
                    loop = asyncio.get_event_loop()
                    mode = task.metadata.get('mode', 'auto')
                    
                    if hasattr(self, 'save_callback') and self.save_callback:
                        self.save_callback(task)
                    
                    # RETRIEVE SETTINGS: Prefer task metadata, fallback to thread
                    task_settings = task.metadata.get('settings')
                    thread = self.threads.get(task.thread_id)
                    
                    settings = {}
                    if thread and hasattr(thread, 'settings'):
                        settings.update(thread.settings)
                    if task_settings:
                        settings.update(task_settings)
                    
                    context_prompt = task.prompt
                    
                    if settings:
                        context_mode = settings.get('context_mode', 'none')
                        context_window = int(settings.get('context_window', 5))
                        
                        if context_mode in ['full', 'smart'] and thread and thread.task_ids:
                            # Fetch previous tasks
                            history_tasks = []
                            # Get task IDs excluding current one triggers infinite loop? No, current task is not in thread.task_ids yet?
                            # Wait, submit_task appends to thread.task_ids BEFORE queueing.
                            # So we should exclude the current task ID.
                            previous_ids = [tid for tid in thread.task_ids if tid != task.id]
                            
                            if context_mode == 'smart':
                                previous_ids = previous_ids[-context_window:]
                            
                            for tid in previous_ids:
                                if tid in self.tasks:
                                    t = self.tasks[tid]
                                    if t.status == TaskStatus.COMPLETED and t.result:
                                        # Approximate history format
                                        history_tasks.append(f"User: {t.prompt}")
                                        if t.result.get('response'):
                                            history_tasks.append(f"Assistant: {t.result.get('response')}")
                            
                            if history_tasks:
                                history_str = "\n".join(history_tasks)
                                context_prompt = f"Chat History:\n{history_str}\n\nCurrent Message:\n{task.prompt}"
                                logger.info(f"[{task.id}] Injected context ({len(history_tasks)//2} turns)")

                    # ── Agent workspace routing ────────────────────────────────────
                    # Note: context_prompt is NOT used for the agent path (AgentRunner
                    # uses task.prompt directly and builds its own rolling history).
                    ws_id = task.metadata.get('workspace_id')
                    ag_tid = task.metadata.get('agent_thread_id')

                    model_id = task.metadata.get('selected_model')
                    # Normalize 'auto' → None so provider manager uses its default routing
                    if model_id == 'auto':
                        model_id = None

                    # Parse attached files for images
                    images = []
                    attached_files = task.metadata.get('attached_files')
                    if attached_files:
                        for file_data in attached_files:
                            if file_data.get("is_image"):
                                try:
                                    with open(file_data["path"], "rb") as f:
                                        img_bytes = f.read()
                                    images.append({
                                        "data": img_bytes,
                                        "mime_type": file_data.get("mime_type", "image/jpeg")
                                    })
                                except Exception as e:
                                    logger.error(f"Failed to load attached image '{file_data.get('filename')}': {e}")

                    ws_id = task.metadata.get('workspace_id')
                    if ws_id:
                        # ── Agent workspace task → run full agent loop ─────────────
                        from core.orchestrator.agent_runner import AgentRunner
                        from core.orchestrator.agent_events import create_task_store, push_event, mark_task_done

                        ws_info = None
                        try:
                            from core.interfaces.dashboard.agent_workspace_routes import workspace_manager as _aws_mgr
                            ws_info = _aws_mgr.get_workspace(ws_id)
                        except Exception:
                            pass

                        workspace_path = ws_info['path'] if ws_info else str(Path.home())
                        create_task_store(task.id)

                        def _agent_step_callback(event: dict):
                            push_event(task.id, event)

                        state_path = None
                        if ws_id and ag_tid:
                            state_path = HISTORY_AGENTS / ws_id / "threads" / f"{ag_tid}_state.json"

                        runner = AgentRunner(
                            task=task.prompt,
                            workspace_path=workspace_path,
                            nexus=self.orchestrator.nexus,
                            step_callback=_agent_step_callback,
                            model_id=model_id,
                            trace_id=task.id,
                            state_path=state_path,
                            images=images or None,
                        )
                        summary = await loop.run_in_executor(None, runner.run)
                        mark_task_done(task.id)

                        from core.orchestrator.master_orchestrator import ExecutionResult
                        result = ExecutionResult(
                            trace_id=task.id,
                            response=summary,
                            actions_taken=[],
                            tools_forged=[],
                            agents_spawned=[],
                            memories_queried=0,
                            execution_time=0.0,
                            success=True,
                        )
                    else:
                        # ── Regular chat task → orchestrator ───────────────────────
                        result = await loop.run_in_executor(
                            None,  # Use default executor
                            lambda: self.orchestrator.process_message(
                                context_prompt, mode=mode, trace_id=task.id,
                                model_id=model_id, images=images, source="chat"
                            )
                        )
                    
                    # Convert ExecutionResult to dict
                    result_dict = {
                        'success': result.success,
                        'response': result.response,
                        'actions_taken': result.actions_taken,
                        'tools_forged': result.tools_forged,
                        'agents_spawned': result.agents_spawned,
                        'memories_queried': result.memories_queried,
                        'execution_time': result.execution_time,
                        'error': result.error,
                        'model_id': result.model_id
                    }

                    # Attach usage data (models used, tokens, costs) from usage tracker
                    try:
                        from core.workspace.usage_tracker import get_usage_tracker
                        tracker = get_usage_tracker()
                        usage = tracker.get_usage_by_trace_id(task.id)
                        if usage:
                            result_dict['usage'] = usage
                            # Surface routing fields into task metadata for memory JSON
                            if usage.get('routing_model'):
                                task.metadata['routing_model'] = usage['routing_model']
                            if usage.get('routed_model'):
                                task.metadata['routed_model'] = usage['routed_model']
                            if usage.get('routing_reason'):
                                task.metadata['routing_reason'] = usage['routing_reason']
                            
                            # Surface the actual model ID if it was auto-routed but result.model_id is missing/auto
                            if not result_dict.get('model_id') or result_dict.get('model_id') == 'auto':
                                # Find the last model used if multiple, or the only one
                                if usage.get('models_used'):
                                    last_model = list(usage['models_used'].keys())[-1]
                                    result_dict['model_id'] = last_model
                                    task.metadata['actual_model'] = last_model
                    except Exception as usage_err:
                        logger.debug(f"[{task.id}] Usage tracking for task failed (non-critical): {usage_err}")
                    
                    # Update task with result
                    task.status = TaskStatus.COMPLETED
                    task.result = result_dict

                    # Record actual model used — keep separate from selected_model to avoid duplication
                    if result.model_id:
                        task.metadata['actual_model'] = result.model_id
                    task.completed_at = datetime.now()

                    # ── Save messages to agent thread ──────────────────────────────
                    _ws_id2 = task.metadata.get('workspace_id')
                    _ag_tid2 = task.metadata.get('agent_thread_id')
                    if _ws_id2 and _ag_tid2:
                        try:
                            from core.interfaces.dashboard.agent_workspace_routes import workspace_manager as _agent_ws_mgr2
                            from core.orchestrator.agent_events import get_snapshot
                            _now_iso = datetime.now().isoformat()
                            # Collect agent step events for history
                            _snap = get_snapshot(task.id)
                            _events = _snap["events"] if _snap else []
                            _messages_to_save = [
                                {
                                    "role": "user",
                                    "content": task.prompt,
                                    "timestamp": _now_iso,
                                    "task_id": task.id,
                                },
                                {
                                    "role": "agent_steps",
                                    "events": _events,
                                    "timestamp": _now_iso,
                                },
                                {
                                    "role": "assistant",
                                    "content": result.response or "",
                                    "timestamp": _now_iso,
                                    "actions": result.actions_taken or [],
                                    "model": result.model_id or task.metadata.get('actual_model', ''),
                                },
                            ]
                            _agent_ws_mgr2.append_messages(_ws_id2, _ag_tid2, _messages_to_save)
                        except Exception as _ag_save_err:
                            logger.debug(f"[{task.id}] Agent thread save failed (non-critical): {_ag_save_err}")
                    # ── End save messages to agent thread ──────────────────────────

                    logger.info(
                        f"Worker {self.worker_id} completed task {task.id} "
                        f"in {task.duration:.2f}s"
                    )
                    
                    # Save task state (completed)
                    if self.save_callback:
                        self.save_callback(task)
                    
                except Exception as e:
                    # Task failed
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = datetime.now()
                    
                    logger.error(
                        f"Worker {self.worker_id} failed task {task.id}: {e}"
                    )
                    
                    # Save task state (failed)
                    if self.save_callback:
                        self.save_callback(task)
                
                finally:
                    self.current_task = None
                    self.queue.task_done()
                    
            except asyncio.CancelledError:
                logger.info(f"Worker {self.worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
    
    def stop(self):
        """Stop the worker."""
        self.running = False
        logger.info(f"Worker {self.worker_id} stopping")
    
    def get_status(self) -> Dict:
        """Get worker status."""
        return {
            'worker_id': self.worker_id,
            'running': self.running,
            'current_task': self.current_task.id if self.current_task else None
        }


class TaskQueueManager:
    """
    Manages async task execution with worker pool.
    
    Enables multiple tasks to run in parallel without blocking.
    """
    
    def __init__(self, orchestrator, max_workers: int = 4):
        """
        Initialize task queue manager.
        
        Args:
            orchestrator: MasterOrchestrator instance
            max_workers: Maximum number of parallel workers
        """
        self.orchestrator = orchestrator
        self.max_workers = max_workers
        self.max_workers = max_workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.tasks: Dict[str, Task] = {}
        self.threads: Dict[str, ChatThread] = {}
        self.workers: List[TaskWorker] = []
        self.running = False
        
        # Persistence: data/workspaces/projects
        self.workspaces_dir = WS_PROJECTS
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        
        self._load_threads()
        self._load_tasks()
        
        logger.info(f"Task Queue Manager initialized (max_workers: {max_workers})")
    
    async def start(self):
        """Start the worker pool."""
        if self.running:
            logger.warning("Task Queue Manager already running")
            return
        
        self.running = True
        
        # Create and start workers
        for i in range(self.max_workers):
            worker = TaskWorker(
                worker_id=f"worker-{i}",
                queue=self.queue,
                tasks=self.tasks,
                threads=self.threads,
                orchestrator=self.orchestrator,
                save_callback=self._save_task
            )
            self.workers.append(worker)
            
            # Start worker in background
            asyncio.create_task(worker.run())
        
        logger.info(f"Task Queue Manager started with {self.max_workers} workers")
    
    async def stop(self):
        """Stop all workers."""
        self.running = False
        
        for worker in self.workers:
            worker.stop()
        
        # Wait for queue to be empty
        await self.queue.join()
        
        logger.info("Task Queue Manager stopped")
    
    def create_thread(self, thread_id: str, title: str = None, mode: str = "auto") -> bool:
        """
        Explicitly create a new thread.
        
        Args:
            thread_id: Thread ID
            title: Thread title
            mode: Default mode for tasks
            
        Returns:
            True if created, False if already exists
        """
        if thread_id in self.threads:
            return False
            
        self.threads[thread_id] = ChatThread(
            id=thread_id,
            title=title if title else f"Thread {thread_id}",
            mode=mode,
            created_at=datetime.now()
        )
        self._save_thread(thread_id)
        logger.info(f"Created new thread: {thread_id} ({title})")
        return True

    def update_thread_settings(self, thread_id: str, settings: Dict[str, Any]) -> bool:
        """
        Update settings for a thread.
        
        Args:
            thread_id: Thread ID
            settings: New settings dictionary
            
        Returns:
            True if updated, False if thread not found
        """
        if thread_id not in self.threads:
            return False
            
        # Update settings
        if not hasattr(self.threads[thread_id], 'settings'):
            self.threads[thread_id].settings = {}
            
        self.threads[thread_id].settings.update(settings)
        self.threads[thread_id].updated_at = datetime.now()
        
        self._save_thread(thread_id)
        logger.info(f"Updated settings for thread {thread_id}: {settings}")
        return True

    async def submit_task(self, prompt: str, thread_id: str = "default", thread_title: str = None,
                    model_id: Optional[str] = None, attached_files: Optional[List[Dict[str, Any]]] = None,
                    mode: Optional[str] = None, settings: Optional[Dict[str, Any]] = None,
                    task_type: Optional[str] = None, channel_id: Optional[str] = None,
                    workspace_id: Optional[str] = None, agent_thread_id: Optional[str] = None) -> str:
        """
        Submit a task to the queue.
        
        Args:
            prompt: User prompt/message
            thread_id: Chat thread ID
            thread_title: Optional title for the thread
            model_id: Optional specific model ID to use
            attached_files: Optional list of attached files
            mode: Optional explicit mode (auto/chat_only)
            settings: Optional explicit thread settings (context_mode, etc)
            task_type: Optional specialized task type (e.g. 'DISCORD_SEND')
            channel_id: Optional channel ID for output tasks
            
        Returns:
            Task ID
        """
        # Create task
        task = Task(
            id=generate_trace_id(),
            thread_id=thread_id,
            prompt=prompt,
            status=TaskStatus.QUEUED,
            created_at=datetime.now()
        )
        
        # Store task
        self.tasks[task.id] = task
        
        # Add to thread
        if thread_id not in self.threads:
            self.threads[thread_id] = ChatThread(
                id=thread_id,
                title=thread_title if thread_title else f"Thread {thread_id}",
                created_at=datetime.now()
            )
        else:
            # Update title if provided and meaningful (not just default)
            if thread_title and thread_title != f"Thread {thread_id}":
                 self.threads[thread_id].title = thread_title
        
        if mode:
            self.threads[thread_id].mode = mode
        if settings:
            if not hasattr(self.threads[thread_id], 'settings'):
                self.threads[thread_id].settings = {}
            self.threads[thread_id].settings.update(settings)

        self.threads[thread_id].task_ids.append(task.id)
        self.threads[thread_id].updated_at = datetime.now()
        
        # Propagate thread mode to task metadata (for worker/orchestrator to see)
        task.metadata['mode'] = self.threads[thread_id].mode
        
        # Propagate settings to task metadata for worker logic
        task.metadata['settings'] = self.threads[thread_id].settings
        
        # Store user's model selection (e.g. 'auto', specific model ID, profile string)
        if model_id:
            task.metadata['selected_model'] = model_id
            
        # Store file attachments
        if attached_files:
            task.metadata['attached_files'] = attached_files
        
        if task_type:
            task.metadata['task_type'] = task_type
        if channel_id:
            task.metadata['channel_id'] = channel_id
        if workspace_id:
            task.metadata['workspace_id'] = workspace_id
        if agent_thread_id:
            task.metadata['agent_thread_id'] = agent_thread_id

        # Save thread state
        self._save_thread(thread_id)
        
        # Save task state
        self._save_task(task)
        
        # Add to queue ONLY if it's not a specialized persistent worker task
        if task_type != 'DISCORD_SEND':
            await self.queue.put(task)
            logger.info(f"Task {task.id} submitted to queue (thread: {thread_id}, mode: {task.metadata['mode']}, model: {model_id})")
        else:
            logger.info(f"Task {task.id} (DISCORD_SEND) registered for DiscordWorker polling")
        
        return task.id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self.tasks.get(task_id)
    
    def get_thread(self, thread_id: str) -> Optional[ChatThread]:
        """Get thread by ID."""
        return self.threads.get(thread_id)
    
    def get_thread_tasks(self, thread_id: str) -> List[Task]:
        """Get all tasks for a thread."""
        thread = self.threads.get(thread_id)
        if not thread:
            return []
        
        return [self.tasks[tid] for tid in thread.task_ids if tid in self.tasks]
    
    def get_status(self) -> Dict:
        """Get queue manager status."""
        queued = sum(1 for t in self.tasks.values() if t.status == TaskStatus.QUEUED)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        
        return {
            'running': self.running,
            'workers': {
                'total': len(self.workers),
                'active': sum(1 for w in self.workers if w.current_task is not None),
                'status': [w.get_status() for w in self.workers]
            },
            'tasks': {
                'total': len(self.tasks),
                'queued': queued,
                'running': running,
                'completed': completed,
                'failed': failed
            },
            'threads': {
                'total': len(self.threads),
                'active': sum(1 for t in self.threads.values() if any(
                    self.tasks[tid].status in [TaskStatus.QUEUED, TaskStatus.RUNNING]
                    for tid in t.task_ids if tid in self.tasks
                ))
            },
            'queue_size': self.queue.qsize()
        }
                
    def delete_thread(self, thread_id: str) -> bool:
        """
        Delete a thread, its persistence file, AND all associated tasks.
        
        Args:
            thread_id: Thread ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        if thread_id not in self.threads:
            return False
            
        # Get thread to find tasks
        thread = self.threads[thread_id]
        task_ids = thread.task_ids.copy()
        
        # Mark as deleted in memory (optional, but good for safety)
        thread.is_deleted = True
        
        # Remove from memory
        del self.threads[thread_id]
        
        # Delete the entire thread workspace folder
        thread_dir = self.workspaces_dir / thread_id
        if thread_dir.exists():
            import shutil
            try:
                shutil.rmtree(thread_dir)
                logger.info(f"Deleted thread workspace: {thread_dir}")
            except Exception as e:
                logger.error(f"Failed to delete thread workspace {thread_dir}: {e}")
                
        return True

    def set_thread_mode(self, thread_id: str, mode: str) -> bool:
        """
        Set thread mode (auto/chat_only).
        
        Args:
            thread_id: Thread ID
            mode: New mode
            
        Returns:
            True if updated
        """
        if thread_id not in self.threads:
            return False
            
        if mode not in ["auto", "chat_only"]:
            return False
            
        self.threads[thread_id].mode = mode
        self.threads[thread_id].updated_at = datetime.now()
        self._save_thread(thread_id)
        
        logger.info(f"Set thread {thread_id} mode to {mode}")
        return True

    def set_thread_title(self, thread_id: str, title: str) -> bool:
        """
        Update the title of an existing thread.
        
        Args:
            thread_id: Thread ID
            title: New title string
            
        Returns:
            True if updated, False if thread not found or title invalid
        """
        if thread_id not in self.threads:
            return False
            
        if not title or not isinstance(title, str):
            return False
            
        self.threads[thread_id].title = title.strip()
        self.threads[thread_id].updated_at = datetime.now()
        self._save_thread(thread_id)
        
        logger.info(f"Updated thread {thread_id} title to: {title}")
        return True

    def _load_threads(self):
        """Load threads from disk."""
        try:
            count = 0
            if self.workspaces_dir.exists():
                for thread_dir in self.workspaces_dir.iterdir():
                    if thread_dir.is_dir():
                        file_path = thread_dir / f"{thread_dir.name}.json"
                        if file_path.exists():
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    data = json.load(f)
                                    
                                # Reconstruct ChatThread
                                thread = ChatThread(
                                    id=data['id'],
                                    title=data.get('title', 'Untitled'),
                                    created_at=datetime.fromisoformat(data['created_at']),
                                    updated_at=datetime.fromisoformat(data['updated_at']),
                                    task_ids=data.get('task_ids', []),
                                    metadata=data.get('metadata', {}),
                                    mode=data.get('mode', 'auto'),
                                    settings=data.get('settings', {"context_mode": "none", "context_window": 5}),
                                    is_deleted=data.get('is_deleted', False),
                                    is_pinned=data.get('is_pinned', False)
                                )
                                
                                if not thread.is_deleted:
                                    self.threads[thread.id] = thread
                                    count += 1
                                    
                            except Exception as e:
                                logger.error(f"Failed to load thread from {file_path}: {e}")
            
            logger.info(f"Loaded {count} threads from disk")
            
        except Exception as e:
            logger.error(f"Error loading threads: {e}")

    def _save_thread(self, thread_id: str):
        """Save thread state to disk."""
        if thread_id not in self.threads:
            return
            
        try:
            thread = self.threads[thread_id]
            
            # Create thread-specific workspace directory
            thread_dir = self.workspaces_dir / thread.id
            thread_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = thread_dir / f"{thread.id}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                # Use to_dict() which now sanitizes data
                json.dump(thread.to_dict(), f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save thread {thread_id}: {e}", exc_info=True)
            # Try to save a backup/sanitized version if possible?
            # For now, just logging the full stack trace is a huge improvement over silent failure

    def _save_task(self, task: Task):
        """Save task state to disk."""
        try:
            # Task goes into its thread's workspace/tasks/ directory
            thread_dir = self.workspaces_dir / task.thread_id
            tasks_dir = thread_dir / "tasks"
            tasks_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = tasks_dir / f"{task.id}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                # Use to_dict() which now sanitizes data
                json.dump(task.to_dict(), f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save task {task.id}: {e}", exc_info=True)

    def _load_tasks(self):
        """Load tasks from disk."""
        try:
            count = 0
            if self.workspaces_dir.exists():
                for thread_dir in self.workspaces_dir.iterdir():
                    if thread_dir.is_dir():
                        tasks_dir = thread_dir / "tasks"
                        if tasks_dir.exists():
                            for file_path in tasks_dir.glob("*.json"):
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        data = json.load(f)
                                    
                                    # Basic reconstruction
                                    task = Task(
                                        id=data['id'],
                                        thread_id=data['thread_id'],
                                        prompt=data['prompt'],
                                        status=TaskStatus(data['status']),
                                        created_at=datetime.fromisoformat(data['created_at']),
                                        started_at=datetime.fromisoformat(data['started_at']) if data.get('started_at') else None,
                                        completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
                                        error=data.get('error'),
                                        result=data.get('result'),
                                        metadata=data.get('metadata', {}),
                                        worker_id=data.get('worker_id')
                                    )
                                    
                                    self.tasks[task.id] = task
                                    count += 1
                                        
                                except Exception as e:
                                    logger.error(f"Failed to load task from {file_path}: {e}")
            
            logger.info(f"Loaded {count} tasks from disk")
            
        except Exception as e:
            logger.error(f"Error loading tasks: {e}")


# Singleton instance
_task_queue_manager = None

# Set of task IDs that have been requested to stop.
# AgentRunner checks this each iteration — no threading primitives needed because
# the runner runs in a thread executor and reads are safe across threads.
_cancelled_agent_task_ids: set = set()


def cancel_agent_task(task_id: str) -> None:
    """Signal the agent runner for this task to exit after its current iteration."""
    _cancelled_agent_task_ids.add(task_id)


def is_agent_task_cancelled(task_id: str) -> bool:
    return task_id in _cancelled_agent_task_ids


def get_task_queue_manager(orchestrator=None, max_workers: int = 4) -> TaskQueueManager:
    """Get the singleton TaskQueueManager instance."""
    global _task_queue_manager
    if _task_queue_manager is None:
        if orchestrator is None:
            raise ValueError("Orchestrator required for first initialization")
        _task_queue_manager = TaskQueueManager(orchestrator, max_workers)
    return _task_queue_manager
