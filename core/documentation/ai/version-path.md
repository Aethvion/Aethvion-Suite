# Version Update Path

Every file that contains a hardcoded version number and must be updated when
bumping Aethvion Suite to a new version. Work through this list top-to-bottom
so nothing is missed.

---

## Required — update every version

### 1. `core/version.py`
The canonical source-of-truth integer used by the Python runtime.

```
VERSION = 15   →   VERSION = 16
```

---

### 2. `pyproject.toml`  (line ~7)
Python package metadata.

```toml
version = "15"   →   version = "16"
```

---

### 3. `CHANGELOG.md`  (top of file)
Add a new entry block above the previous one:

```markdown
## [v16] - YYYY-MM-DD

### Added
- ...

### Changed
- ...
```

---

### 4. `README.md`  (line ~22)
Badge / header line:

```markdown
**Current version: v15**   →   **Current version: v16**
```

---

### 5. `core/interfaces/dashboard/static/index.html`  (line ~364)
Splash screen build label — search for `id="splash-version"`:

```html
<div id="splash-version" class="splash-version">BUILD v15</div>
                                                        ↑
                                                   change to v16
```

---

### 6. `core/interfaces/dashboard/static/partials/suite-home.html`  (line ~256)
Hero badge visible on the home tab — search for `status-live`:

```html
<span class="sys-badge status-live">Aethvion Suite v15</span>
                                                    ↑
                                               change to v16
```

---

### 7. `core/interfaces/dashboard/static/assets/system-status.json`  (line ~5)
Runtime status file. The top-level `version` key is the current version;
a new history entry should also be added below it:

```json
{
    "version": "15",        →   "version": "16",
    ...
    "history": [
        {
            "version": "16",     ← add new entry at top of history array
            "changes": [
                "..."
            ]
        },
        {
            "version": "15",     ← previous entry stays
            ...
        }
    ]
}
```

---

### 8. `core/devtools/csharpwrapper/AethvionSuite.csproj`  (lines ~15-17)
Version metadata baked into the Windows `.exe` (shows in Properties → Details):

```xml
<Version>15.0.0</Version>              →   <Version>16.0.0</Version>
<FileVersion>15.0.0.0</FileVersion>    →   <FileVersion>16.0.0.0</FileVersion>
<InformationalVersion>15.0.0</InformationalVersion>   →   16.0.0
```

Rebuild with `core/devtools/csharpwrapper/publish.bat` after changing this.

---

## Optional — check each version, update if content has changed

These files contain prose documentation. They do not always need a version
bump but should be reviewed to confirm they still accurately describe the
current state of the suite.

| File | What to check |
|------|---------------|
| `core/documentation/ai/*.md` | Feature descriptions, architecture notes, tool lists |
| `core/documentation/human/*.md` | User-facing guides, screenshots, instructions |
| `core/documentation/README.md` | Overview still accurate, version references current |

---

## Quick grep to verify nothing was missed

Run this from the project root after updating to confirm no stale version
strings remain (adjust `15` to the old version number):

```bash
grep -rn "v15\b\|version.*15\|15.*version" \
    --include="*.py" \
    --include="*.toml" \
    --include="*.json" \
    --include="*.html" \
    --include="*.md" \
    --include="*.csproj" \
    . \
    --exclude-dir=".venv" \
    --exclude-dir="__pycache__" \
    --exclude-dir=".git"
```

> The `system-status.json` history array intentionally keeps old version
> numbers — those hits are expected and can be ignored.
