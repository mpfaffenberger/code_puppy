import { expect, test } from "bun:test";
import { SPINNER_VERBS, VERB_POOLS, pickVerb } from "./spinnerVerbs";
import { THEMES, applyTheme } from "./theme";

test("pickVerb returns a member and avoids immediate repeats", () => {
  applyTheme("cinnamon"); // no themed verbs — standard pools in effect
  expect(SPINNER_VERBS.length).toBeGreaterThan(180);
  for (let i = 0; i < 50; i++) {
    const v = pickVerb("Pondering");
    expect(SPINNER_VERBS).toContain(v);
    expect(pickVerb(v)).not.toBe(v);
  }
  applyTheme("mist");
});

test("pools are subsets of the master list", () => {
  for (const pool of Object.values(VERB_POOLS)) {
    for (const v of pool) expect(SPINNER_VERBS).toContain(v);
  }
});

test("context pool is used ~70% (deterministic rand)", () => {
  applyTheme("cinnamon");
  // rand()=0.1 → pool branch; second rand indexes the pool
  const v = pickVerb(undefined, "edit", () => 0.1);
  expect(VERB_POOLS.edit).toContain(v);
  // rand()=0.9 → general branch
  const g = pickVerb(undefined, "edit", () => 0.9);
  expect(SPINNER_VERBS).toContain(g);
  applyTheme("mist");
});

test("themed verbs replace the pools (breathing forms per theme)", () => {
  for (const name of ["hinokami", "mist", "moon"]) {
    applyTheme(name);
    const forms = THEMES[name]!.verbs!;
    for (let i = 0; i < 20; i++) {
      expect(forms).toContain(pickVerb(undefined, "edit"));
    }
  }
  applyTheme("cinnamon"); // no themed verbs — clears the override
  expect(SPINNER_VERBS).toContain(pickVerb(undefined, "general", () => 0.9));
  applyTheme("mist");
});
