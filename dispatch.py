#!/usr/bin/env python3
"""
Deep Research Dispatcher — calls available models in parallel.

Supported models and their API keys:
  ANTHROPIC_API_KEY  → Claude (Anthropic)
  OPENAI_API_KEY     → ChatGPT (OpenAI)
  PERPLEXITY_API_KEY → Perplexity
  GOOGLE_API_KEY     → Gemini (Google)
  XAI_API_KEY        → Grok (xAI)

Only models with a valid API key in the environment are dispatched.
Missing keys are skipped with a notice — no failures.

Usage:
  python3 dispatch.py --topic "Oil trading" --scope "Full scope..." --output-dir ./round1/
  python3 dispatch.py --topic "AI safety" --scope "..." --output-dir ./round1/ --models claude,grok
  python3 dispatch.py --topic "..." --scope "..." --output-dir ./round1/ --max-cost-usd 30 --resume
  python3 dispatch.py --topic "..." --scope "..." --output-dir ./round1/ --languages en,fr,de
  python3 dispatch.py --topic "..." --scope "..." --output-dir ./round1/ --scope-file round0/scope.json
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Make sibling scripts/ importable when run as a CLI
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from scripts.cost import estimate_run, format_report, enforce_budget
except ImportError:
    estimate_run = format_report = enforce_budget = None

# Auto-load API keys from ~/.env and .env
for env_path in [Path.home() / ".env", Path(".env")]:
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip("'\"")
                if key and val and key not in os.environ:
                    os.environ[key] = val


def fail_with_install_hint(model: str, package: str):
    msg = (
        f"\n  ✗ {model}: Python package '{package}' not installed.\n"
        f"     Fix: pip install -r requirements.txt   (or: pip install {package})\n"
    )
    return {"model": model, "status": "error", "error": msg.strip()}


SHARED_RULES = """
## Non-Negotiable Research Rules
1. NEVER fabricate sources, URLs, DOIs, ISBNs, or quotes. If you cannot verify, mark "UNVERIFIED".
2. Every factual claim must have an inline citation [Author, Year] or [Source, Year].
3. If you cannot verify a source URL, mark it as "URL unverified" — do not invent one.
4. Prefer primary and institutional sources over Wikipedia.
5. When a topic is contested in the literature, present both sides with sources.
6. Include a full bibliography at the end, organized by category (Academic / Institutional / Books / Primary Sources).
7. Write in flat, factual prose. No hedging, no filler, no "in conclusion", no "it is worth noting".
8. Target 15,000-30,000 words. Be exhaustive. Cover every subtopic in depth.
9. DATE STAMPING: any claim with a year, statistic, or "current" qualifier must carry "[as of: <date>]".
   If you do not know the as-of date, write "[as of: unknown]" — do not guess.
10. CONFIDENCE: For high-stakes empirical claims, append "[confidence: high/medium/low]" with a one-line reason
    (e.g., "[confidence: medium — single source, no replication]").
"""

MODEL_REGISTRY = {
    "claude":     {"env_key": "ANTHROPIC_API_KEY", "label": "Claude (Anthropic)", "filename": "agent-1-claude.md"},
    "chatgpt":    {"env_key": "OPENAI_API_KEY",    "label": "ChatGPT (OpenAI)",    "filename": "agent-2-chatgpt.md"},
    "perplexity": {"env_key": "PERPLEXITY_API_KEY","label": "Perplexity",          "filename": "agent-3-perplexity.md"},
    "gemini":     {"env_key": "GOOGLE_API_KEY",    "label": "Gemini (Google)",     "filename": "agent-4-gemini.md"},
    "grok":       {"env_key": "XAI_API_KEY",       "label": "Grok (xAI)",          "filename": "agent-5-grok.md"},
}

STRATEGIES = {
    "claude": """Academic Deep Dive — focus on the most-cited academic papers, NBER/SSRN working papers,
journal articles, university research, think tank publications, and review articles.
Find the canonical authors in the field. Follow citation chains. Identify theoretical
frameworks and empirical debates. Structure as a literature review with theoretical
underpinnings and empirical findings.""",

    "chatgpt": """Practitioner & Explainer — focus on practical, applied, how-it-works sources.
Industry white papers, consulting reports, trade publications, professional guides,
technical documentation, methodology documents, company reports. Find the best
explainers and how-to guides. Include data tables, process descriptions, and
real-world examples. Structure for a practitioner audience.""",

    "perplexity": """Real-Time Web Intelligence — focus on current, up-to-date information.
Search extensively for recent sources (last 1-3 years). Find recent news articles,
government reports, regulatory filings, press releases, current data, recent
conference proceedings. Identify what has changed recently, current controversies,
recent policy changes, emerging trends. Verify current figures and statistics.
Structure around current state and recent developments.""",

    "gemini": """Grey Literature & Primary Sources — focus on primary documents and original data.
Government reports, international organization publications (UN, World Bank, IMF, OECD),
NGO reports, official datasets, legal documents, treaties, standards, congressional
testimony, regulatory dockets. Find the PRIMARY source behind secondary claims.
If a paper cites a government report, find the report. Structure around documentary
evidence and original-source citations.""",

    "grok": """Contrarian & Cross-Disciplinary Analysis — challenge conventional narratives.
Search for dissenting academic views, minority positions in policy debates,
cross-disciplinary insights (e.g., complexity science applied to markets, network
theory applied to supply chains), unconventional data sources, and perspectives
from outside the mainstream Western institutional framework. Find what the other
research strategies are likely to miss. Structure around alternative framings,
overlooked evidence, and underrepresented perspectives.""",
}


def build_prompt(topic, scope, strategy, languages=None, domain_priorities=None):
    lang_clause = ""
    if languages and languages != ["en"]:
        non_en = [l for l in languages if l != "en"]
        if non_en:
            lang_clause = (
                "\n\n## Multilingual sourcing\n"
                f"In addition to English sources, search for high-quality sources in: {', '.join(non_en)}.\n"
                "Cite original-language titles. Translate critical quotes into English and indicate the original language.\n"
                "Do not skip non-English primary sources just because English summaries exist.\n"
            )

    domain_clause = ""
    if domain_priorities:
        domain_clause = "\n\n## Domain-specific source priorities\n" + domain_priorities + "\n"

    return f"""You are producing a fact-checked, evidence-based deep research report.

## Topic
{topic}

## Scope
{scope}
{domain_clause}{lang_clause}

## Research Strategy
{strategy}

{SHARED_RULES}

## Output Format
- Start with an executive summary (200-300 words)
- Organize into clear sections with subsections
- Use inline citations: [Author, Year] or [Source, Year]
- Apply [as of: <date>] to time-sensitive claims
- Apply [confidence: ...] to high-stakes empirical claims
- End with a complete bibliography organized by category
- Include URLs for every source where possible
"""


# --- Model callers ---

def call_claude(prompt, output_path):
    try:
        import anthropic
    except ImportError:
        return fail_with_install_hint("claude", "anthropic")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    start = time.time()
    msg = client.messages.create(
        model="claude-opus-4-20250514",
        max_tokens=128000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text
    output_path.write_text(text, encoding="utf-8")
    return _result("claude", text, start, output_path)


def call_chatgpt(prompt, output_path):
    try:
        from openai import OpenAI
    except ImportError:
        return fail_with_install_hint("chatgpt", "openai")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    start = time.time()
    resp = client.chat.completions.create(
        model="gpt-4.1",
        max_tokens=32768,
        messages=[
            {"role": "system", "content": "You are a deep research analyst producing comprehensive, fact-checked, evidence-based research reports with full citations. Produce the COMPLETE report in a single response. Do NOT ask for confirmation or suggest splitting into parts. Write the full report now."},
            {"role": "user", "content": prompt},
        ],
    )
    text = resp.choices[0].message.content
    output_path.write_text(text, encoding="utf-8")
    return _result("chatgpt", text, start, output_path)


def call_perplexity(prompt, output_path):
    try:
        from openai import OpenAI
    except ImportError:
        return fail_with_install_hint("perplexity", "openai")
    client = OpenAI(api_key=os.environ["PERPLEXITY_API_KEY"], base_url="https://api.perplexity.ai")
    start = time.time()
    resp = client.chat.completions.create(
        model="sonar-deep-research",
        max_tokens=128000,
        messages=[
            {"role": "system", "content": "You are a deep research analyst. Use your web search capabilities extensively to find and cite real, verifiable sources. Every claim must have a citation."},
            {"role": "user", "content": prompt},
        ],
    )
    text = resp.choices[0].message.content
    output_path.write_text(text, encoding="utf-8")
    return _result("perplexity", text, start, output_path)


def call_gemini(prompt, output_path):
    try:
        from google import genai
    except ImportError:
        try:
            import google.generativeai as genai_legacy
            return _call_gemini_legacy(genai_legacy, prompt, output_path)
        except ImportError:
            return fail_with_install_hint("gemini", "google-genai")
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    start = time.time()
    for model_id in ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"]:
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=genai.types.GenerateContentConfig(max_output_tokens=65536),
            )
            text = response.text
            output_path.write_text(text, encoding="utf-8")
            return _result("gemini", text, start, output_path)
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e) or "overloaded" in str(e).lower():
                continue
            raise
    return {"model": "gemini", "status": "error", "error": "All Gemini models unavailable (503)"}


def _call_gemini_legacy(genai, prompt, output_path):
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash")
    start = time.time()
    response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(max_output_tokens=16000))
    text = response.text
    output_path.write_text(text, encoding="utf-8")
    return _result("gemini", text, start, output_path)


def call_grok(prompt, output_path):
    try:
        from openai import OpenAI
    except ImportError:
        return fail_with_install_hint("grok", "openai")
    client = OpenAI(api_key=os.environ["XAI_API_KEY"], base_url="https://api.x.ai/v1")
    start = time.time()
    resp = client.chat.completions.create(
        model="grok-3-latest",
        max_tokens=128000,
        messages=[
            {"role": "system", "content": "You are a deep research analyst producing comprehensive, fact-checked, evidence-based research reports with full citations. Challenge conventional narratives where evidence warrants it."},
            {"role": "user", "content": prompt},
        ],
    )
    text = resp.choices[0].message.content
    output_path.write_text(text, encoding="utf-8")
    return _result("grok", text, start, output_path)


CALLERS = {
    "claude": call_claude,
    "chatgpt": call_chatgpt,
    "perplexity": call_perplexity,
    "gemini": call_gemini,
    "grok": call_grok,
}


def _result(model, text, start, path):
    return {
        "model": model,
        "status": "ok",
        "words": len(text.split()),
        "seconds": round(time.time() - start, 1),
        "file": str(path),
    }


def load_scope_brief(scope_file):
    if not scope_file:
        return None
    path = Path(scope_file)
    if not path.exists():
        print(f"  warn: --scope-file {scope_file} not found, ignoring", file=sys.stderr)
        return None
    if path.suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return path.read_text(encoding="utf-8")
        lines = []
        if data.get("primary_domain"):
            lines.append(f"Primary domain: {data['primary_domain']}")
        if "llm_proposal" in data:
            prop = data["llm_proposal"]
            lines.append("Priority sources:")
            for s in prop.get("priority_sources", []):
                lines.append(f"- {s}")
            if prop.get("must_check"):
                lines.append(f"Must check: {prop['must_check']}")
        return "\n".join(lines) if lines else None
    return path.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Deep Research Dispatcher — multi-model parallel research",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="Research topic")
    parser.add_argument("--scope", required=True, help="Detailed scope description")
    parser.add_argument("--output-dir", required=True, help="Output directory for round 1 files")
    parser.add_argument("--models", default="auto",
                        help="Comma-separated models (claude,chatgpt,perplexity,gemini,grok) or 'auto'")
    parser.add_argument("--languages", default="en", help="Search languages, e.g. en,fr,de,zh")
    parser.add_argument("--scope-file", help="JSON or markdown from scripts/scope.py — injects domain priorities")
    parser.add_argument("--max-cost-usd", type=float, help="Hard cap on estimated full-run cost")
    parser.add_argument("--resume", action="store_true",
                        help="Skip models whose output file already exists in --output-dir")
    parser.add_argument("--no-confirm", action="store_true", help="Skip the interactive cost prompt")
    parser.add_argument("--estimate-only", action="store_true", help="Print cost estimate and exit")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    languages = [l.strip() for l in args.languages.split(",") if l.strip()]
    domain_priorities = load_scope_brief(args.scope_file)

    if args.models == "auto":
        candidates = list(MODEL_REGISTRY.keys())
    else:
        candidates = [m.strip() for m in args.models.split(",")]

    available, skipped = [], []
    for name in candidates:
        if name not in MODEL_REGISTRY:
            skipped.append((name, "unknown model"))
            continue
        env_key = MODEL_REGISTRY[name]["env_key"]
        if os.environ.get(env_key):
            available.append(name)
        else:
            skipped.append((name, f"{env_key} not set"))

    resumed_skip = []
    if args.resume:
        runnable = []
        for name in available:
            target = output_dir / MODEL_REGISTRY[name]["filename"]
            if target.exists() and target.stat().st_size > 1000:
                resumed_skip.append(name)
            else:
                runnable.append(name)
        available = runnable

    if skipped:
        print("Skipping (no API key):", flush=True)
        for name, reason in skipped:
            print(f"  · {name}: {reason}", flush=True)
        print(flush=True)
    if resumed_skip:
        print(f"Resume: skipping {len(resumed_skip)} models with existing output: {', '.join(resumed_skip)}", flush=True)
        print(flush=True)

    if not available:
        if resumed_skip:
            print("All models already have output. Nothing to do (use without --resume to re-run).", flush=True)
            return
        print("ERROR: No models available. Set at least one API key:", flush=True)
        for name, info in MODEL_REGISTRY.items():
            print(f"  {info['env_key']:25s} → {info['label']}", flush=True)
        raise SystemExit(1)

    # Cost preflight
    if estimate_run is not None:
        prompt_sample = build_prompt(args.topic, args.scope, STRATEGIES[available[0]],
                                     languages=languages, domain_priorities=domain_priorities)
        prompt_words = len(prompt_sample.split())
        estimate = estimate_run(available, prompt_words=prompt_words, output_words=25000)
        print(format_report(estimate), flush=True)
        if args.estimate_only:
            return
        if not enforce_budget(estimate, args.max_cost_usd, prompt=not args.no_confirm):
            raise SystemExit(2)
    elif args.max_cost_usd is not None:
        print("  warn: scripts/cost.py unavailable, --max-cost-usd ignored", file=sys.stderr)

    print(f"\nDispatching {len(available)} model(s) in parallel: {', '.join(available)}", flush=True)
    if languages != ["en"]:
        print(f"Languages: {', '.join(languages)}", flush=True)
    if domain_priorities:
        print(f"Domain scope: injected ({len(domain_priorities)} chars)", flush=True)
    print(flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=len(available)) as executor:
        futures = {}
        for name in available:
            prompt = build_prompt(args.topic, args.scope, STRATEGIES[name],
                                  languages=languages, domain_priorities=domain_priorities)
            path = output_dir / MODEL_REGISTRY[name]["filename"]
            futures[executor.submit(CALLERS[name], prompt, path)] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                results.append(result)
                if result["status"] == "ok":
                    print(f"  ✓ {name}: {result['words']} words in {result['seconds']}s → {result['file']}", flush=True)
                else:
                    print(f"  ✗ {name}: {result['error']}", flush=True)
            except Exception as e:
                results.append({"model": name, "status": "error", "error": str(e)})
                print(f"  ✗ {name}: {e}", flush=True)

    manifest_path = output_dir / "manifest.json"
    existing = {}
    if args.resume and manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    prior_results = existing.get("results", [])
    prior_by_model = {r["model"]: r for r in prior_results if isinstance(r, dict) and "model" in r}
    for r in results:
        prior_by_model[r["model"]] = r
    merged_results = list(prior_by_model.values())

    manifest = {
        "topic": args.topic,
        "scope": args.scope,
        "languages": languages,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "models_dispatched": available,
        "models_resumed": resumed_skip,
        "models_skipped": [{"model": n, "reason": r} for n, r in skipped],
        "results": merged_results,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    ok_count = sum(1 for r in results if r["status"] == "ok")
    total_words = sum(r.get("words", 0) for r in results if r["status"] == "ok")
    print(f"\n{'='*50}", flush=True)
    print(f"Done: {ok_count}/{len(available)} models succeeded, {total_words:,} new words", flush=True)
    print(f"Manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
