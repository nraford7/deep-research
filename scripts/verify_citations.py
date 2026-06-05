#!/usr/bin/env python3
"""
verify_citations.py — adversarial citation verification.

Extracts every inline citation [Author, Year] and every URL from a markdown
file (or all .md files in a directory), then resolves each against OpenAlex
and Crossref (free, no API key). Flags:

  - orphaned inline cites: [Author, Year] with no bibliography entry
  - unresolvable bib entries: cannot find the work in OpenAlex/Crossref
  - URL liveness: HTTP HEAD with redirects, mark dead URLs
  - suspicious entries: bib entries that resolve to a very different title

Output: a verification report in markdown.

Usage:
  python3 verify_citations.py <path> --output verify-report.md
  python3 verify_citations.py research/topic/sections/ --output factcheck/citations.md

Set CONTACT_EMAIL env var for the OpenAlex/Crossref "polite pool" — recommended.
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

try:
    import requests
except ImportError:
    sys.stderr.write("Missing dep: pip install requests\n")
    sys.exit(1)


CONTACT = os.environ.get("CONTACT_EMAIL", "anonymous@example.com")
OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"

INLINE_CITE_RE = re.compile(r"\[([A-Z][A-Za-z\-' ]+?(?:\s+(?:et al\.|&\s+[A-Z][A-Za-z\-']+))?),\s*(\d{4}[a-z]?)\]")
URL_RE = re.compile(r"https?://[^\s\)\]\>]+")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
BIB_HEADER_RE = re.compile(r"^#{1,3}\s*(bibliography|references|sources)\b", re.IGNORECASE | re.MULTILINE)


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": f"deep-research/1.0 (mailto:{CONTACT})"})
    return s


def find_md_files(path: Path):
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.md"))


def extract_inline_cites(text: str):
    return [{"author": m.group(1).strip(), "year": m.group(2)} for m in INLINE_CITE_RE.finditer(text)]


def extract_urls(text: str):
    return list({m.group(0).rstrip(".,;") for m in URL_RE.finditer(text)})


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
        entries.append(raw)
    return entries


def resolve_openalex(s, entry: str):
    doi_match = DOI_RE.search(entry)
    try:
        if doi_match:
            r = s.get(f"{OPENALEX}/works/doi:{doi_match.group(0).lower()}", params={"mailto": CONTACT}, timeout=15)
            if r.ok:
                return r.json()
        title = entry[:240].replace("\n", " ")
        r = s.get(f"{OPENALEX}/works", params={"search": title, "per-page": 1, "mailto": CONTACT}, timeout=15)
        if r.ok:
            results = r.json().get("results", [])
            return results[0] if results else None
    except requests.RequestException:
        return None
    return None


def resolve_crossref(s, entry: str):
    doi_match = DOI_RE.search(entry)
    try:
        if doi_match:
            r = s.get(f"{CROSSREF}/works/{doi_match.group(0)}", params={"mailto": CONTACT}, timeout=15)
            if r.ok:
                return r.json().get("message")
        r = s.get(f"{CROSSREF}/works", params={"query.bibliographic": entry[:240], "rows": 1, "mailto": CONTACT}, timeout=15)
        if r.ok:
            items = r.json().get("message", {}).get("items", [])
            return items[0] if items else None
    except requests.RequestException:
        return None
    return None


def title_match(entry: str, resolved_title: str) -> float:
    if not resolved_title:
        return 0.0
    a = re.sub(r"[^a-z0-9 ]+", "", entry.lower())
    b = re.sub(r"[^a-z0-9 ]+", "", resolved_title.lower())
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(b_tokens)


def resolve_entry(s, entry: str):
    oa = resolve_openalex(s, entry)
    if oa:
        title = (oa.get("title") or "").strip()
        match = title_match(entry, title)
        return {
            "source": "openalex",
            "title": title,
            "doi": oa.get("doi"),
            "id": oa.get("id"),
            "cited_by": oa.get("cited_by_count"),
            "year": oa.get("publication_year"),
            "title_match": round(match, 2),
        }
    cr = resolve_crossref(s, entry)
    if cr:
        title = (cr.get("title") or [""])[0]
        match = title_match(entry, title)
        return {
            "source": "crossref",
            "title": title,
            "doi": cr.get("DOI"),
            "year": (cr.get("issued", {}).get("date-parts") or [[None]])[0][0],
            "title_match": round(match, 2),
        }
    return None


def check_url(s, url: str):
    try:
        r = s.head(url, allow_redirects=True, timeout=10)
        if r.status_code >= 400:
            r = s.get(url, allow_redirects=True, timeout=10, stream=True)
        return r.status_code
    except requests.RequestException:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="Markdown file or directory")
    ap.add_argument("--output", default="verify-report.md", help="Where to write the report")
    ap.add_argument("--check-urls", action="store_true", help="HEAD-check every URL (slow)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    s = session()
    files = find_md_files(Path(args.path))
    if not files:
        sys.exit(f"No .md files found at {args.path}")

    all_cites, all_urls, all_bib = [], [], []
    bib_origin = {}
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for c in extract_inline_cites(text):
            c["file"] = str(f)
            all_cites.append(c)
        for u in extract_urls(text):
            all_urls.append((u, str(f)))
        for entry in extract_bibliography(text):
            all_bib.append(entry)
            bib_origin.setdefault(entry, []).append(str(f))

    bib_unique = list(dict.fromkeys(all_bib))
    print(f"Files scanned: {len(files)}", flush=True)
    print(f"Inline citations: {len(all_cites)}  Bibliography entries: {len(bib_unique)}  URLs: {len(all_urls)}", flush=True)

    resolutions = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(resolve_entry, s, e): e for e in bib_unique}
        done = 0
        for fut in as_completed(futures):
            entry = futures[fut]
            try:
                resolutions[entry] = fut.result()
            except Exception as exc:
                resolutions[entry] = {"error": str(exc)}
            done += 1
            if done % 10 == 0:
                print(f"  resolved {done}/{len(bib_unique)}", flush=True)

    bib_keys = []
    for entry in bib_unique:
        author_m = re.match(r"([A-Z][A-Za-z\-']+)", entry)
        year_m = re.search(r"\b(19|20)\d{2}\b", entry)
        if author_m and year_m:
            bib_keys.append((author_m.group(1).lower(), year_m.group(0), entry))

    orphans = []
    for c in all_cites:
        last = c["author"].split()[-1].lower().rstrip(",")
        if c["author"].lower().endswith("et al."):
            last = c["author"].split()[0].lower()
        if not any(k[0] == last and k[1] == c["year"] for k in bib_keys):
            orphans.append(c)

    dead_urls = []
    if args.check_urls:
        unique_urls = list({u for u, _ in all_urls})
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(check_url, s, u): u for u in unique_urls}
            for fut in as_completed(futures):
                code = fut.result()
                if code is None or code >= 400:
                    dead_urls.append((futures[fut], code))

    unresolved = [e for e, r in resolutions.items() if not r or r.get("error")]
    weak_match = [(e, r) for e, r in resolutions.items() if r and not r.get("error") and r.get("title_match", 0) < 0.4]
    resolved = [(e, r) for e, r in resolutions.items() if r and not r.get("error") and r.get("title_match", 0) >= 0.4]

    out = [
        "# Citation Verification Report",
        "",
        f"- Files scanned: **{len(files)}**",
        f"- Inline citations found: **{len(all_cites)}**",
        f"- Bibliography entries: **{len(bib_unique)}**",
        f"- URLs: **{len(all_urls)}**" + ("" if not args.check_urls else f" — dead: **{len(dead_urls)}**"),
        "",
        "## Summary",
        "",
        f"| Outcome | Count |",
        f"|---|---|",
        f"| Resolved (title match ≥ 0.4) | {len(resolved)} |",
        f"| Weak match (< 0.4) | {len(weak_match)} |",
        f"| Unresolved | {len(unresolved)} |",
        f"| Orphaned inline cites | {len(orphans)} |",
        f"| Dead URLs | {len(dead_urls) if args.check_urls else 'not checked'} |",
        "",
    ]

    if unresolved:
        out += ["## ⚠ Unresolved bibliography entries", "", "Could not match against OpenAlex or Crossref. Likely hallucinated or non-academic.", ""]
        for e in unresolved[:200]:
            out.append(f"- `{e[:300]}`")
        out.append("")

    if weak_match:
        out += ["## ⚠ Weak title match", "", "Resolved to a work whose title shares few tokens with the citation. Possible misattribution.", ""]
        for e, r in weak_match[:200]:
            out.append(f"- `{e[:200]}` → **{r['title'][:200]}** (match {r['title_match']}, {r['source']})")
        out.append("")

    if orphans:
        out += ["## ⚠ Orphaned inline citations", "", "Inline `[Author, Year]` with no matching bibliography entry.", ""]
        for c in orphans[:200]:
            out.append(f"- `[{c['author']}, {c['year']}]` in `{c['file']}`")
        out.append("")

    if args.check_urls and dead_urls:
        out += ["## ⚠ Dead URLs", "", "Returned 4xx/5xx or no response.", ""]
        for u, code in dead_urls[:200]:
            out.append(f"- {code or 'no-response'} — {u}")
        out.append("")

    if resolved:
        out += ["## ✓ Resolved entries (sample of 50)", ""]
        for e, r in resolved[:50]:
            cited_by = r.get("cited_by", "—")
            out.append(f"- `{e[:120]}` → **{r['title'][:120]}** ({r.get('year','?')}, cited {cited_by}× via {r['source']})")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("\n".join(out), encoding="utf-8")
    print(f"\nReport: {args.output}", flush=True)

    json_path = Path(args.output).with_suffix(".json")
    json_path.write_text(json.dumps({
        "files": [str(f) for f in files],
        "stats": {
            "inline_cites": len(all_cites),
            "bib_entries": len(bib_unique),
            "urls": len(all_urls),
            "resolved": len(resolved),
            "weak_match": len(weak_match),
            "unresolved": len(unresolved),
            "orphans": len(orphans),
            "dead_urls": len(dead_urls) if args.check_urls else None,
        },
        "unresolved": unresolved,
        "orphans": orphans,
    }, indent=2), encoding="utf-8")
    print(f"JSON: {json_path}", flush=True)


if __name__ == "__main__":
    main()
