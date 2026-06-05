# deep-research

Four-model parallel deep research with adversarial cross-validation. A Claude Code skill that orchestrates Claude, ChatGPT, Perplexity, Gemini, and Grok against the same topic with differentiated strategies, compares their outputs adversarially, integrates them by topic section, and runs a final fact-check pass. Produces a fact-checked, fully-cited "Research Bible."

## What it does

Most LLM research is one model, one pass, hallucinated citations. This is five models in parallel, then three rounds of cross-validation, integration, and adversarial fact-checking.

```
Round 1  Five models research in parallel — each with a different strategy
         ├─ Claude       → Academic deep dive (journals, NBER, SSRN)
         ├─ ChatGPT      → Practitioner & explainer (industry, methodology)
         ├─ Perplexity   → Real-time web (current news, live citations)
         ├─ Gemini       → Grey literature & primary sources (govt, IGO, treaties)
         └─ Grok         → Contrarian & cross-disciplinary (dissent, outside views)

Round 2  Adversarial comparison agent maps agreement, disagreement, hallucination risk

Round 3  Section-by-section integration (per topic, not per model) — parallel agents

Round 4  Fact-check + cross-section audit + fix pass

Output   Hub-and-spoke Research Bible: index + sections + bibliography + provenance
```

## Install

```bash
# 1. Clone into your Claude skills directory
git clone https://github.com/nraford7/deep-research.git ~/.claude/skills/deep-research

# 2. Install Python deps
pip install anthropic openai google-genai

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

Or invoke the dispatcher directly:

```bash
python3 ~/.claude/skills/deep-research/dispatch.py \
  --topic "Your research topic" \
  --scope "What to cover, subtopics, depth, time period..." \
  --output-dir ./research/topic-slug/round1/
```

Optional model filter:

```bash
--models claude,perplexity,grok
```

## API keys

| Env var | Model | Get a key |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude | https://console.anthropic.com |
| `OPENAI_API_KEY` | ChatGPT | https://platform.openai.com |
| `PERPLEXITY_API_KEY` | Perplexity Deep Research | https://www.perplexity.ai/settings/api |
| `GOOGLE_API_KEY` | Gemini | https://aistudio.google.com/apikey |
| `XAI_API_KEY` | Grok | https://console.x.ai |

The dispatcher reads from `~/.env` and `./.env` automatically. Or export them in your shell.

## Output

```
research/<topic-slug>/
├── README.md                  ← The hub: index, exec summary, key findings
├── sections/
│   ├── 01-<name>.md           ← Integrated topic sections (each 8k–20k words)
│   ├── 02-<name>.md
│   └── bibliography.md        ← Deduplicated master bibliography
├── factcheck/
│   ├── factcheck-*.md         ← Per-section adversarial fact-check
│   ├── cross-section-audit.md
│   └── fix-log.md
└── round1/                    ← Raw model outputs preserved for provenance
```

## Why five models, not one

- **Hallucination triangulation** — a fake citation rarely appears in three reports
- **Coverage** — each model has different blind spots; cross-section completeness map exposes them
- **Citation quality** — Perplexity finds live web sources, Gemini surfaces primary documents, Claude follows academic citation chains
- **Disagreement is signal** — when models split on a figure, that's a flag, not a problem

See `SKILL.md` for the full architecture, prompt templates, and failure modes.

## License

MIT — see `LICENSE`.

## Credits

Built for use inside Claude Code as a slash-command skill. Adapt freely.
