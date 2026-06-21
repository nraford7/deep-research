---
title: "Bundle semantic search into deep-research — Design"
date: 2026-06-21
status: Approved for implementation
supersedes: external-companion-skill approach (the prior shell-out-to-~/.claude design)
---

# Bundle Semantic Search into deep-research

## Goal

Make deep-research a **single self-contained repo**: clone it, `pip install -r
requirements.txt`, and you have full multi-model research. The semantic-search
**code is bundled in the repo too** — no separate skill to install — and activates
once you add its optional deps (`pip install -r requirements-search.txt`) and an
`OPENAI_API_KEY`. Until then it skips gracefully without affecting anything. With
it on, the final step of every run refreshes one project-wide index over every
topic's Bible, so the whole research library is searchable by meaning with a
short, clean command.

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
| Search ergonomics | Clean command. **Indexing:** `scripts/search.py index` (no flags). **Querying:** `scripts/search.py "<query>"` (query is a positional argument, matching the engine's own CLI) with optional `--topic <slug>`. The wrapper hides root resolution + Bible globs. |
| Index scope | One project-wide index at `research/.semantic-index.db`, over each topic's `README.md` + `sections/*.md` (Bibles only). |
| Trigger | Auto — final step of every run calls the wrapper's `index`. |
| Keys | Reuse `OPENAI_API_KEY` (engine already reads env then `~/.env`). No new keys. |
| Search deps | Live in a **separate** `requirements-search.txt`, NOT base `requirements.txt`, so a clean `pip install -r requirements.txt` can never fail on `sqlite-vec`/`apsw` and break core research. Search is opt-in: `pip install -r requirements-search.txt`. |

## Components

### 1. `vendor/semantic_search/`
- `search.py` — pristine copy of the upstream engine (importable: `cmd_index`,
  `cmd_query`, `cmd_stats`, `load_openai_key`, `open_db`, `embed_all`). Unedited.
- `LICENSE` — upstream MIT license, copied verbatim for attribution.
- `__init__.py` — makes it importable as `vendor.semantic_search.search`.
- A short `VENDOR.md` noting upstream source + "do not edit; re-sync instead."

### 2. `scripts/search.py` (the native wrapper)
Imports the vendored engine and exposes a small CLI. Exactly two forms:

- `python3 scripts/search.py index`
  - Resolves the research root: `./research` under cwd (or `--root PATH`).
  - Indexes only Bibles via the engine's `in_patterns=['*/README.md',
    '*/sections/*.md']`, db at `<root>/.semantic-index.db`.
  - Prints the engine's summary line.
- `python3 scripts/search.py "<query>"`  (query is a positional argument)
  - Queries the same index. `--topic <slug>` scopes via `in_patterns=['<slug>/**']`.
  - `--top N`, `--json` pass through.
  - `index` is a reserved first token (the index subcommand); any other first
    token is treated as the query string.

**Graceful-degradation gate — the contract the wrapper MUST honor:**
The wrapper performs ALL engine interaction (import, key resolution, and the
`cmd_index`/`cmd_query` calls themselves) inside guarded handling so that NO
prerequisite gap or engine failure can ever propagate as a nonzero exit:

1. **Lazy import inside the command handler**, wrapped in `try/except
   ImportError` — catches a missing vendored engine AND missing transitive deps
   (`sqlite-vec`, `apsw`, `openai`), since those only fail on import/first use.
   On failure: print a one-line notice naming `requirements-search.txt`, exit 0.
2. **Key check** before any embedding, **reusing deep-research's own env
   loader**: call `config.load_env_files()` (the repo's existing function:
   env → `~/.env` → `./.env`, never overriding an already-set value), then read
   the merged result. Note `load_env_files()` **returns a dict** (env → `~/.env`
   → `./.env`, first-set-wins; it does not mutate `os.environ`). The wrapper does:
   `merged = config.load_env_files(); key = merged.get("OPENAI_API_KEY")`, and if
   `key` is set, assigns `os.environ["OPENAI_API_KEY"] = key`. This guarantees the
   wrapper resolves the *exact same key with the exact same precedence* as the
   rest of deep-research — no divergence, no duplicated logic. (The vendored
   engine's own `load_openai_key` only checks env + `~/.env` and `sys.exit(1)`s on
   miss; because the wrapper has now set `os.environ["OPENAI_API_KEY"]`, the
   engine sees the key and never hits its `exit(1)`. If the key is still
   unresolved, the wrapper prints a one-line notice and exits 0.)
3. **Runtime guard:** the `cmd_index`/`cmd_query` calls run inside `try/except
   Exception`. See the single rule in the contract below.

### Exit-code rule (one rule, all cases)

**Every failure mode exits 0 with a one-line stderr notice. There is no nonzero
exit path.** This is the simplest contract that satisfies the hard requirement
("search failures skip with a notice and continue, never break the pipeline").

| Situation | `index` | `"<query>"` |
|---|---|---|
| Missing engine import / missing deps | exit 0 + notice | exit 0 + notice |
| Missing `OPENAI_API_KEY` (after `load_env_files()`) | exit 0 + notice | exit 0 + notice |
| Missing index db (not built yet) | n/a (index builds it) | exit 0 + "run `index` first" |
| Unexpected runtime error inside engine call | exit 0 + notice | exit 0 + notice |
| Success | exit 0 | exit 0 |

Rationale: collapsing to a single exit-0-on-any-failure rule removes all
ambiguity. `index` must never break a pipeline run; `query` is interactive and a
clear stderr notice serves the human better than a bare nonzero code. The
pipeline's index step never treats any exit code as fatal regardless.

### 3. Dependencies — `requirements-search.txt` (NOT base `requirements.txt`)
Create a new `requirements-search.txt` holding `sqlite-vec>=0.1.6` and
`apsw>=3.46` (the engine's runtime deps beyond `openai`, which base already has).
**No dependency lines are added to base `requirements.txt`** so `pip install -r
requirements.txt` can never fail on `sqlite-vec`/`apsw` and block core research.
The only permitted edit to base `requirements.txt` is a single trailing **comment**
(not a dep line) pointing to `requirements-search.txt`. Docs present search as
opt-in: `pip install -r requirements-search.txt`.

### 4. Pipeline wiring (`SKILL.md`)
Replace the prior external-path command and "install the companion skill" framing
with the bundled wrapper. The final step runs `python3 scripts/search.py index`
and is documented to **skip with a notice** if keys/deps are missing — the Bible
is complete without it. Add the clean query commands and update the output tree
(`research/.semantic-index.db`). Update the architecture diagram + execution
checklist accordingly.

### 5. `README.md`
Rewrite the semantic-index sections to the bundled, self-contained story:
install is the existing clone + `pip install`; semantic search is opt-in via
`pip install -r requirements-search.txt`; no companion skill. Document
`scripts/search.py index` and `scripts/search.py "<query>"` / `--topic`, and the
graceful-skip behavior. Note that `research/` (hence the index db) is already
git-ignored by the repo's `.gitignore` — do NOT imply a new ignore rule is
required; for users whose own project does not ignore `research/`, mention the
db path so they can ignore it if desired.

### 6. Tests (`tests/`)
A no-network test module for the wrapper (mock the engine functions; assert the
wrapper's wiring, not the engine internals). Covering the FULL graceful contract:
- research-root resolution (`./research` default and `--root`).
- `--topic` produces the correct scoping glob (`['<slug>/**']`).
- index uses the correct Bible globs (`['*/README.md', '*/sections/*.md']`).
- positional query is routed to `cmd_query`; first token `index` routes to index.
- **graceful skip when `OPENAI_API_KEY` is absent** → exit 0 + notice, no raise.
- **graceful skip when the engine import fails** (simulate `ImportError`, e.g.
  missing `sqlite-vec`/`apsw`) → exit 0 + notice naming `requirements-search.txt`.
- **graceful skip when `cmd_index` raises** at runtime → exit 0 + notice (index
  is best-effort).
- **missing index on query** → exit 0 + guidance (run `index` first), no raise.
- **key resolved from project-local `./.env`** → wrapper finds it via
  `config.load_env_files()` (not just env / `~/.env`) and proceeds; assert it does
  not falsely skip.
- **`cmd_query` raises a genuine runtime error** → query path exits **0** with a
  notice (single-rule contract: no nonzero path), confirming graceful handling.

## Graceful-degradation contract (the keystone)

- **Single rule: every failure exits 0 with a one-line stderr notice — no
  nonzero exit path exists.** Applies to both `index` and `query`, and to all
  failure classes: missing key, missing deps (`sqlite-vec`/`apsw`/`openai`),
  missing vendored engine, missing index db, and unexpected runtime errors inside
  the engine call. (See the exit-code table above.)
- The pipeline's index step is best-effort: its outcome never changes the run's
  success status, and the research output is already on disk before indexing runs.
- Install-time safety: search deps are isolated in `requirements-search.txt`, so
  a failed/unsupported `sqlite-vec`/`apsw` install cannot break the base
  `pip install -r requirements.txt` that core research needs.

## Out of scope

- No edits to the vendored engine (fork/patch upstream instead).
- No per-topic sub-indexes, no result enrichment/provenance links (Option 3 — deferred).
- No cross-project/global-filesystem index.
