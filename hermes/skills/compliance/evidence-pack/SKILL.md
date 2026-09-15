---
name: evidence-pack
description: Assemble a draft evidence-pack index for a control over a period.
version: 1.0.0
metadata:
  hermes:
    tags: [compliance, audit, evidence]
    category: compliance
---
# Evidence Pack

## When to use
An analyst asks for the evidence pack, exam support, or audit index for a control
(e.g. "evidence pack for CTL-GE-01 for H1 2026").

## Procedure
1. Confirm the control id and the period (start and end dates). If either is missing, ask once.
2. `evidence_bundle(requester, control_id, start, end)`. The manifest lists policy versions in force,
   test results, change tickets, detected gaps, and a manifest hash.
3. For each policy version in the manifest, `policy_get(requester, policy_id, as_of=<period end>)`
   to confirm which version applied at period end, and note any version change inside the period.
4. Build the index using `templates/index.md`: control description and owner, period, the policy
   versions with effective dates and document hashes, each test with date, tester, result, and notes,
   each ticket with status, the gaps list verbatim from the tool, and the manifest hash.
5. `draft_create(requester, kind="evidence_pack_index", title="Evidence index <control> <start>..<end>",
   body=<index>, related_ids=[control id, test ids, ticket ids])`.
6. Reply with the draft id, counts (policy versions, tests, tickets, gaps), and the gaps in full.
   State that an approver must sign off before the pack is used.

## Pitfalls
- Never omit or soften a gap. Examiners will find it; the approver must see it first.
- Do not describe a failed test as remediated unless a ticket in the manifest says so.
- Do not include document text in the index, only identifiers, versions, and hashes.

## Verification
Every id in the index appears in the manifest. The manifest hash is included unchanged.
