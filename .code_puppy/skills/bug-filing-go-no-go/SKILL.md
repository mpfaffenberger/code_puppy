---
name: bug-filing-go-no-go
description: Review a proposed bug report and issue a traceable GO, NO-GO, or NEEDS-INFO filing decision based on configured P1-goal alignment and flow admissibility. Use for bug-intake and filing-gate reviews; do not use for severity triage, root-cause analysis, or issue filing itself.
---

# Bug Filing Go/No-Go

Decide whether a proposed bug may be filed. Base the decision only on P1-goal
alignment and flow admissibility as defined by the applicable policy.

Before reviewing a bug, read [the decision policy](references/decision-policy.md).
Treat policy supplied by the user in the current conversation as newer than the
local reference for that review. Do not permanently change the reference unless
the user asks to update the skill.

## Review workflow

1. Extract the reported behavior, expected behavior, affected user or system,
   reproduction flow, and supporting evidence. Mark missing facts as unknown;
   never invent them.
2. Evaluate P1 alignment against a named goal or criterion in the applicable
   policy. Record the criterion and the bug evidence that supports the result.
3. Evaluate flow admissibility against a named rule in the applicable policy.
   Identify the relevant entry point and flow step when the description provides
   them.
4. Assign each gate `PASS`, `FAIL`, or `UNKNOWN`.
5. Apply the decision table and return the required output. Ask only for facts
   that could change the decision.

| P1 alignment | Flow admissibility | Decision |
|---|---|---|
| PASS | PASS | GO |
| FAIL | Any result | NO-GO |
| Any result | FAIL | NO-GO |
| UNKNOWN | No FAIL | NEEDS-INFO |
| No FAIL | UNKNOWN | NEEDS-INFO |

`GO` means the bug passes this filing gate. It does not assign severity,
priority, ownership, or a root cause. `NO-GO` requires a specific failed policy
criterion. `NEEDS-INFO` means the bug description or governing policy lacks the
information needed for a defensible decision.

## Required output

Use this exact structure:

```text
Decision: GO | NO-GO | NEEDS-INFO
Reason: <one-sentence explanation of the controlling result>

P1 alignment: PASS | FAIL | UNKNOWN
Criterion: <policy goal or criterion, or "Not configured">
Evidence: <facts from the bug description>

Flow admissibility: PASS | FAIL | UNKNOWN
Rule: <policy rule, or "Not configured">
Evidence: <facts from the reported flow>

Missing information: <minimum information needed, or "None">
Next action: <file the bug, do not file it, or provide the listed information>
```

Keep the reason short and make the two gate assessments independently
auditable. When the policy is missing, state which policy section is needed.
When the report is missing facts, request concrete evidence such as the entry
point, actor, ordered steps, observed result, or expected result.

## Guardrails

- Do not treat severity, customer impact, urgency, or reproducibility as proof
  of P1 alignment unless the policy explicitly says to do so.
- Do not infer that a flow is admissible merely because a user can perform it.
- Do not invent P1 goals, admissible flows, exceptions, or policy precedence.
- Do not reinterpret a feature request as a bug unless the policy defines that
  distinction and the evidence satisfies it.
- Do not file, edit, close, or comment on an issue. Perform those actions only
  when the user separately requests them.

