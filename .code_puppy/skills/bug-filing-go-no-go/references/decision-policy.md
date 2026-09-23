# Bug filing decision policy

## Policy status

Organization-specific P1 goals and flow-admissibility rules have not been
configured yet. Until they are configured, do not infer them from general
engineering practice, severity labels, or the wording of a bug report.

If the current user message supplies enough policy to evaluate a bug, apply
that policy for the current review and identify it as `session-provided` in the
criterion or rule field. Otherwise, return `NEEDS-INFO` and name the missing
policy information.

## P1-goal policy

The policy owner should define each P1 goal with:

- a stable goal name or identifier;
- the outcome and time horizon covered by the goal;
- concrete in-scope signals;
- concrete exclusions or non-goals;
- any required evidence; and
- the source, owner, or version used to resolve conflicts.

A P1-alignment `PASS` requires evidence connecting the reported behavior to at
least one configured goal. A `FAIL` requires evidence that a configured
criterion excludes the bug. If neither can be established, assign `UNKNOWN`.

## Flow-admissibility policy

The policy owner should define each reviewed flow with:

- a stable flow name or identifier;
- valid actors, entry points, and preconditions;
- the supported sequence or relevant boundary;
- prohibited, unsupported, or out-of-scope variants;
- exception rules; and
- the evidence needed to prove that the reported flow occurred.

An admissibility `PASS` requires the described flow to satisfy a configured
rule. A `FAIL` requires a specific conflict with a configured rule. If the
report or policy cannot establish either result, assign `UNKNOWN`.

## Policy precedence

For a single review, use policy in this order:

1. explicit instructions from the user in the current conversation;
2. the configured rules in this reference; and
3. no assumption or customary practice.

If two applicable rules conflict and the precedence cannot be resolved, return
`NEEDS-INFO` and cite both rules.
