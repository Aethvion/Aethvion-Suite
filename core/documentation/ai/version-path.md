# Version System

Aethvion Suite uses **automatic git-derived versioning**. There are no hardcoded
version numbers to maintain. The version string is computed at process startup
from the git history and cached for the lifetime of the process.

---

## Format

```
2026.05.1142 (fc86ae4)
```

| Segment       | Source                                    |
|---------------|-------------------------------------------|
| `2026`        | Year of HEAD commit (`git log -1 --format=%ad --date=format:%Y`) |
| `05`          | Month of HEAD commit (zero-padded)        |
| `1142`        | Total commit count (`git rev-list --count HEAD`) |
| `fc86ae4`     | 7-char short hash (`git rev-parse --short=7 HEAD`) |

---

## How it works

### `core/version.py`

The canonical source. Calls `git` once at import time, caches the result via
`@lru_cache`. Exports:

- `VERSION: str` — the full version string (e.g. `"2026.05.1142 (fc86ae4)"`)
- `get_version() -> str` — same value via function call
- `get_version_parts() -> dict` — individual fields: `year`, `month`, `count`, `short`, `string`

### `core/interfaces/dashboard/server.py`

Injects `VERSION` into `index.html` at request time by replacing the
`__VERSION__` placeholder in the HTML. The splash screen and any
`__VERSION__`/`__VNUM__` tokens in the page get the real string automatically.

### `/api/system/version-info`

Returns:
```json
{
  "local": {
    "version": "2026.05.1142 (fc86ae4)",
    "commit":  "fc86ae4",
    "count":   1142,
    "year":    "2026",
    "month":   "05",
    "last_update_commit": "...",
    "changelog": [...]
  },
  "remote": { "commit": "abc1234" }
}
```

The JS update checker compares `local.commit` against `remote.commit` to detect
available updates — no numeric version comparison needed.

---

## Adding a new feature / release

**Nothing needs to change.** Commit your code. The version string updates
automatically on next startup. The commit count increments, the date reflects
the latest commit, and the hash identifies it uniquely.

---

## Files that DO NOT need manual version updates anymore

These files previously required manual bumping — they are now fully automatic:

| File | Was | Now |
|------|-----|-----|
| `core/version.py` | `VERSION = 16` | computed from git |
| `pyproject.toml` | `version = "16"` | `"0.0.0"` placeholder |
| `core/interfaces/dashboard/static/index.html` | `BUILD v16` | `__VERSION__` (server-injected) |
| `core/interfaces/dashboard/static/partials/suite-home.html` | `v16` badge | populated by JS via API |

---

## Update detection logic

The sidebar dot and Version Control page compare:
- `local.commit` (7-char hash of HEAD on disk)
- `remote.commit` (7-char hash from `git ls-remote origin HEAD`)

If they differ → updates are available. No version number comparison is done.

---

## Fallback behaviour

If `git` is not available (zip install, no git binary, no `.git` folder), every
field returns a safe default:

```python
{"year": "0000", "month": "00", "count": 0, "short": "unknown", "string": "unknown"}
```
