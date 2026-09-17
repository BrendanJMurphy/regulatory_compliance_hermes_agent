"""Regulator feed fetcher: the one component that talks to the outside world.

Pulls RSS/Atom feeds from an explicit allowlist of regulator hosts and writes them into the
cache format the MCP server reads (``regulatory_feed/<source>.json``). It runs as a separate
scheduled job with its own egress allowance; the agent itself never has network access.

Design points:

* **Allowlist, not denylist.** A feed URL must be on a host in ``ALLOWED_HOSTS`` or it is
  refused before any request is made.
* **Idempotent merge.** Existing releases are kept, new ones appended, and an item with a
  known ``release_id`` is never overwritten: a regulator's page edit must not silently
  change text that a draft already quoted. Changed text arrives as a new release id.
* **Plain text only.** Item HTML is stripped to text; the agent quotes from this text and
  ``draft_checks`` verifies quotes against it, so it must be stable and deterministic.

    compliance-feed fetch --source SEC --url https://www.sec.gov/rss/... --out data/regulatory_feed
    compliance-feed fetch --source FINRA --file fixtures/finra.xml --out data/regulatory_feed   # offline
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from .logging_setup import configure_logging, get_logger
from .models import Release

log = get_logger(__name__)

ALLOWED_HOSTS: frozenset[str] = frozenset({"www.sec.gov", "sec.gov", "www.finra.org", "finra.org", "www.fca.org.uk", "fca.org.uk"})

_ATOM = "{http://www.w3.org/2005/Atom}"
_TAGS = re.compile(r"<[^>]+>")


class FeedRefused(ValueError):
    """The URL is not on the regulator allowlist."""


def _text_of(node: ET.Element | None) -> str:
    if node is None:
        return ""
    raw = "".join(node.itertext()) if node.text is None else node.text
    return html.unescape(_TAGS.sub(" ", raw or "")).strip()


def _normalise_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _iso_date(raw: str) -> str:
    """Accept RFC 2822 (RSS) or ISO 8601 (Atom) and return YYYY-MM-DD in UTC."""
    if not raw:
        return datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt.astimezone(UTC).strftime("%Y-%m-%d")


def parse_feed(xml_text: str, source: str) -> list[Release]:
    """Parse RSS 2.0 or Atom into releases. The id is derived from source, date, and a hash of the text."""
    root = ET.fromstring(xml_text)
    items = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
    releases: list[Release] = []
    for item in items:
        is_atom = item.tag.startswith(_ATOM)
        title = _text_of(item.find(f"{_ATOM}title" if is_atom else "title"))
        if is_atom:
            link_node = item.find(f"{_ATOM}link")
            url = (link_node.get("href") if link_node is not None else "") or ""
            published = _iso_date(_text_of(item.find(f"{_ATOM}updated")) or _text_of(item.find(f"{_ATOM}published")))
            body = _text_of(item.find(f"{_ATOM}content")) or _text_of(item.find(f"{_ATOM}summary"))
        else:
            url = _text_of(item.find("link"))
            published = _iso_date(_text_of(item.find("pubDate")))
            body = _text_of(item.find("{http://purl.org/rss/1.0/modules/content/}encoded")) or _text_of(item.find("description"))
        text = _normalise_ws(body)
        if not title or not text:
            continue
        digest = hashlib.sha256(f"{title}\n{text}".encode()).hexdigest()[:8]
        releases.append(
            Release(
                release_id=f"{source}-{published.replace('-', '')}-{digest}", source=source, published=published, title=_normalise_ws(title), url=url, text=text
            )
        )
    return releases


def fetch_xml(url: str, *, timeout: float = 20.0) -> str:
    host = urlparse(url).hostname or ""
    if host.lower() not in ALLOWED_HOSTS:
        raise FeedRefused(f"host '{host}' is not on the regulator allowlist")
    import httpx

    resp = httpx.get(url, timeout=timeout, follow_redirects=False, headers={"User-Agent": "compliance-feed-fetcher/1.0"})
    resp.raise_for_status()
    return resp.text


def merge_into_cache(cache_file: Path, source: str, releases: list[Release]) -> tuple[int, int]:
    """Append unknown releases to the source's cache file. Returns (added, kept)."""
    existing: list[dict] = []
    if cache_file.exists():
        existing = json.loads(cache_file.read_text(encoding="utf-8")).get("releases", [])
    known = {r["release_id"] for r in existing}
    added = [r.model_dump() for r in releases if r.release_id not in known]
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": source, "fetched": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "releases": existing + added}
    tmp = cache_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(cache_file)
    return len(added), len(existing)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="compliance-feed", description="Fetch regulator feeds into the MCP server's cache.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--source", required=True, help="SEC, FINRA, or FCA")
    src = fetch.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="feed URL; host must be on the allowlist")
    src.add_argument("--file", help="local RSS/Atom file (offline use and tests)")
    fetch.add_argument("--out", required=True, help="cache directory, e.g. data/regulatory_feed")
    args = parser.parse_args(argv)

    try:
        xml_text = Path(args.file).read_text(encoding="utf-8") if args.file else fetch_xml(args.url)
    except FeedRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    releases = parse_feed(xml_text, args.source.upper())
    added, kept = merge_into_cache(Path(args.out) / f"{args.source.lower()}.json", args.source.upper(), releases)
    log.info("feed merged", extra={"source": args.source.upper(), "parsed": len(releases), "added": added, "kept": kept})
    print(f"{args.source.upper()}: {len(releases)} parsed, {added} new, {kept} already cached")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
