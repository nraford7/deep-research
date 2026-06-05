#!/usr/bin/env python3
"""
cost.py — pre-flight cost estimator and budget gate.

Pricing table is in USD per million tokens, accurate as of early 2026.
These are best-effort estimates — check provider websites for current rates.
The tool is conservative (rounds up) and adds a 15% safety margin.

Usage as a library (called from dispatch.py):
  from scripts.cost import estimate_run, enforce_budget

Usage as a CLI:
  python3 scripts/cost.py --models claude,chatgpt,gemini --prompt-words 1500 --output-words 25000
"""

import argparse
import sys


# USD per 1M tokens. Conservative defaults — refresh periodically.
PRICING = {
    "claude":     {"in": 15.00, "out": 75.00, "model": "claude-opus-4"},
    "chatgpt":    {"in":  2.00, "out":  8.00, "model": "gpt-4.1"},
    "perplexity": {"in":  5.00, "out":  5.00, "model": "sonar-deep-research", "search_fee": 0.50},
    "gemini":     {"in":  1.25, "out": 10.00, "model": "gemini-2.5-pro"},
    "grok":       {"in":  3.00, "out": 15.00, "model": "grok-3-latest"},
}

# Rough token-per-word ratio for English prose
TOKENS_PER_WORD = 1.35
SAFETY_MARGIN = 1.15


def words_to_tokens(words: int) -> int:
    return int(words * TOKENS_PER_WORD)


def estimate_model(model: str, prompt_words: int, output_words: int) -> dict:
    p = PRICING.get(model)
    if not p:
        return {"model": model, "error": "unknown model in pricing table"}
    in_tokens = words_to_tokens(prompt_words)
    out_tokens = words_to_tokens(output_words)
    in_cost = (in_tokens / 1_000_000) * p["in"]
    out_cost = (out_tokens / 1_000_000) * p["out"]
    extra = p.get("search_fee", 0.0)
    subtotal = (in_cost + out_cost + extra) * SAFETY_MARGIN
    return {
        "model": model,
        "model_id": p["model"],
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "in_cost": round(in_cost, 3),
        "out_cost": round(out_cost, 3),
        "search_fee": extra,
        "total": round(subtotal, 3),
    }


def estimate_run(models, prompt_words: int, output_words: int) -> dict:
    per_model = [estimate_model(m, prompt_words, output_words) for m in models]
    total = round(sum(r.get("total", 0) for r in per_model), 2)
    return {"per_model": per_model, "total": total}


def format_report(estimate: dict) -> str:
    lines = ["Cost estimate (Round 1 only — Rounds 2–4 add ~30–80% on top):", ""]
    lines.append(f"  {'Model':<14}{'Model ID':<26}{'In $':>10}{'Out $':>10}{'Total $':>12}")
    lines.append("  " + "-" * 72)
    for r in estimate["per_model"]:
        if "error" in r:
            lines.append(f"  {r['model']:<14}ERROR: {r['error']}")
            continue
        lines.append(
            f"  {r['model']:<14}{r['model_id']:<26}{r['in_cost']:>10.2f}{r['out_cost']:>10.2f}{r['total']:>12.2f}"
        )
    lines.append("  " + "-" * 72)
    lines.append(f"  {'Round 1 total':<50}{'':>10}{estimate['total']:>12.2f}")
    lines.append("")
    lines.append(f"  Rounds 2–4 (comparison + integration + fact-check) typically add 30–80% — budget {estimate['total']*1.5:.2f}–{estimate['total']*1.8:.2f} USD total.")
    return "\n".join(lines)


def enforce_budget(estimate: dict, max_cost: float | None, prompt=True) -> bool:
    """Returns True if run should proceed, False otherwise."""
    full_estimate = estimate["total"] * 1.65
    if max_cost is not None and full_estimate > max_cost:
        print(f"\n  ✗ BUDGET EXCEEDED: estimated full-run cost ${full_estimate:.2f} > --max-cost-usd ${max_cost:.2f}", file=sys.stderr)
        print(f"    To proceed: re-run with --max-cost-usd {full_estimate:.0f} (or higher), or use --models to trim.", file=sys.stderr)
        return False
    if prompt and estimate["total"] >= 5.0:
        try:
            ans = input(f"\n  Estimated Round 1 cost: ${estimate['total']:.2f} (full run ~${full_estimate:.2f}). Proceed? [y/N] ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="claude,chatgpt,perplexity,gemini,grok")
    ap.add_argument("--prompt-words", type=int, default=1500)
    ap.add_argument("--output-words", type=int, default=25000)
    ap.add_argument("--max-cost-usd", type=float)
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",")]
    estimate = estimate_run(models, args.prompt_words, args.output_words)
    print(format_report(estimate))
    if args.max_cost_usd is not None:
        full = estimate["total"] * 1.65
        status = "OK" if full <= args.max_cost_usd else "EXCEEDED"
        print(f"\n  Budget check vs --max-cost-usd {args.max_cost_usd:.2f}: {status} (est full ${full:.2f})")


if __name__ == "__main__":
    main()
