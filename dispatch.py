#!/usr/bin/env python3
"""
Deep Research Dispatcher — calls available models in parallel.

Supported models and their API keys:
  ANTHROPIC_API_KEY  → Claude
  OPENAI_API_KEY     → ChatGPT
  PERPLEXITY_API_KEY → Perplexity
  GOOGLE_API_KEY     → Gemini
  XAI_API_KEY        → Grok

Only models with a valid API key in the environment are dispatched.
Missing keys are skipped with a notice — no failures.

Usage:
  python3 dispatch.py --topic "Oil trading" --scope "Full scope..." --output-dir ./round1/
  python3 dispatch.py --topic "AI safety" --scope "..." --output-dir ./round1/ --models claude,grok
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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

SHARED_RULES = """
## Non-Negotiable Research Rules
1. NEVER fabricate sources, URLs, DOIs, ISBNs, or quotes.
2. Every factual claim must have an inline citation [Author, Year] or [Source, Year].
3. If you cannot verify a source URL, mark it as "URL unverified" — do not invent one.
4. Prefer primary and institutional sources over Wikipedia.
5. When a topic is contested in the literature, present both sides with sources.
6. Include a full bibliography at the end, organized by category (Academic / Institutional / Books / Primary Sources).
7. Write in flat, factual prose. No hedging, no filler, no "in conclusion", no "it is worth noting".
8. Target 15,000-30,000 words. Be exhaustive. Cover every subtopic in depth. Do not summarize where you can elaborate.
"""

MODEL_REGISTRY = {
    "claude": {
        "env_key": "ANTHROPIC_API_KEY",
        "label": "Claude (Anthropic)",
        "filename": "agent-1-claude.md",
    },
    "chatgpt": {
        "env_key": "OPENAI_API_KEY",
        "label": "ChatGPT (OpenAI)",
        "filename": "agent-2-chatgpt.md",
    },
    "perplexity": {
        "env_key": "PERPLEXITY_API_KEY",
        "label": "Perplexity",
        "filename": "agent-3-perplexity.md",
    },
    "gemini": {
        "env_key": "GOOGLE_API_KEY",
        "label": "Gemini (Google)",
        "filename": "agent-4-gemini.md",
    },
    "grok": {
        "env_key": "XAI_API_KEY",
        "label": "Grok (xAI)",
        "filename": "agent-5-grok.md",
    },
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


def build_prompt(topic: str, scope: str, strategy: str) -> str:
    return f"""You are producing a fact-checked, evidence-based deep research report.

## Topic
{topic}

## Scope
{scope}

## Research Strategy
{strategy}

{SHARED_RULES}

## Output Format
- Start with an executive summary (200-300 words)
- Organize into clear sections with subsections
- Use inline citations: [Author, Year] or [Source, Year]
- End with a complete bibliography organized by category
- Include URLs for every source where possible
"""


# --- Model callers ---

def call_claude(prompt: str, output_path: Path) -> dict:
    try:
        import anthropic
    except ImportError:
        return {"model": "claude", "status": "error", "error": "pip install anthropic"}

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


def call_chatgpt(prompt: str, output_path: Path) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        return {"model": "chatgpt", "status": "error", "error": "pip install openai"}

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


def call_perplexity(prompt: str, output_path: Path) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        return {"model": "perplexity", "status": "error", "error": "pip install openai"}

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


def call_gemini(prompt: str, output_path: Path) -> dict:
    try:
        from google import genai
    except ImportError:
        try:
            import google.generativeai as genai_legacy
            return _call_gemini_legacy(genai_legacy, prompt, output_path)
        except ImportError:
            return {"model": "gemini", "status": "error", "error": "pip install google-genai"}

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    start = time.time()
    # Try 2.5 Pro first, fall back to 2.0 Flash if unavailable
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


def _call_gemini_legacy(genai, prompt: str, output_path: Path) -> dict:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash")
    start = time.time()
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(max_output_tokens=16000),
    )
    text = response.text
    output_path.write_text(text, encoding="utf-8")
    return _result("gemini", text, start, output_path)


def call_grok(prompt: str, output_path: Path) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        return {"model": "grok", "status": "error", "error": "pip install openai"}

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


def _result(model: str, text: str, start: float, path: Path) -> dict:
    return {
        "model": model,
        "status": "ok",
        "words": len(text.split()),
        "seconds": round(time.time() - start, 1),
        "file": str(path),
    }


def main():
    parser = argparse.ArgumentParser(description="Deep Research Dispatcher — multi-model parallel research")
    parser.add_argument("--topic", required=True, help="Research topic")
    parser.add_argument("--scope", required=True, help="Detailed scope description")
    parser.add_argument("--output-dir", required=True, help="Output directory for round 1 files")
    parser.add_argument("--models", default="auto",
                        help="Comma-separated models (claude,chatgpt,perplexity,gemini,grok) or 'auto' to use all with valid keys")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which models to use
    if args.models == "auto":
        candidates = list(MODEL_REGISTRY.keys())
    else:
        candidates = [m.strip() for m in args.models.split(",")]

    # Filter to models with valid API keys
    available = []
    skipped = []
    for name in candidates:
        if name not in MODEL_REGISTRY:
            skipped.append((name, "unknown model"))
            continue
        env_key = MODEL_REGISTRY[name]["env_key"]
        if os.environ.get(env_key):
            available.append(name)
        else:
            skipped.append((name, f"{env_key} not set"))

    if skipped:
        print("Skipping (no API key):", flush=True)
        for name, reason in skipped:
            print(f"  · {name}: {reason}", flush=True)
        print(flush=True)

    if not available:
        print("ERROR: No models available. Set at least one API key:", flush=True)
        for name, info in MODEL_REGISTRY.items():
            print(f"  {info['env_key']:25s} → {info['label']}", flush=True)
        raise SystemExit(1)

    print(f"Dispatching {len(available)} model(s) in parallel: {', '.join(available)}", flush=True)
    print(flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=len(available)) as executor:
        futures = {}
        for name in available:
            prompt = build_prompt(args.topic, args.scope, STRATEGIES[name])
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

    manifest = {
        "topic": args.topic,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "models_dispatched": available,
        "models_skipped": [{"model": n, "reason": r} for n, r in skipped],
        "results": results,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    ok_count = sum(1 for r in results if r["status"] == "ok")
    total_words = sum(r.get("words", 0) for r in results if r["status"] == "ok")
    print(f"\n{'='*50}", flush=True)
    print(f"Done: {ok_count}/{len(available)} models succeeded, {total_words:,} total words", flush=True)
    print(f"Manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
