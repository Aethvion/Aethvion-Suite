# Benchmark: Aethvion Project Mapper × ASP.NET Core (C#)

> **This is a real benchmark, not a demo. All numbers were measured on the actual
> ASP.NET Core source repository — 10,437 C# files, 1.6 million lines.**

---

## What is Project Mapper?

Project Mapper is a tool that scans a code repository and builds a structured,
token-efficient index of its entire architecture:

- Every class, interface, struct, enum, record, and delegate
- Every method signature (name, parameters, return type)
- Every import and dependency
- Kind labels: `sealed`, `abstract`, `static`, `interface`, `record`, `record struct`, `delegate` …

The index lets an LLM understand *what a codebase contains* without reading
millions of lines of source. One entity lookup. One query. Seconds, not minutes.

---

## The Repository

[**ASP.NET Core**](https://github.com/dotnet/aspnetcore) — the official Microsoft web
framework for .NET. Every .NET web API, Blazor app, or SignalR hub is built on it.

| Stat | Value |
|---|---|
| C# files | **10,437** |
| Total lines | **1,632,867** |
| Largest file | `ControllerBase.cs` — 2,843 lines |
| Test files | 3,977 (38%) |
| Production files | 6,460 (62%) |

---

## What PM Extracts

| Metric | Value |
|---|---|
| Total entities | **16,965** |
| Regular classes | 9,908 |
| Sealed classes | 2,954 |
| Static utility classes | 1,603 |
| Interfaces | 836 |
| Abstract classes | 432 |
| Structs | 406 |
| Enums | 368 |
| Records (C# 9+) | 347 |
| Record structs (C# 10+) | 58 |
| Delegates | 53 |
| **Method signatures** | **87,064** |
| Import statements | 36,725 |

The C# analyzer understands every C# type kind — including modern additions like
records (C# 9+), record structs (C# 10+), `init`-only properties, file-scoped
namespaces, and default interface implementations.

---

## Token Savings (Measured)

> 4 chars/token approximation. All values measured, not estimated.

### Entity lookup — `ControllerBase`

| | Tokens |
|---|---|
| Read `ControllerBase.cs` in full | **~36,430** |
| PM `get_entity("ControllerBase")` | **~187** |
| **Reduction** | **99.5 %** |

`ControllerBase` has 175 methods. Reading the file costs 36,430 tokens.
The PM response is 187 tokens — all method names, return types, and base classes
in a compact structured form.

### Entity lookup — `UserManager`

| | Tokens |
|---|---|
| Read `UserManager.cs` in full | **~31,932** |
| PM `get_entity("UserManager")` | **~216** |
| **Reduction** | **99.3 %** |

### Complexity query

*"Which types in ASP.NET Core have 20 or more methods?"*

| | Tokens |
|---|---|
| Read all 10,437 source files | **~16,155,216** |
| PM query (748 matching types) | **~2,333** |
| **Reduction** | **>99.9 %** |

### Full-repo overview

| | Tokens |
|---|---|
| Read all source files | **~16,155,216** |
| PM full entity index | **~1,091,080** |
| **Reduction** | **93.2 %** |

---

## Parse Success Rate

**98.4 %** of files parsed with full extraction.

The 1.6% that trigger errors (165 files) are almost entirely files wrapped in
`#if NET` preprocessor guards — platform-specific interop files that tree-sitter
correctly identifies as containing a syntax element it can't resolve at parse time.
Even in those cases, 84 files still yield partial extraction. These are low-level
native API wrappers, not application-layer abstractions.

---

## Scan Performance

| | Value |
|---|---|
| Full scan (Windows) | **81.6 s** |
| Full scan (Linux, est.) | **~20–40 s** |
| Per-file median | **0.42 ms** |
| Throughput | **20,005 lines/sec** |

---

## Language Coverage

With ASP.NET Core, Project Mapper now covers five languages:

| Language | Benchmark repo | Token reduction |
|---|---|---|
| Python | Django 5.1 | 89–93% |
| TypeScript | Zod v3+v4 | 97–99% |
| Java | Spring Framework | 95–100% |
| Go | Hugo | 97–100% |
| **C#** | **ASP.NET Core** | **93–>99.9%** |

---

## Try It

```bash
pip install "aethvion-project-mapper>=1.3.0"
pip install "tree-sitter>=0.23.0" tree-sitter-c-sharp
```

Full details, all raw numbers, and the complete benchmark methodology:  
→ [github.com/aethvion/project-mapper — C# case study](https://github.com/aethvion/project-mapper/blob/main/docs/benchmarks/aspnetcore-csharp-case-study.md)

---

*Benchmark · June 2026 · Project Mapper v1.3.0 · Python 3.12 · Windows 11*
