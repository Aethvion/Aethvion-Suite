# Aethvion Suite — Debloat Analysis

This document records the dead code, orphaned files, and artifacts identified during the debloat pass on **2026-03-31**. All items below have been removed from the repository unless explicitly marked as retained.

---

## 1. Debug / Repro / Fix Scripts in `core/tests/`

These files are one-off debugging, reproduction, and manual-fix scripts that were created during development and left behind. They are **not unit tests**, are not executed by any test runner or CI pipeline, and several contain hard-coded memory IDs or paths from past debugging sessions.

**Removed:**

| File | Reason |
|---|---|
| `core/tests/debug_load_logic.py` | One-off debug script for task-model loading logic |
| `core/tests/debug_memory_full.py` | Debug script for memory persistence checks |
| `core/tests/debug_memory_retrieval.py` | Debug script for episodic memory retrieval |
| `core/tests/debug_thread_flow.py` | Debug script for task-queue thread flow |
| `core/tests/fix_missing_memory.py` | One-time script to inject a missing memory entry |
| `core/tests/minimal_file_check.py` | Bare-minimum file-path sanity check, no assertions |
| `core/tests/remove_manual_fix.py` | One-time script to delete a specific hard-coded memory ID |
| `core/tests/repro_full_persistence.py` | Full persistence reproduction script |
| `core/tests/repro_history_loading.py` | History-loading reproduction script |
| `core/tests/repro_persistence.py` | Persistence reproduction script |
| `core/tests/repro_save.py` | Save-flow reproduction script |
| `core/tests/repro_task_persistence.py` | Task-persistence reproduction script |
| `core/tests/run_model_selection_test.py` | Standalone runner duplicating `test_model_selection.py` |
| `core/tests/simulate_api.py` | Ad-hoc API simulation script |

**Retained** (genuine unit tests):
`test_factory.py`, `test_forge.py`, `test_integration.py`, `test_memory.py`, `test_model_selection.py`, `test_usage_assistant.py`

---

## 2. `core/orchestrator/output_validator.py`

`OutputValidator` and `get_output_validator()` are defined here but are **never imported or called** from any other file in the codebase. The class validates file-write output from agents, but the code path that was supposed to use it was removed in a prior refactor. The `ValidationResult` dataclass it defines is also independent from (and unrelated to) the same-named class inside `core/forge/tool_validator.py`.

**Removed.**

---

## 3. `core/tools/register_standard_tools.py`

A one-time setup script that registers `Data_Save_File` and `Data_Read_File` into `ToolRegistry` at startup. It references a wrong path (`project_root / "tools" / "standard" / "file_ops.py"` instead of `core/tools/standard/file_ops.py`), is **never imported or called** from any other file, and has no effect at runtime. The actual `file_ops.py` tools are already referenced directly by the agents that need them.

**Removed.**

---

## 4. `core/forge/validators/` (subdirectory)

This directory contains a second, stricter `ToolValidator` implementation with a whitelist-based import policy (`PERMITTED_IMPORTS`) and a `validate_tool` method. It was created as a security-hardened replacement for `core/forge/tool_validator.py`.

However, **the replacement was never wired in**:
- `core/forge/tool_forge.py` still imports from `core/forge/tool_validator.py` (the original).
- Nothing outside of `core/forge/__init__.py` imports `ToolValidator`, `PERMITTED_IMPORTS`, or `FORBIDDEN_OPERATIONS` from `core.forge`.

The subdirectory is therefore entirely dead code. `core/forge/__init__.py` has been updated to remove the re-exports that came from this directory.

**Removed:** `core/forge/validators/__init__.py`, `core/forge/validators/tool_validator.py`

**Updated:** `core/forge/__init__.py` — removed `validators` imports and their `__all__` entries.

---

## 5. `core/config/suggested_models.json`

An older combined model-suggestion file. The codebase uses two separate, up-to-date files:
- `core/config/suggested_apimodels.json` (referenced via `SUGGESTED_API_MODELS` in `core/utils/paths.py`)
- `core/config/suggested_localmodels.json` (referenced via `SUGGESTED_LOCAL_MODELS`)

`suggested_models.json` is **not referenced anywhere** in Python, JavaScript, HTML, or configuration files.

**Removed.**

---

## 6. `apps/tracking/osf_process.log`

A runtime log file from the OpenSeeFace tracker that was accidentally committed to the repository. Log files are runtime artifacts and should not be tracked in version control.

**Removed.** `.gitignore` updated to exclude `*.log` files project-wide.

---

## Summary

| Category | Files Removed |
|---|---|
| Debug / repro / fix scripts | 14 |
| Unused orchestrator module | 1 |
| Orphaned setup script | 1 |
| Dead validator subdirectory | 2 |
| Orphaned config file | 1 |
| Accidentally committed log | 1 |
| **Total** | **20** |

No actively-used code paths were altered. The following files were **modified** (not removed):
- `core/forge/__init__.py` — removed dead `validators/` re-exports
- `.gitignore` — added `*.log` exclusion
