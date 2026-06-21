# Bundle Semantic Search into deep-research — Implementation Plan

> **For Claude:** Execution uses **Agency** (per user CLAUDE.md), not subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking. Source of truth: `docs/superpowers/specs/2026-06-21-semantic-search-integration-design.md`.

**Goal:** Make deep-research a single self-contained repo by bundling the semantic-search engine and exposing a research-aware wrapper, with graceful degradation that never breaks core research.

**Architecture:** Vendor a pristine, importable copy of the engine at `vendor/semantic_search/`. A thin native wrapper `scripts/search.py` imports it, bakes in research conventions (root = `./research`, Bible globs, `--topic` scoping), reuses `config.load_env_files()` for key resolution, and guarantees every failure exits 0 with a notice. Search deps are isolated in `requirements-search.txt` so base install never breaks.

**Tech Stack:** Python 3, argparse, the vendored engine (OpenAI embeddings + sqlite-vec + FTS5), pytest with mocked engine (no network).

**Engine entrypoints (verified signatures):**
- `cmd_index(root: Path, db_path: Path, *, rebuild: bool, in_patterns: list[str] | None) -> None`
- `cmd_query(q: str, root: Path, db_path: Path, *, top_k: int, in_patterns: list[str] | None, as_json: bool) -> None` — **calls `sys.exit(2)` if db missing**
- `load_openai_key()` — **calls `sys.exit(1)` if key missing**
- Module global `_QUIET` controls progress output.

**Keystone:** because the engine uses `sys.exit()` internally, the wrapper's runtime guard MUST catch **both `Exception` and `SystemExit`**.

---

## Chunk 1: Bundle, wrap, document

### Task 1: Vendor the pristine engine

**Files:**
- Create: `vendor/__init__.py` (empty)
- Create: `vendor/semantic_search/__init__.py` (empty)
- Create: `vendor/semantic_search/search.py` (verbatim copy of upstream)
- Create: `vendor/semantic_search/LICENSE` (verbatim copy of upstream)
- Create: `vendor/semantic_search/VENDOR.md`

- [ ] **Step 1: Copy the engine + license verbatim**

```bash
mkdir -p vendor/semantic_search
cp /Users/noahraford/Dropbox/Noah_Remote_Shared/claude-brain/skills/semantic-search/search.py vendor/semantic_search/search.py
cp /Users/noahraford/Dropbox/Noah_Remote_Shared/claude-brain/skills/semantic-search/LICENSE vendor/semantic_search/LICENSE
touch vendor/__init__.py vendor/semantic_search/__init__.py
```

- [ ] **Step 2: Write `vendor/semantic_search/VENDOR.md`**

```markdown
# Vendored: semantic-search engine

This is a **pristine, unmodified** copy of the semantic-search engine
(`search.py`) bundled so deep-research is self-contained.

- **Do NOT edit `search.py` here.** Fix bugs/features upstream, then re-sync.
- Upstream source: the `semantic-search` skill (private).
- Re-sync: `cp <upstream>/search.py vendor/semantic_search/search.py`
- License: see `LICENSE` (MIT), copied verbatim for attribution.

deep-research interacts with this engine ONLY through `scripts/search.py`.
```

- [ ] **Step 3: Verify the engine imports as a module**

Run: `python3 -c "import sys; sys.path.insert(0,'.'); from vendor.semantic_search import search; print(hasattr(search,'cmd_index'), hasattr(search,'cmd_query'))"`
Expected: `True True`

- [ ] **Step 4: Commit**

```bash
git add vendor/
git commit -m "Vendor pristine semantic-search engine into vendor/semantic_search/"
```

**Acceptance:** engine importable as `vendor.semantic_search.search`; `search.py` byte-identical to upstream; LICENSE present.

---

### Task 2: Isolate optional search dependencies

**Files:**
- Create: `requirements-search.txt`
- Modify: `requirements.txt` (append a comment line ONLY — no dep lines)

- [ ] **Step 1: Create `requirements-search.txt`**

```
# Optional — semantic search over your research (scripts/search.py).
# Install with:  pip install -r requirements-search.txt
# Core research does NOT need these; without them, search skips gracefully.
sqlite-vec>=0.1.6
apsw>=3.46
# openai is already in base requirements.txt
```

- [ ] **Step 2: Append a pointer COMMENT to base `requirements.txt`**

Append (comment only — adds no installable dependency):

```
# Optional: semantic search over your research — see requirements-search.txt
```

- [ ] **Step 3: Verify base requirements has no new dep lines**

Run: `git diff requirements.txt | grep '^+' | grep -vE '^\+#|^\+\+\+'`
Expected: no output (only a comment was added).

- [ ] **Step 4: Commit**

```bash
git add requirements.txt requirements-search.txt
git commit -m "Isolate search deps in requirements-search.txt (base install stays safe)"
```

**Acceptance:** base `pip install -r requirements.txt` unaffected; search deps opt-in.

---

### Task 3: Write the wrapper tests FIRST (TDD)

**Files:**
- Test: `tests/test_search_wrapper.py`

The tests import the wrapper as a module and call a dispatch function
`run(argv: list[str]) -> int` (the wrapper exposes this for testability; `main()`
calls `sys.exit(run(sys.argv[1:]))`). The engine is monkeypatched so no network
or sqlite work happens. Tests assert wiring + the exit-0 contract.

- [ ] **Step 1: Write the failing tests**

```python
import os, sys, types
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import scripts.search as w  # the wrapper


@pytest.fixture
def fake_engine(monkeypatch):
    """Install a fake vendored engine; record calls. Key resolves True."""
    calls = {}
    eng = types.SimpleNamespace()
    def cmd_index(root, db_path, *, rebuild, in_patterns):
        calls["index"] = dict(root=root, db_path=db_path, rebuild=rebuild, in_patterns=in_patterns)
    def cmd_query(q, root, db_path, *, top_k, in_patterns, as_json):
        calls["query"] = dict(q=q, root=root, db_path=db_path, top_k=top_k, in_patterns=in_patterns, as_json=as_json)
    eng.cmd_index = cmd_index
    eng.cmd_query = cmd_query
    monkeypatch.setattr(w, "_load_engine", lambda: eng)
    monkeypatch.setattr(w, "_resolve_key", lambda: True)
    return calls


def _make_index(tmp_path):
    """Create research/.semantic-index.db so _do_query reaches the engine call."""
    r = tmp_path / "research"
    r.mkdir(exist_ok=True)
    (r / ".semantic-index.db").write_bytes(b"x")
    return r


# --- wiring ---------------------------------------------------------------

def test_index_uses_bible_globs_and_research_root(fake_engine, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert w.run(["index"]) == 0
    assert fake_engine["index"]["in_patterns"] == ["*/README.md", "*/sections/*.md"]
    assert fake_engine["index"]["root"] == (tmp_path / "research").resolve()
    assert fake_engine["index"]["db_path"] == (tmp_path / "research").resolve() / ".semantic-index.db"
    assert fake_engine["index"]["rebuild"] is False


def test_index_honors_root_flag(fake_engine, tmp_path):
    target = tmp_path / "custom"
    assert w.run(["index", "--root", str(target)]) == 0
    assert fake_engine["index"]["root"] == target.resolve()


def test_query_positional_routed(fake_engine, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _make_index(tmp_path)
    assert w.run(["why does X happen?"]) == 0
    assert fake_engine["query"]["q"] == "why does X happen?"
    assert fake_engine["query"]["in_patterns"] is None
    assert fake_engine["query"]["top_k"] == 5


def test_topic_scopes_glob(fake_engine, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _make_index(tmp_path)
    assert w.run(["risks", "--topic", "cbdc"]) == 0
    assert fake_engine["query"]["in_patterns"] == ["cbdc/**"]


def test_no_query_is_graceful(fake_engine, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert w.run([]) == 0
    assert "index" in capsys.readouterr().err


# --- graceful degradation (assert exit 0 AND the notice text) -------------

def test_missing_key_skips_exit0(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(w, "_load_engine", lambda: types.SimpleNamespace(
        cmd_index=lambda *a, **k: None, cmd_query=lambda *a, **k: None))
    monkeypatch.setattr(w, "_resolve_key", lambda: False)
    assert w.run(["index"]) == 0
    assert w.run(["some query"]) == 0
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_import_failure_names_requirements_file_exit0(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    def boom():
        raise ImportError("No module named 'sqlite_vec'")
    monkeypatch.setattr(w, "_load_engine", boom)
    assert w.run(["index"]) == 0
    assert "requirements-search.txt" in capsys.readouterr().err
    # query path import failure also names the requirements file
    assert w.run(["q"]) == 0
    assert "requirements-search.txt" in capsys.readouterr().err


def test_index_runtime_error_skips_exit0(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    eng = types.SimpleNamespace()
    eng.cmd_index = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
    monkeypatch.setattr(w, "_load_engine", lambda: eng)
    monkeypatch.setattr(w, "_resolve_key", lambda: True)
    assert w.run(["index"]) == 0
    assert "indexing failed" in capsys.readouterr().err


def test_bad_args_exit0(monkeypatch, tmp_path, capsys):
    """argparse errors (unknown flag / bad type) must NOT propagate nonzero."""
    monkeypatch.chdir(tmp_path)
    assert w.run(["index", "--bogus"]) == 0
    assert w.run(["--bogus", "q"]) == 0
    assert "invalid arguments" in capsys.readouterr().err


def test_missing_index_gives_guidance_exit0(monkeypatch, tmp_path, capsys):
    """No db on disk -> _do_query short-circuits with 'run index' guidance, exit 0."""
    monkeypatch.chdir(tmp_path)  # NOTE: no _make_index here
    eng = types.SimpleNamespace(cmd_index=lambda *a, **k: None,
                                cmd_query=lambda *a, **k: None)
    monkeypatch.setattr(w, "_load_engine", lambda: eng)
    monkeypatch.setattr(w, "_resolve_key", lambda: True)
    assert w.run(["anything"]) == 0
    assert "index" in capsys.readouterr().err


def test_query_engine_sysexit_caught_exit0(monkeypatch, tmp_path, capsys):
    """Engine sys.exit(2) (e.g. db race) must be caught -> exit 0.
    DB exists so we get past the missing-index guard into the engine call."""
    monkeypatch.chdir(tmp_path); _make_index(tmp_path)
    def cmd_query(*a, **k):
        raise SystemExit(2)
    eng = types.SimpleNamespace(cmd_query=cmd_query, cmd_index=lambda *a, **k: None)
    monkeypatch.setattr(w, "_load_engine", lambda: eng)
    monkeypatch.setattr(w, "_resolve_key", lambda: True)
    assert w.run(["anything"]) == 0
    assert "search failed" in capsys.readouterr().err


def test_query_runtime_error_exit0(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path); _make_index(tmp_path)
    eng = types.SimpleNamespace(
        cmd_query=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        cmd_index=lambda *a, **k: None)
    monkeypatch.setattr(w, "_load_engine", lambda: eng)
    monkeypatch.setattr(w, "_resolve_key", lambda: True)
    assert w.run(["anything"]) == 0
    assert "search failed" in capsys.readouterr().err


def test_resolve_key_uses_config_loader(monkeypatch):
    """_resolve_key reads via config.load_env_files (which honors ./.env) and
    sets os.environ. We mock the loader to avoid depending on the dev's real
    ~/.env precedence (config.py has its own precedence tests)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sys.path.insert(0, str(REPO))
    import config
    monkeypatch.setattr(config, "load_env_files",
                        lambda *a, **k: {"OPENAI_API_KEY": "sk-local-test"})
    assert w._resolve_key() is True
    assert os.environ.get("OPENAI_API_KEY") == "sk-local-test"
```

- [ ] **Step 2: Run tests — verify they FAIL (module not yet written / no `run`)**

Run: `python3 -m pytest tests/test_search_wrapper.py -q`
Expected: FAIL (ImportError or AttributeError on `scripts.search`).

---

### Task 4: Implement the wrapper

**Files:**
- Create: `scripts/search.py`

- [ ] **Step 1: Write `scripts/search.py`**

```python
#!/usr/bin/env python3
"""deep-research — semantic search over your research (native wrapper).

Bundles the vendored semantic-search engine and bakes in deep-research
conventions: ONE project-wide index over each topic's Bible
(README.md + sections/*.md) at research/.semantic-index.db.

GRACEFUL DEGRADATION: every failure mode exits 0 with a one-line stderr notice.
Semantic search is strictly additive and must never break a research run.

Usage:
    python3 scripts/search.py index [--root PATH]
    python3 scripts/search.py "<query>" [--topic SLUG] [--top N] [--json]
"""
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIBLE_GLOBS = ["*/README.md", "*/sections/*.md"]
DB_NAME = ".semantic-index.db"
SEARCH_REQ = "requirements-search.txt"


def _notice(msg: str) -> None:
    print(f"[semantic-search skipped] {msg}", file=sys.stderr)


def _ensure_path() -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def _load_engine():
    """Import the vendored engine. Raises ImportError if deps/engine missing."""
    _ensure_path()
    from vendor.semantic_search import search as engine
    return engine


def _resolve_key() -> bool:
    """Populate os.environ['OPENAI_API_KEY'] using deep-research's own loader
    (env -> ~/.env -> ./.env, first-set-wins). Returns True if a key is available."""
    if os.environ.get("OPENAI_API_KEY"):
        return True
    try:
        _ensure_path()
        import config
        merged = config.load_env_files()
        key = merged.get("OPENAI_API_KEY")
        if key:
            os.environ["OPENAI_API_KEY"] = key
    except Exception:
        pass
    return bool(os.environ.get("OPENAI_API_KEY"))


def _research_root(arg_root) -> Path:
    return Path(arg_root).resolve() if arg_root else (Path.cwd() / "research").resolve()


def _do_index(root: Path) -> int:
    try:
        engine = _load_engine()
    except ImportError as e:
        _notice(f"search dependencies not installed ({e}). Run: pip install -r {SEARCH_REQ}")
        return 0
    if not _resolve_key():
        _notice("OPENAI_API_KEY not found (env, ./.env, or ~/.env).")
        return 0
    db = root / DB_NAME
    try:
        engine.cmd_index(root, db, rebuild=False, in_patterns=BIBLE_GLOBS)
    except (Exception, SystemExit) as e:  # engine may sys.exit internally
        _notice(f"indexing failed ({e!r}); run completed without it.")
        return 0
    return 0


def _do_query(query: str, topic, top: int, as_json: bool) -> int:
    try:
        engine = _load_engine()
    except ImportError as e:
        _notice(f"search dependencies not installed ({e}). Run: pip install -r {SEARCH_REQ}")
        return 0
    if not _resolve_key():
        _notice("OPENAI_API_KEY not found (env, ./.env, or ~/.env).")
        return 0
    root = _research_root(None)
    db = root / DB_NAME
    if not db.exists():
        _notice(f"no index yet at {db}. Run: python3 scripts/search.py index")
        return 0
    in_patterns = [f"{topic}/**"] if topic else None
    try:
        engine.cmd_query(query, root, db, top_k=top, in_patterns=in_patterns, as_json=as_json)
    except (Exception, SystemExit) as e:  # engine sys.exit(2) on missing db, etc.
        _notice(f"search failed ({e!r}).")
        return 0
    return 0


def run(argv) -> int:
    """Manual dispatch — NOT argparse subparsers. Subparsers would treat the
    first token as a subcommand and reject a normal query like
    `search.py "why does X happen?"` with SystemExit(2). Rule: first token
    'index' => index subcommand; ANY other first token => positional query.

    argparse calls sys.exit() on bad args (and on --help). We catch that
    SystemExit so the wrapper honors the absolute 'every failure exits 0'
    contract — a malformed invocation prints a notice and exits 0, never nonzero.
    """
    argv = list(argv)
    try:
        if argv and argv[0] == "index":
            ip = argparse.ArgumentParser(prog="scripts/search.py index")
            ip.add_argument("--root", default=None, help="research root (default ./research)")
            a = ip.parse_args(argv[1:])
            return _do_index(_research_root(a.root))

        qp = argparse.ArgumentParser(
            prog="scripts/search.py",
            description="Semantic search over your deep-research output.",
        )
        qp.add_argument("query", nargs="?", default=None, help="natural-language query")
        qp.add_argument("--topic", default=None, help="scope search to one topic slug")
        qp.add_argument("--top", type=int, default=5, help="results to return (default 5)")
        qp.add_argument("--json", action="store_true", help="emit JSONL")
        a = qp.parse_args(argv)
    except SystemExit as e:
        # --help exits 0 (help text already printed); bad args exit nonzero.
        if e.code not in (0, None):
            _notice("invalid arguments; run: python3 scripts/search.py --help")
        return 0
    if not a.query:
        _notice("provide a query, or run: python3 scripts/search.py index")
        return 0
    return _do_query(a.query, a.topic, a.top, a.json)


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the wrapper tests — verify PASS**

Run: `python3 -m pytest tests/test_search_wrapper.py -q`
Expected: all tests PASS.

- [ ] **Step 3: Smoke-test graceful skip with no deps/key in a temp dir**

Run: `cd /tmp && OPENAI_API_KEY= python3 /Users/noahraford/Projects/deep-research/scripts/search.py "test" ; echo "exit=$?"`
Expected: a `[semantic-search skipped]` notice on stderr and `exit=0`.

- [ ] **Step 4: Confirm existing tests still pass**

Run: `cd /Users/noahraford/Projects/deep-research && python3 -m pytest tests/ -q`
Expected: all pass (new + existing).

- [ ] **Step 5: Commit**

```bash
git add scripts/search.py tests/test_search_wrapper.py
git commit -m "Add research-aware semantic-search wrapper + graceful-degradation tests"
```

**Acceptance:** all tests pass; wrapper exits 0 on every failure mode; index uses Bible globs at `research/.semantic-index.db`; `--topic` scopes; key resolves via `config.load_env_files()`.

---

### Task 5: Rewrite SKILL.md docs (bundled story)

**Files:**
- Modify: `SKILL.md` (the "Index for semantic search" subsection + architecture diagram + execution checklist added in PR #2)

- [ ] **Step 1: Replace the external-path command and "companion skill" framing**

Replace the prior `~/.claude/skills/semantic-search/search.py ... --cwd ... --in ...` invocation with the bundled wrapper:
- Index: `python3 scripts/search.py index`
- Query: `python3 scripts/search.py "<query>"` and `--topic <slug>`

Document: deps are opt-in via `pip install -r requirements-search.txt`; the step **skips with a notice (never fails the run)** if deps/key absent; reuses `OPENAI_API_KEY`. Keep the `research/.semantic-index.db` output-tree entry. Update the checklist line to call the wrapper.

- [ ] **Step 2: Verify no stale external path remains**

Run: `grep -n "skills/semantic-search" SKILL.md ; echo "---"; grep -n "companion" SKILL.md`
Expected: no matches (external framing fully removed).

- [ ] **Step 3: Commit**

```bash
git add SKILL.md
git commit -m "SKILL.md: document bundled semantic search (drop external-companion framing)"
```

**Acceptance:** SKILL.md describes only the bundled `scripts/search.py` flow + graceful skip.

---

### Task 6: Rewrite README.md docs (bundled story)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the pipeline diagram, "What's new" bullet, Use section, output tree**

- Pipeline: add an `Index` line (bundled, after Export).
- "What's new" bullet: semantic index is **bundled**; opt-in deps; graceful skip.
- "Use" → direct scripts: add `python3 scripts/search.py index`.
- Add a "Searching what you've researched" subsection: `scripts/search.py "<query>"`, `--topic`.
- Output tree: `research/.semantic-index.db` at the root.
- Optional-install note: `pip install -r requirements-search.txt` (NOT a companion skill).

- [ ] **Step 2: Verify**

Run: `grep -n "requirements-search.txt\|scripts/search.py" README.md`
Expected: present. `grep -n "skills/semantic-search\|companion skill" README.md` → no matches.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "README: document bundled, self-contained semantic search"
```

**Acceptance:** README tells the self-contained story; no external-install instruction.

---

### Task 7: Final verification + redeploy

**Files:** none (verification + deployment)

- [ ] **Step 1: Full test suite green**

Run: `cd /Users/noahraford/Projects/deep-research && python3 -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 2: Engine still byte-identical to upstream (pristine vendor check)**

Run: `diff vendor/semantic_search/search.py /Users/noahraford/Dropbox/Noah_Remote_Shared/claude-brain/skills/semantic-search/search.py && echo IDENTICAL`
Expected: `IDENTICAL`.

- [ ] **Step 3: Two-stage review on the combined branch diff** (handled by /do-it Step 4)

- [ ] **Step 4: After merge to main — redeploy full repo to both live copies**

```bash
SRC=/Users/noahraford/Projects/deep-research/
for DEST in ~/.claude/skills/deep-research/ "/Users/noahraford/Dropbox/Noah_Remote_Shared/claude-brain/skills/deep-research/"; do
  rsync -a --delete --exclude='.git/' --exclude='__pycache__/' --exclude='*.pyc' \
    --exclude='.pytest_cache/' --exclude='.env' --exclude='.env.*' \
    --exclude='deep-research.toml' --exclude='config.toml' "$SRC" "$DEST"
done
```

Expected: both copies contain `vendor/semantic_search/` + `scripts/search.py`.

**Acceptance:** tests green; vendored engine pristine; both deployments updated.

---

## Rollback

All work is on branch `feat/bundle-semantic-search`. Rollback = don't merge, or `git revert` the merge commit. The vendored engine and `scripts/search.py` are additive; reverting them plus the doc edits restores prior behavior. No data migrations, no destructive operations.
