/**
 * The live plan (the "DST" — dynamic status tree the user watches and steers).
 * The model maintains it via the `update_plan` tool (full-replace semantics,
 * like codex's update_plan / Claude Code's task list); every update is
 * broadcast as a `plan.updated` envelope so the UI re-renders in place.
 */

export type PlanStatus = "pending" | "active" | "done" | "skipped";

export interface PlanItem {
  id: string;
  title: string;
  status: PlanStatus;
}

const VALID: PlanStatus[] = ["pending", "active", "done", "skipped"];

export function normalizePlan(raw: unknown): PlanItem[] {
  if (!Array.isArray(raw)) return [];
  const items: PlanItem[] = [];
  for (const [i, entry] of raw.entries()) {
    if (typeof entry !== "object" || entry === null) continue;
    const e = entry as Record<string, unknown>;
    const title = typeof e["title"] === "string" ? e["title"].trim() : "";
    if (!title) continue;
    const status = VALID.includes(e["status"] as PlanStatus)
      ? (e["status"] as PlanStatus)
      : "pending";
    const id = typeof e["id"] === "string" && e["id"] ? e["id"] : `p${i + 1}`;
    items.push({ id, title: title.slice(0, 120), status });
  }
  return items.slice(0, 20); // a plan longer than 20 items is a smell
}
