# Project Structure — AX Ollama Usage Tracker

> Live reference: directory tree + one-line file roles. Long-form rationale lives in [`memory-bank/old/projectstructure-archive.md`](memory-bank/old/projectstructure-archive.md) — read it only if a one-line summary here lacks the context you need.

---

## Directory Tree

```
AX-Ollama-Usage-Tracker/
├── README.md
├── LICENSE
├── .gitignore
└── memory-bank/
    ├── activeContext.md
    ├── progress.md
    ├── projectstructure.md
    └── old/
        └── .gitkeep
```

---

## Root-Level Files (one-line roles)

| File | Role |
|------|------|
| [`README.md`](README.md) | Main user doc — title, purpose statement, scaffold-phase status note, placeholder feature list. |
| [`LICENSE`](LICENSE) | MIT license, matching sibling repos. |
| [`.gitignore`](.gitignore) | Python artifacts + misc ignores (mirrors `ax_dose_logger` conventions). |

---

## `memory-bank/` Directory

| File | Role |
|------|------|
| [`memory-bank/activeContext.md`](memory-bank/activeContext.md) | Current feature status + recent changes (truncated; current + last 2 archived blocks). |
| [`memory-bank/progress.md`](memory-bank/progress.md) | Recent completed work (truncated; last ~16 feature sections). |
| [`memory-bank/projectstructure.md`](memory-bank/projectstructure.md) | This file — live directory tree + one-line file roles. |
| [`memory-bank/old/`](memory-bank/old/) | Full history archive (`activeContext-archive.md`, `progress-archive.md`, `projectstructure-archive.md`); read only when the truncated root files lack context. |

---

> 📜 **Long-form per-file descriptions are archived in [`memory-bank/old/projectstructure-archive.md`](memory-bank/old/projectstructure-archive.md)** — read it only if a one-line summary above lacks the context you need.