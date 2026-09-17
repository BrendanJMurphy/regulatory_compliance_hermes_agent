---
name: regulatory-intake
description: Draft obligation extraction and policy mapping for new regulatory releases.
version: 1.0.0
metadata:
  hermes:
    tags: [compliance, regulatory-change]
    category: compliance
---
# Regulatory Intake

## When to use
On the scheduled morning run, or when an analyst asks to "process", "map", or "assess"
a regulatory release. Output is always a draft for human review, never a decision.

## Procedure
1. `regulatory_releases(requester, since=<yesterday or the date given>)`. If none, report "no new releases" and stop.
2. For each release, `regulatory_release_get(requester, release_id)` and read the full text.
3. Extract obligations. An obligation is a sentence that requires, prohibits, or sets a deadline
   for the firm. For each, record: verbatim quote, obligation type (requirement | prohibition |
   deadline | record-keeping | disclosure), effective or compliance date if stated, and who it applies to.
4. `policy_list(requester)` and, for each obligation, `policy_lookup(requester, <obligation terms>)`
   to find candidate policies and controls. Mark each mapping as one of:
   - `covered`: current policy text already satisfies the obligation (cite the section),
   - `gap`: policy is silent or conflicts (quote both sides),
   - `review`: unclear, needs analyst judgement.
5. Compose the draft body using `templates/mapping.md`. Include the release id, the fetched URL,
   every obligation with its quote, the mapping table, and a proposed next step for each gap
   (e.g. "amend POL-GE Gift Limits before 2027-01-01; owner dana.whitfield").
6. `draft_create(requester, kind="policy_mapping", title="<source> <release id>: <short title>",
   body=<draft>, related_ids=[release id, policy ids, control ids])`.
   The server verifies every quoted string in the obligations table against the text of the
   releases in `related_ids`. A paraphrase is refused with `draft_rejected` and the offending
   quotes listed: fix them by copying the exact text (`regulatory_release_get` again if needed)
   and resubmit. Do not shorten quotes to make them pass; quote the full clause.
7. Reply with the draft id, a one-line summary per release (n obligations, n gaps), and
   "Pending review by an approver. Nothing has been changed."

## Pitfalls
- Never mark an obligation `covered` without a citation from the current policy.
- Effective dates: copy the regulator's exact wording; do not infer a date that is not stated.
- One draft per release, not one per obligation, so the approver sees the whole picture.
- If a release is outside scope (e.g. banking capital rules), say so in the summary and still
  file a draft with mapping "not applicable" so the decision is recorded.

## Verification
Every obligation row has a verbatim quote that appears in the release text. Every `covered` row has a citation.
