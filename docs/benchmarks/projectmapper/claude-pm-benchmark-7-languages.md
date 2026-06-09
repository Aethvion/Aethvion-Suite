# Project Mapper — 7 New Language Analyzers Benchmark
*Rust · C · C++ · PHP · Ruby · Kotlin · Swift — Measured 2026-06-09*

---

## What was built

Seven new tree-sitter-based language analyzers were added to Project Mapper (v1.4.0), completing coverage of the most widely used systems and scripting languages. All results below are **measured on real public codebases**, not modelled.

---

## Results at a glance

| Language | Repo | Files | Types | Methods | Token reduction |
|----------|------|-------|-------|---------|----------------|
| **Rust** | ripgrep | 100 | 385 | 2,046 | **93.9%** |
| **C** | Redis | 781 | 259 | 9,086 fns | **97.8%** |
| **C++** | nlohmann/json | 490 | 126 | 354 | **98.1%** |
| **PHP** | WordPress | 1,888 | 776 | 7,327 | **98.2%** |
| **Ruby** | Jekyll | 161 | 325 | 929 | **94.9%** |
| **Kotlin** | Spring Framework | 390 | 381 | 1,795 | **86.1%** |
| **Swift** | swift-algorithms | 57 | 273 | 555 | **92.7%** |

**Overall: 3,867 files, 2,525 types, 13,006 methods — 94.5% average token reduction**

---

## Language-specific highlights

### Rust
- 0% parse errors — Rust's grammar is well-defined, no preprocessor
- Two-pass impl strategy: impl methods attached to their owning struct/enum/trait across file
- Async functions detected via `function_modifiers.async` child
- Supports: struct, enum, trait, type alias, impl blocks, top-level functions

### C
- 9,086 functions extracted from 781 Redis files
- 44.2% parse error rate — caused by GCC extensions and preprocessor macros (documented limitation)
- Even with parse errors, token reduction holds at 97.8% on successfully-parsed content

### C++
- 33.5% parse error rate — nlohmann/json uses C++20 template metaprogramming beyond tree-sitter-cpp grammar v0.23 support
- Class body methods extracted from both inline `function_definition` nodes and forward-declaration `field_declaration` nodes
- Namespace traversal: walks into namespace bodies for class discovery

### PHP
- Best parse accuracy: 0.1% errors across 1,888 WordPress files
- Extracts class, abstract class, interface, enum, trait — all 5 PHP type kinds
- PHP enum cases captured as `class_vars`
- Parameter `$` prefix stripped automatically from PHP variable names

### Ruby
- Key fix: recursive body traversal captures classes nested inside modules
  (Jekyll pattern: `module Jekyll; class Site; def render; end; end; end`)
- Imports from `require`, `require_relative`, `include`, `extend`
- 0% parse errors

### Kotlin
- Spring Framework Kotlin snippets: 2,038 files/s (fastest in the batch)
- Primary constructor parameters captured as `class_vars`
- Detects: class, abstract class, data class, enum class, interface, object, companion
- `suspend` modifier → `is_async=True` on MethodInfo

### Swift
- All type declarations use `class_declaration` node in tree-sitter-swift
- Leading keyword (`class`, `struct`, `enum`, `actor`, `extension`) determines `kind`
- Protocol declarations use separate `protocol_declaration` node
- `init_declaration` captured as constructor method

---

## Technical details

All analyzers follow the same soft-dependency pattern:
```python
try:
    from tree_sitter import Language, Parser
    import tree_sitter_rust as _tsrust
    _RUST_LANGUAGE = Language(_tsrust.language())
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False
```

If the tree-sitter package for a language isn't installed, the analyzer returns a stub `CodeAnalysis` with an explanatory `parse_errors` message — it never raises.

Install just the languages you need:
```bash
pip install "aethvion-project-mapper[rust]"      # Rust only
pip install "aethvion-project-mapper[languages]"  # All 10 languages
```

---

## Language support matrix (after this sprint)

| Language | Status | tree-sitter package |
|----------|--------|---------------------|
| Python | ✅ built-in (ast) | — |
| TypeScript/JavaScript | ✅ | tree-sitter-typescript |
| Java | ✅ | tree-sitter-java |
| Go | ✅ | tree-sitter-go |
| C# | ✅ | tree-sitter-c-sharp |
| **Rust** | ✅ new | tree-sitter-rust |
| **C** | ✅ new | tree-sitter-c |
| **C++** | ✅ new | tree-sitter-cpp |
| **PHP** | ✅ new | tree-sitter-php |
| **Ruby** | ✅ new | tree-sitter-ruby |
| **Kotlin** | ✅ new | tree-sitter-kotlin |
| **Swift** | ✅ new | tree-sitter-swift |

---

*All benchmark figures measured by Claude Sonnet 4.6, 2026-06-09.*
