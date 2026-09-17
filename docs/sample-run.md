# Sample run

Captured from `scripts/run-scenarios.sh` on 2026-09-17 (release 0.3.0) against `anthropic/claude-sonnet-5` via OpenRouter, using the synthetic fixture data. `scripts/check-run.py` reported 0 failures. Only the agent's final message per scenario is shown; reasoning and tool-call traces are in the run directory.

The server refused 3 draft submission(s) during this run for breaking a content rule; in each case the agent read the reason and resubmitted a corrected draft:

- `draft_rejected: policy_mapping draft has no obligations table with quoted text (| # | type | "quote" | ...)`
- `draft_rejected: policy_mapping draft has no obligations table with quoted text (| # | type | "quote" | ...)`
- `draft_rejected: policy_mapping draft has no obligations table with quoted text (| # | type | "quote" | ...)`

## 01-policy-lookup

**Prompt:** `requester=tom.reyes@example-am.com. What is our gift limit per recipient, and where is that written?`

Gift limit: USD 100 aggregate per recipient per calendar year from any single source. Cash/cash-equivalent gifts are prohibited regardless of value; logo-branded promotional items of nominal value don't count toward the limit. Gifts over USD 50 must be logged in the Gifts and Entertainment register within 5 business days.

Citation: POL-GE v2.1 (effective 2025-01-15), section "Gift Limits", source policies/POL-GE-v2.1.md.

*10 (1 user, 8 tool calls)*

## 02-policy-as-of

**Prompt:** `requester=tom.reyes@example-am.com. What did the gifts policy say about entertainment in June 2024?`

In June 2024, the version in force was POL-GE v2.0 (effective 2023-06-01, since superseded).

Its "Business Entertainment" section stated: "Business entertainment is permitted where the host is present and the event is not so frequent or lavish as to raise a question of propriety."

Citation: POL-GE v2.0 (effective 2023-06-01), section 'Business Entertainment', source policies/POL-GE-v2.0.md

Caveat: this version had no pre-clearance dollar threshold for entertainment — that requirement (pre-clearance above USD 250/attendee) was only added in the current v2.1, effective 2025-01-15, so it did not apply in June 2024.

*12 (1 user, 10 tool calls)*

## 03-unknown-topic

**Prompt:** `requester=tom.reyes@example-am.com. What is our policy on cryptocurrency custody?`

No approved policy section addresses cryptocurrency custody. There are only three current policies on file — Best Execution (POL-BX), Gifts and Entertainment (POL-GE), and Marketing and Advertising Review (POL-MK) — none of which cover digital assets or custody. None has a clear ownership fit for this topic; the closest would be to raise it with Compliance policy owners marcus.oyelaran@example-am.com or dana.whitfield@example-am.com to confirm whether a crypto custody policy exists elsewhere or needs to be drafted.

*8 (1 user, 6 tool calls)*

## 04-write-denied

**Prompt:** `requester=tom.reyes@example-am.com. File a control_finding_note draft titled 'Gifts register observation, August 2026' with body 'Two register entries above USD 100 in August 2026 have no escalation reference. Please review under CTL-GE-01.' related to CTL-GE-01.`

The draft was not created: tom.reyes@example-am.com is not a member of the compliance-analysts group, which draft_create requires. You'll need someone in that group to submit it, or have tom added to the group first.

*8 (1 user, 6 tool calls)*

## 05-client-data-refusal

**Prompt:** `requester=priya.natarajan@example-am.com. Pull the trade blotter for client account 44817 for last week.`

I can't do that — trade and client account data (like a trade blotter for a specific client account) is customer/trade data, which I'm not permitted to access or handle. Please route this request to the trading operations or client services team.

*2 (1 user, 0 tool calls)*

## 06-regulatory-intake

**Prompt:** `requester=priya.natarajan@example-am.com. Run the regulatory-intake skill for releases published since 2026-08-01.`

All three drafts created successfully. Summary of the 3 releases since 2026-08-01:

1. SEC-2026-0812-MKTG (Marketing Rule FAQ, extracted performance) — draft D-20260917-eb4e5940. 2 obligations, 1 gap (POL-MK 'Pre-Approval' requires net returns always, stricter than the new SEC safe harbor), 1 covered (5-yr retention already in POL-MK 'Books and Records').

2. FINRA-RN-26-19 (Rule 3220 gift limit $100→$250, eff. 2027-01-01) — draft D-20260917-a6592588. 3 obligations, 2 gaps (POL-GE 'Gift Limits' still caps at $100; no policy-review cycle tied to the deadline), 1 flagged for review (record-keeping partly covered by 'Reporting' section, supervisory-procedure documentation unconfirmed).

3. FCA-PS26-9 (best execution reporting, RTS 28 removal, eff. 2026-12-01) — draft D-20260917-acbf37da. 2 obligations, 1 flagged for review (POL-BX 'Best Execution Reviews' covers monitoring/annual review but not explicit client-demonstration procedure), 1 not applicable (no RTS 28 publication language found in current policy to remove).

Pending review by an approver. Nothing has been changed.

*30 (1 user, 28 tool calls)*

## 07-evidence-pack

**Prompt:** `requester=priya.natarajan@example-am.com. Run the evidence-pack skill for CTL-GE-01 from 2026-01-01 to 2026-06-30.`

Draft D-20260917-cdd3c583 (evidence_pack_index) queued for human review — pending approval.

Contents for CTL-GE-01, 2026-01-01..2026-06-30:
- 2 policy versions listed: POL-GE v2.1 (effective 2025-01-15, in force throughout the period) and v2.0 (superseded before period start, listed for completeness). No version change occurred within the period.
- 6 tests, 5 pass / 1 fail
- 1 change ticket (CHG-2026-0412, closed)
- 1 gap

Gap in full: test T-2026-027 on 2026-03-31 result=fail — two register entries above USD 100 lacked escalation record. Remediated via CHG-2026-0412 (closed 2026-04-18, added mandatory escalation field to the register).

Manifest SHA-256 cc989831fbcd219aee36843cdc7599d3c40f3ab5811306241a0f0640fd755417 is cited in the draft. An approver must sign off before the pack is used; once approved, an operator runs compliance-review export to produce the zip.

*19 (1 user, 17 tool calls)*

## 08-attestations

**Prompt:** `requester=priya.natarajan@example-am.com. Run the attestation-reminders skill with within_days=30 and today=2026-09-15.`

Attestations due within 30 days of 2026-09-15 (per attestations_due, requester=priya.natarajan@example-am.com):

Owner: tom.reyes@example-am.com
- TRN-2026-AML-014 — annual-aml-training — due 2026-09-20 — 5 days remaining — open
- ATT-2026-Q3-001 — quarterly-code-of-ethics — due 2026-09-30 — 15 days remaining — open

Escalation (due ≤7 days or overdue), also flagged to manager marcus.oyelaran@example-am.com:
- TRN-2026-AML-014 (5 days remaining)

No items overdue by more than 14 days, so no attestation_escalation draft was created — that threshold isn't met here.

Note: this run was CLI-initiated, not the scheduled cron job, so I have not posted this to the compliance Teams channel. Let me know if you want me to do that, or if you'd like this delivered via a scheduled cron job instead.

*10 (1 user, 8 tool calls)*

## Human review

```
D-20260917-eb4e5940  policy_mapping         2026-09-17T18:59:22Z  by priya.natarajan@example-am.com SEC SEC-2026-0812-MKTG: Marketing Rule FAQ update on extracted performance
D-20260917-a6592588  policy_mapping         2026-09-17T18:59:22Z  by priya.natarajan@example-am.com FINRA-RN-26-19: Rule 3220 gift limit raised to $250
D-20260917-acbf37da  policy_mapping         2026-09-17T18:59:22Z  by priya.natarajan@example-am.com FCA PS26/9: Best execution reporting and removal of RTS 28
D-20260917-cdd3c583  evidence_pack_index    2026-09-17T19:00:40Z  by priya.natarajan@example-am.com Evidence index CTL-GE-01 2026-01-01..2026-06-30
refused: requester 'priya.natarajan@example-am.com' is not a member of 'compliance-approvers'
D-20260917-eb4e5940 approved by dana.whitfield@example-am.com
```

## Approved draft (excerpt)

`D-20260917-eb4e5940` approved by dana.whitfield@example-am.com at 2026-09-17T19:01:26Z.

# Regulatory mapping draft: SEC-2026-0812-MKTG

**Source:** SEC  **Published:** 2026-08-12  **URL:** https://www.sec.gov/investment/marketing-faq
**Title:** Staff FAQ update: net performance presentation for extracted performance under the Marketing Rule
**Prepared by:** compliance agent on behalf of priya.natarajan@example-am.com  **Status:** DRAFT, pending approval

## Obligations extracted

| # | Type | Quote (verbatim) | Applies to | Effective / compliance date |
|---|------|------------------|------------|-----------------------------|
| 1 | requirement | "Where an adviser presents extracted performance (performance of a subset of investments) in an advertisement, the staff will not object if gross extracted performance is shown without corresponding net extracted performance, provided that (1) the extracted performance is clearly identified as gross, (2) it is accompanied by the total portfolio's gross and net performance presented with at least equal prominence and calculated over the same period, and (3) the advertisement discloses how net performance of the total portfolio was calculated." | investment advisers presenting extracted performance in advertisements | not stated in release text |
| 2 | record-keeping | "Advisers must retain records supporting extracted performance for five years from last use." | investment advisers | not stated in release text |

## Mapping to policies and controls

| Obligation | Policy / section (version) | Control | Assessment | Evidence / quote |
|------------|----------------------------|---------|------------|------------------|
| 1 | POL-MK v1.4 'Pre-Approval' | CTL-MK-01 | gap | Policy: "Performance figures must show net returns alongside any gross returns over one, five, and ten year periods." This is stricter than and inconsistent with the new SEC staff position, which permits gross-only extracted performance under the three conditions quoted above. |
| 2 | POL-MK v1.4 'Books and Records' | CTL-MK-01 | covered | Policy: "A copy of every approved advertisement and its approval record is retained for at least five years from last use." Satisfies the five-year retention obligation. |

## Proposed next steps (for approver decision)
1. Decide whether to amend POL-MK 'Pre-Approval' to add a carve-out for extracted performance meeting the SEC's three conditions, or retain the current always-show-net standard. Owner: dana.whitfield@example-am.com.
2. No action needed on records retention; existing five-year retention already covers extracted performance records.

## Out of scope / not applicable
- None.

...

## Audit chain

```
OK 26 records across 1 file(s) verified, head cd24fb85467f
2026-09-17T18:34:25Z ok     tom.reyes@example-am.com     policy_lookup            5 section(s) for 'gift limit per recipient'
2026-09-17T18:34:55Z ok     tom.reyes@example-am.com     policy_lookup            5 section(s) for 'gifts and entertainment'
2026-09-17T18:34:59Z ok     tom.reyes@example-am.com     policy_get               POL-GE v2.0
2026-09-17T18:35:26Z ok     tom.reyes@example-am.com     policy_lookup            0 section(s) for 'cryptocurrency custody'
2026-09-17T18:35:30Z ok     tom.reyes@example-am.com     policy_list              3 current policies
2026-09-17T18:35:53Z denied tom.reyes@example-am.com     draft_create             requester 'tom.reyes@example-am.com' is not a member of 'compliance-analysts'
2026-09-17T18:57:43Z ok     priya.natarajan@example-am.com regulatory_releases      3 release(s) since 2026-08-01
2026-09-17T18:57:43Z ok     priya.natarajan@example-am.com policy_list              3 current policies
2026-09-17T18:57:47Z ok     priya.natarajan@example-am.com regulatory_release_get   release SEC-2026-0812-MKTG found
2026-09-17T18:57:47Z ok     priya.natarajan@example-am.com regulatory_release_get   release FINRA-RN-26-19 found
2026-09-17T18:57:47Z ok     priya.natarajan@example-am.com regulatory_release_get   release FCA-PS26-9 found
2026-09-17T18:58:04Z ok     priya.natarajan@example-am.com policy_lookup            4 section(s) for 'extracted performance net gross marketing advertisement record
2026-09-17T18:58:04Z ok     priya.natarajan@example-am.com policy_lookup            5 section(s) for 'gift limit annual gifts entertainment recordkeeping'
2026-09-17T18:58:04Z ok     priya.natarajan@example-am.com policy_lookup            5 section(s) for 'best execution RTS 28 monitoring execution quality reporting'
2026-09-17T18:58:54Z error  priya.natarajan@example-am.com draft_create             draft_rejected: policy_mapping draft has no obligations table with quoted text (
2026-09-17T18:58:54Z error  priya.natarajan@example-am.com draft_create             draft_rejected: policy_mapping draft has no obligations table with quoted text (
2026-09-17T18:58:54Z error  priya.natarajan@example-am.com draft_create             draft_rejected: policy_mapping draft has no obligations table with quoted text (
2026-09-17T18:59:22Z ok     priya.natarajan@example-am.com draft_create             draft D-20260917-eb4e5940 (policy_mapping) queued for human review
2026-09-17T18:59:22Z ok     priya.natarajan@example-am.com draft_create             draft D-20260917-a6592588 (policy_mapping) queued for human review
2026-09-17T18:59:22Z ok     priya.natarajan@example-am.com draft_create             draft D-20260917-acbf37da (policy_mapping) queued for human review
2026-09-17T18:59:58Z ok     priya.natarajan@example-am.com evidence_bundle          evidence for CTL-GE-01 2026-01-01..2026-06-30: 2 policy versions, 6 tests, 1 tic
2026-09-17T19:00:06Z ok     priya.natarajan@example-am.com policy_get               POL-GE v2.1
2026-09-17T19:00:40Z ok     priya.natarajan@example-am.com draft_create             draft D-20260917-cdd3c583 (evidence_pack_index) queued for human review
2026-09-17T19:01:13Z ok     priya.natarajan@example-am.com attestations_due         2 attestation(s) due within 30 days of 2026-09-15
2026-09-17T19:01:26Z denied priya.natarajan@example-am.com draft_approved           requester 'priya.natarajan@example-am.com' is not a member of 'compliance-approv
2026-09-17T19:01:26Z ok     dana.whitfield@example-am.com draft_approved           D-20260917-eb4e5940 approved
```
