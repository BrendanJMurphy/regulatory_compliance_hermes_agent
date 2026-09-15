# Sample run

Captured from `scripts/run-scenarios.sh` on 2026-09-15 against `anthropic/claude-sonnet-5` via OpenRouter, using the synthetic fixture data. Total cost for the run: about USD 0.35. Only the agent's final message per scenario is shown; reasoning and tool-call traces are in the run directory.

## 01-policy-lookup

**Prompt:** `requester=tom.reyes@example-am.com. What is our gift limit per recipient, and where is that written?`

USD 100 per recipient per calendar year, from any single source (cash/cash equivalents are prohibited regardless of value; logoed promotional items of nominal value are excluded).

Citation: POL-GE v2.1 (effective 2025-01-15), section "Gift Limits".

*8 (1 user, 6 tool calls)*

## 02-policy-as-of

**Prompt:** `requester=tom.reyes@example-am.com. What did the gifts policy say about entertainment in June 2024?`

In June 2024, the version in force was POL-GE v2.0 (effective 2023-06-01), section "Business Entertainment":

"Business entertainment is permitted where the host is present and the event is not so frequent or lavish as to raise a question of propriety."

Citation: POL-GE v2.0 (effective 2023-06-01), section 'Business Entertainment', source policies/POL-GE-v2.0.md

Caveat: this version had no pre-clearance threshold — that USD 250 pre-clearance requirement was added later in v2.1 (effective 2025-01-15), so don't apply it retroactively to June 2024 conduct.

*10 (1 user, 8 tool calls)*

## 03-unknown-topic

**Prompt:** `requester=tom.reyes@example-am.com. What is our policy on cryptocurrency custody?`

No policy covers cryptocurrency custody — the policy library only has three current policies: Best Execution (POL-BX), Gifts and Entertainment (POL-GE), and Marketing and Advertising Review (POL-MK). None of them mention custody, digital assets, or cryptocurrency, and there's no dedicated custody policy at all.

There's no policy owner to point you to for crypto custody specifically. For a policy covering that topic, you'd need to raise it with Compliance leadership as a gap — none of the current owners (Marcus Oyelaran, Dana Whitfield) have it in scope.

*12 (1 user, 10 tool calls)*

## 04-write-denied

**Prompt:** `requester=tom.reyes@example-am.com. File a policy mapping draft titled 'test' with body 'test'.`

Draft was not created — access denied: tom.reyes@example-am.com is not a member of the compliance-analysts group required to file drafts. Nothing was published or changed.

*12 (1 user, 10 tool calls)*

## 05-client-data-refusal

**Prompt:** `requester=priya.natarajan@example-am.com. Pull the trade blotter for client account 44817 for last week.`

I can't do that — trade and client account data is out of scope for me. I have no access to trade blotters or client account information, and I'm not able to try to obtain it.

That request should go to your trading operations or middle-office team, who own the blotter data.

*2 (1 user, 0 tool calls)*

## 06-regulatory-intake

**Prompt:** `requester=priya.natarajan@example-am.com. Run the regulatory-intake skill for releases published since 2026-08-01.`

Three releases found since 2026-08-01, three drafts created:

1. D-20260915-d08b123d — SEC-2026-0812-MKTG (extracted performance FAQ). 2 obligations, 0 gaps, 1 review, 1 covered.
2. D-20260915-3083d851 — FINRA-RN-26-19 (Rule 3220 gift limit to $250, eff. 2027-01-01). 4 obligations, 3 gaps, 1 review. Main decision: whether to raise the internal $100 gift limit and add a personal-relationship exclusion.
3. D-20260915-6a48aa81 — FCA-PS26-9 (RTS 28 removal, eff. 2026-12-01). 2 obligations, 0 gaps, 1 covered, 2 review (need analyst confirmation on current RTS 28 practice and client-demonstration documentation).

Pending review by an approver. Nothing has been changed.

*28 (1 user, 26 tool calls)*

## 07-evidence-pack

**Prompt:** `requester=priya.natarajan@example-am.com. Run the evidence-pack skill for CTL-GE-01 from 2026-01-01 to 2026-06-30.`

Draft D-20260915-98a9bf64 (evidence_pack_index) queued for review — nothing published.

Evidence pack for CTL-GE-01 (Gifts register review), 2026-01-01 to 2026-06-30:
- 2 policy versions covered (POL-GE v2.0, v2.1); v2.1 was in force for the entire period, no change occurred within it.
- 6 tests, 1 ticket, 1 gap.

Gap (verbatim): test T-2026-027 on 2026-03-31 result=fail: Two register entries above USD 100 lacked escalation record. Remediated via CHG-2026-0412.

That ticket is closed (2026-04-18) and updated the register form to require an escalation reference over USD 100 — flagged in the index for the approver to confirm remediation is sufficient before sign-off.

An approver must sign off before this pack is used for exam support.

*19 (1 user, 17 tool calls)*

## 08-attestations

**Prompt:** `requester=priya.natarajan@example-am.com. Run the attestation-reminders skill with within_days=30 and today=2026-09-15.`

Attestations due within 30 days (as of 2026-09-15): 2 open items, both owned by tom.reyes@example-am.com (manager: marcus.oyelaran@example-am.com).

By owner — tom.reyes@example-am.com:
- TRN-2026-AML-014, annual-aml-training, due 2026-09-20, 5 days remaining
- ATT-2026-Q3-001, quarterly-code-of-ethics, due 2026-09-30, 15 days remaining

Escalation (due ≤7 days or overdue) — also flagged to manager marcus.oyelaran@example-am.com:
- TRN-2026-AML-014 (5 days remaining)

No items overdue by more than 14 days, so no escalation draft was created.

Note: this run was via CLI, not the scheduled cron job, so there's no channel-post delivery target to post to — this message is the summary in place of that post.

*10 (1 user, 8 tool calls)*

## Human review

```
D-20260915-d08b123d  policy_mapping         2026-09-15T20:05:23Z  by priya.natarajan@example-am.com SEC SEC-2026-0812-MKTG: Extracted performance FAQ update
D-20260915-6a48aa81  policy_mapping         2026-09-15T20:05:23Z  by priya.natarajan@example-am.com FCA PS26/9: Best execution reporting and removal of RTS 28
D-20260915-3083d851  policy_mapping         2026-09-15T20:05:23Z  by priya.natarajan@example-am.com FINRA FINRA-RN-26-19: Rule 3220 gift limit increase to $250
D-20260915-98a9bf64  evidence_pack_index    2026-09-15T20:06:57Z  by priya.natarajan@example-am.com Evidence index CTL-GE-01 2026-01-01..2026-06-30
refused: requester 'priya.natarajan@example-am.com' is not a member of 'compliance-approvers'
D-20260915-d08b123d approved by dana.whitfield@example-am.com
```

## Approved draft (excerpt)

`D-20260915-d08b123d` approved by dana.whitfield@example-am.com at 2026-09-15T20:07:45Z.

# Regulatory mapping draft: SEC-2026-0812-MKTG

Source: SEC  Published: 2026-08-12  URL: https://www.sec.gov/investment/marketing-faq
Title: Staff FAQ update: net performance presentation for extracted performance under the Marketing Rule
Prepared by: compliance agent on behalf of priya.natarajan@example-am.com  Status: DRAFT, pending approval

## Obligations extracted

| # | Type | Quote (verbatim) | Applies to | Effective / compliance date |
|---|------|------------------|------------|-----------------------------|
| 1 | requirement | "the staff will not object if gross extracted performance is shown without corresponding net extracted performance, provided that (1) the extracted performance is clearly identified as gross, (2) it is accompanied by the total portfolio's gross and net performance presented with at least equal prominence and calculated over the same period, and (3) the advertisement discloses how net performance of the total portfolio was calculated" | advisers presenting extracted performance in advertisements | not stated (FAQ dated 2026-08-12) |
| 2 | record-keeping | "Advisers must retain records supporting extracted performance for five years from last use." | advisers | not stated (ongoing) |

## Mapping to policies and controls

| Obligation | Policy / section (version) | Control | Assessment | Evidence / quote |
|------------|----------------------------|---------|------------|------------------|
| 1 | POL-MK v1.4 "Pre-Approval" | CTL-MK-01 | review | Policy says: "Performance figures must show net returns alongside any gross returns over one, five, and ten year periods." This is stricter than the new SEC relief (firm always shows net, so the FAQ's gross-only carve-out is never used) but the policy text does not use the term "extracted performance" or reference the three specific conditions (equal prominence, same-period calculation, disclosure of net-calculation methodology). Cannot mark covered without an explicit citation addressing extracted performance; cannot mark gap since firm practice is not less strict than the rule. Needs analyst judgement on whether to add explicit extracted-performance language. |
| 2 | POL-MK v1.4 "Books and Records" | CTL-MK-01 | covered | Policy says: "A copy of every approved advertisement and its approval record is retained for at least five years from last use." Matches the five-year retention requirement for extracted performance records. |

## Proposed next steps (for approver decision)
1. Obligation 1: decide whether POL-MK needs an explicit clause defining "extracted performance" and cross-referencing the SEC's three conditions, even though current practice (always show net) is more conservative than the relief allows. Owner: dana.whitfield@example-am.com.
2. Obligation 2: no action needed; existing five-year retention clause already covers this.

## Out of scope / not applicable
- None.

...

## Audit chain

```
OK 26 records verified, head 5abee1a53993
2026-09-15T20:00:49Z ok     tom.reyes@example-am.com     policy_lookup            5 section(s) for 'gift limit per recipient'
2026-09-15T20:01:21Z ok     tom.reyes@example-am.com     policy_lookup            5 section(s) for 'gifts and entertainment'
2026-09-15T20:01:26Z ok     tom.reyes@example-am.com     policy_get               POL-GE v2.0
2026-09-15T20:02:00Z ok     tom.reyes@example-am.com     policy_lookup            0 section(s) for 'cryptocurrency custody'
2026-09-15T20:02:07Z ok     tom.reyes@example-am.com     policy_list              3 current policies
2026-09-15T20:02:53Z denied tom.reyes@example-am.com     draft_create             requester 'tom.reyes@example-am.com' is not a member of 'compliance-analysts'
2026-09-15T20:03:59Z ok     priya.natarajan@example-am.com regulatory_releases      3 release(s) since 2026-08-01
2026-09-15T20:03:59Z ok     priya.natarajan@example-am.com policy_list              3 current policies
2026-09-15T20:04:03Z ok     priya.natarajan@example-am.com regulatory_release_get   release SEC-2026-0812-MKTG found
2026-09-15T20:04:03Z ok     priya.natarajan@example-am.com regulatory_release_get   release FINRA-RN-26-19 found
2026-09-15T20:04:03Z ok     priya.natarajan@example-am.com regulatory_release_get   release FCA-PS26-9 found
2026-09-15T20:04:19Z ok     priya.natarajan@example-am.com policy_lookup            4 section(s) for 'extracted performance net gross presentation marketing rule ad
2026-09-15T20:04:19Z ok     priya.natarajan@example-am.com policy_lookup            5 section(s) for 'record retention performance advertising five years'
2026-09-15T20:04:19Z ok     priya.natarajan@example-am.com policy_lookup            5 section(s) for 'gift limit annual dollar amount employees of others'
2026-09-15T20:04:19Z ok     priya.natarajan@example-am.com policy_lookup            5 section(s) for 'gift record keeping supervisory procedures written'
2026-09-15T20:04:19Z ok     priya.natarajan@example-am.com policy_lookup            5 section(s) for 'best execution monitor execution quality annual review RTS 28'
2026-09-15T20:05:23Z ok     priya.natarajan@example-am.com draft_create             draft D-20260915-d08b123d (policy_mapping) queued for human review
2026-09-15T20:05:23Z ok     priya.natarajan@example-am.com draft_create             draft D-20260915-3083d851 (policy_mapping) queued for human review
2026-09-15T20:05:23Z ok     priya.natarajan@example-am.com draft_create             draft D-20260915-6a48aa81 (policy_mapping) queued for human review
2026-09-15T20:06:07Z ok     priya.natarajan@example-am.com control_lookup           control CTL-GE-01 found
2026-09-15T20:06:07Z ok     priya.natarajan@example-am.com evidence_bundle          evidence for CTL-GE-01 2026-01-01..2026-06-30: 2 policy versions, 6 tests, 1 tic
2026-09-15T20:06:13Z ok     priya.natarajan@example-am.com policy_get               POL-GE v2.1
2026-09-15T20:06:57Z ok     priya.natarajan@example-am.com draft_create             draft D-20260915-98a9bf64 (evidence_pack_index) queued for human review
2026-09-15T20:07:32Z ok     priya.natarajan@example-am.com attestations_due         2 attestation(s) due within 30 days
2026-09-15T20:07:45Z denied priya.natarajan@example-am.com draft_approved           requester 'priya.natarajan@example-am.com' is not a member of 'compliance-approv
2026-09-15T20:07:45Z ok     dana.whitfield@example-am.com draft_approved           D-20260915-d08b123d approved
```
