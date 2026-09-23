# Bug Filing Go/No-Go Skill

This Code Puppy skill reviews a proposed bug and decides whether it passes the
filing gate. It evaluates two independent requirements:

1. The bug aligns with a configured P1 goal.
2. The reported user flow is admissible under the configured policy.

The skill reviews the filing decision only. It does not assign severity,
investigate root cause, or create an issue in a tracker.

## Enable the skill

From Code Puppy, refresh skill discovery and enable the skill:

```text
/skills refresh
/skills enable bug-filing-go-no-go
```

Use `/skills list` to confirm that it is enabled.

## Configure the decision policy

Add your organization-specific P1 goals and flow rules to
[`references/decision-policy.md`](references/decision-policy.md). Define:

- the names, scope, exclusions, and evidence requirements for each P1 goal;
- valid actors, entry points, preconditions, and steps for admissible flows;
- unsupported flows and exceptions; and
- the source or version that resolves conflicts between policies.

Until those rules are configured, the skill returns `NEEDS-INFO` instead of
inventing criteria. You can also provide temporary policy directly in a prompt;
the skill applies it to that review without changing the policy file.

## Review a bug

Ask Code Puppy to review a bug description using this skill. Include the
observed behavior, expected behavior, affected user or system, reproduction
steps, and any supporting evidence.

Example:

```text
Use the bug-filing-go-no-go skill to review this proposed bug.

Observed behavior: A signed-in account owner receives an error after selecting
Save on the billing-address step.
Expected behavior: The updated billing address is saved and shown at checkout.
Flow: Account > Billing > Edit address > Save.
Evidence: Reproduced three times in production on build 8421.
```

If the policy has not been saved yet, include it in the same request:

```text
Use the bug-filing-go-no-go skill to review this bug.

P1 goal: Reduce failures that prevent existing customers from completing
checkout. Account billing updates are in scope.
Admissible flow: Signed-in account owners may edit their billing address from
Account > Billing. The Save action is supported.

Bug description: <paste the proposed bug here>
```

## Understand the result

The skill returns one of three decisions:

| Decision | Meaning |
|---|---|
| `GO` | P1 alignment and flow admissibility both pass. |
| `NO-GO` | At least one gate clearly fails a configured rule. |
| `NEEDS-INFO` | The report or policy lacks information needed for a defensible decision. |

Every result identifies the controlling criterion, the evidence from the bug
description, missing information, and the next action. A `GO` permits filing;
it does not determine the bug's severity or priority.

## Files

- [`SKILL.md`](SKILL.md) contains the agent workflow and output contract.
- [`references/decision-policy.md`](references/decision-policy.md) contains the
  configurable P1 and flow-admissibility rules.
