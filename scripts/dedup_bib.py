#!/usr/bin/env python3
"""
dedup_bib.py — merge bibliographies from multiple model outputs.

Strategy:
  1. Parse bibliography sections from each input file
  2. Normalize DOIs (strip http://dx.doi.org/, lowercase)
  3. Cluster by DOI when available
  4. For entries without DOI: fuzzy-match by normalized title
  5. Pick the longest / most-complete entry per cluster as canonical
  6. Emit merged bibliography + dedup-decisions.md sidecar for audit

Usage:
  python3 dedup_bib.py round1/*.md --output sections/bibliography.md
  python3 dedup_bib.py round1/*.md --output bib.md --threshold 0.85
"""

import argparse
import re
import sys
from pathlib import Path

try:
    from rapidfuzz import fuzz
    HAVE_RAPIDFUZZ = True
except ImportError:
    import difflib
    HAVE_RAPIDFUZZ = False


DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
URL_DOI_RE = re.compile(r"https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
BIB_HEADER_RE = re.compile(r"^#{1,3}\s*(bibliography|references|sources)\b", re.IGNORECASE | re.MULTILINE)
TITLE_NORM_RE = re.compile(r"[^a-z0-9]+")
STOPWORDS = {"the", "a", "an", "of", "in", "and", "on", "for", "to", "with", "by"}


def extract_bibliography(text: str):
    m = BIB_HEADER_RE.search(text)
    if not m:
        return []
    tail = text[m.end():]
    next_h = re.search(r"^#{1,3}\s+\S", tail, re.MULTILINE)
    if next_h:
        tail = tail[:next_h.start()]
    entries = []
    for raw in re.split(r"\n(?=\s*[-*]\s|\s*\d+\.\s)", tail):
        raw = raw.strip(" -*\t\n")
        if len(raw) < 20:
            continue
        entries.append(re.sub(r"\s+", " ", raw))
    return entries


def normalize_doi(entry: str):
    m = DOI_RE.search(entry)
    if not m:
        return None
    return m.group(0).lower().rstrip(".,)").strip()


def extract_title_key(entry: str):
    cleaned = re.sub(r"\(\d{4}[a-z]?\)", " ", entry)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"\bdoi:\S+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[A-Z][A-Za-z\-',. ]+?(?:\(\d{4}\))?\.?\s*", "", cleaned)
    tokens = TITLE_NORM_RE.sub(" ", cleaned.lower()).split()
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 2]
    return " ".join(tokens[:20])


def similarity(a: str, b: str) -> float:
    if HAVE_RAPIDFUZZ:
        return fuzz.token_set_ratio(a, b) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def cluster_entries(entries_by_origin, threshold: float):
    items = []
    for origin, entries in entries_by_origin.items():
        for e in entries:
            items.append({
                "text": e,
                "origin": origin,
                "doi": normalize_doi(e),
                "key": extract_title_key(e),
            })

    doi_clusters = {}
    no_doi = []
    for it in items:
        if it["doi"]:
            doi_clusters.setdefault(it["doi"], []).append(it)
        else:
            no_doi.append(it)

    title_clusters = []
    for it in no_doi:
        placed = False
        for cluster in title_clusters:
            if similarity(it["key"], cluster[0]["key"]) >= threshold:
                cluster.append(it)
                placed = True
                break
        if not placed:
            title_clusters.append([it])

    all_clusters = list(doi_clusters.values()) + title_clusters
    return all_clusters


def pick_canonical(cluster):
    return max(cluster, key=lambda it: (len(it["text"]), bool(it["doi"])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="Input markdown files")
    ap.add_argument("--output", required=True, help="Output merged bibliography")
    ap.add_argument("--decisions", help="Sidecar dedup-decisions.md (default: alongside output)")
    ap.add_argument("--threshold", type=float, default=0.85, help="Fuzzy match threshold (0–1)")
    args = ap.parse_args()

    entries_by_origin = {}
    for path in args.inputs:
        p = Path(path)
        if not p.exists():
            print(f"skip (not found): {path}", file=sys.stderr)
            continue
        entries = extract_bibliography(p.read_text(encoding="utf-8", errors="replace"))
        if entries:
            entries_by_origin[str(p)] = entries
            print(f"  {p.name}: {len(entries)} entries", file=sys.stderr)

    if not entries_by_origin:
        sys.exit("No bibliography sections found.")

    clusters = cluster_entries(entries_by_origin, args.threshold)
    total_in = sum(len(es) for es in entries_by_origin.values())
    print(f"Input: {total_in} entries  →  Output: {len(clusters)} unique", file=sys.stderr)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    decisions_path = Path(args.decisions) if args.decisions else out_path.with_name("dedup-decisions.md")

    canonical_entries = []
    decisions = ["# Bibliography Dedup Decisions", "",
                 f"Input: {total_in} entries across {len(entries_by_origin)} files.",
                 f"Output: {len(clusters)} unique entries (fuzzy threshold: {args.threshold}).", ""]
    for i, cluster in enumerate(sorted(clusters, key=lambda c: pick_canonical(c)["text"].lower())):
        canonical = pick_canonical(cluster)
        canonical_entries.append(canonical["text"])
        if len(cluster) > 1:
            decisions.append(f"## Cluster {i+1} — {len(cluster)} entries merged")
            decisions.append("")
            decisions.append(f"**Canonical** ({Path(canonical['origin']).name}): `{canonical['text'][:240]}`")
            decisions.append("")
            decisions.append("**Merged from:**")
            for it in cluster:
                if it is not canonical:
                    decisions.append(f"- ({Path(it['origin']).name}) `{it['text'][:240]}`")
            decisions.append("")

    out_lines = [
        "# Master Bibliography",
        "",
        f"Deduplicated across {len(entries_by_origin)} model outputs ({total_in} → {len(canonical_entries)}).",
        "",
    ]
    for e in canonical_entries:
        out_lines.append(f"- {e}")
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    decisions_path.write_text("\n".join(decisions), encoding="utf-8")
    print(f"Bibliography:  {out_path}")
    print(f"Decisions log: {decisions_path}")


if __name__ == "__main__":
    main()
