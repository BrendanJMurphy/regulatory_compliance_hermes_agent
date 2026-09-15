---
name: attestation-reminders
description: Chase open attestations and training on the compliance manual's schedule.
version: 1.0.0
metadata:
  hermes:
    tags: [compliance, attestations]
    category: compliance
---
# Attestation Reminders

## When to use
The scheduled weekly run, or when an analyst asks what attestations or training are outstanding.

## Procedure
1. `attestations_due(requester, within_days=14)`.
2. Group by owner. For each owner list item id, type, due date, and days remaining.
3. Escalation rule (from the compliance manual): items due in 7 days or fewer, or overdue,
   are also listed under the owner's manager.
4. Post the summary to the compliance channel (the cron job's delivery target). Address people
   by UPN, not by inferred first name.
5. If any item is overdue by more than 14 days, `draft_create(requester, kind="attestation_escalation",
   title="Overdue attestations <date>", body=<list>, related_ids=[item ids])` so an approver can
   decide on formal escalation. Do not contact anyone directly; the channel post is the reminder.

## Pitfalls
- Do not mark anything complete. Only the attestation system does that.
- Do not send private messages to individuals; only the channel post is permitted.

## Verification
Every item in the message came from the tool output for this run.
