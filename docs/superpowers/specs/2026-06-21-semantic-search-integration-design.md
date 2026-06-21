---
title: "Bundle semantic search into deep-research — Design"
date: 2026-06-21
status: Approved for implementation
supersedes: external-companion-skill approach (the prior shell-out-to-~/.claude design)
---

# Bundle Semantic Search into deep-research

## Goal

Make deep-research a **single self-contained repo**: clone it, `pip install -r
requirements.txt`, and you have multi-model research **plus** semantic search over
everything you research — no separate skill to install. After each run, one
project-wide index over every topic's Bible is refreshed so the whole research
library is searchable by meaning with a short, clean command.

## Hard requirements

1. **Single repo, runnable from a clean clone.** No dependency on any externally
   installed skill (the earlier `~/.claude/skills/semantic-search/` design is
   discarded). Everything needed is committed.
2. **Graceful degradation — never break core research.** If `OPENAI_API_KEY` is
   absent, or the search dependencies (`sqlite-vec`, `apsw`) are not installed, or
   indexing/search otherwise fails: print a clear one-line notice and continue.
   The deep-research pipeline (Rounds 0–5 + export) must complete normally. The
   index/search step is strictly additive and must never raise an uncaught
   exception that aborts a run.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Distribution | Single self-contained public repo; vendored engine committed in. |
| Engine handling | Vendor a **pristine, unedited** copy of `search.py` + its `LICENSE` at `vendor/semantic_search/`, re-syncable from the upstream private repo. Never edited. |
| Integration | A deep-research-native wrapper `scripts/search.py` that **imports** the engine's functions and bakes in research conventions. |
| Search ergonomics | Clean command: `index` (no flags) and `query "..."` with optional `--topic <slug>`. The wrapper hides root resolution + Bible globs. |
| Index scope | One project-wide index at `research/.semantic-index.db`, over each topic's `README.md` + `sections/*.md` (Bibles only). |
| Trigger | Auto — final step of every run calls the wrapper's `index`. |
| Keys | Reuse `OPENAI_API_KEY` (engine already reads env then `~/.env`). No new keys. |

## Components

### 1. `vendor/semantic_search/`
- `search.py` — pristine copy of the upstream engine (importable: `cmd_index`,
  `cmd_query`, `cmd_stats`, `load_openai_key`, `open_db`, `embed_all`). Unedited.
- `LICENSE` — upstream MIT license, copied verbatim for attribution.
- `__init__.py` — makes it importable as `vendor.semantic_search.search`.
- A short `VENDOR.md` noting upstream source + "do not edit; re-sync instead."

### 2. `scripts/search.py` (the native wrapper)
Imports the vendored engine and exposes a small CLI:

- `python3 scripts/search.py index`
  - Resolves the research root: `./research` under cwd (or `--root PATH`).
  - Indexes only Bibles via the engine's `in_patterns=['*/README.md',
    '*/sections/*.md']`, db at `<root>/.semantic-index.db`.
  - Prints the engine's summary line.
- `python3 scripts/search.py "<query>"`
  - Queries the same index. `--topic <slug>` scopes via `in_patterns=['<slug>/**']`.
  - `--top N`, `--json` pass through.
- **Graceful-degradation gate (shared):** before doing work, check (a)
  `OPENAI_API_KEY` resolvable and (b) engine import succeeds. If either fails,
  print a one-line actionable notice to stderr and exit **0** (so a pipeline
  caller treats it as a skip, not an error). Document exit codes.

### 3. `requirements.txt`
Add `sqlite-vec>=0.1.6` and `apsw>=3.46` under a "Semantic search (optional at
runtime)" comment. `openai` is already present.

### 4. Pipeline wiring (`SKILL.md`)
Replace the prior external-path command and "install the companion skill" framing
with the bundled wrapper. The final step runs `python3 scripts/search.py index`
and is documented to **skip with a notice** if keys/deps are missing — the Bible
is complete without it. Add the clean query commands and update the output tree
(`research/.semantic-index.db`). Update the architecture diagram + execution
checklist accordingly.

### 5. `README.md`
Rewrite the semantic-index sections to the bundled, self-contained story:
install is just the existing clone + `pip install`; no companion skill. Document
`scripts/search.py index` / `query` / `--topic`, the graceful-skip behavior, and
git-ignoring `research/.semantic-index.db`.

### 6. Tests (`tests/`)
A no-network test module for the wrapper:
- research-root resolution (`./research` default and `--root`).
- `--topic` produces the correct scoping glob.
- index Bible globs are correct.
- **graceful skip when `OPENAI_API_KEY` is absent** → exit 0 + notice, no raise.
- graceful skip when the engine import fails (simulate ImportError) → exit 0.
Mock the engine functions; assert the wrapper's wiring, not the engine internals.

## Graceful-degradation contract (the keystone)

- Wrapper missing key/deps → exit 0 + stderr notice. Never exit non-zero from a
  missing prerequisite (only from a genuine, unexpected error mid-index — and
  even then the pipeline step swallows it as a warning).
- The pipeline's index step is documented as best-effort: its failure is reported
  but does not change the run's success status. Core research output is already
  written before indexing runs.

## Out of scope

- No edits to the vendored engine (fork/patch upstream instead).
- No per-topic sub-indexes, no result enrichment/provenance links (Option 3 — deferred).
- No cross-project/global-filesystem index.
