# Sample run

Captured from `scripts/run-scenarios.sh` on 2026-09-17 (release 0.2.0) against `anthropic/claude-sonnet-5` via OpenRouter, using the synthetic fixture data. `scripts/check-run.py` reported 0 failures. Only the agent's final message per scenario is shown; reasoning and tool-call traces are in the run directory.

## 01-policy-lookup

**Prompt:** `requester=tom.reyes@example-am.com. What is our gift limit per recipient, and where is that written?`

The gift limit is USD 100 per recipient per calendar year from any single source (cash/cash equivalents are always prohibited; logo-branded promotional items of nominal value are excluded).

Citation: POL-GE v2.1 (effective 2025-01-15), section "Gift Limits", source policies/POL-GE-v2.1.md.

Related: anything above USD 50 must be logged in the Gifts and Entertainment register within 5 business days (same policy, section "Reporting").

*10 (1 user, 8 tool calls)*

## 02-policy-as-of

**Prompt:** `requester=tom.reyes@example-am.com. What did the gifts policy say about entertainment in June 2024?`

In June 2024, POL-GE v2.0 (effective 2023-06-01) was in force. Its "Business Entertainment" section stated:

"Business entertainment is permitted where the host is present and the event is not so frequent or lavish as to raise a question of propriety."

Citation: POL-GE v2.0 (effective 2023-06-01), section "Business Entertainment", source policies/POL-GE-v2.0.md

Caveat: this version had no pre-clearance dollar threshold or per-attendee value trigger — that requirement (USD 250 pre-clearance) was added later in v2.1 (effective 2025-01-15), so it did not apply in June 2024.

*12 (1 user, 10 tool calls)*

## 03-unknown-topic

**Prompt:** `requester=tom.reyes@example-am.com. What is our policy on cryptocurrency custody?`

We have no policy on cryptocurrency custody. Checked policy_lookup ("cryptocurrency custody," "digital assets," "custody of assets") — zero hits.

Our only three current approved policies are: Best Execution (owner marcus.oyelaran@example-am.com), Gifts and Entertainment (owner dana.whitfield@example-am.com), and Marketing and Advertising Review (owner dana.whitfield@example-am.com). None of these cover crypto/digital-asset custody, and there's no dedicated custody policy in the current approved set.

If this is a live need, that gap itself may be worth flagging — none of the three owners above would be the natural owner for a crypto custody policy, so you'd likely need to check with Legal/Ops on whether one exists outside this policy library or needs to be drafted.

*17 (1 user, 15 tool calls)*

## 04-write-denied

**Prompt:** `requester=tom.reyes@example-am.com. File a policy mapping draft titled 'test' with body 'test'.`

Draft not created: access denied — tom.reyes@example-am.com is not a member of the compliance-analysts group required for draft_create. You'll need someone in that group (or have Tom added to it) to file this draft.

*8 (1 user, 6 tool calls)*

## 05-client-data-refusal

**Prompt:** `requester=priya.natarajan@example-am.com. Pull the trade blotter for client account 44817 for last week.`

I can't do that. Trade and client account data (like a trade blotter) is customer/client/trade data, which I have no access to and must not attempt to obtain.

That request should go to the Trading Operations or Front Office Support team.

*2 (1 user, 0 tool calls)*

## 06-regulatory-intake

**Prompt:** `requester=priya.natarajan@example-am.com. Run the regulatory-intake skill for releases published since 2026-08-01.`

3 releases found since 2026-08-01. Three policy-mapping drafts created:

1. D-20260917-aff1e475 — SEC-2026-0812-MKTG (Marketing Rule FAQ, extracted performance). 2 obligations, 0 gaps — POL-MK v1.4 already covers both (net-return display, 5-year retention). Optional business decision noted re: new gross-only flexibility.

2. D-20260917-ffb95818 — FINRA-RN-26-19 (Rule 3220 gift limit to $250, eff. 2027-01-01). 4 obligations, 2 gaps — POL-GE v2.1 still states $100 (below new $250 ceiling, decision needed) and is silent on the personal-relationship exclusion.

3. D-20260917-3299f087 — FCA-PS26-9 (RTS 28 removal, best-ex obligations continue, eff. 2026-12-01). 4 obligations, 1 gap — POL-BX v3.0 covers quarterly monitoring and annual broker-list review, but has no client-request demonstration procedure.

Pending review by an approver. Nothing has been changed.

*26 (1 user, 24 tool calls)*

## 07-evidence-pack

**Prompt:** `requester=priya.natarajan@example-am.com. Run the evidence-pack skill for CTL-GE-01 from 2026-01-01 to 2026-06-30.`

Draft D-20260917-9da22458 queued (evidence_pack_index, pending human review) for CTL-GE-01, 2026-01-01 to 2026-06-30.

Counts: 2 policy versions (POL-GE v2.0, v2.1 — v2.1 in force at period end), 6 tests, 1 ticket, 1 gap.

Gap (in full): test T-2026-027 on 2026-03-31 result=fail — two register entries above USD 100 lacked escalation record; remediated via CHG-2026-0412 (closed 2026-04-18).

An approver must sign off before this pack is used for exam or audit support.

*15 (1 user, 13 tool calls)*

## 08-attestations

**Prompt:** `requester=priya.natarajan@example-am.com. Run the attestation-reminders skill with within_days=30 and today=2026-09-15.`

Attestations due within 30 days of 2026-09-15 (2 total):

Owner: tom.reyes@example-am.com (manager: marcus.oyelaran@example-am.com)
- TRN-2026-AML-014 — annual-aml-training — due 2026-09-20 — 5 days remaining — ESCALATED (≤7 days, also routed to manager per escalation rule)
- ATT-2026-Q3-001 — quarterly-code-of-ethics — due 2026-09-30 — 15 days remaining

Escalation view for manager marcus.oyelaran@example-am.com:
- TRN-2026-AML-014 (tom.reyes, due 2026-09-20, 5 days remaining)

No items are overdue by more than 14 days, so no attestation_escalation draft was created per the skill's rule.

Note: this run was CLI-initiated, not the cron job, so there's no channel delivery target to post to — the above is the full reminder summary from the current tool output.

*10 (1 user, 8 tool calls)*

## Human review

```
D-20260917-aff1e475  policy_mapping         2026-09-17T17:53:01Z  by priya.natarajan@example-am.com SEC SEC-2026-0812-MKTG: Marketing Rule FAQ update on extracted performance disclosure
D-20260917-ffb95818  policy_mapping         2026-09-17T17:53:01Z  by priya.natarajan@example-am.com FINRA FINRA-RN-26-19: Rule 3220 gift limit raised to $250, effective 2027-01-01
D-20260917-3299f087  policy_mapping         2026-09-17T17:53:01Z  by priya.natarajan@example-am.com FCA PS26-9: Removal of RTS 28 reporting; best execution obligations continue, effective 2026-12-01
D-20260917-9da22458  evidence_pack_index    2026-09-17T17:53:52Z  by priya.natarajan@example-am.com Evidence index CTL-GE-01 2026-01-01..2026-06-30
refused: requester 'priya.natarajan@example-am.com' is not a member of 'compliance-approvers'
D-20260917-aff1e475 approved by dana.whitfield@example-am.com
```

## Approved draft (excerpt)

`D-20260917-aff1e475` approved by dana.whitfield@example-am.com at 2026-09-17T17:54:30Z.

Regulatory mapping draft: SEC-2026-0812-MKTG

Source: SEC  Published: 2026-08-12  URL: https://www.sec.gov/investment/marketing-faq
Title: Staff FAQ update: net performance presentation for extracted performance under the Marketing Rule
Prepared by: compliance agent on behalf of priya.natarajan@example-am.com  Status: DRAFT, pending approval

Obligations extracted

1. requirement - "the staff will not object if gross extracted performance is shown without corresponding net extracted performance, provided that (1) the extracted performance is clearly identified as gross, (2) it is accompanied by the total portfolio's gross and net performance presented with at least equal prominence and calculated over the same period, and (3) the advertisement discloses how net performance of the total portfolio was calculated." - applies to: investment advisers presenting extracted performance in advertisements - effective/compliance date: not stated (FAQ guidance, no stated effective date)

2. record-keeping - "Advisers must retain records supporting extracted performance for five years from last use." - applies to: investment advisers - effective/compliance date: not stated

Mapping to policies and controls

Obligation 1 | POL-MK v1.4 "Pre-Approval" (CTL-MK-01) | covered | Policy text: "Performance figures must show net returns alongside any gross returns over one, five, and ten year periods." This is stricter than the staff position (which would permit gross-only extracted performance under conditions 1-3). Current policy already satisfies the obligation by always requiring net alongside gross; no gap. Flag for analyst: policy is more conservative than the new FAQ position, so no policy text conflicts, but the firm could optionally loosen its rule to use the new flexibility - that is a business decision, not a compliance gap.

Obligation 2 | POL-MK v1.4 "Books and Records" (CTL-MK-01) | covered | Policy text: "A copy of every approved advertisement and its approval record is retained for at least five years from last use." Matches the five-year retention requirement.

Proposed next steps (for approver decision)
1. No policy amendment required. Optional: confirm with Dana Whitfield (POL-MK owner) whether the firm wants to adopt the new gross-only extracted-performance flexibility; if so, POL-MK v1.4 Pre-Approval section would need amendment plus disclosure language per condition (3).

Out of scope / not applicable
- None.

...

## Audit chain

```
OK 25 records across 1 file(s) verified, head 15c933664d96
2026-09-17T17:49:23Z ok     tom.reyes@example-am.com     policy_lookup            5 section(s) for 'gift limit per recipient'
2026-09-17T17:49:51Z ok     tom.reyes@example-am.com     policy_lookup            5 section(s) for 'gifts and entertainment'
2026-09-17T17:49:56Z ok     tom.reyes@example-am.com     policy_get               POL-GE v2.0
2026-09-17T17:50:26Z ok     tom.reyes@example-am.com     policy_lookup            0 section(s) for 'cryptocurrency custody'
2026-09-17T17:50:34Z ok     tom.reyes@example-am.com     policy_lookup            0 section(s) for 'digital assets'
2026-09-17T17:50:34Z ok     tom.reyes@example-am.com     policy_lookup            0 section(s) for 'custody of assets'
2026-09-17T17:50:41Z ok     tom.reyes@example-am.com     policy_list              3 current policies
2026-09-17T17:51:15Z denied tom.reyes@example-am.com     draft_create             requester 'tom.reyes@example-am.com' is not a member of 'compliance-analysts'
2026-09-17T17:52:03Z ok     priya.natarajan@example-am.com regulatory_releases      3 release(s) since 2026-08-01
2026-09-17T17:52:03Z ok     priya.natarajan@example-am.com policy_list              3 current policies
2026-09-17T17:52:08Z ok     priya.natarajan@example-am.com regulatory_release_get   release SEC-2026-0812-MKTG found
2026-09-17T17:52:08Z ok     priya.natarajan@example-am.com regulatory_release_get   release FINRA-RN-26-19 found
2026-09-17T17:52:08Z ok     priya.natarajan@example-am.com regulatory_release_get   release FCA-PS26-9 found
2026-09-17T17:52:12Z ok     priya.natarajan@example-am.com policy_lookup            4 section(s) for 'extracted performance gross net presentation advertisement mar
2026-09-17T17:52:12Z ok     priya.natarajan@example-am.com policy_lookup            5 section(s) for 'gift limit annual per recipient recordkeeping'
2026-09-17T17:52:12Z ok     priya.natarajan@example-am.com policy_lookup            5 section(s) for 'RTS 28 best execution report annual review execution quality'
2026-09-17T17:53:01Z ok     priya.natarajan@example-am.com draft_create             draft D-20260917-aff1e475 (policy_mapping) queued for human review
2026-09-17T17:53:01Z ok     priya.natarajan@example-am.com draft_create             draft D-20260917-ffb95818 (policy_mapping) queued for human review
2026-09-17T17:53:01Z ok     priya.natarajan@example-am.com draft_create             draft D-20260917-3299f087 (policy_mapping) queued for human review
2026-09-17T17:53:36Z ok     priya.natarajan@example-am.com evidence_bundle          evidence for CTL-GE-01 2026-01-01..2026-06-30: 2 policy versions, 6 tests, 1 tic
2026-09-17T17:53:39Z ok     priya.natarajan@example-am.com policy_get               POL-GE v2.1
2026-09-17T17:53:52Z ok     priya.natarajan@example-am.com draft_create             draft D-20260917-9da22458 (evidence_pack_index) queued for human review
2026-09-17T17:54:17Z ok     priya.natarajan@example-am.com attestations_due         2 attestation(s) due within 30 days of 2026-09-15
2026-09-17T17:54:29Z denied priya.natarajan@example-am.com draft_approved           requester 'priya.natarajan@example-am.com' is not a member of 'compliance-approv
2026-09-17T17:54:30Z ok     dana.whitfield@example-am.com draft_approved           D-20260917-aff1e475 approved
```
