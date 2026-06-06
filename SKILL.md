---
name: deep-research
description: Use when the user needs comprehensive, fact-checked, evidence-based research on any topic. Triggers on requests for deep research, literature reviews, comprehensive reports, or evidence-based analysis. Runs domain scoping, multi-model parallel research, adversarial cross-validation, integration, mechanical citation verification, and optional iterative deepening to produce a single authoritative reference document.
---

# Deep Research

Five-model parallel deep research (Claude + ChatGPT + Perplexity + Gemini + Grok) with domain scoping, adversarial cross-validation, mechanical citation verification, and optional iterative deepening. Each model gets the same topic but a differentiated research strategy matching its strengths. Produces a single, fact-checked, fully-cited reference document — a "Research Bible."

## Prerequisites

**API keys** — set whichever you have. The dispatcher auto-detects available keys and only calls models you've configured:
```
ANTHROPIC_API_KEY    # Claude Opus (claude-opus-4-20250514)
OPENAI_API_KEY       # OpenAI GPT-4.1
PERPLEXITY_API_KEY   # Perplexity Deep Research (sonar-deep-research)
GOOGLE_API_KEY       # Gemini 2.5 Pro
XAI_API_KEY          # Grok 3 (grok-3-latest)
SEMANTIC_SCHOLAR_KEY # Optional — raises rate limit for lit_search.py
CONTACT_EMAIL        # Optional — joins OpenAlex/Crossref "polite pool"
```

No key = that model is skipped with a notice. At least one key required. **More models = better cross-validation.**

Providers can also be defined in TOML (see [Provider/Agent Config](#provideragent-config-toml)) for arbitrary OpenAI-compatible endpoints — without touching your environment.

**Python packages**:
```bash
pip install -r requirements.txt
```

## Provider/Agent Config (TOML)

The dispatcher uses two independent axes of configuration:

- **Providers** — LLM engines. Each provider has `api_type` (`openai`/`anthropic`/`gemini`), `api_key` (inline key) or `api_key_env` (name of an environment variable holding the key — use this to avoid embedding secrets in TOML), `base_url` (for OpenAI-compatible endpoints), `model`, `max_tokens`, `capabilities` (e.g. `["web_search"]`), `pricing`, `fallback_models`, and `max_concurrency`.
- **Agent types** — Research strategies. Five are built-in (`academic`, `practitioner`, `real-time`, `grey-literature`, `contrarian`). Each has a `strategy` prompt and an optional `provider` override. Agent types are remappable and extensible.

**Config discovery order** (later overrides earlier):
1. `~/.config/deep-research/config.toml`
2. `./deep-research.toml`

TOML config **augments** `~/.env` — built-in providers still activate automatically when their env-var API key is set. TOML entries add new providers or override existing ones; you do not need to re-specify built-ins unless you want to change their model or settings.

**Inline API keys are supported in TOML** — see `config.toml.example` at the repo root. Copy it to `./deep-research.toml` or `~/.config/deep-research/config.toml` and fill in your keys. Both paths are gitignored.

> **Model-ID drift warning:** Provider model IDs change. For example, DeepSeek legacy IDs `deepseek-reasoner` and `deepseek-chat` retire 2026-07-24 in favour of `deepseek-v4-*`; GLM model IDs also shift. Always verify the current ID in the provider's docs. `max_tokens` must stay within each model's output cap — exceeding it causes a 400 error.

## When to Use

- User asks for deep research, comprehensive analysis, or evidence-based report on a topic
- User says `/deep-research [topic]`
- User needs a literature review, state-of-knowledge summary, or authoritative reference
- Any research task where accuracy, citation quality, and completeness matter more than speed

## Architecture: Six Rounds

```
Round 0  DOMAIN SCOPING (rule-based + optional LLM)
              ↓
Round 1  MULTI-MODEL RESEARCH (parallel)
         ┌─ Claude     ── Academic deep dive
         ├─ ChatGPT    ── Practitioner & explainer
         ├─ Perplexity ── Real-time web + citations
         ├─ Gemini     ── Grey literature & primary sources
         └─ Grok       ── Contrarian & cross-disciplinary
              ↓
Round 2  ADVERSARIAL COMPARISON + citation-laundering detection
              ↓
Round 3  INTEGRATION (3-planner section reconciliation, then parallel section agents)
              ↓
Round 4  MECHANICAL VERIFICATION (Crossref/OpenAlex resolver) + adversarial fact-check + fix pass
              ↓
Round 5  (optional) ITERATIVE DEEPENING — rerun weak sections, cap 2 iterations
              ↓
OUTPUT   Hub-and-spoke Research Bible + BibTeX + claims.jsonl
```

## Round 0: Domain Scoping (NEW)

Before any models are called, run the scoping agent. It classifies the topic into a domain (medicine, law, economics, geopolitics, technology, physical sciences, social sciences) and proposes domain-specific source priorities (which databases, journals, repositories, regulatory filings to weight).

```bash
python3 scripts/scope.py \
  --topic "Your topic" \
  --scope "Your scope" \
  --output research/[topic-slug]/round0/scope.md \
  --use-llm   # optional — refines with Claude
```

The output is injected into every Round 1 agent prompt via `--scope-file`, so each agent knows which sources to weight. **This is the single largest credibility upgrade in the pipeline** — a generic prompt produces generic sources.

## Round 1: Multi-Model Parallel Research

### Step 1.1: Pre-flight cost check

```bash
python3 dispatch.py --topic "..." --scope "..." --output-dir ./round1/ \
    --scope-file ./round0/scope.json \
    --estimate-only
```

The dispatcher prints a cost estimate per agent. Round 1 alone runs $5–40 depending on which agent types are enabled; full pipeline (rounds 2–5) typically adds 50–80% on top.

### Step 1.2: Dispatch with budget gate and language list

```bash
python3 dispatch.py \
  --topic "Your research topic here" \
  --scope "Detailed scope: what to cover, subtopics, depth, time period..." \
  --output-dir ./research/[topic-slug]/round1/ \
  --scope-file ./research/[topic-slug]/round0/scope.json \
  --languages en,fr,de,zh \
  --max-cost-usd 50 \
  --resume
```

| Flag | Purpose |
|---|---|
| `--scope-file` | Injects Round 0 domain priorities into each agent's prompt |
| `--languages` | Tells agents to also search non-English primary sources |
| `--max-cost-usd` | Hard cap; aborts if estimated cost exceeds it |
| `--resume` | Skip agent types whose output file already exists (recovers from partial failure) |
| `--no-confirm` | Skip the interactive cost prompt |
| `--estimate-only` | Print estimate and exit |
| `--agents` | Run a subset of agent types, e.g. `--agents academic,real-time,contrarian` (default: all) |

### Step 1.3: Agent types and default provider pairings

| Agent type | Default provider | Strategy | Why this pairing |
|---|---|---|---|
| **academic** | Claude (claude-opus-4-20250514) | Academic deep dive — journals, NBER, SSRN, citation chains | Best at long-form analytical synthesis |
| **practitioner** | ChatGPT (gpt-4.1) | Practitioner & explainer — white papers, industry reports | Strong structured analysis |
| **real-time** | Perplexity (sonar-deep-research) | Real-time web — current news, recent data, live citations | Built-in deep web search; requires `web_search` capability |
| **grey-literature** | Gemini (gemini-2.5-pro) | Grey literature & primary sources — governmental, IGO, treaty | Largest context, strong document analysis |
| **contrarian** | Grok (grok-3-latest) | Contrarian & cross-disciplinary — dissent, alternative framings | Challenges consensus |

The default provider is used when the built-in env-var key is present. Override any pairing via `[agents.<name>] provider = "..."` in TOML. Add entirely new agent types the same way.

> **Real-time guard:** The `real-time` agent type requires a provider with `capabilities = ["web_search"]` (e.g. perplexity). If no such provider is configured, a console warning is printed and the report file is prefixed with `> [no live web search — knowledge-cutoff results]` so a stale answer is never silently filed under a real-time heading.

### Round 1 prompt rules — encoded in `dispatch.py`

Every Round 1 agent prompt enforces:

- **No fabrication.** "Mark UNVERIFIED rather than guess."
- **Date stamping.** Any year/statistic/"current" claim must carry `[as of: <date>]`.
- **Confidence tagging.** High-stakes empirical claims get `[confidence: high/medium/low — <one-line reason>]`.
- **Source preference.** Primary > institutional > peer-reviewed > news > blog > wiki.
- **Multilingual.** If `--languages` includes non-English, cite original-language titles.

### Step 1.4: Citation supplement with Claude Code subagent

After the dispatcher completes, dispatch **one additional Claude Code subagent** with WebSearch/WebFetch tools to fill gaps identified in the manifest. This agent can verify URLs, fetch specific documents, and search Google Scholar — capabilities the raw API calls lack.

```
Dispatch a Claude Code background agent that:
1. Reads all 4-5 round1 files
2. Uses WebSearch to verify 20-30 key citations from each report
3. Fetches any URLs that other models cited but couldn't verify
4. Writes a verification overlay to round1/citation-verification.md
```

### Output Location

```
[project]/research/[topic-slug]/
├── round0/
│   ├── scope.md                       ← Domain classification + priorities
│   └── scope.json                     ← Machine-readable (used by dispatch.py)
├── round1/
│   ├── agent-academic.md
│   ├── agent-practitioner.md
│   ├── agent-real-time.md
│   ├── agent-grey-literature.md
│   ├── agent-contrarian.md
│   ├── citation-verification.md
│   ├── excerpts/                      ← Pre-extracted section excerpts
│   └── manifest.json                  ← Includes `assignments` map (agent-type → provider)
├── round2/
│   └── adversarial-comparison.md
├── round3/
│   ├── section-plans/                 ← 3 independent planner outputs
│   │   ├── planner-1.md
│   │   ├── planner-2.md
│   │   ├── planner-3.md
│   │   └── reconciled-plan.md
│   ├── section-01-[topic].md
│   ├── section-02-[topic].md
│   ├── ...
│   ├── section-bibliography.md
│   └── cross-section-audit.md
├── round4/
│   ├── citation-verification.md       ← From scripts/verify_citations.py
│   ├── tier-report.md                 ← From scripts/classify_sources.py
│   ├── missing-lit.md                 ← From scripts/lit_search.py --compare-bib
│   ├── factcheck-*.md
│   ├── fix-log.md
│   └── [TOPIC] - Research Bible.md
└── round5/                            ← optional iterative deepening
    └── deepening-log.md
```

### Graceful degradation

The dispatcher auto-detects which API keys are set and only runs those agent types. Missing providers are skipped with a notice — no errors, no failures. Even a single agent type produces useful output that feeds into Rounds 2-4. But **more agent types = better cross-validation**. Three or more is the sweet spot.

You can also run a subset of agent types: `--agents academic,contrarian,real-time`

## Round 2: Adversarial Comparison

After all Round 1 agents complete, dispatch **1 adversarial comparison agent** that reads ALL reports.

### Comparison Agent Brief

```
You are an adversarial research analyst. Read ALL FOUR/FIVE research reports
entirely. Do not skim. Produce a structured comparison report covering:

## AREAS OF AGREEMENT
Claims that appear in 3+ reports with consistent citations.
These are high-confidence findings. List each with all supporting citations.
Tag each: [N/M support] where N = reports supporting, M = reports examined.

## AREAS OF OVERLAP
Claims that appear in 2+ reports but with different framing or emphasis.
Note the differences in framing and which sources each report uses.

## AREAS OF DISAGREEMENT
Claims where reports contradict each other on facts, figures, or
interpretation. Present both sides with their respective sources.
Flag which version appears better-sourced.

## CITATION-LAUNDERING DETECTION (NEW)
When 2+ models cite the same SECONDARY source claiming X (e.g. a news article
or blog post that itself cites a primary source), that is ONE confirmation,
not multiple. Identify cases of citation laundering: list the secondary
source, the underlying primary source it draws on, and which models
double-counted it. Recommend re-citation to the primary source.

## CITATION QUALITY AUDIT
- Which reports have the strongest primary-source citations?
- Which reports rely too heavily on secondary sources?
- Flag any citation that appears in only one report and looks suspicious
- Flag any figures that differ between reports (e.g., "70%" vs "80%")
- For each disputed figure, propose how Round 3 should reconcile

## POTENTIAL HALLUCINATIONS
Claims that appear in only one report with no verifiable citation,
suspiciously specific figures, or citations that don't match known works.
Use WebSearch to spot-check 10-15 of these.

## COMPLETENESS MAP
What does each report cover that others miss? Create a matrix:
| Subtopic | academic | practitioner | real-time | grey-literature | contrarian |
Each cell: ✓ (covered in depth), ~ (mentioned), ✗ (absent)

## INTEGRATION RECOMMENDATIONS
Based on the above, provide specific instructions for Round 3:
- Which report should be the narrative spine for each section?
- Which specific claims need reconciliation, with proposed resolution
- Which unique content from each report must be preserved?
- What gaps remain that need additional research?
```

## Round 3: Integration

A single agent CANNOT reliably integrate 75,000-150,000 words. Split by topic section, not by source model.

### Step 3.1: Multi-planner section reconciliation (NEW)

The Round 2 completeness map can suggest section structures, but one planner's mistakes propagate. **Dispatch 3 independent section-planning agents in parallel**, each reading the comparison report and proposing a section structure. Then dispatch a fourth "reconciler" that picks the best plan and writes `reconciled-plan.md`.

```
Section planner brief:
You have read the Round 2 comparison report. Propose a section structure
(5-8 sections) for the integrated Research Bible. For each section:
- Title
- One-line scope
- Which Round 1 reports contribute most heavily
- Estimated word count
Output as a clean markdown table.

Reconciler brief:
Read all 3 planner proposals. Identify points of agreement and disagreement
in section boundaries. Produce a single reconciled plan that:
- Adopts section boundaries supported by 2+ planners
- For contested boundaries, justify your choice with one sentence
- Preserves every distinct subtopic at least one planner identified
```

### Step 3.2: Pre-extraction

For very large Round 1 outputs, run a pre-extraction step:
```
For each Round 1 report:
  For each section in reconciled-plan.md:
    Extract the relevant content from that report into a section-specific excerpt file
```

This creates a matrix of excerpt files that integration agents can read reliably.

### Step 3.3: Parallel section integration

Dispatch **one integration agent per section** in parallel. Each receives no more than ~40,000 words of input.

### Integration Agent Prompt Template

The excerpt filenames use agent-type names (matching the round1 output files). The manifest `assignments` map records which provider produced each agent-type report, so provenance is always traceable.

```
You are integrating ALL available research on [SECTION TOPIC] into a
single comprehensive section.

Read these files ENTIRELY — they contain ONLY the [SECTION TOPIC]
content extracted from each agent type's full report:

1. round1/excerpts/[section]-academic.md
2. round1/excerpts/[section]-practitioner.md
3. round1/excerpts/[section]-real-time.md
4. round1/excerpts/[section]-grey-literature.md
5. round1/excerpts/[section]-contrarian.md
6. round2/adversarial-comparison.md — SECTION: [relevant section]

## Non-Negotiable Integration Rules
1. PRESERVE ALL CITATIONS from ALL sources. Unified format: [Author, Year]
2. PROPAGATE CONFIDENCE — preserve [N/M support] tags from Round 2.
   Add [confidence: high/medium/low] to high-stakes claims.
3. PROPAGATE DATE STAMPS — every [as of: <date>] tag from Round 1 must survive.
4. Where sources agree, merge into single statement with MULTIPLE citations,
   tagged [N/M support]
5. Where figures differ, present ALL values with their respective sources,
   tagged [disputed: a=X (src), b=Y (src)]
6. Include EVERY unique finding from EVERY model — nothing gets dropped
7. Do NOT fabricate any new information during integration
8. Do NOT summarize where you can preserve detail
9. If two models provide different levels of detail on the same point,
   keep the MORE detailed version and add citations from the less detailed one
10. Flat, factual prose — no hedging, no filler

## Completeness Check
Before finishing, verify against the Round 2 COMPLETENESS MAP:
- Every ✓ item for this section from EVERY model must appear in your output
- Every ~ item should appear unless it contradicts a ✓ item
- Flag any item you could not integrate with a [INTEGRATION NOTE: ...]

Write to: [OUTPUT_PATH]
Target: this section should be LONGER than any single model's version
```

### Step 3.4: Dedicated Bibliography Agent

Use the helper script — deterministic dedup beats LLM dedup:

```bash
python3 scripts/dedup_bib.py \
    research/[slug]/round1/agent-*.md \
    --output research/[slug]/round3/section-bibliography.md
```

It clusters by DOI when available, fuzzy-matches by title otherwise, picks the longest entry as canonical, and emits a `dedup-decisions.md` sidecar for audit.

### Step 3.5: Assembly and cross-section auditor

After all section agents complete:
1. Assemble sections into a single document with frontmatter and table of contents
2. Run a cross-section consistency auditor that reads the full assembled document
3. The auditor checks: contradictions between sections, orphaned citations, redundant narratives, and tone violations

## Round 4: Mechanical Verification + Adversarial Fact-Check + Fix Pass

This round combines deterministic verification (scripts) and LLM fact-checking. Run mechanically first, then send the report to fact-checking agents.

### Step 4.1: Mechanical citation verification

```bash
python3 scripts/verify_citations.py research/[slug]/round3/ \
    --output research/[slug]/round4/citation-verification.md \
    --check-urls
```

This resolves every `[Author, Year]` and bibliography entry against **OpenAlex** and **Crossref** (free, no key). The report flags:
- **Unresolved**: bibliography entries that don't match any real work — likely hallucinated
- **Weak match**: resolved to a different work — possible misattribution
- **Orphans**: inline cites with no matching bibliography entry
- **Dead URLs**: 4xx/5xx or no response

### Step 4.2: Source tier classification

```bash
python3 scripts/classify_sources.py \
    research/[slug]/round3/section-bibliography.md \
    --output research/[slug]/round4/tier-report.md
```

Emits a tier mix table and a "quality score" weighted on peer-reviewed/institutional sources. A score under 0.4 means the bibliography skews toward blogs/wikis — consider re-running Round 1 with stronger source priorities.

### Step 4.3: Missing-literature check

```bash
python3 scripts/lit_search.py \
    --topic "Your topic" \
    --limit 50 \
    --compare-bib research/[slug]/round3/section-bibliography.md \
    --output research/[slug]/round4/missing-lit.md
```

Queries OpenAlex and Semantic Scholar for the top-N highly-cited works in the topic area and flags any that don't appear in the bibliography. Major works that are absent suggest the literature spine is incomplete.

### Step 4.4: Adversarial fact-check

Dispatch **2-3 parallel adversarial fact-checking agents** plus **1 cross-section consistency auditor**, now armed with the mechanical reports.

### Fact-Check Agent Brief

```
You are an adversarial fact-checker. Your job is to find errors, not praise.

Read:
- [SECTION FILES] entirely
- round4/citation-verification.md (which cites failed mechanical resolution)
- round4/tier-report.md (source quality distribution)
- round4/missing-lit.md (canonical works absent from bibliography)

For every factual claim:
1. Cross-reference against citation-verification.md flags
2. Identify contradictions within the document or with widely known facts
3. Check citation attributions (right author? right year? right paper?)
4. Flag figure discrepancies; cross-check against confidence tags
5. Identify potential hallucinations not already in citation-verification.md
6. Check completeness gaps against missing-lit.md

Use WebSearch to verify at least 15-20 specific claims against primary sources.

Write structured report:
## CONTRADICTIONS
## UNSOURCED CLAIMS
## CITATION ERRORS (cross-reference citation-verification.md)
## FIGURE DISCREPANCIES
## POTENTIAL HALLUCINATIONS
## COMPLETENESS GAPS (cross-reference missing-lit.md)
## VERIFIED CLAIMS (spot-checked and confirmed)
## OVERALL ASSESSMENT
```

### Step 4.5: Fix pass

After fact-check reports land, dispatch **fix agents** to correct identified errors:
- Critical errors (wrong facts, wrong attributions)
- Medium errors (inconsistencies, unreconciled figures)
- Artifact cleanup (process language, orphaned citations)

Then reassemble the final document from corrected sections.

## Round 5: Iterative Deepening (Optional)

After Round 4, the cross-section auditor gives a grade A-F. If sections graded C or lower, **rerun Rounds 1-4 on those specific sections only** with tighter scope. Cap at 2 iterations to avoid loops.

Useful when:
- The first pass surfaced a known gap that warrants targeted depth
- Mechanical verification (Round 4) found a section with high unresolved-citation rate
- A specific subtopic is contested and needs another model pass

For each weak section:
```bash
python3 dispatch.py \
    --topic "[original topic] — focus: [weak section title]" \
    --scope "Tighter scope from cross-section auditor + missing-lit findings" \
    --output-dir research/[slug]/round5/iter1/[section]/ \
    --scope-file research/[slug]/round0/scope.json \
    --max-cost-usd 15
```

Then re-integrate the new content into the section file, re-run Round 4 on just that section, and update the cross-section grade.

## Final Output: Hub-and-Spoke Research Bible + Machine-Readable Export

The output is NOT a single monolithic file. It's a **hub-and-spoke structure** plus a machine-readable export:

```
research/[topic-slug]/
├── README.md                          ← THE HUB
├── sections/
│   ├── 01-[section-name].md
│   ├── 02-[section-name].md
│   ├── ...
│   └── bibliography.md
├── export/
│   ├── bibliography.bib               ← BibTeX for downstream use
│   └── claims.jsonl                   ← One row per inline citation w/ context
├── round4/
│   ├── citation-verification.md
│   ├── tier-report.md
│   ├── missing-lit.md
│   └── fix-log.md
└── round0..round5/                    ← Provenance preserved
```

### Generate the export

```bash
python3 scripts/export.py \
    --sections research/[slug]/sections/ \
    --bibliography research/[slug]/sections/bibliography.md \
    --output-dir research/[slug]/export/
```

### The Hub: README.md

```markdown
---
title: "[Topic] — Research Bible"
date: [date]
version: "Final — Fact-Checked Edition"
models_used: [list]
total_words: [N]
unique_sources: [N]
source_quality_score: [from tier-report.md]
fact_check_grade: [from cross-section audit]
citation_resolution_rate: [from verify_citations.py — % resolved]
---

# [Topic]

## Executive Summary
[500-800 words — entire report compressed to its core findings]

## How to Use This Research
[What's covered, what's not, how sections connect, citation format,
confidence and as-of conventions]

## Sections
| # | Section | Words | Sources | File |
|---|---------|-------|---------|------|
| 1 | [Name] | [N] | [N] | [link] |

## Key Findings (high cross-model support)
[5-10 bullet points — claims tagged [4/5] or [5/5] in cross-model support]

## Contested Questions
[Claims tagged [disputed: ...] — present both sides with sources]

## Known Gaps
[Items in missing-lit.md that the team decided not to integrate, with reason]

## Provenance
- Round 0 scoping: [primary_domain]
- Models used: [list with model IDs]
- Citation resolution: [X% of bibliography resolved against Crossref/OpenAlex]
- Source quality: [from tier-report.md]
- Languages searched: [from manifest]
- Round 5 iterations: [N]
- Estimated cost: [USD]
```

## Execution Checklist

When `/deep-research [topic]` is invoked:

1. **Parse the topic** — clarify scope if ambiguous
2. **Round 0** — run `scripts/scope.py`; capture `scope.json`
3. **Create working directory** — `research/[topic-slug]/round1/` etc.
4. **Pre-flight cost** — run `dispatch.py --estimate-only`; confirm budget
5. **Round 1** — `dispatch.py` with `--scope-file`, `--max-cost-usd`, `--resume`
6. **Round 1 supplement** — Claude Code subagent with WebSearch/WebFetch
7. **Wait** — all models must complete before Round 2
8. **Round 2** — dispatch adversarial comparison + citation-laundering detection
9. **Wait** — comparison must complete before Round 3
10. **Round 3.1** — dispatch 3 section planners + reconciler in parallel
11. **Round 3.2** — pre-extract section excerpts per agent type
12. **Round 3.3** — dispatch integration agents (parallelize by section)
13. **Round 3.4** — `scripts/dedup_bib.py` for master bibliography
14. **Assemble** — combine sections into single draft document
15. **Round 4.1** — `scripts/verify_citations.py` (mechanical)
16. **Round 4.2** — `scripts/classify_sources.py` (tier audit)
17. **Round 4.3** — `scripts/lit_search.py --compare-bib` (missing literature)
18. **Round 4.4** — dispatch adversarial fact-check agents armed with reports
19. **Round 4.5** — apply fixes; reassemble final document
20. **(Optional) Round 5** — iterative deepening on sections graded C or lower
21. **Export** — `scripts/export.py` for BibTeX + claims.jsonl
22. **Report** — present summary to user with file location, stats, grade

## Scaling Guidance

Each agent type is configured to `max_tokens=128000` (or model max) and instructed to produce 15,000-30,000 words per report. This is industrial-strength — each Round 1 output should be 30-50 pages.

| Topic complexity | Round 1 per agent | Final Bible | Agents × Rounds | Est. cost |
|---|---|---|---|---|
| Narrow (single concept) | 10-15k w | 30-50k w | 3-5 / 1 / 2 / 2 | $10–25 |
| Medium (multi-faceted) | 15-25k w | 50-80k w | 3-5 / 1 / 4 / 3 | $25–60 |
| Broad (entire field) | 20-30k w | 80-150k w | 5 / 1 / 5 / 4 | $50–150 |

Adding Round 5 typically increases cost by 20–40%.

## Common Failure Modes

| Failure | Prevention |
|---|---|
| Agents fabricate sources | Rule in every prompt + `verify_citations.py` mechanical resolver in Round 4 |
| Figures differ between reports | Round 2 flags + Round 3 `[disputed: ...]` tags preserve both with sources |
| Citation laundering (multiple cites of same secondary) | Round 2 dedicated detection pass |
| Redundancy in integrated doc | Cross-section auditor flags; fix pass deduplicates |
| Orphaned citations | `verify_citations.py` detects; fix pass closes |
| Process artifacts in output | Final grep for "docx report", "Source ID", "our earlier research", etc. |
| One agent produces weak output | Round 2 comparison identifies weakest; Round 3 reconciler weights accordingly |
| Stale data | `[as of: <date>]` rule in prompts; Round 4 audits time-sensitive claims |
| Bibliography skewed to blogs/wikis | `classify_sources.py` quality score — flags if under 0.4 |
| Major canonical works missing | `lit_search.py --compare-bib` against OpenAlex/Semantic Scholar |
| Partial pipeline failure | `dispatch.py --resume` skips completed models |
| Surprise cost | `--estimate-only`, `--max-cost-usd` budget gate |
