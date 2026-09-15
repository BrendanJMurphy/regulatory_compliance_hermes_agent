"""Model-risk validation for the regulatory-intake step.

Sends each release in the feed to the governed model endpoint with the same extraction
instructions the skill uses, then scores the JSON output against the gold set:
  - obligation recall: fraction of gold quotes found verbatim (case-insensitive substring) in the output
  - hallucination rate: fraction of output quotes that do not appear in the release text
  - date accuracy: fraction of gold obligations with a date where the output date matches

Run before go-live and after any model change. Results land in eval/results/<timestamp>.json.
Thresholds are set in the model inventory entry (docs/controls-matrix.md, MRM-1).

    COMPLIANCE_MODEL_BASE_URL=... COMPLIANCE_MODEL_API_KEY=... COMPLIANCE_MODEL=... python eval/validate_extraction.py
    python eval/validate_extraction.py --dry-run     # scores a canned output to exercise the scorer
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEED = ROOT.parent / "mcp" / "data" / "regulatory_feed"
GOLD = ROOT / "gold"
RESULTS = ROOT / "results"

PROMPT = """You extract obligations from a regulatory release for a compliance team.
An obligation is a sentence or clause that requires, prohibits, or sets a deadline for the firm.
Return JSON only: {"obligations": [{"type": "requirement|prohibition|deadline|record-keeping|disclosure", "quote": "<verbatim text from the release>", "date": "YYYY-MM-DD or null"}]}
Quotes must be copied exactly from the release. Do not invent dates.

RELEASE:
"""

THRESHOLDS = {"recall": 0.85, "hallucination": 0.05, "date_accuracy": 0.90}


def load_feed() -> dict[str, dict]:
    out = {}
    for p in FEED.glob("*.json"):
        for r in json.loads(p.read_text())["releases"]:
            out[r["release_id"]] = r
    return out


def call_model(text: str) -> dict:
    import httpx

    base = os.environ["COMPLIANCE_MODEL_BASE_URL"].rstrip("/")
    r = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['COMPLIANCE_MODEL_API_KEY']}"},
        json={"model": os.environ["COMPLIANCE_MODEL"], "temperature": 0, "messages": [{"role": "user", "content": PROMPT + text}]},
        timeout=120,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    start, end = content.find("{"), content.rfind("}")
    return json.loads(content[start : end + 1])


def score(release_text: str, gold: dict, output: dict) -> dict:
    text = release_text.lower()
    out_quotes = [o.get("quote", "") for o in output.get("obligations", [])]
    found = 0
    date_hits = date_total = 0
    for g in gold["obligations"]:
        gq = g["quote"].lower()
        match = next((o for o in output.get("obligations", []) if gq in o.get("quote", "").lower() or o.get("quote", "").lower() in gq and len(o.get("quote", "")) > 20), None)
        if match:
            found += 1
            if g["date"]:
                date_total += 1
                date_hits += int(match.get("date") == g["date"])
    halluc = sum(1 for q in out_quotes if q and q.lower() not in text)
    return {
        "release_id": gold["release_id"],
        "recall": found / len(gold["obligations"]),
        "hallucination": halluc / max(1, len(out_quotes)),
        "date_accuracy": (date_hits / date_total) if date_total else 1.0,
        "n_gold": len(gold["obligations"]),
        "n_output": len(out_quotes),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="score the gold set against itself (scorer self-test, no model call)")
    a = ap.parse_args()
    feed = load_feed()
    rows = []
    for gp in sorted(GOLD.glob("*.json")):
        gold = json.loads(gp.read_text())
        rel = feed[gold["release_id"]]
        output = {"obligations": gold["obligations"]} if a.dry_run else call_model(rel["text"])
        rows.append(score(rel["text"], gold, output))
    agg = {k: sum(r[k] for r in rows) / len(rows) for k in ("recall", "hallucination", "date_accuracy")}
    passed = agg["recall"] >= THRESHOLDS["recall"] and agg["hallucination"] <= THRESHOLDS["hallucination"] and agg["date_accuracy"] >= THRESHOLDS["date_accuracy"]
    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "model": os.environ.get("COMPLIANCE_MODEL", "dry-run"), "thresholds": THRESHOLDS, "aggregate": agg, "per_release": rows, "passed": passed}
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{report['ts'].replace(':', '')}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"aggregate": agg, "passed": passed, "report": str(out)}, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
