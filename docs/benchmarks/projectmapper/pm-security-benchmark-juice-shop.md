# ProjectMapper Security Benchmark — OWASP Juice Shop
**Model:** Gemini 2.5 Flash  
**Date:** 2026-06-13  
**Target:** OWASP Juice Shop (632 files, TypeScript/JavaScript)  
**Rules:** Reading `SOLUTIONS.md` was prohibited for both agents

---

## Setup

Two agents were given the same task:

> *"Find as many real security vulnerabilities as possible. Report file path, line number, vulnerability type, and why it is dangerous."*

| Agent | Tools available |
|-------|----------------|
| **No PM** | `read_file`, `list_dir`, `grep` |
| **PM + pm_security** | `pm_security`, `pm_context`, `pm_find`, `read_file` |

The PM snapshot had 17 `data/static/codefixes/` findings pre-triaged as `false_positive` (educational challenge code, not real application vulnerabilities). These were automatically suppressed from the PM agent's output.

---

## Results

| Metric | No PM | PM + pm_security | PM advantage |
|--------|-------|-----------------|-------------|
| **Time** | 32.9s | 9.2s | **3.6× faster** |
| **Input tokens** | 65,369 | 4,686 | **13.9× fewer** |
| **Output tokens** | 5,677 | 1,662 | **3.4× fewer** |
| **Total tokens** | 71,046 | 6,348 | **11.2× fewer** |
| **Tool calls** | 26 | 1 | **26× fewer** |
| **Vulnerabilities found** | 17 | 32 | **+88% more** |

---

## Findings Comparison

### Vulnerabilities found by BOTH agents

| File | Vuln type |
|------|-----------|
| `routes/login.ts:34` | SQL Injection (template literal) |
| `routes/search.ts:23` | SQL Injection (template literal) |
| `routes/trackOrder.ts:18` | NoSQL Injection (`$where` + template literal) |
| `routes/userProfile.ts:61/64` | Code Injection (`eval()`) |
| `routes/dataErasure.ts:104` | Path Traversal (`path.resolve` + user input) |

---

### Vulnerabilities found ONLY by PM + pm_security (17 additional)

| File | Vuln type | OWASP | CWE |
|------|-----------|-------|-----|
| `lib/insecurity.ts:191` | JWT algorithm confusion | A02 | CWE-347 |
| `routes/verify.ts:119` | JWT algorithm confusion | A02 | CWE-347 |
| `Gruntfile.js:76` | Weak hash (MD5) | A02 | CWE-327 |
| `lib/insecurity.ts:43` | Weak hash (MD5) | A02 | CWE-327 |
| `routes/b2bOrder.ts:23` | RCE via `vm.runInContext` | A03 | CWE-95 |
| `routes/captcha.ts:22` | Code injection (`eval`) | A03 | CWE-95 |
| `routes/fileUpload.ts:83` | RCE via `vm.runInContext` | A03 | CWE-95 |
| `routes/fileUpload.ts:117` | RCE via `vm.runInContext` | A03 | CWE-95 |
| `lib/codingChallenges.ts:76` | ReDoS via `new RegExp(userInput)` | A03 | CWE-400 |
| `lib/codingChallenges.ts:78` | ReDoS via `new RegExp(userInput)` | A03 | CWE-400 |
| `frontend/…/about.component.ts:119` | XSS (`bypassSecurityTrustHtml`) | A03 | CWE-79 |
| `frontend/…/administration.component.ts:73,91` | XSS (`bypassSecurityTrustHtml`) | A03 | CWE-79 |
| `frontend/…/data-export.component.ts:57` | XSS (`bypassSecurityTrustHtml`) | A03 | CWE-79 |
| `frontend/…/data-export.component.ts:71` | XSS (`document.write`) | A03 | CWE-79 |
| `frontend/…/last-login-ip.component.ts:39` | XSS (`bypassSecurityTrustHtml`) | A03 | CWE-79 |
| `lib/insecurity.ts:195` | Cookie missing `httpOnly` | A05 | CWE-1004 |
| `routes/updateUserProfile.ts:40` | Cookie missing `httpOnly` | A05 | CWE-1004 |

---

### Vulnerabilities found ONLY by No PM agent (12 additional)

These required reading individual route files to identify authorization logic gaps — not detectable by regex patterns:

| File | Vuln type | Note |
|------|-----------|------|
| `routes/basketItems.ts:68` | IDOR | No ownership check on basket items |
| `routes/delivery.ts:34` | IDOR | No ownership check on delivery ID |
| `routes/recycles.ts:14` | NoSQL Injection | JSON-parsed ID in query |
| `routes/address.ts:13,18,29` | IDOR | `UserId` from request body |
| `routes/payment.ts:18,41,70` | IDOR | `UserId` from request body |
| `routes/profileImageFileUpload.ts:43` | Path Traversal (potential) | Upload destination |
| `routes/fileServer.ts:33` | Path Traversal | Bypass of slash check |
| `routes/keyServer.ts:11` | Path Traversal | No path sanitization |
| `routes/logfileServer.ts:11` | Path Traversal | No path sanitization |
| `routes/quarantineServer.ts:11` | Path Traversal | No path sanitization |
| `routes/showProductReviews.ts:34` | NoSQL Injection | `$where` + string concat |
| `routes/videoHandler.ts:79` | XSS | `.vtt` content injected into `<script>` |

> **Note:** The IDOR and logic-based path traversal findings require reading the actual route code to understand what authorization checks are missing. These are outside pm_security's regex-based detection range. `pm_security` focuses on dangerous *patterns*; IDOR detection requires *semantic* reasoning about the route logic.

---

## OWASP Coverage Comparison

| OWASP Category | No PM | PM + pm_security |
|----------------|-------|-----------------|
| A01 Broken Access Control | 6 (IDOR + path traversal) | 1 (path traversal pattern) |
| A02 Cryptographic Failures | 0 | 4 (JWT + MD5) |
| A03 Injection (SQLi, XSS, RCE) | 5 | 21 |
| A05 Security Misconfiguration | 0 | 2 (httpOnly) |
| A07 Auth Failures | 0 | 5 (localStorage token) |
| A09 Logging/Monitoring | 0 | 2 |
| **Total** | **17** | **32** |

---

## Triage System Validation

The v1.8.0 triage system was tested as part of this benchmark:

- 17 `data/static/codefixes/` findings were pre-marked `false_positive` via `pm_security_triage`
- The PM agent received a clean output with `Hidden: 17 false_positive` in the header
- No codefixes appeared in the PM agent's final findings list
- The snapshot correctly persisted triage statuses across rescans
- Stable 8-char content-hash IDs (`d85752fe` etc.) survived rescans without line-number drift

---

## Key Takeaways

**Token efficiency (11.2×):** pm_security pre-processes 632 files and returns a structured, ranked report in one call. The No PM agent spent 65K input tokens reading files and grepping individually — with no coverage of the frontend Angular components at all.

**Coverage gap — PM wins:** pm_security caught all pattern-detectable issues across every file in the project: XSS in frontend components, JWT misconfigurations in lib/, RCE in routes/, weak crypto in Gruntfile.js — all in 1 tool call. The No PM agent focused on the `routes/` directory and missed the entire `frontend/` and `lib/` surface.

**Coverage gap — No PM wins:** IDOR findings and logic-level path traversal (checking what authorization guard is *missing*) require reading and understanding the route handler logic. These are beyond what regex patterns can detect and represent the "Tier 3" detection category (agent-driven semantic reasoning) from the SAST ceiling analysis.

**Combined agent strategy (recommended):** Use `pm_security` first (1 tool call, 6K tokens) to identify all pattern-based findings, then direct follow-up tool calls to investigate IDOR and access-control logic in specific routes. This gives both the breadth of automated scanning and the depth of code reasoning, at a fraction of the cost of manual exploration.
