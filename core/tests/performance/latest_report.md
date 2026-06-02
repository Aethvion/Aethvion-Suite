# Aethvion Suite Tester - Performance Report

- **Report ID**: `report_1780399217_5996f7d`
- **Timestamp**: `2026-06-02 13:20:17`
- **Commit**: `5996f7d`
- **Commit Message**: `Updated Suite Tester, token info`
- **Version**: `2026.06.1188 (5996f7d)`

## 🖥️ Test Device

| Component | Details |
| :--- | :--- |
| **OS** | Windows 10 |
| **CPU** | 13th Gen Intel(R) Core(TM) i9-13900K (24P / 32L cores) |
| **RAM** | 63.8 GB |
| **GPU** | NVIDIA GeForce RTX 4090 (24.0 GB VRAM) |
| **Python** | 3.10.11 |

## 📊 Telemetry Summary

| Metric Stream | Offline Baseline | Active Test Average | Active Test Peak (Max) |
| :--- | :---: | :---: | :---: |
| **Process CPU** | — | 0.0% | 0.0% |
| **Process Memory (RAM)** | — | 488.30 MB | 507.86 MB |
| **System CPU** | 1.6% | 1.4% | 13.9% |
| **System Memory (RAM)** | 34.5% | 0.7% | 0.9% |
| **GPU Utilization** | 1.0% | 0.4% | 23.0% |
| **GPU VRAM** | 2,539 MB | 12.07 MB | 95.00 MB |

## ⏱️ Orchestration & Stress Tests

- **Startup Duration**: `9.68 seconds`
- **API Health Check Average Latency**: `11.79 ms`
- **LLM Task Queue Routing Stress**: `Response Mismatch` (took `0.44s`)

## 📁 Repository Codebase Stats

- **Total Files Tracked**: `469`
- **Total Lines of Code (LOC)**: `169,162`
- **Total Tokens**: `1,509,621` *(tokenizer: cl100k_base (tiktoken))*

### Context Window Fit

| Model | Context Window | Fits? | Remaining |
| :--- | :---: | :---: | :---: |
| Claude 3.x (Sonnet / Haiku / Opus) | 200,000 | ✗ No | — |
| GPT-4o / GPT-4 | 128,000 | ✗ No | — |
| Gemini 1.5 / 2.0 Pro | 1,000,000 | ✗ No | — |
| Llama 3.1 70B / DeepSeek V3 | 128,000 | ✗ No | — |
| Mistral Large | 128,000 | ✗ No | — |

### Language Breakdown

| Language | Files | LOC | Tokens | Token Share |
| :--- | :---: | :---: | :---: | :---: |
| **Python** | 291 | 61,416 | 520,933 | 34.5% |
| **JavaScript** | 53 | 51,231 | 500,861 | 33.2% |
| **CSS** | 47 | 39,566 | 304,506 | 20.2% |
| **HTML** | 57 | 15,493 | 172,282 | 11.4% |
| **Batch** | 16 | 943 | 7,035 | 0.5% |
| **C#** | 5 | 513 | 4,004 | 0.3% |