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
