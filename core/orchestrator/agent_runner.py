"""Agent Runner — multi-step ReAct-style execution loop."""
import re
import json
import subprocess
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

from core.utils.logger import get_logger

logger = get_logger(__name__)

MAX_ITERATIONS = 20

SYSTEM_PROMPT = """\
You are an expert AI software agent. You execute tasks step by step by taking real actions.

Working directory: {workspace}

## HOW TO TAKE ACTIONS

Output JSON action blocks using triple backticks labeled "action":

Write or create a file (use full content — no placeholders):
```action
{{"type": "write_file", "path": "relative/path.html", "content": "full content here"}}
```

Read a file:
```action
{{"type": "read_file", "path": "relative/path"}}
```

List directory:
```action
{{"type": "list_dir", "path": ""}}
```

Run a shell command:
```action
{{"type": "run_command", "command": "npm install"}}
```

Mark the task as fully complete:
```action
{{"type": "done", "summary": "What was accomplished"}}
```

## RULES

1. Create REAL, COMPLETE files — not stubs. Full HTML, CSS, JS, etc.
2. After each action you will see its result. Use that to decide next steps.
3. Paths are relative to the working directory.
4. Keep going until the task is genuinely finished. Only use `done` when everything is complete.
5. You have up to {max_iterations} actions.
"""


class AgentRunner:
    def __init__(
        self,
        task: str,
        workspace_path: str,
        nexus,
        step_callback: Callable[[Dict[str, Any]], None],
        model_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ):
        self.task = task
        self.workspace = Path(workspace_path) if workspace_path else Path.cwd()
        self.nexus = nexus
        self.step_callback = step_callback
        self.model_id = model_id
        self.trace_id = trace_id
        self.conversation: List[str] = []

    # ── emit ──────────────────────────────────────────────────────
    def _emit(self, event: Dict[str, Any]) -> None:
        self.step_callback(event)

    # ── LLM call ──────────────────────────────────────────────────
    def _build_prompt(self) -> str:
        system = SYSTEM_PROMPT.format(workspace=str(self.workspace), max_iterations=MAX_ITERATIONS)
        parts = [system, "\n---\n", f"USER TASK:\n{self.task}\n"]
        parts.extend(self.conversation)
        parts.append("\nAGENT:")
        return "\n".join(parts)

    def _call_llm(self) -> str:
        from core.nexus_core import Request
        try:
            req = Request(
                prompt=self._build_prompt(),
                request_type="generation",
                temperature=0.2,
                max_tokens=4096,
                trace_id=self.trace_id,
                model=self.model_id,
            )
            resp = self.nexus.route_request(req)
            return resp.content if resp.success else f"(LLM error: {resp.error})"
        except Exception as e:
            logger.error(f"AgentRunner LLM call failed: {e}")
            return f"(Error calling LLM: {e})"

    # ── parsing ───────────────────────────────────────────────────
    def _parse_actions(self, text: str) -> List[Dict[str, Any]]:
        pattern = r"```action\s*\n(.*?)\n```"
        actions = []
        for m in re.findall(pattern, text, re.DOTALL):
            try:
                actions.append(json.loads(m.strip()))
            except json.JSONDecodeError:
                pass
        return actions

    def _thinking_text(self, text: str) -> str:
        idx = text.find("```action")
        return text[:idx].strip() if idx != -1 else text.strip()

    # ── tool execution ────────────────────────────────────────────
    def _execute(self, action: Dict[str, Any]) -> str:
        t = action.get("type", "")
        if t == "write_file":
            return self._write_file(action.get("path", ""), action.get("content", ""))
        if t == "read_file":
            return self._read_file(action.get("path", ""))
        if t == "list_dir":
            return self._list_dir(action.get("path", ""))
        if t == "run_command":
            return self._run_command(action.get("command", ""))
        return f"Unknown action: {t}"

    def _write_file(self, path: str, content: str) -> str:
        try:
            fp = self.workspace / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            return f"✓ Written {len(content.encode()):,} bytes"
        except Exception as e:
            return f"Error: {e}"

    def _read_file(self, path: str) -> str:
        try:
            fp = self.workspace / path
            if not fp.exists():
                return f"Not found: {path}"
            content = fp.read_text(encoding="utf-8", errors="replace")
            if len(content) > 6000:
                return content[:6000] + f"\n...(truncated, {len(content):,} total chars)"
            return content
        except Exception as e:
            return f"Error: {e}"

    def _list_dir(self, path: str) -> str:
        try:
            target = self.workspace / path if path else self.workspace
            if not target.exists():
                return f"Not found: {path}"
            entries = [
                ("\U0001f4c1 " if e.is_dir() else "\U0001f4c4 ") + e.name
                for e in sorted(target.iterdir())
            ]
            return "\n".join(entries) if entries else "(empty)"
        except Exception as e:
            return f"Error: {e}"

    def _run_command(self, command: str) -> str:
        try:
            res = subprocess.run(
                command, shell=True, cwd=str(self.workspace),
                capture_output=True, text=True, timeout=60,
            )
            out = ((res.stdout or "") + (res.stderr or "")).strip()
            if len(out) > 3000:
                out = out[:3000] + "\n...(truncated)"
            return out or f"(exit {res.returncode})"
        except subprocess.TimeoutExpired:
            return "Timed out (60s)"
        except Exception as e:
            return f"Error: {e}"

    # ── event builder ─────────────────────────────────────────────
    def _make_event(self, action: Dict[str, Any]) -> Dict[str, Any]:
        t = action.get("type", "")
        path = action.get("path", "")
        cmd = action.get("command", "")
        content = action.get("content", "")
        if t == "write_file":
            preview = content[:400] + ("\u2026" if len(content) > 400 else "")
            return {"type": t, "title": f"Writing {path}", "path": path,
                    "detail": preview, "bytes": len(content.encode())}
        if t == "read_file":
            return {"type": t, "title": f"Reading {path}", "path": path, "detail": ""}
        if t == "list_dir":
            return {"type": t, "title": f"Listing {path or 'workspace'}", "path": path, "detail": ""}
        if t == "run_command":
            return {"type": t, "title": f"$ {cmd[:80]}", "command": cmd, "detail": ""}
        return {"type": t, "title": t, "detail": ""}

    # ── main loop ─────────────────────────────────────────────────
    def run(self) -> str:
        self._emit({"type": "start", "title": "Starting task", "detail": self.task})

        for iteration in range(MAX_ITERATIONS):
            response = self._call_llm()

            # Emit thinking text before first action
            thinking = self._thinking_text(response)
            if thinking:
                self._emit({"type": "thinking", "title": "Planning" if iteration == 0 else "Continuing", "detail": thinking})

            actions = self._parse_actions(response)

            if not actions:
                # No actions — treat response as final answer
                self._emit({"type": "done", "title": "Complete", "detail": thinking or response})
                return thinking or response

            self.conversation.append(f"\nAGENT:\n{response}")

            results = []
            done_triggered = False
            done_summary = ""

            for action in actions:
                if action.get("type") == "done":
                    done_summary = action.get("summary", "Task complete.")
                    done_triggered = True
                    break

                event = self._make_event(action)
                result = self._execute(action)
                event["result"] = result
                self._emit(event)
                results.append(f"<result>{result}</result>")

            if done_triggered:
                self._emit({"type": "done", "title": "Complete", "detail": done_summary})
                return done_summary

            self.conversation.append(
                "\nRESULTS:\n" + "\n".join(results) +
                "\n\nContinue. When the task is fully done, use the `done` action."
            )

        summary = f"Reached {MAX_ITERATIONS} action limit."
        self._emit({"type": "done", "title": "Stopped (limit)", "detail": summary})
        return summary
