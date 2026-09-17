"""Server-side checks on draft content.

The skills tell the model to quote regulatory text verbatim and to carry the evidence
manifest hash into an index. Prompts are not controls, so the same rules are enforced here,
where the model cannot talk its way past them. A draft that fails is refused with the exact
reasons, and the agent gets to try again with corrected content.

Checks by draft kind:

* ``policy_mapping``: every quoted string in the obligations table must appear verbatim
  (whitespace-normalised, case-sensitive) in the text of one of the releases named in
  ``related_ids``. Catches paraphrase and invention at the point of writing.
* ``evidence_pack_index``: the body must cite a manifest hash, and that hash must equal the
  hash of the evidence bundle recomputed now for the same control and period. Catches an
  index that drifted from the evidence, or a hash the model made up.

Other kinds have no structural check beyond the non-empty title and body.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .models import DraftKind, Release

# A markdown table row whose third cell holds the quote: | # | type | "quote" | ...
_QUOTE_CELL = re.compile(r'^\|\s*\d+\s*\|[^|]*\|\s*"(.+?)"\s*\|', re.M)
_SHA256 = re.compile(r"\b[0-9a-f]{64}\b")
_INDEX_TITLE = re.compile(r"Evidence index (?P<control>[A-Z0-9-]+) (?P<start>\d{4}-\d{2}-\d{2})\.\.(?P<end>\d{4}-\d{2}-\d{2})")


class DraftRejected(ValueError):
    """The draft violates a content rule. The message lists every failing item."""


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_policy_mapping(body: str, related_ids: tuple[str, ...], lookup_release: Callable[[str], Release | None]) -> None:
    quotes = [_normalise(q) for q in _QUOTE_CELL.findall(body)]
    if not quotes:
        raise DraftRejected('policy_mapping draft has no obligations table with quoted text (| # | type | "quote" | ...)')
    corpus = [_normalise(r.text) for r in (lookup_release(rid) for rid in related_ids) if r is not None]
    if not corpus:
        raise DraftRejected("related_ids must include at least one known release id so quotes can be verified")
    missing = [q for q in quotes if not any(q in text for text in corpus)]
    if missing:
        listed = "; ".join(f'"{q[:80]}{"..." if len(q) > 80 else ""}"' for q in missing)
        raise DraftRejected(f"{len(missing)} quote(s) are not verbatim from the related release(s): {listed}")


def check_evidence_pack_index(body: str, title: str, recompute_hash: Callable[[str, str, str], str | None]) -> None:
    match = _INDEX_TITLE.search(title)
    if not match:
        raise DraftRejected("evidence_pack_index title must be 'Evidence index <control_id> <start>..<end>'")
    cited = set(_SHA256.findall(body))
    if not cited:
        raise DraftRejected("evidence_pack_index body must cite the manifest SHA-256 from evidence_bundle")
    actual = recompute_hash(match["control"], match["start"], match["end"])
    if actual is None:
        raise DraftRejected(f"cannot recompute evidence for {match['control']} {match['start']}..{match['end']}")
    if actual not in cited:
        raise DraftRejected("cited manifest hash does not match the evidence bundle for this control and period; re-run evidence_bundle")


def check_draft(
    *,
    kind: DraftKind,
    title: str,
    body: str,
    related_ids: tuple[str, ...],
    lookup_release: Callable[[str], Release | None],
    recompute_hash: Callable[[str, str, str], str | None],
) -> None:
    """Raise ``DraftRejected`` if the draft violates the rule for its kind."""
    if kind is DraftKind.POLICY_MAPPING:
        check_policy_mapping(body, related_ids, lookup_release)
    elif kind is DraftKind.EVIDENCE_PACK_INDEX:
        check_evidence_pack_index(body, title, recompute_hash)
