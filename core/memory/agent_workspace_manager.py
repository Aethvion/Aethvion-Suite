"""Agent Workspace Manager - Manages workspaces and threads for the Agents tab."""
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from core.utils.logger import get_logger
from core.utils import utcnow_iso

logger = get_logger(__name__)


class AgentWorkspaceManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # --- Internal helpers ---
    def _ws_dir(self, workspace_id: str) -> Path:
        return self.base_dir / workspace_id

    def _ws_file(self, workspace_id: str) -> Path:
        return self._ws_dir(workspace_id) / "workspace.json"

    def _threads_dir(self, workspace_id: str) -> Path:
        return self._ws_dir(workspace_id) / "threads"

    def _thread_file(self, workspace_id: str, thread_id: str) -> Path:
        return self._threads_dir(workspace_id) / f"{thread_id}.json"

    def _touch_workspace(self, workspace_id: str):
        ws = self.get_workspace(workspace_id)
        if ws:
            ws["last_active"] = utcnow_iso()
            self._ws_file(workspace_id).write_text(json.dumps(ws, indent=2))

    # --- Workspace CRUD ---
    def list_workspaces(self) -> list:
        result = []
        if not self.base_dir.exists():
            return result
        for ws_dir in self.base_dir.iterdir():
            if ws_dir.is_dir():
                f = ws_dir / "workspace.json"
                if f.exists():
                    try:
                        result.append(json.loads(f.read_text()))
                    except Exception as e:
                        logger.error(f"Failed to read workspace {ws_dir.name}: {e}")
        return sorted(result, key=lambda w: w.get("last_active", ""), reverse=True)

    def create_workspace(self, path: str, name: str = None, workspace_id: str = None) -> dict:
        workspace_id = workspace_id or str(uuid.uuid4())
        name = name or Path(path).name or path
        now = utcnow_iso()
        self._ws_dir(workspace_id).mkdir(parents=True, exist_ok=True)
        self._threads_dir(workspace_id).mkdir(exist_ok=True)
        (self._ws_dir(workspace_id) / "uploads").mkdir(exist_ok=True)
        workspace = {
            "id": workspace_id,
            "name": name,
            "path": path,
            "created_at": now,
            "last_active": now,
        }
        self._ws_file(workspace_id).write_text(json.dumps(workspace, indent=2))
        return workspace

    def get_workspace(self, workspace_id: str) -> Optional[dict]:
        f = self._ws_file(workspace_id)
        return json.loads(f.read_text()) if f.exists() else None

    def update_workspace(self, workspace_id: str, name: str = None, path: str = None) -> Optional[dict]:
        ws = self.get_workspace(workspace_id)
        if not ws:
            return None
        if name is not None:
            ws["name"] = name
        if path is not None:
            ws["path"] = path
        ws["last_active"] = utcnow_iso()
        self._ws_file(workspace_id).write_text(json.dumps(ws, indent=2))
        return ws

    def delete_workspace(self, workspace_id: str) -> bool:
        ws_dir = self._ws_dir(workspace_id)
        if not ws_dir.exists():
            return False
        shutil.rmtree(ws_dir)
        return True

    # --- Thread CRUD ---
    def list_threads(self, workspace_id: str) -> list:
        d = self._threads_dir(workspace_id)
        if not d.exists():
            return []
        result = []
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                result.append({
                    "id": data["id"],
                    "workspace_id": data["workspace_id"],
                    "name": data.get("name", "Thread"),
                    "created_at": data.get("created_at"),
                    "last_active": data.get("last_active"),
                    "message_count": len(data.get("messages", [])),
                })
            except Exception as e:
                logger.error(f"Failed to read thread {f.name}: {e}")
        return sorted(result, key=lambda t: t.get("last_active", ""), reverse=True)

    def create_thread(self, workspace_id: str, name: str = None) -> Optional[dict]:
        if not self.get_workspace(workspace_id):
            return None
        thread_id = str(uuid.uuid4())
        now = utcnow_iso()
        if not name:
            count = len(self.list_threads(workspace_id))
            name = datetime.now().strftime("%B %d, %Y")
            if count > 0:
                name = f"{name} #{count + 1}"
        thread = {
            "id": thread_id,
            "workspace_id": workspace_id,
            "name": name,
            "created_at": now,
            "last_active": now,
            "messages": [],
        }
        self._thread_file(workspace_id, thread_id).write_text(json.dumps(thread, indent=2))
        self._touch_workspace(workspace_id)
        return {k: v for k, v in thread.items() if k != "messages"}

    def get_thread(self, workspace_id: str, thread_id: str) -> Optional[dict]:
        f = self._thread_file(workspace_id, thread_id)
        return json.loads(f.read_text()) if f.exists() else None

    def delete_thread(self, workspace_id: str, thread_id: str) -> bool:
        f = self._thread_file(workspace_id, thread_id)
        if not f.exists():
            return False
        f.unlink()
        return True

    def rename_thread(self, workspace_id: str, thread_id: str, name: str) -> bool:
        thread = self.get_thread(workspace_id, thread_id)
        if not thread:
            return False
        thread["name"] = name
        self._thread_file(workspace_id, thread_id).write_text(json.dumps(thread, indent=2))
        return True

    def append_messages(self, workspace_id: str, thread_id: str, messages: list) -> bool:
        thread = self.get_thread(workspace_id, thread_id)
        if not thread:
            return False
        thread["messages"].extend(messages)
        thread["last_active"] = utcnow_iso()
        self._thread_file(workspace_id, thread_id).write_text(json.dumps(thread, indent=2))
        self._touch_workspace(workspace_id)
        return True

    def get_thread_history(self, workspace_id: str, thread_id: str, limit: int = 20) -> list:
        thread = self.get_thread(workspace_id, thread_id)
        if not thread:
            return []
        messages = thread.get("messages", [])
        return messages[-limit:] if limit > 0 else messages
