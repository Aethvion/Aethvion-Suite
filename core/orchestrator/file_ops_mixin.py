"""
core/orchestrator/file_ops_mixin.py
════════════════════════════════════
FileOpsMixin — all file, directory, and shell operation methods
for the Code agent runner. Mixed into AgentRunner via multiple inheritance.

These methods access self.workspace, self.state, and self._emit — all
provided by AgentRunner.__init__.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.utils import get_logger, utcnow_iso

logger = get_logger(__name__)


class FileOpsMixin:
    """Mixin providing file, directory, and shell operation methods.

    Requires the host class (AgentRunner) to provide:
        self.workspace: Path
        self.state:     AgentState
        self._emit:     Callable[[dict], None]
        self._unresolved_failures: set
        self._action_repeats:      dict
        self._BLOCKED_COMMAND_PATTERNS: list
    """

    def _patch_file(self, path: str, old: str, new: str) -> str:
        """Replace first occurrence of `old` with `new`, with whitespace-tolerant fallbacks.

        Three strategies are tried in order, most to least strict:
          1. Exact match — fastest, always preferred.
          2. Trailing-whitespace normalised — handles lines where the LLM strips
             trailing spaces/tabs that are present in the file (very common).
          3. Full strip (leading + trailing) — handles indentation differences
             while still preserving the file's own indentation for the replaced block.

        On success, the file is written and a summary is returned.  Only if all
        three strategies fail is ``patch_file FAILED`` returned.
        """
        try:
            fp, err = self._safe_path(path)
            if err:
                return err
            if not fp.exists():
                return f"Error: {path} does not exist — use write_file to create it first."
            if not old:
                return "Error: patch_file requires a non-empty 'old' string."
            content = fp.read_text(encoding="utf-8", errors="replace")

            # Strategy 1: exact match
            if old in content:
                count = content.count(old)
                updated = content.replace(old, new, 1)
                fp.write_text(updated, encoding="utf-8")
                suffix = f" ({count} occurrences, replaced first)" if count > 1 else ""
                msg = f"Patched {path}: {len(old):,}→{len(new):,} chars.{suffix}"
                syntax_err = self._validate_file_syntax(path)
                if syntax_err:
                    msg += f"\n\n[WARNING] Syntax validation failed:\n{syntax_err}"
                return msg

            # Strategy 2: strip trailing whitespace per line
            # Covers the very common case where the LLM omits trailing spaces
            # that exist in the actual file (e.g. in Python docstrings, HTML).
            def _rstrip_lines(s: str) -> str:
                return "\n".join(line.rstrip() for line in s.splitlines())

            norm_content = _rstrip_lines(content)
            norm_old     = _rstrip_lines(old)
            if norm_old and norm_old in norm_content:
                idx        = norm_content.index(norm_old)
                line_start = norm_content[:idx].count("\n")
                line_count = norm_old.count("\n") + 1
                orig_lines = content.splitlines(keepends=True)
                orig_block = "".join(orig_lines[line_start : line_start + line_count])
                updated    = content.replace(orig_block, new, 1)
                if updated != content:
                    fp.write_text(updated, encoding="utf-8")
                    msg = (
                        f"Patched {path} (trailing-ws normalized): "
                        f"{len(orig_block):,}→{len(new):,} chars."
                    )
                    syntax_err = self._validate_file_syntax(path)
                    if syntax_err:
                        msg += f"\n\n[WARNING] Syntax validation failed:\n{syntax_err}"
                    return msg

            # Strategy 3: strip all whitespace per line (indentation-agnostic)
            # or vice-versa.  The original file's indentation is preserved — only
            # the content of those lines is replaced.
            def _strip_lines(s: str) -> str:
                return "\n".join(line.strip() for line in s.splitlines())

            stripped_content = _strip_lines(content)
            stripped_old     = _strip_lines(old)
            if stripped_old and stripped_old in stripped_content:
                idx        = stripped_content.index(stripped_old)
                line_start = stripped_content[:idx].count("\n")
                line_count = stripped_old.count("\n") + 1
                orig_lines = content.splitlines(keepends=True)
                orig_block = "".join(orig_lines[line_start : line_start + line_count])
                updated    = content.replace(orig_block, new, 1)
                if updated != content:
                    fp.write_text(updated, encoding="utf-8")
                    msg = (
                        f"Patched {path} (whitespace-normalized): "
                        f"{len(orig_block):,}→{len(new):,} chars."
                    )
                    syntax_err = self._validate_file_syntax(path)
                    if syntax_err:
                        msg += f"\n\n[WARNING] Syntax validation failed:\n{syntax_err}"
                    return msg

            return (
                f"patch_file FAILED: 'old' string not found in {path} "
                f"(tried exact, trailing-ws, and indentation-agnostic matching). "
                f"Use read_file to get the exact current contents, then retry."
            )
        except Exception as e:
            return f"Error: {e}"

    def _validate_file_syntax(self, path: str) -> Optional[str]:
        """Validate syntax of Python and JSON files.
        Returns a string error description if invalid, or None if valid or non-applicable.
        """
        try:
            fp, err = self._safe_path(path)
            if err or not fp or not fp.exists():
                return None

            content = fp.read_text(encoding="utf-8", errors="replace")

            if path.endswith(".py"):
                try:
                    compile(content, path, "exec")
                except SyntaxError as se:
                    text_line = f"\nCode: {se.text.strip()}" if se.text else ""
                    return f"Python SyntaxError: {se.msg} at line {se.lineno}, column {se.offset}{text_line}"
                except Exception as e:
                    return f"Python Compilation Error: {e}"
            elif path.endswith(".json"):
                try:
                    json.loads(content)
                except json.JSONDecodeError as jde:
                    return f"JSON SyntaxError: {jde.msg} at line {jde.lineno}, column {jde.colno}"
                except Exception as e:
                    return f"JSON Parse Error: {e}"
        except Exception as e:
            return f"Syntax check failed: {e}"
        return None

    # Path safety helper

    def _safe_path(self, path: str) -> "tuple[Path | None, str | None]":
        """Resolve *path* relative to workspace and block directory traversal.

        Returns ``(resolved_path, None)`` on success, or ``(None, error_message)``
        when the resolved path escapes the workspace root.
        """
        try:
            resolved = (self.workspace / path).resolve()
            ws_root  = self.workspace.resolve()
            # str comparison is safe because resolve() returns absolute paths
            if not str(resolved).startswith(str(ws_root) + os.sep) and resolved != ws_root:
                return None, (
                    f"Security: path {path!r} resolves outside the workspace. "
                    "Use relative paths that stay within the workspace directory."
                )
            return resolved, None
        except Exception as e:
            return None, f"Invalid path {path!r}: {e}"

    def _write_file(self, path: str, content: str) -> str:
        try:
            fp, err = self._safe_path(path)
            if err:
                return err
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            msg = f"Written {len(content.encode()):,} bytes"
            syntax_err = self._validate_file_syntax(path)
            if syntax_err:
                msg += f"\n\n[WARNING] Syntax validation failed:\n{syntax_err}"
            return msg
        except Exception as e:
            return f"Error: {e}"

    def _append_file(self, path: str, content: str) -> str:
        """Append `content` to the end of a file (creates it if it doesn't exist)."""
        try:
            fp, err = self._safe_path(path)
            if err:
                return err
            fp.parent.mkdir(parents=True, exist_ok=True)
            with open(fp, "a", encoding="utf-8") as f:
                if fp.stat().st_size > 0:
                    f.write("\n")
                f.write(content)
            msg = f"Appended {len(content.encode()):,} bytes to {path}"
            syntax_err = self._validate_file_syntax(path)
            if syntax_err:
                msg += f"\n\n[WARNING] Syntax validation failed:\n{syntax_err}"
            return msg
        except Exception as e:
            return f"Error: {e}"

    def _delete_file(self, path: str) -> str:
        try:
            fp, err = self._safe_path(path)
            if err:
                return err
            if not fp.exists():
                return f"Not found: {path}"
            if fp.is_dir():
                import shutil
                shutil.rmtree(fp)
                return f"Deleted directory {path}"
            fp.unlink()
            return f"Deleted {path}"
        except Exception as e:
            return f"Error: {e}"

    def _read_file(self, path: str, offset: int = 0, limit: Optional[int] = None) -> str:
        """Read a file, optionally starting at line `offset` and capping at `limit` lines.

        The per-chunk char cap is 50,000 — large enough to read most source files in
        a single call.  If a chunk is still truncated, the response says exactly what
        offset to use next so the agent can continue without shell-command workarounds.
        """
        MAX_CHARS = 50_000
        try:
            fp, err = self._safe_path(path)
            if err:
                return err
            if not fp.exists():
                return f"Not found: {path}"
            content = fp.read_text(encoding="utf-8", errors="replace")
            lines   = content.splitlines(keepends=True)
            total   = len(lines)

            # Apply line-based offset / limit
            if offset:
                lines = lines[offset:]
            if limit is not None:
                lines = lines[:limit]

            chunk = "".join(lines)

            if len(chunk) <= MAX_CHARS:
                # Entire requested slice fits — include a summary footer so the agent
                # knows whether it has the whole file or just a slice.
                end_line = offset + len(lines)
                if end_line < total:
                    return (
                        chunk
                        + f"\n\n[File: {total} total lines. Showing lines {offset}–{end_line}. "
                        f"To read more use: ACTION: {{\"type\": \"read_file\", \"path\": \"{path}\", \"offset\": {end_line}}}]"
                    )
                return chunk  # whole file (or final slice) — no footer needed

            trimmed = chunk[:MAX_CHARS]
            lines_returned = trimmed.count("\n")
            next_offset = offset + lines_returned
            return (
                trimmed
                + f"\n\n[TRUNCATED at {MAX_CHARS:,} chars. "
                f"File has {total} lines. Next offset: {next_offset}. "
                f"Continue with: ACTION: {{\"type\": \"read_file\", \"path\": \"{path}\", \"offset\": {next_offset}}}]"
            )
        except Exception as e:
            return f"Error: {e}"

    def _list_dir(self, path: str) -> str:
        try:
            if path:
                target, err = self._safe_path(path)
                if err:
                    return err
            else:
                target = self.workspace
            if not target.exists():
                return f"Not found: {path}"
            entries = [
                ("\U0001f4c1 " if e.is_dir() else "\U0001f4c4 ") + e.name
                for e in sorted(target.iterdir())
                if e.name != ".aethvion_backup"
            ]
            return "\n".join(entries) if entries else "(empty)"
        except Exception as e:
            return f"Error: {e}"

    def _glob(self, pattern: str, sub_path: str = "") -> str:
        """Find files matching a glob pattern. Returns workspace-relative paths."""
        try:
            if sub_path:
                root, err = self._safe_path(sub_path)
                if err:
                    return f"Error: {err}"
            else:
                root = self.workspace
            if not root.exists():
                return f"Error: path '{sub_path}' not found."
            matches = sorted(root.glob(pattern))
            if not matches:
                return f"No files matching '{pattern}'"
            rel = [
                str(m.relative_to(self.workspace)).replace("\\", "/")
                for m in matches
                if not m.name.endswith("_blueprint.txt")
                and ".aethvion_backup" not in m.parts
            ]
            total = len(rel)
            if total > 200:
                rel = rel[:200]
                rel.append(f"... {total} total — showing first 200")
            return "\n".join(rel)
        except Exception as e:
            return f"Error: {e}"

    def _move_file(self, src: str, dst: str) -> str:
        """Move or rename a file/directory within the workspace."""
        import shutil
        try:
            if not src or not dst:
                return "Error: move_file requires non-empty 'src' and 'dst'."
            src_fp, err = self._safe_path(src)
            if err:
                return err
            dst_fp, err = self._safe_path(dst)
            if err:
                return err
            if not src_fp.exists():
                return f"Error: {src} not found."
            dst_fp.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_fp), str(dst_fp))
            # Transfer state caches from old path to new path
            self.state.file_cache.pop(src, None)
            if src in self.state.workspace_map:
                self.state.workspace_map.remove(src)
                self.state.workspace_map.append(dst)
            if src in self.state.file_digests:
                self.state.file_digests[dst] = self.state.file_digests.pop(src)
            return f"Moved {src} → {dst}"
        except Exception as e:
            return f"Error: {e}"

    def _create_directory(self, path: str) -> str:
        """Create a directory (and all parents) within the workspace."""
        try:
            if not path:
                return "Error: create_directory requires a non-empty 'path'."
            dp, err = self._safe_path(path)
            if err:
                return err
            dp.mkdir(parents=True, exist_ok=True)
            return f"Created directory: {path}"
        except Exception as e:
            return f"Error: {e}"

    def _compute_write_diff(self, path: str, new_content: str) -> str:
        """Compute a unified diff of the existing file vs new_content.
        Returns an empty string if the file doesn't exist (new file) or is identical."""
        import difflib
        try:
            fp = self.workspace / path
            if not fp.exists():
                return ""
            old = fp.read_text(encoding="utf-8", errors="replace")
            if old == new_content:
                return ""
            diff = list(difflib.unified_diff(
                old.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3,
            ))
            result = "".join(diff)
            if len(result) > 3000:
                result = result[:2800] + "\n...[diff truncated]"
            return result
        except Exception:
            return ""


    def _backup_file(self, path: str) -> bool:
        """Copy the current file to .aethvion_backup/<path> before overwriting.

        Returns True if a backup was saved, False if the file didn't exist
        (nothing to back up — new file creation).
        """
        try:
            import shutil
            fp = self.workspace / path
            if not fp.exists() or not fp.is_file():
                return False
            bak = self.workspace / ".aethvion_backup" / path
            bak.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(fp), str(bak))
            return True
        except Exception:
            return False

    def _restore_file(self, path: str) -> str:
        """Restore a file from .aethvion_backup/<path>."""
        try:
            import shutil
            bak = self.workspace / ".aethvion_backup" / path
            if not bak.exists():
                return f"No backup found for {path}"
            fp = self.workspace / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(bak), str(fp))
            return f"Restored {path} from backup"
        except Exception as e:
            return f"Error: {e}"


    def _run_command(self, command: str, timeout: int = 120) -> str:
        """Run a shell command, streaming output line-by-line via run_command_line events."""
        import re
        import time

        # Safety guard: block catastrophically destructive patterns
        for pattern in self._BLOCKED_COMMAND_PATTERNS:
            if re.search(pattern, command):
                logger.warning(
                    "[AgentRunner] Blocked destructive command (pattern=%r): %r",
                    pattern, command[:200],
                )
                return (
                    "Error: command blocked — matches a destructive pattern that is "
                    "never permitted within the workspace. Revise your approach."
                )

        logger.info("[AgentRunner] run_command (workspace=%s): %s", self.workspace.name, command[:200])

        try:
            proc = subprocess.Popen(
                command, shell=True, cwd=str(self.workspace),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )

            output_lines: list[str] = []
            line_q: queue.Queue = queue.Queue()

            def _reader():
                try:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        line_q.put(line)
                except Exception:
                    pass
                finally:
                    line_q.put(None)  # sentinel

            reader = threading.Thread(target=_reader, daemon=True)
            reader.start()

            start = time.time()
            timed_out = False

            while True:
                try:
                    line = line_q.get(timeout=0.15)
                except queue.Empty:
                    if time.time() - start > timeout:
                        proc.kill()
                        timed_out = True
                        break
                    continue

                if line is None:
                    break  # reader finished
                output_lines.append(line)
                self._emit({"type": "run_command_line", "line": line.rstrip("\n")})

                if time.time() - start > timeout:
                    proc.kill()
                    timed_out = True
                    break

            reader.join(timeout=3)
            try:
                proc.wait(timeout=5)
            except Exception:
                pass

            if timed_out:
                output_lines.append(f"\n(timeout: {timeout}s — process killed)\n")

            out = "".join(output_lines).strip()
            # Rolling tail cap so errors at the end are never truncated
            if len(out) > 5000:
                out = out[:2000] + f"\n...[{len(out):,} chars — middle truncated]...\n" + out[-2500:]

            rc = proc.returncode if proc.returncode is not None else (124 if timed_out else 0)
            if rc != 0:
                return f"(exit {rc})\n{out}" if out else f"(exit {rc})"
            return out or "(exit 0)"

        except Exception as e:
            return f"Error: {e}"

    # event builder
