---
name: policy-lookup
description: Answer "what does our policy say" questions with citations.
version: 1.0.0
metadata:
  hermes:
    tags: [compliance, policy]
    category: compliance
---
# Policy Lookup

## When to use
Someone asks what the firm's policy, threshold, procedure, or control is on a topic
(e.g. "what is our gift limit", "which control covers best execution reviews",
"who owns the marketing policy").

## Procedure
1. Call `policy_lookup(requester, query)` with the question's key terms. Use `limit` 5.
2. If the question is about a control rather than a policy, also call `control_lookup(requester, query=...)`.
3. If the question is "what was the policy on <date>", call `policy_get(requester, policy_id, as_of=<date>)`
   and say explicitly which version was in force.
4. Answer using only the returned section text. End with the `citation` string for each section used.
5. If nothing relevant came back, say "No approved policy section addresses this" and give the
   owner of the closest policy from `policy_list`.

## Pitfalls
- Do not combine sections from different policies into one rule without saying which is which.
- Do not fill gaps from general knowledge of regulation. The firm's policy may be stricter.
- Thresholds and dates must match the tool output character for character.

## Verification
Each factual sentence in your answer maps to a returned section, and the citation is present.
