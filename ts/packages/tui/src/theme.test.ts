import { expect, test } from "bun:test";
import { THEMES, applyTheme, loadPersistedTheme, persistTheme, theme } from "./theme";

test("applyTheme swaps the live theme in place", () => {
  applyTheme("mist");
  const mistAccent = theme.accent;
  expect(applyTheme("cinnamon")).toBe(true);
  expect(theme.name).toBe("cinnamon");
  expect(theme.accent).not.toBe(mistAccent);
  expect(applyTheme("nope")).toBe(false);
  expect(theme.name).toBe("cinnamon"); // unchanged on unknown
  applyTheme("mist");
});

test("theme persists and reloads", async () => {
  process.env.MIST_TS_SETTINGS = `/tmp/mist-ts-settings-${Date.now()}.json`;
  await persistTheme("cinnamon");
  applyTheme("mist");
  await loadPersistedTheme();
  expect(theme.name).toBe("cinnamon");
  expect(Object.keys(THEMES)).toContain("mist");
  applyTheme("mist");
  delete process.env.MIST_TS_SETTINGS;
});
