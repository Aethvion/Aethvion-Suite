"""
core/modelhub/templating.py
Tiny template engine for endpoint definitions.

    "{{prompt}}"                 replaced by the value (type preserved when the whole
                                 string is one placeholder — numbers stay numbers)
    "seed-{{params.seed}}"       string interpolation
    "${MESHY_API_KEY}"           environment variable (for secrets; never stored in JSON)
    "{{response.result.id}}"     dotted / indexed lookup: a.b[0].c

A placeholder that resolves to nothing becomes "" inside a larger string, or None when it
is the whole value — callers drop None entries from request bodies so optional inputs
simply disappear.
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Mapping

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_ENVVAR      = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PATH_TOKEN  = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


class LazyVars(dict):
    """A dict whose values may be zero-argument callables, resolved on first access.

    Keeps large payloads (base64 of a mesh, say) from being built unless a template
    actually references them.
    """

    def __getitem__(self, key: str) -> Any:
        val = super().__getitem__(key)
        if callable(val):
            val = val()
            super().__setitem__(key, val)
        return val

    def get(self, key: str, default: Any = None) -> Any:
        return self[key] if key in self else default


def lookup(data: Any, path: str) -> Any:
    """Resolve 'a.b[0].c' against nested dicts/lists.  Returns None when missing."""
    cur = data
    for name, index in _PATH_TOKEN.findall(path.strip()):
        if cur is None:
            return None
        if index != "":
            if not isinstance(cur, (list, tuple)) or int(index) >= len(cur):
                return None
            cur = cur[int(index)]
        elif isinstance(cur, Mapping):
            cur = cur[name] if name in cur else None
        elif isinstance(cur, (list, tuple)) and name.isdigit():
            cur = cur[int(name)] if int(name) < len(cur) else None
        else:
            return None
    return cur


def _env(match: re.Match) -> str:
    return os.environ.get(match.group(1), "")


def render(template: Any, variables: Mapping[str, Any]) -> Any:
    """Recursively render a template structure (str / dict / list / scalar)."""
    if isinstance(template, str):
        whole = _PLACEHOLDER.fullmatch(template.strip())
        if whole:
            val = lookup(variables, whole.group(1))
            return None if val in (None, "") else val

        def _sub(m: re.Match) -> str:
            val = lookup(variables, m.group(1))
            return "" if val is None else str(val)

        return _ENVVAR.sub(_env, _PLACEHOLDER.sub(_sub, template))

    if isinstance(template, Mapping):
        out = {}
        for k, v in template.items():
            rv = render(v, variables)
            if rv is not None:
                out[k] = rv
        return out

    if isinstance(template, (list, tuple)):
        return [rv for rv in (render(v, variables) for v in template) if rv is not None]

    return template


def missing_env(template: Any) -> list[str]:
    """Names of ${ENV} variables referenced by a template that are not set."""
    found: set[str] = set()

    def _walk(t: Any) -> None:
        if isinstance(t, str):
            found.update(_ENVVAR.findall(t))
        elif isinstance(t, Mapping):
            for v in t.values():
                _walk(v)
        elif isinstance(t, (list, tuple)):
            for v in t:
                _walk(v)

    _walk(template)
    return sorted(n for n in found if not os.environ.get(n))


Resolver = Callable[[], Any]
