# deep-research

Five research strategies run in parallel — each by a provider you configure — with domain scoping, adversarial cross-validation, and mechanical citation verification. A Claude Code skill that runs five agent types (academic, practitioner, real-time, grey-literature, contrarian) against the same topic with differentiated strategies, compares their outputs adversarially, integrates them by topic section, verifies every citation against OpenAlex/Crossref, and runs an optional iterative deepening pass. Produces a fact-checked, fully-cited "Research Bible" plus BibTeX and a machine-readable claims file.

## What it does

Most LLM research is one model, one pass, hallucinated citations. This is five research strategies in parallel — each via a configured provider — six rounds, mechanical citation resolution, and budget-aware execution.

```
Round 0  Domain scoping — classify topic, propose source priorities
Round 1  Five agent types research in parallel — each with a different strategy
         ├─ academic         (default: Claude)      → Academic deep dive (journals, NBER, SSRN)
         ├─ practitioner     (default: ChatGPT)     → Practitioner & explainer (industry, methodology)
         ├─ real-time        (default: Perplexity)  → Real-time web (current news, live citations)
         ├─ grey-literature  (default: Gemini)      → Grey literature & primary sources (govt, IGO, treaties)
         └─ contrarian       (default: Grok)        → Contrarian & cross-disciplinary (dissent, outside views)
Round 2  Adversarial comparison + citation-laundering detection + completeness map
Round 3  Three section planners + reconciler → parallel integration agents
Round 4  Mechanical citation verification (Crossref/OpenAlex) + source tier audit
         + missing-literature check + adversarial fact-check + fix pass
Round 5  (optional) Iterative deepening on weak sections, cap 2 iterations
Output   Hub-and-spoke Research Bible + BibTeX + claims.jsonl + provenance
```

## What's new vs. a one-shot LLM

- **Domain scoping** — classifies topic before Round 1, injects domain-specific source priorities (PubMed for medicine, NBER for economics, arXiv for tech, etc.)
- **Date stamping** — every time-sensitive claim carries `[as of: <date>]`
- **Confidence tagging** — high-stakes claims carry `[confidence: high/medium/low]`
- **Cross-model support tags** — `[4/5 support]` shows how many models agree on a claim
- **Citation-laundering detection** — flags when N models cite the same secondary source as if it were N confirmations
- **Mechanical citation verification** — resolves every `[Author, Year]` against OpenAlex and Crossref (free, no key)
- **Source tier audit** — scores bibliography quality (peer-reviewed vs blog vs wiki)
- **Missing-literature check** — compares against OpenAlex top-N to flag canonical works absent from the bibliography
- **Multi-language search** — `--languages en,fr,de,zh` finds non-English primary sources
- **Cost gate + resume** — pre-flight estimate, `--max-cost-usd` hard cap, `--resume` recovers from partial failure
- **BibTeX + JSONL export** — machine-readable downstream consumption

## Install

```bash
# 1. Clone into your Claude skills directory
git clone https://github.com/nraford7/deep-research.git ~/.claude/skills/deep-research

# 2. Install Python deps
pip install -r ~/.claude/skills/deep-research/requirements.txt

# 3. Set whichever API keys you have
cp ~/.claude/skills/deep-research/.env.example ~/.env
# edit ~/.env and fill in keys
```

The skill auto-detects which keys are set. Missing keys = that model skipped, no failure. **One key works. Three or more is the sweet spot. Five is maximum.**

## Use

In Claude Code:

```
/deep-research [your topic and scope]
```

The skill walks the agent through all six rounds. Or invoke the dispatcher and helper scripts directly:

```bash
# 1. Domain scoping
python3 scripts/scope.py \
  --topic "Central bank digital currencies" \
  --scope "Design, adoption, monetary-policy implications" \
  --output research/cbdc/round0/scope.md \
  --use-llm

# 2. Pre-flight cost estimate
python3 dispatch.py --topic "..." --scope "..." \
  --output-dir research/cbdc/round1/ \
  --scope-file research/cbdc/round0/scope.json \
  --estimate-only

# 3. Round 1 dispatch with budget cap
python3 dispatch.py --topic "..." --scope "..." \
  --output-dir research/cbdc/round1/ \
  --scope-file research/cbdc/round0/scope.json \
  --languages en,zh \
  --max-cost-usd 50 \
  --resume

# 4. Bibliography dedup (after Round 3 integration)
python3 scripts/dedup_bib.py research/cbdc/round1/agent-*.md \
  --output research/cbdc/sections/bibliography.md

# 5. Round 4 mechanical verification
python3 scripts/verify_citations.py research/cbdc/sections/ \
  --output research/cbdc/round4/citation-verification.md --check-urls
python3 scripts/classify_sources.py research/cbdc/sections/bibliography.md \
  --output research/cbdc/round4/tier-report.md
python3 scripts/lit_search.py --topic "CBDC monetary policy" --limit 50 \
  --compare-bib research/cbdc/sections/bibliography.md \
  --output research/cbdc/round4/missing-lit.md

# 6. Export
python3 scripts/export.py \
  --sections research/cbdc/sections/ \
  --bibliography research/cbdc/sections/bibliography.md \
  --output-dir research/cbdc/export/
```

## API keys

| Env var | Purpose | Get a key |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude | https://console.anthropic.com |
| `OPENAI_API_KEY` | ChatGPT | https://platform.openai.com |
| `PERPLEXITY_API_KEY` | Perplexity Deep Research | https://www.perplexity.ai/settings/api |
| `GOOGLE_API_KEY` | Gemini | https://aistudio.google.com/apikey |
| `XAI_API_KEY` | Grok | https://console.x.ai |
| `SEMANTIC_SCHOLAR_KEY` | Optional — raises rate limit on `lit_search.py` | https://www.semanticscholar.org/product/api |
| `CONTACT_EMAIL` | Optional — joins OpenAlex/Crossref "polite pool" | — |

The dispatcher reads from `~/.env` and `./.env` automatically. Or export them in your shell.

Providers can also be defined in TOML for arbitrary OpenAI-compatible endpoints. Copy `config.toml.example` to `./deep-research.toml` or `~/.config/deep-research/config.toml` and fill in inline keys. TOML config augments env keys — built-in providers still activate from env vars. Both TOML paths are gitignored.

> **Model-ID drift warning:** Provider model IDs change over time (e.g. DeepSeek legacy IDs retire 2026-07-24). Always verify current IDs in provider docs. `max_tokens` must not exceed each model's output cap.

**Free APIs (no key required):** OpenAlex, Crossref, Semantic Scholar (low rate).

## Helper scripts

| Script | Purpose |
|---|---|
| `scripts/scope.py` | Domain classification + source priority recommendations (rule-based + optional Claude) |
| `scripts/cost.py` | Cost estimator with budget gate |
| `scripts/verify_citations.py` | Resolve every citation against OpenAlex + Crossref; flag unresolved, weak matches, orphans, dead URLs |
| `scripts/dedup_bib.py` | DOI-normalized + fuzzy-title bibliography merge with audit log |
| `scripts/classify_sources.py` | Tier classifier (peer-reviewed / institutional / book / news / blog / wiki) + quality score |
| `scripts/lit_search.py` | Query OpenAlex + Semantic Scholar; optionally compare against finished bibliography to flag missing canonical works |
| `scripts/export.py` | Emit BibTeX (`bibliography.bib`) + JSONL (`claims.jsonl`) from final Bible |

## Output

```
research/<topic-slug>/
├── README.md                  ← The hub: index, exec summary, key findings
├── sections/
│   ├── 01-<name>.md           ← Integrated topic sections (each 8k–20k words)
│   ├── 02-<name>.md
│   └── bibliography.md        ← Deduplicated master bibliography
├── export/
│   ├── bibliography.bib       ← BibTeX
│   └── claims.jsonl           ← Inline citations with surrounding sentence
├── round4/
│   ├── citation-verification.md  ← Mechanical OpenAlex/Crossref resolution
│   ├── tier-report.md            ← Source quality breakdown
│   ├── missing-lit.md            ← Canonical works absent
│   ├── factcheck-*.md            ← Adversarial fact-check reports
│   └── fix-log.md
└── round0..round5/            ← Provenance preserved
```

## Why five strategies, not one

- **Hallucination triangulation** — a fake citation rarely appears in three reports from different providers
- **Mechanical backstop** — `verify_citations.py` resolves every cite against OpenAlex/Crossref; what agents invent, the resolver catches
- **Coverage** — each agent type has a different strategy and each provider has different blind spots; cross-section completeness map exposes them
- **Citation quality** — Perplexity finds live web sources, Gemini surfaces primary documents, Claude follows academic citation chains
- **Disagreement is signal** — when providers split on a figure, that becomes a `[disputed: ...]` tag, not a silent average
- **Citation laundering caught** — Round 2 flags when N agents cite the same secondary source as if it were N confirmations

See `SKILL.md` for the full architecture, prompt templates, and failure modes.

## Tests

Minimal regression tests for the parser functions (citation regex, bibliography
parsers, dedup, BibTeX key, DOI normalization, source classification):

```bash
python3 tests/test_parsers.py
# or
python3 -m pytest tests/
```

## License

MIT — see `LICENSE`.

## Credits

Built for use inside Claude Code as a slash-command skill. Adapt freely.
