# Rollout plan

## Phase 0: platform (weeks 1 to 2)
- Provision the model endpoint inside the VPC with a no-training, no-retention agreement. Record it in the model inventory.
- Azure Bot registration in the firm tenant; `TEAMS_ALLOWED_USERS` limited to the compliance team.
- Deploy `docker-compose.yml` on a hardened host. Egress allowlist: model endpoint, Azure Bot Service, regulator feed hosts (for the feed fetcher, not the agent).
- Wire `COMPLIANCE_AUDIT_FORWARD_URL` to the SIEM. Confirm records arrive and `compliance-audit verify` passes.
- Replace fixture adapters in `store.py` with read-only clients for the policy repository, GRC platform, and ticketing.

## Phase 1: lookup and reminders (weeks 3 to 6)
- Enable `policy-lookup` and `attestation-reminders` only. Remove `regulatory-intake` and `evidence-pack` from the skills directory for this phase.
- Weekly sampling: an analyst reviews 20 answers for citation accuracy. Target: zero uncited factual claims.
- Exit criteria: four clean weekly samples, audit chain verified daily, no denied-write events from unexpected users.

## Phase 2: regulatory intake (weeks 7 to 12)
- Run `eval/validate_extraction.py` against the production model. Attach the result to the model inventory. Do not proceed below threshold.
- Enable `regulatory-intake` and the daily cron. Approvers review every draft.
- Exit criteria: analyst-rated draft usefulness, and no draft approved without edits being wrong on a material point.

## Phase 3: evidence packs (weeks 13+)
- Enable `evidence-pack`. First use on an internal audit, not a regulator exam.
- Exit criteria: internal audit confirms the index matched the pack they assembled by hand.

## Ongoing
- Re-run validation on any model, prompt, or skill change. Skills are change-controlled through pull requests with security review.
- Quarterly access review of `users.json` against the directory groups.
- Annual review of this document and the controls matrix.
