import { expect, test } from "bun:test";
import { SPINNER_VERBS, pickVerb } from "./spinnerVerbs";

test("pickVerb returns a member and avoids immediate repeats", () => {
  expect(SPINNER_VERBS.length).toBeGreaterThan(180);
  for (let i = 0; i < 50; i++) {
    const v = pickVerb("Pondering");
    expect(SPINNER_VERBS).toContain(v);
    expect(pickVerb(v)).not.toBe(v);
  }
});

import { VERB_POOLS } from "./spinnerVerbs";

test("pools are subsets of the master list", () => {
  for (const pool of Object.values(VERB_POOLS)) {
    for (const v of pool) expect(SPINNER_VERBS).toContain(v);
  }
});

test("context pool is used ~70% (deterministic rand)", () => {
  // rand()=0.1 → pool branch; second rand indexes the pool
  const v = pickVerb(undefined, "edit", () => 0.1);
  expect(VERB_POOLS.edit).toContain(v);
  // rand()=0.9 → general branch
  const g = pickVerb(undefined, "edit", () => 0.9);
  expect(SPINNER_VERBS).toContain(g);
});
