---
name: deep-research
description: Use when the user needs comprehensive, fact-checked, evidence-based research on any topic. Triggers on requests for deep research, literature reviews, comprehensive reports, or evidence-based analysis. Runs four parallel research agents with differentiated strategies, adversarial cross-validation, integration, and final fact-checking to produce a single authoritative reference document.
---

# Deep Research

Four-model parallel deep research (Claude + ChatGPT + Perplexity + Gemini) with adversarial cross-validation and integration. Each model gets the same topic but a differentiated research strategy matching its strengths. Produces a single, fact-checked, fully-cited reference document — a "research Bible."

## Prerequisites

**API keys** — set whichever you have. The dispatcher auto-detects available keys and only calls models you've configured:
```
ANTHROPIC_API_KEY    # Claude Opus (claude-opus-4)
OPENAI_API_KEY       # OpenAI o3 (reasoning model)
PERPLEXITY_API_KEY   # Perplexity Deep Research (sonar-deep-research)
GOOGLE_API_KEY       # Gemini 2.5 Pro
XAI_API_KEY          # Grok 3 (grok-3-latest)
```

No key = that model is skipped with a notice. At least one key required. More models = better cross-validation.

**Python packages** (install once):
```bash
pip install anthropic openai google-genai
```

The dispatcher script lives alongside this `SKILL.md`. When installed into Claude Code, that's typically `~/.claude/skills/deep-research/dispatch.py`.

## When to Use

- User asks for deep research, comprehensive analysis, or evidence-based report on a topic
- User says `/deep-research [topic]`
- User needs a literature review, state-of-knowledge summary, or authoritative reference
- Any research task where accuracy, citation quality, and completeness matter more than speed

## Architecture: Four Rounds

```
Round 1: MULTI-MODEL RESEARCH
         ┌─ Claude (Anthropic API) ── Academic deep dive
         ├─ ChatGPT (OpenAI API)  ── Practitioner & explainer
         ├─ Perplexity (Pplx API) ── Real-time web + citations
         └─ Gemini (Google API)   ── Grey literature & primary sources
              ↓ (all 4 in parallel)
Round 2: ADVERSARIAL COMPARISON (Claude subagent reads all 4 outputs)
              ↓
Round 3: INTEGRATION (Claude subagents merge into single document)
              ↓
Round 4: FACT-CHECK + WEB VERIFICATION (adversarial agents + fix pass)
              ↓
OUTPUT:  Research Bible (single authoritative document + fact-check report)
```

## Round 1: Multi-Model Parallel Research

### Step 1: Run the dispatcher

The dispatcher script calls all four model APIs in parallel. Each model gets the same topic and citation rules but a different research strategy tuned to its strengths:

| Model | API Key | Strategy | Why this model |
|---|---|---|---|
| Model | API model ID | Strategy | Why this model |
|---|---|---|---|
| **Claude Opus** | `claude-opus-4` | Academic deep dive — journals, NBER, SSRN, think tanks, citation chains | Best at long-form analytical synthesis and nuance |
| **OpenAI GPT-4.1** | `gpt-4.1` | Practitioner & explainer — white papers, industry reports, how-to guides | Best long-form output, strongest at structured analysis |
| **Perplexity Deep Research** | `sonar-deep-research` | Real-time web intelligence — current news, recent data, live sources | Built-in deep web search with inline citations |
| **Gemini 2.5 Pro** | `gemini-2.5-pro` | Grey literature & primary sources — government reports, treaties, datasets | Largest context window, strong on document analysis |
| **Grok 3** | `grok-3-latest` | Contrarian & cross-disciplinary — dissenting views, alternative framings, overlooked evidence | Challenges consensus, finds what others miss |

```bash
python3 ~/.claude/skills/deep-research/dispatch.py \
  --topic "Your research topic here" \
  --scope "Detailed scope: what to cover, subtopics, depth, time period..." \
  --output-dir ./research/[topic-slug]/round1/
```

The script:
- Calls all 4 APIs in parallel (ThreadPoolExecutor)
- Each model gets strict anti-hallucination rules and citation requirements
- Saves responses to `round1/agent-1-claude.md` through `agent-4-gemini.md`
- Writes a `manifest.json` with timing and word counts
- Prints status as each model completes

### Step 2: Supplement with Claude Code subagent

After the dispatcher completes, dispatch **one additional Claude Code subagent** with WebSearch/WebFetch tools to fill gaps identified in the manifest. This agent can verify URLs, fetch specific documents, and search Google Scholar — capabilities the raw API calls lack.

```
Dispatch a Claude Code background agent that:
1. Reads all 4 round1 files
2. Uses WebSearch to verify 20-30 key citations from each report
3. Fetches any URLs that other models cited but couldn't verify
4. Writes a verification overlay to round1/citation-verification.md
```

### Output Location

```
[project]/research/[topic-slug]/
├── round1/
│   ├── agent-1-claude.md              ← Claude Opus
│   ├── agent-2-chatgpt.md            ← OpenAI o3
│   ├── agent-3-perplexity.md         ← Perplexity Deep Research
│   ├── agent-4-gemini.md             ← Gemini 2.5 Pro
│   ├── agent-5-grok.md               ← Grok 3 (if key set)
│   ├── citation-verification.md      ← Claude Code URL spot-check
│   ├── excerpts/                     ← Pre-extracted section excerpts
│   │   ├── section-1-claude.md
│   │   ├── section-1-chatgpt.md
│   │   └── ...
│   └── manifest.json                 ← Timing, word counts, status
├── round2/
│   └── adversarial-comparison.md     ← Agreement/disagreement/hallucination map
├── round3/
│   ├── section-01-[topic].md         ← Integrated section files
│   ├── section-02-[topic].md
│   ├── ...
│   ├── section-bibliography.md       ← Deduplicated master bibliography
│   └── cross-section-audit.md        ← Consistency check
├── round4/
│   ├── factcheck-*.md                ← Per-section fact-check reports
│   ├── fix-log.md                    ← What was corrected
│   └── [TOPIC] - Research Bible.md   ← FINAL OUTPUT
```

### Graceful degradation

The dispatcher auto-detects which API keys are set and only calls those models. Missing keys are skipped with a notice — no errors, no failures. Even a single model produces useful output that feeds into Rounds 2-4. But **more models = better cross-validation**. Five models is the maximum; three or more is the sweet spot.

You can also force specific models: `--models claude,grok,perplexity`

## Round 2: Adversarial Comparison

After all 4 Round 1 agents complete, dispatch **1 adversarial comparison agent** that reads ALL four reports.

### Comparison Agent Brief

```
You are an adversarial research analyst. Read ALL FOUR research reports
entirely. Do not skim. Produce a structured comparison report covering:

## AREAS OF AGREEMENT
Claims that appear in 3+ reports with consistent citations.
These are high-confidence findings. List each with all supporting citations.

## AREAS OF OVERLAP
Claims that appear in 2+ reports but with different framing or emphasis.
Note the differences in framing and which sources each report uses.

## AREAS OF DISAGREEMENT
Claims where reports contradict each other on facts, figures, or
interpretation. Present both sides with their respective sources.
Flag which version appears better-sourced.

## CITATION QUALITY AUDIT
- Which reports have the strongest primary-source citations?
- Which reports rely too heavily on secondary sources?
- Flag any citation that appears in only one report and looks suspicious
- Flag any figures that differ between reports (e.g., "70%" vs "80%")

## POTENTIAL HALLUCINATIONS
Claims that appear in only one report with no verifiable citation,
suspiciously specific figures, or citations that don't match known works.
Use WebSearch to spot-check 10-15 of these.

## COMPLETENESS MAP
What does each report cover that others miss? Create a matrix:
| Subtopic | Agent 1 | Agent 2 | Agent 3 | Agent 4 |
Each cell: ✓ (covered in depth), ~ (mentioned), ✗ (absent)

## INTEGRATION RECOMMENDATIONS
Based on the above, provide specific instructions for Round 3:
- Which report should be the narrative spine for each section?
- Which specific claims need reconciliation?
- Which unique content from each report must be preserved?
- What gaps remain that need additional research?
```

### Use Agency if Available

If agency MCP tools are available, use `agency_create_project` and `agency_assign` for the adversarial comparison — agency selects optimal primitives for critical analysis tasks.

## Round 3: Integration (Section-Based Architecture)

A single agent CANNOT reliably integrate 75,000-150,000 words. It will truncate, skim, and lose material. The proven approach: **split by topic section, not by source model**.

### Step 3.1: Section Planning

Use the Round 2 **COMPLETENESS MAP** to identify 5-8 major topic sections. The comparison report's matrix shows what each model covered — this becomes your section structure.

Example for a broad topic:
```
Section 1: Historical background
Section 2: Core mechanisms / how it works
Section 3: Key institutions and actors
Section 4: Theoretical frameworks and academic debates
Section 5: Current state and recent developments
Section 6: Geopolitics, regulation, and governance
Section 7: Future outlook and contested questions
Section 8: Master bibliography (dedicated agent)
```

### Step 3.2: Parallel Section Integration

Dispatch **one integration agent per section** in parallel. Each agent reads ONLY the relevant portions of each Round 1 report (not the entire 30K-word report — extract the relevant sections first, or instruct the agent to read only specific section headers).

**Critical constraint**: each integration agent should receive no more than ~40,000 words of input (the relevant sections from all models, not entire reports). This keeps the agent within reliable processing range.

### Step 3.3: Pre-extraction (if needed for large inputs)

For very large Round 1 outputs, run a pre-extraction step before integration:
```
For each Round 1 report:
  For each planned section:
    Extract the relevant content from that report into a section-specific excerpt file
```
This creates a matrix of excerpt files that integration agents can read reliably.

### Integration Agent Prompt Template

```
You are integrating ALL available research on [SECTION TOPIC] into a
single comprehensive section.

Read these files ENTIRELY — they contain ONLY the [SECTION TOPIC]
content extracted from each model's full report:

1. round1/excerpts/[section]-claude.md
2. round1/excerpts/[section]-chatgpt.md
3. round1/excerpts/[section]-perplexity.md
4. round1/excerpts/[section]-gemini.md
5. round1/excerpts/[section]-grok.md  (if available)
6. round2/adversarial-comparison.md — SECTION: [relevant section]

The comparison report identifies areas of agreement, disagreement, and
unique content. Follow its integration recommendations for this section.

## Non-Negotiable Integration Rules
1. PRESERVE ALL CITATIONS from ALL sources. Unified format: [Author, Year]
2. Where sources agree, merge into single statement with MULTIPLE citations
3. Where figures differ, present ALL values with their respective sources
4. Include EVERY unique finding from EVERY model — nothing gets dropped
5. Do NOT fabricate any new information during integration
6. Do NOT summarize where you can preserve detail
7. If two models provide different levels of detail on the same point,
   keep the MORE detailed version and add citations from the less detailed one
8. Flat, factual prose — no hedging, no filler

## Completeness Check
Before finishing, verify against the Round 2 COMPLETENESS MAP:
- Every ✓ item for this section from EVERY model must appear in your output
- Every ~ item should appear unless it contradicts a ✓ item
- Flag any item you could not integrate with a [INTEGRATION NOTE: ...]

Write to: [OUTPUT_PATH]
Target: this section should be LONGER than any single model's version
```

### Step 3.4: Dedicated Bibliography Agent

Dispatch a **separate bibliography agent** that reads ONLY the bibliography sections from all Round 1 reports and produces a single deduplicated master bibliography:

```
Read the bibliography/references section from each Round 1 report.
Produce a single master bibliography:
1. DEDUPLICATE — same source from multiple models = one entry with best metadata
2. RECONCILE — where models cite different years/authors for the same work, verify
3. CATEGORIZE — organize by type (Academic / Institutional / Books / Primary / etc.)
4. ANNOTATE — 1-2 sentence annotation per entry explaining why it matters
5. FLAG — mark any entry that appears in only one model and looks suspicious
```

### Step 3.5: Assembly and Cross-Check

After all section agents complete:
1. **Assemble** sections into single document with frontmatter and table of contents
2. **Run a cross-section consistency auditor** that reads the full assembled document
3. The auditor checks for: contradictions between sections, orphaned citations
   (inline citation with no bibliography entry), redundant narratives (same event
   told in multiple sections), and tone violations

### Why This Architecture Works

| Problem | How it's solved |
|---|---|
| Agent can't read 150K words | Each agent reads ~20-40K words (one section from all models) |
| Content gets dropped during integration | Completeness map from Round 2 serves as checklist; integration agent verifies against it |
| Citations get orphaned | Dedicated bibliography agent + cross-section auditor |
| Same event narrated 5 times | Cross-section auditor flags redundancy; fix pass deduplicates |
| Figures contradict between models | Comparison report flags discrepancies; integration presents all with sources |
| Integration agent hallucinates new claims | Rule 5: "Do NOT fabricate" + Round 4 fact-check catches survivors |

## Round 4: Final Fact-Check

Dispatch **2-3 parallel adversarial fact-checking agents** plus **1 cross-section consistency auditor**.

### Fact-Check Agent Brief

```
You are an adversarial fact-checker. Your job is to find errors, not praise.

Read [SECTION FILES] ENTIRELY. For every factual claim:
1. Flag unsourced or weakly sourced claims
2. Identify contradictions within the document or with widely known facts
3. Check citation attributions (right author? right year? right paper?)
4. Flag figure discrepancies
5. Identify potential hallucinations
6. Check completeness gaps

Use WebSearch to verify at least 15-20 specific claims against primary sources.

Write structured report:
## CONTRADICTIONS
## UNSOURCED CLAIMS
## CITATION ERRORS
## FIGURE DISCREPANCIES
## POTENTIAL HALLUCINATIONS
## COMPLETENESS GAPS
## VERIFIED CLAIMS (spot-checked and confirmed)
## OVERALL ASSESSMENT
```

### Cross-Section Consistency Auditor

```
Read ALL sections. Check:
1. CROSS-REFERENCES — same date/figure consistent across sections?
2. NARRATIVE COHERENCE — coherent story or jarring transitions?
3. ORPHANED CITATIONS — inline citations with no bibliography entry?
4. REDUNDANCY — same event narrated multiple times?
5. TONE — any LLM filler? ("in conclusion", "it is worth noting", etc.)

Grade: A-F with justification
```

### Fix Pass

After fact-check reports land, dispatch **fix agents** to correct all identified errors:
- Critical errors (wrong facts, wrong attributions)
- Medium errors (inconsistencies, unreconciled figures)
- Artifact cleanup (process language, orphaned citations)

Then **reassemble the final document** from corrected sections.

## Final Output: Hub-and-Spoke Research Bible

The output is NOT a single monolithic file. It's a **hub-and-spoke structure** that adapts to the topic:

```
research/[topic-slug]/
├── README.md                          ← THE HUB: index, navigation, executive summary
├── sections/
│   ├── 01-[section-name].md           ← Detailed section file (8,000-20,000 words each)
│   ├── 02-[section-name].md
│   ├── ...
│   └── bibliography.md               ← Deduplicated master bibliography
├── factcheck/
│   ├── factcheck-*.md                 ← Per-section fact-check reports
│   ├── cross-section-audit.md
│   └── fix-log.md
└── round1/                            ← Raw model outputs (preserved for provenance)
```

### The Hub: README.md

```markdown
---
title: "[Topic] — Research Bible"
date: [date]
version: "Final — Fact-Checked Edition"
models_used: [list of models that contributed]
total_words: [N across all sections]
unique_sources: [N]
fact_check_grade: [grade from cross-section audit]
---

# [Topic]

## Executive Summary
[500-800 words — the entire report compressed to its core findings]

## How to Use This Research
[What's covered, what's not, how sections connect, citation format]

## Sections

| # | Section | Words | Sources | File |
|---|---------|-------|---------|------|
| 1 | [Name] | [N] | [N] | [link to file] |
| 2 | [Name] | [N] | [N] | [link to file] |
| ... | ... | ... | ... | ... |
| B | Master Bibliography | [N entries] | — | [link] |

## Key Findings
[5-10 bullet points — the claims with strongest cross-model agreement]

## Contested Questions
[Claims where models disagreed or evidence is mixed — with both sides]

## Known Gaps
[What this research does NOT cover, flagged for future work]

## Provenance
- Round 1 raw outputs preserved in `round1/`
- Fact-check reports in `factcheck/`
- Models used: [list with model IDs]
- Total API cost estimate: [if calculable from token counts]
```

### Why Hub-and-Spoke

| Monolith problem | Hub-and-spoke solution |
|---|---|
| 150K words = unusable to navigate | Index with word counts and direct links |
| Can't update one section without touching everything | Each section is an independent file |
| Exceeds context windows for follow-up analysis | Individual sections fit in any model's context |
| No way to see the forest | Executive summary + key findings in the hub |
| Hard to fact-check | Fact-check reports map 1:1 to section files |
| No provenance trail | Raw Round 1 outputs preserved alongside final |

### Section Structure (each file)

Each section file follows this template:

```markdown
---
title: "[Section Name]"
parent: "../README.md"
sources_in_section: [N]
word_count: [N]
---

# [Section Name]

[Full content with inline citations]

## Section Bibliography
[Sources cited in THIS section only — the master bibliography has everything]
```

### Adaptive Structure

The number and nature of sections adapts to the topic. The skill does NOT prescribe a fixed structure — the Round 2 completeness map determines what sections exist:

- A **narrow technical topic** might produce 3-4 deep sections
- A **broad field survey** might produce 7-10 sections covering history, theory, practice, institutions, current state, and outlook
- A **policy question** might organize around positions, evidence, stakeholders, and scenarios

The section plan is decided AFTER Round 2, based on what the models actually produced — not before.

## Execution Checklist

When `/deep-research [topic]` is invoked:

1. **Parse the topic** — clarify scope if ambiguous
2. **Create working directory** — `research/[topic-slug]/round1/` etc.
3. **Round 1** — dispatch 4 background agents in parallel with differentiated strategies
4. **Wait** — all 4 must complete before Round 2
5. **Round 2** — dispatch adversarial comparison agent
6. **Wait** — comparison must complete before Round 3
7. **Round 3** — dispatch integration agents (parallelize by section)
8. **Assemble** — combine sections into single draft document
9. **Round 4** — dispatch fact-check agents in parallel
10. **Fix** — apply all corrections from fact-check reports
11. **Reassemble** — produce final Research Bible
12. **Report** — present summary to user with file location and stats

## Scaling Guidance

Each model is set to `max_tokens=128000` and instructed to produce 15,000-30,000 words per report. This is industrial-strength — each Round 1 output should be 30-50 pages.

| Topic complexity | Round 1 target per model | Final Bible target | Models × Rounds |
|---|---|---|---|
| Narrow (single concept) | 10,000-15,000 w | 30,000-50,000 w | 3-5 / 1 / 2 / 2 |
| Medium (multi-faceted) | 15,000-25,000 w | 50,000-80,000 w | 3-5 / 1 / 4 / 3 |
| Broad (entire field) | 20,000-30,000 w | 80,000-150,000 w | 5 / 1 / 5 / 4 |

## Common Failure Modes

| Failure | Prevention |
|---|---|
| Agents fabricate sources | Non-negotiable rule in every prompt: "NEVER invent sources" + fact-check round catches survivors |
| Figures differ between reports | Round 2 flags all discrepancies; Round 3 reconciles with source preference |
| Redundancy in integrated doc | Cross-section auditor flags; fix pass deduplicates |
| Orphaned citations | Cross-section auditor checks every inline citation against bibliography |
| Process artifacts in output | Final grep for "docx report", "Source ID", "our earlier research", etc. |
| One agent produces weak output | Round 2 comparison identifies weakest agent; Round 3 weights accordingly |
