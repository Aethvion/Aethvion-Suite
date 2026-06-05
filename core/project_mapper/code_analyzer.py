"""
core/project_mapper/code_analyzer.py
Python AST-based code structure extractor.

Given a file path and its content, extracts all structurally meaningful
information without any AI calls:
  - Module docstring
  - Classes (with methods, bases, decorators, class vars)
  - Top-level functions (with signatures, decorators, docstrings)
  - Imports (distinguishing internal vs. external, relative vs. absolute)
  - Module-level constants (__all__, UPPER_CASE names)
  - Parse errors (so callers can fall back gracefully)

Requires Python 3.9+ for ast.unparse().
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ImportInfo:
    module:      str         # "jwt", "core.auth.service", "" (for "from . import x")
    names:       list[str]   # [] for "import x", ["y","z"] for "from x import y,z"
    is_from:     bool        # True for "from X import Y"
    is_relative: bool        # True for "from . import ..."
    level:       int = 0     # number of leading dots in relative import
    alias:       str = ""    # "import jwt as j" → alias="j"


@dataclass
class ArgInfo:
    name:       str
    annotation: str = ""
    default:    str = ""


@dataclass
class MethodInfo:
    name:            str
    args:            list[str]       # parameter names only (brief)
    return_type:     str = ""
    decorators:      list[str] = field(default_factory=list)
    is_async:        bool = False
    is_property:     bool = False
    is_classmethod:  bool = False
    is_staticmethod: bool = False


@dataclass
class ClassInfo:
    name:        str
    bases:       list[str]
    methods:     list[MethodInfo]
    class_vars:  list[str]            # UPPER_CASE class-level names
    decorators:  list[str] = field(default_factory=list)
    docstring:   str = ""
    line_start:  int = 0
    line_end:    int = 0


@dataclass
class FunctionInfo:
    name:        str
    args:        list[ArgInfo]
    return_type: str = ""
    decorators:  list[str] = field(default_factory=list)
    docstring:   str = ""
    is_async:    bool = False
    line_start:  int = 0
    line_end:    int = 0


@dataclass
class CodeAnalysis:
    path:             str              # relative path from project root
    language:         str              # "python", etc.
    line_count:       int
    module_docstring: str
    classes:          list[ClassInfo]
    functions:        list[FunctionInfo]   # top-level public functions only
    imports:          list[ImportInfo]
    all_exports:      list[str]            # __all__ contents
    constants:        list[tuple[str, str]]  # (name, value_repr) for UPPER_CASE
    parse_errors:     list[str]


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _safe_unparse(node: ast.expr) -> str:
    """Convert an AST expression to source string; fall back to type name."""
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _node_to_str(node: ast.expr) -> str:
    """Simplified expression to string — handles Name, Attribute, Subscript."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_node_to_str(node.value)}.{node.attr}"
    return _safe_unparse(node)


def _decorator_name(dec: ast.expr) -> str:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return _node_to_str(dec)
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    return _safe_unparse(dec)


def _arg_info(arg: ast.arg, default_val: Optional[ast.expr] = None) -> ArgInfo:
    ann = _safe_unparse(arg.annotation) if arg.annotation else ""
    dflt = _safe_unparse(default_val) if default_val else ""
    return ArgInfo(name=arg.arg, annotation=ann, default=dflt)


def _is_upper(name: str) -> bool:
    """True for UPPER_CASE_NAMES (module constants)."""
    return bool(re.match(r"^[A-Z][A-Z0-9_]*$", name))


def _literal_repr(node: ast.expr) -> str:
    """Return a compact string representation of a simple literal."""
    try:
        val = ast.literal_eval(node)
        r = repr(val)
        return r[:80] + "…" if len(r) > 80 else r
    except Exception:
        return _safe_unparse(node)[:60]


# ---------------------------------------------------------------------------
# Python AST visitor
# ---------------------------------------------------------------------------

class _PythonVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes:   list[ClassInfo] = []
        self.functions: list[FunctionInfo] = []
        self.imports:   list[ImportInfo] = []
        self.all_exports: list[str] = []
        self.constants: list[tuple[str, str]] = []
        self._class_stack: list[str] = []   # track nesting

    def _in_class(self) -> bool:
        return bool(self._class_stack)

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportInfo(
                module=alias.name,
                names=[],
                is_from=False,
                is_relative=False,
                level=0,
                alias=alias.asname or "",
            ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        level  = node.level or 0
        names  = [a.name for a in node.names]
        self.imports.append(ImportInfo(
            module=module,
            names=names,
            is_from=True,
            is_relative=(level > 0),
            level=level,
        ))
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Only process top-level classes
        if self._in_class():
            self.generic_visit(node)
            return

        bases      = [_node_to_str(b) for b in node.bases]
        decorators = [_decorator_name(d) for d in node.decorator_list]
        docstring  = ast.get_docstring(node) or ""

        methods:    list[MethodInfo] = []
        class_vars: list[str] = []

        self._class_stack.append(node.name)
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m = self._build_method(item)
                methods.append(m)
            elif isinstance(item, ast.Assign):
                for t in item.targets:
                    if isinstance(t, ast.Name) and _is_upper(t.id):
                        class_vars.append(t.id)
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name) and _is_upper(item.target.id):
                    class_vars.append(item.target.id)
        self._class_stack.pop()

        end_line = getattr(node, "end_lineno", node.lineno)
        self.classes.append(ClassInfo(
            name=node.name,
            bases=bases,
            methods=methods,
            class_vars=class_vars,
            decorators=decorators,
            docstring=docstring[:300],
            line_start=node.lineno,
            line_end=end_line,
        ))

    def _build_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
        decs      = [_decorator_name(d) for d in node.decorator_list]
        args      = [a.arg for a in node.args.args if a.arg != "self" and a.arg != "cls"]
        ret_type  = _safe_unparse(node.returns) if node.returns else ""
        is_async  = isinstance(node, ast.AsyncFunctionDef)
        is_prop   = "property" in decs
        is_cm     = "classmethod" in decs
        is_sm     = "staticmethod" in decs
        return MethodInfo(
            name=node.name,
            args=args,
            return_type=ret_type,
            decorators=decs,
            is_async=is_async,
            is_property=is_prop,
            is_classmethod=is_cm,
            is_staticmethod=is_sm,
        )

    # ------------------------------------------------------------------
    # Top-level functions
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self._in_class():
            # Skip private/dunder functions
            if not node.name.startswith("_"):
                self._record_function(node, is_async=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not self._in_class():
            if not node.name.startswith("_"):
                self._record_function(node, is_async=True)
        self.generic_visit(node)

    def _record_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool,
    ) -> None:
        decs      = [_decorator_name(d) for d in node.decorator_list]
        docstring = ast.get_docstring(node) or ""
        ret_type  = _safe_unparse(node.returns) if node.returns else ""

        # Build args list with defaults aligned
        all_args   = node.args.args
        defaults   = node.args.defaults
        # defaults are right-aligned: last len(defaults) args have defaults
        pad        = len(all_args) - len(defaults)
        args: list[ArgInfo] = []
        for i, arg in enumerate(all_args):
            dflt_node = defaults[i - pad] if i >= pad else None
            args.append(_arg_info(arg, dflt_node))

        end_line = getattr(node, "end_lineno", node.lineno)
        self.functions.append(FunctionInfo(
            name=node.name,
            args=args,
            return_type=ret_type,
            decorators=decs,
            docstring=docstring[:200],
            is_async=is_async,
            line_start=node.lineno,
            line_end=end_line,
        ))

    # ------------------------------------------------------------------
    # Module-level assignments: constants + __all__
    # ------------------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._in_class():
            self.generic_visit(node)
            return
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if name == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    self.all_exports = [
                        elt.s if isinstance(elt, ast.Constant) and isinstance(elt.s, str)
                        else _safe_unparse(elt)
                        for elt in node.value.elts
                    ]
            elif _is_upper(name):
                self.constants.append((name, _literal_repr(node.value)))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self._in_class():
            if isinstance(node.target, ast.Name) and _is_upper(node.target.id):
                val_repr = _literal_repr(node.value) if node.value else ""
                self.constants.append((node.target.id, val_repr))
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Public analysis functions
# ---------------------------------------------------------------------------

def analyze_python(path: str, content: str) -> CodeAnalysis:
    """
    Parse *content* as Python source and return a CodeAnalysis.
    Never raises — parse errors are collected in CodeAnalysis.parse_errors.
    """
    line_count   = content.count("\n") + 1
    parse_errors: list[str] = []

    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        return CodeAnalysis(
            path=path, language="python", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"SyntaxError: {exc}"],
        )
    except Exception as exc:
        return CodeAnalysis(
            path=path, language="python", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"ParseError: {exc}"],
        )

    module_docstring = ast.get_docstring(tree) or ""

    visitor = _PythonVisitor()
    try:
        visitor.visit(tree)
    except Exception as exc:
        parse_errors.append(f"VisitorError: {exc}")

    return CodeAnalysis(
        path=path,
        language="python",
        line_count=line_count,
        module_docstring=module_docstring[:500],
        classes=visitor.classes,
        functions=visitor.functions,
        imports=visitor.imports,
        all_exports=visitor.all_exports,
        constants=visitor.constants[:30],
        parse_errors=parse_errors,
    )


_LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".java": "java", ".cpp": "cpp", ".c": "c", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".go": "go", ".rs": "rust", ".php": "php",
    ".cs": "csharp", ".swift": "swift", ".kt": "kotlin",
}


def detect_language_for_path(path: str) -> str:
    """Return a language slug for the given file path."""
    return _LANGUAGE_BY_EXT.get(Path(path).suffix.lower(), "")


def analyze_file(path: str, content: str, language: str = "") -> CodeAnalysis:
    """
    Route to the appropriate language analyzer.
    Currently only Python is fully supported; all others get a minimal stub.
    Language is auto-detected from the path if not provided.
    """
    if not language:
        language = detect_language_for_path(path)
    if language == "python":
        return analyze_python(path, content)
    # Minimal stub for non-Python files
    return CodeAnalysis(
        path=path,
        language=language or "unknown",
        line_count=content.count("\n") + 1,
        module_docstring="",
        classes=[],
        functions=[],
        imports=[],
        all_exports=[],
        constants=[],
        parse_errors=[],
    )


def build_compact_summary(analysis: CodeAnalysis) -> str:
    """
    Build a compact, LLM-friendly structured text summary of a CodeAnalysis.
    Designed to fit well within a prompt without wasting tokens.
    """
    lines: list[str] = []
    lines.append(f"Module: {analysis.path} ({analysis.language}, {analysis.line_count} lines)")

    if analysis.module_docstring:
        lines.append(f"Docstring: {analysis.module_docstring[:300]}")

    if analysis.classes:
        lines.append("\nClasses:")
        for cls in analysis.classes:
            bases_str = f"({', '.join(cls.bases)})" if cls.bases else ""
            lines.append(f"  {cls.name}{bases_str}")
            if cls.docstring:
                lines.append(f"    \"{cls.docstring[:120]}\"")
            public_methods = [m for m in cls.methods if not m.name.startswith("_") or m.name.startswith("__") and m.name.endswith("__")]
            if public_methods:
                meth_strs = []
                for m in public_methods[:8]:
                    sig = f"{m.name}({', '.join(m.args)})"
                    if m.return_type:
                        sig += f" -> {m.return_type}"
                    if m.is_async:
                        sig = "[async] " + sig
                    if m.is_property:
                        sig = "@property " + sig
                    meth_strs.append(sig)
                lines.append(f"    Methods: {', '.join(meth_strs)}")
            if cls.class_vars:
                lines.append(f"    Class vars: {', '.join(cls.class_vars[:6])}")

    if analysis.functions:
        lines.append("\nTop-level Functions:")
        for fn in analysis.functions[:12]:
            arg_strs = []
            for a in fn.args[:6]:
                s = a.name
                if a.annotation:
                    s += f": {a.annotation}"
                if a.default:
                    s += f" = {a.default}"
                arg_strs.append(s)
            sig = f"  {fn.name}({', '.join(arg_strs)})"
            if fn.return_type:
                sig += f" -> {fn.return_type}"
            if fn.is_async:
                sig = "  [async]" + sig[1:]
            lines.append(sig)
            if fn.docstring:
                lines.append(f"    \"{fn.docstring[:100]}\"")

    # Partition imports
    int_imps = [i for i in analysis.imports if _could_be_internal(i)]
    ext_imps = [i for i in analysis.imports if not _could_be_internal(i)]

    if int_imps:
        names = [i.module or ("." * i.level) for i in int_imps[:10]]
        lines.append(f"\nInternal Imports: {', '.join(filter(None, names))}")
    if ext_imps:
        names = list(dict.fromkeys(i.module.split(".")[0] for i in ext_imps if i.module))[:12]
        lines.append(f"External Dependencies: {', '.join(names)}")

    if analysis.all_exports:
        lines.append(f"\n__all__: {', '.join(analysis.all_exports[:10])}")

    if analysis.constants:
        const_strs = [f"{n} = {v}" for n, v in analysis.constants[:8]]
        lines.append(f"Constants: {', '.join(const_strs)}")

    if analysis.parse_errors:
        lines.append(f"\nParse Warnings: {'; '.join(analysis.parse_errors)}")

    return "\n".join(lines)


def _could_be_internal(imp: ImportInfo) -> bool:
    """Heuristic: relative imports are always internal; absolute imports with
    known stdlib top-level names are external. Everything else is ambiguous
    (treated as potentially internal for display purposes in the summary)."""
    if imp.is_relative:
        return True
    if not imp.module:
        return False
    first = imp.module.split(".")[0]
    return first not in _STDLIB_TOP_LEVEL


# ---------------------------------------------------------------------------
# Known stdlib top-level package names (Python 3.10 stdlib)
# ---------------------------------------------------------------------------

_STDLIB_TOP_LEVEL: frozenset[str] = frozenset({
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii",
    "binhex", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
    "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "csv", "ctypes",
    "curses", "dataclasses", "datetime", "dbm", "decimal", "difflib",
    "dis", "distutils", "doctest", "email", "encodings", "enum",
    "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
    "gettext", "glob", "grp", "gzip", "hashlib", "heapq", "hmac",
    "html", "http", "idlelib", "imaplib", "imghdr", "imp", "importlib",
    "inspect", "io", "ipaddress", "itertools", "json", "keyword",
    "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox",
    "marshal", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
    "netrc", "nis", "nntplib", "numbers", "operator", "optparse",
    "os", "ossaudiodev", "pathlib", "pdb", "pickle", "pickletools",
    "pipes", "pkgutil", "platform", "plistlib", "poplib", "posix",
    "posixpath", "pprint", "profile", "pstats", "pty", "pwd", "py_compile",
    "pyclbr", "pydoc", "queue", "quopri", "random", "re", "readline",
    "reprlib", "resource", "rlcompleter", "runpy", "sched", "secrets",
    "select", "selectors", "shelve", "shlex", "shutil", "signal",
    "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver",
    "spwd", "sqlite3", "sre_compile", "sre_constants", "sre_parse",
    "ssl", "stat", "statistics", "string", "stringprep", "struct",
    "subprocess", "sunau", "symtable", "sys", "sysconfig", "syslog",
    "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
    "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty",
    "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
    "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp",
    "zipfile", "zipimport", "zlib", "zoneinfo",
    # Common third-party that look like stdlib
    "typing_extensions",
})
