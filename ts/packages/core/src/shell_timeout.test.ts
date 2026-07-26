import { afterEach, expect, test } from "bun:test";
import { SHELL_TIMEOUT, runTool, shellTimeoutFor } from "./tools";
import { listBgJobs, readBgOutput, resetBgJobs } from "./background";

afterEach(() => {
  delete process.env.MIST_SHELL_TIMEOUT;
  delete process.env.MIST_SHELL_MAX_TIMEOUT;
  resetBgJobs();
});

const ctx = { cwd: "/tmp", onStep: () => {} };

test("dynamic timeouts: quick reads get 30s, builds get 600s, the rest 120s", () => {
  expect(shellTimeoutFor("git status --short")).toBe(SHELL_TIMEOUT.quick);
  expect(shellTimeoutFor("ls -la /tmp")).toBe(SHELL_TIMEOUT.quick);
  expect(shellTimeoutFor("cat package.json")).toBe(SHELL_TIMEOUT.quick);

  expect(shellTimeoutFor("bun install")).toBe(SHELL_TIMEOUT.long);
  expect(shellTimeoutFor("cd ts && bun test")).toBe(SHELL_TIMEOUT.long);
  expect(shellTimeoutFor("docker build -t x .")).toBe(SHELL_TIMEOUT.long);
  expect(shellTimeoutFor("pytest -q")).toBe(SHELL_TIMEOUT.long);

  expect(shellTimeoutFor("./scripts/deploy.sh")).toBe(SHELL_TIMEOUT.default);
  expect(shellTimeoutFor("curl https://example.com")).toBe(SHELL_TIMEOUT.default);
});

test("model override wins, clamped to the hard max; env sets the default", () => {
  expect(shellTimeoutFor("git status", 5)).toBe(5); // shorter than the class default
  expect(shellTimeoutFor("git status", 300)).toBe(300); // longer, allowed
  expect(shellTimeoutFor("git status", 9999)).toBe(SHELL_TIMEOUT.max); // clamped

  process.env.MIST_SHELL_MAX_TIMEOUT = "45";
  expect(shellTimeoutFor("bun install")).toBe(45); // class default clamped by max
  expect(shellTimeoutFor("git status", 300)).toBe(45);
  delete process.env.MIST_SHELL_MAX_TIMEOUT;

  process.env.MIST_SHELL_TIMEOUT = "90";
  expect(shellTimeoutFor("./anything.sh")).toBe(90); // env default
  expect(shellTimeoutFor("./anything.sh", 10)).toBe(10); // explicit still wins
});

test("a hung command with a surviving grandchild times out instead of stalling", async () => {
  // THE regression: killing bash does not close the pipe a grandchild holds,
  // so a naive `new Response(proc.stdout).text()` waits forever.
  const t0 = Date.now();
  const res = await runTool(
    "shell",
    { command: "sleep 30 & echo working; wait", timeout_seconds: 1 },
    ctx,
  );
  const elapsed = Date.now() - t0;
  expect(elapsed).toBeLessThan(8000); // returned, did not hang
  expect(res.isError).toBe(true);
  expect(res.content).toContain("timed out");
  expect(res.content).toContain("working"); // partial output preserved
});

test("run_in_background returns immediately and keeps capturing output", async () => {
  const res = await runTool(
    "shell",
    { command: "echo first; sleep 1; echo second", run_in_background: true },
    ctx,
  );
  expect(res.isError).toBeFalsy();
  expect(res.content).toContain("still running");
  const jobs = listBgJobs();
  expect(jobs.length).toBe(1);
  const id = jobs[0]!.id;

  // bg_output reports status + captured output once the job finishes.
  await Bun.sleep(2500);
  const out = await runTool("bg_output", { id }, ctx);
  expect(out.content).toContain("second");
  expect(await readBgOutput(id)).toContain("first");
});

test("bg_kill stops a running job; unknown ids are reported, not thrown", async () => {
  await runTool("shell", { command: "sleep 30", run_in_background: true }, ctx);
  const id = listBgJobs()[0]!.id;
  const killed = await runTool("bg_kill", { id }, ctx);
  expect(killed.isError).toBeFalsy();
  expect(listBgJobs()[0]!.status).toBe("killed");

  const missing = await runTool("bg_output", { id: "bg_999" }, ctx);
  expect(missing.isError).toBe(true);
  expect(missing.content).toContain("no background job");
});

test("normal commands still return output and exit codes unchanged", async () => {
  const ok = await runTool("shell", { command: "echo hello" }, ctx);
  expect(ok.isError).toBeFalsy();
  expect(ok.content).toContain("exit 0");
  expect(ok.content).toContain("hello");

  const bad = await runTool("shell", { command: "exit 3" }, ctx);
  expect(bad.isError).toBe(true);
  expect(bad.content).toContain("exit 3");
});
