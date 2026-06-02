"""
core/utils/pkg_repair.py
========================
Startup package health checker for Aethvion Suite.

Reads dependency lists directly from  pyproject.toml  so there is only
one place to maintain dependencies.  Checked sections:

    [project.dependencies]                 -> treated as core (must-have)
    [project.optional-dependencies.auto]   -> treated as optional (best-effort)

Uses  importlib.metadata.distribution()  to check whether a distribution
is installed — no import-name mapping required (works with Pillow/PIL,
opencv-python/cv2, discord.py/discord, etc. automatically).

This module uses only the Python stdlib so it is safe to call before any
third-party imports have been verified.

Adding a new dependency
-----------------------
  * Core requirement  ->  add to  [project.dependencies]  in pyproject.toml
  * Optional feature  ->  add to  [project.optional-dependencies.auto]

Existing installations self-heal on next startup.
"""
from __future__ import annotations

import importlib.metadata
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent


# ANSI helpers (ASCII-safe, no dependencies)

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def _bold(t: str)   -> str: return _c("1",  t)
def _cyan(t: str)   -> str: return _c("36", t)
def _green(t: str)  -> str: return _c("32", t)
def _yellow(t: str) -> str: return _c("33", t)
def _red(t: str)    -> str: return _c("31", t)
def _dim(t: str)    -> str: return _c("2",  t)


# pyproject.toml parsing

def _load_toml(path: Path) -> dict:
    """Parse pyproject.toml using tomllib (3.11+) or a simple line parser."""
    if sys.version_info >= (3, 11):
        import tomllib                          # noqa: PLC0415
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    # Python 3.10 fallback — try tomli if available
    try:
        import tomli                            # noqa: PLC0415
        with open(path, "rb") as fh:
            return tomli.load(fh)
    except ImportError:
        pass
    # Last resort: minimal line-by-line parser for our specific format
    return _parse_pyproject_minimal(path.read_text(encoding="utf-8"))


def _parse_pyproject_minimal(content: str) -> dict:
    """Very small TOML parser — handles only what pkg_repair needs."""
    result: dict = {"project": {"dependencies": [], "optional-dependencies": {}}}
    lines          = content.splitlines()
    current_path: list[str] = []   # e.g. ["project"] or ["project","optional-dependencies"]
    current_key:  str | None = None
    in_array      = False
    array_items:  list[str] = []

    def _commit_array() -> None:
        nonlocal in_array, current_key, array_items
        if current_key is None:
            return
        node = result
        for part in current_path:
            node = node.setdefault(part, {})
        node[current_key] = array_items
        in_array = False
        current_key = None
        array_items = []

    for line in lines:
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Section header: [project] or [project.optional-dependencies]
        m_sec = re.match(r'^\[([^\[\]]+)\]$', stripped)
        if m_sec:
            if in_array:
                _commit_array()
            raw = m_sec.group(1).strip()
            current_path = [p.strip() for p in raw.split(".")]
            continue

        # Start of a multi-line array or inline array
        m_arr = re.match(r'^(\S+)\s*=\s*\[(.*)', stripped)
        if m_arr and not in_array:
            key  = m_arr.group(1).strip()
            rest = m_arr.group(2)
            if "]" in rest:
                # Single-line array
                node = result
                for part in current_path:
                    node = node.setdefault(part, {})
                node[key] = re.findall(r'["\']([^"\']+)["\']', rest)
            else:
                current_key = key
                in_array    = True
                array_items = []
                # Any items on the opening line
                for s in re.findall(r'["\']([^"\']+)["\']', rest):
                    array_items.append(s)
            continue

        if in_array:
            if stripped.startswith("]"):
                _commit_array()
            else:
                for s in re.findall(r'["\']([^"\']+)["\']', stripped):
                    array_items.append(s)

    if in_array:
        _commit_array()

    return result


def _read_pyproject_deps() -> tuple[list[str], list[str]]:
    """Return (core_deps, auto_optional_deps) from pyproject.toml."""
    path = _ROOT / "pyproject.toml"
    if not path.exists():
        return [], []
    try:
        data    = _load_toml(path)
        project = data.get("project", {})
        core    = list(project.get("dependencies", []))
        opt     = project.get("optional-dependencies", {})
        auto    = list(opt.get("auto", []))
        return core, auto
    except Exception as exc:
        print(_yellow(f"  [pkg_repair] Could not parse pyproject.toml: {exc}"))
        return [], []


# Installation checks

# Normalise a distribution name the same way pip / importlib.metadata does:
# lowercase, replace [-_.] with a single hyphen.
_NORM_RE = re.compile(r"[-_.]+")

def _norm(name: str) -> str:
    return _NORM_RE.sub("-", name).lower()


# Strip version specifier and platform markers from a pip spec.
# "fastapi>=0.109.1"           -> ("fastapi",  None)
# "winrt-runtime; sys_platform == 'win32'"
#                              -> ("winrt-runtime", "sys_platform == 'win32'")
_SPEC_RE = re.compile(r"^([A-Za-z0-9_.%-]+)(.*?)(?:;(.+))?$")

def _split_spec(pip_spec: str) -> tuple[str, str | None]:
    """Return (pkg_name, marker_or_None) from a pip specifier string."""
    pip_spec = pip_spec.strip()
    # Split on ';' for environment markers
    if ";" in pip_spec:
        name_part, marker = pip_spec.split(";", 1)
    else:
        name_part, marker = pip_spec, None
    # Strip version operators: >=, <=, ==, !=, ~=, >, <, [extras]
    pkg_name = re.split(r"[><=!~\[\s]", name_part.strip())[0].strip()
    return pkg_name, (marker.strip() if marker else None)


def _marker_applies(marker: str | None) -> bool:
    """Evaluate simple environment markers (enough for our pyproject.toml)."""
    if marker is None:
        return True
    # sys_platform == 'win32'  /  sys_platform != 'win32'
    m = re.match(r'sys_platform\s*(==|!=)\s*["\'](\w+)["\']', marker.strip())
    if m:
        op, platform = m.group(1), m.group(2)
        match = sys.platform == platform
        return match if op == "==" else not match
    # python_version, os_name, etc. — default to True (attempt install)
    return True


def _is_installed(pkg_name: str) -> bool:
    """Return True if the distribution named *pkg_name* is installed."""
    try:
        importlib.metadata.distribution(pkg_name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def _pip_install(pip_spec: str) -> tuple[bool, str]:
    """Run ``pip install <pip_spec>`` in the current interpreter."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pip_spec,
         "--quiet", "--disable-pip-version-check"],
        capture_output=True, text=True,
    )
    err = (result.stderr or result.stdout).strip()
    return result.returncode == 0, err


# Public API

def repair(verbose: bool = True) -> dict[str, list]:
    """Check all pyproject.toml dependencies and install any that are missing.

    Sections checked:
      [project.dependencies]               -> core (failures reported)
      [project.optional-dependencies.auto] -> optional (failures silenced)

    Returns ``{"installed": [...], "failed": [...]}``.
    """
    core_specs, auto_specs = _read_pyproject_deps()

    if not core_specs and not auto_specs:
        return {"installed": [], "failed": []}

    # Build a flat list of (pip_spec, is_optional) filtering by platform marker
    candidates: list[tuple[str, bool]] = []
    for spec in core_specs:
        pkg, marker = _split_spec(spec)
        if pkg and _marker_applies(marker):
            candidates.append((spec, False))
    for spec in auto_specs:
        pkg, marker = _split_spec(spec)
        if pkg and _marker_applies(marker):
            candidates.append((spec, True))

    total   = len(candidates)
    missing = [(spec, opt) for spec, opt in candidates
               if not _is_installed(_split_spec(spec)[0])]

    if not missing:
        if verbose:
            print(_dim(f"  * Packages OK ({total} checked)"))
        return {"installed": [], "failed": []}

    # Something is missing — install it
    if verbose:
        _banner()
        print(_cyan(_bold(f"  {len(missing)} missing package(s) - installing...\n")))

    installed: list[str]  = []
    failed:    list[dict] = []

    for pip_spec, optional in missing:
        pkg_name, _ = _split_spec(pip_spec)
        tag = _dim("optional") if optional else _bold("core")

        if verbose:
            print(f"  {_cyan('->')} {_bold(pkg_name)}  [{tag}] ... ",
                  end="", flush=True)

        ok, err = _pip_install(pip_spec)

        if ok and _is_installed(pkg_name):
            installed.append(pkg_name)
            if verbose:
                print(_green("* installed"))
        else:
            if optional:
                if verbose:
                    print(_yellow("! skipped (optional)"))
            else:
                failed.append({"pip": pkg_name, "error": err})
                if verbose:
                    short = (err.splitlines()[-1][:80] if err else "unknown error")
                    print(_red(f"x  {short}"))

    if verbose:
        parts = []
        if installed:
            parts.append(_green(f"{len(installed)} installed"))
        if failed:
            parts.append(_red(f"{len(failed)} failed"))
        skipped = len(missing) - len(installed) - len(failed)
        if skipped:
            parts.append(_yellow(f"{skipped} optional skipped"))
        summary = ",  ".join(parts) if parts else _green("no changes")
        print(f"\n  Done - {summary}\n")

        if failed:
            print(_yellow("  ! Some core packages could not be installed."))
            print(_dim("    The app will start but affected features may not work.\n"))

    return {"installed": installed, "failed": failed}


def _banner() -> None:
    line = "-" * 48
    print(f"\n{_cyan(line)}")
    print(_bold(_cyan("  Aethvion Suite - Package Health Check")))
    print(f"{_cyan(line)}")
