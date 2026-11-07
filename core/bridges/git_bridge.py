"""
core/bridges/git_bridge.py
Git & Project Workspace Inspector Connector.
Allows companions and users (/git) to inspect current branch, modified files,
recent commits, and uncommitted code diffs for co-working and code review.
"""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _resolve_repo_path(args: dict) -> Path:
    raw = str(
        args.get("repo_path")
        or args.get("path")
        or args.get("settings", {}).get("default_repo_path")
        or ""
    ).strip()
    if raw:
        p = Path(raw).expanduser()
        if p.exists() and p.is_dir():
            return p
    return PROJECT_ROOT


def _run_git(cwd: Path, git_args: list[str]) -> str:
    try:
        res = subprocess.run(
            ["git", *git_args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        if res.returncode != 0 and not out:
            return f"Git Error: {err or f'exit code {res.returncode}'}"
        return out
    except Exception as e:
        return f"Git Error: {e}"


def get_status(args: dict = None) -> str:
    """Return active Git branch, modified/untracked files, diff summary, and last 5 commits."""
    if args is None:
        args = {}
    repo = _resolve_repo_path(args)
    branch = _run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    status = _run_git(repo, ["status", "--short"])
    diff_stat = _run_git(repo, ["diff", "--stat"])
    recent = _run_git(repo, ["log", "-n", "5", "--oneline"])

    lines = [
        f"Git Workspace: {repo}",
        f"Branch: {branch or 'unknown'}",
        "",
        "Working Tree Status:",
        status if status else "  (clean working tree — no modified or untracked files)",
    ]
    if diff_stat:
        lines.extend(["", "Diff Summary:", diff_stat])
    if recent:
        lines.extend(["", "Recent Commits:", recent])
    return "\n".join(lines)


def get_diff(args: dict = None) -> str:
    """Return the uncommitted git diff (or staged diff if staged=True) for code review."""
    if args is None:
        args = {}
    repo = _resolve_repo_path(args)
    target_file = str(args.get("file") or "").strip()
    git_cmd = ["diff"]
    if args.get("staged"):
        git_cmd.append("--staged")
    if target_file:
        git_cmd.extend(["--", target_file])

    diff_out = _run_git(repo, git_cmd)
    if not diff_out:
        diff_out = _run_git(repo, ["diff", "--staged"])
    if not diff_out:
        return f"Git Diff ({repo}): No uncommitted or staged diffs found."
    max_chars = 14000
    if len(diff_out) > max_chars:
        diff_out = diff_out[:max_chars] + f"\n...[diff truncated at {max_chars} chars]"
    return f"Git Diff ({repo}):\n```diff\n{diff_out}\n```"


def get_log(args: dict = None) -> str:
    """Return the last N commits (default 10) from the Git repository."""
    if args is None:
        args = {}
    repo = _resolve_repo_path(args)
    count = min(30, max(1, int(args.get("count", 10) or 10)))
    log_out = _run_git(repo, ["log", f"-n{count}", "--pretty=format:%h | %ad | %an: %s", "--date=short"])
    return f"Git Commit History ({repo}, last {count}):\n{log_out or '(no commits)'}"
