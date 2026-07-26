/**
 * Background jobs — Ctrl+B detaches a running shell command so the turn can
 * continue while it keeps working (dev servers, long builds, watchers).
 *
 * The process keeps running with its output drained to a log file; the agent
 * polls it with `bg_output` and can stop it with `bg_kill`. Jobs live for the
 * process lifetime of the CLI — they are deliberately NOT persisted, since a
 * pid is meaningless once the shell that owns it is gone.
 */

import { join } from "node:path";
import { tmpdir } from "node:os";

export interface BgJob {
  id: string;
  command: string;
  pid: number;
  logPath: string;
  startedAt: number;
  status: "running" | "exited" | "killed";
  exitCode?: number;
}

const jobs = new Map<string, BgJob>();
let seq = 0;

export function bgLogPath(id: string): string {
  return join(process.env.MIST_BG_DIR ?? tmpdir(), `mist-${id}.log`);
}

export function registerBgJob(command: string, pid: number, startedAt: number): BgJob {
  const id = `bg_${++seq}`;
  const job: BgJob = {
    id,
    command,
    pid,
    logPath: bgLogPath(id),
    startedAt,
    status: "running",
  };
  jobs.set(id, job);
  return job;
}

export function markBgExited(id: string, exitCode: number): void {
  const job = jobs.get(id);
  if (!job || job.status === "killed") return;
  job.status = "exited";
  job.exitCode = exitCode;
}

export function listBgJobs(): BgJob[] {
  return [...jobs.values()];
}

export function getBgJob(id: string): BgJob | undefined {
  return jobs.get(id);
}

/** Tail of a job's captured output (the log is rewritten as it grows). */
export async function readBgOutput(id: string, maxChars = 8000): Promise<string> {
  const job = jobs.get(id);
  if (!job) return "";
  const text = await Bun.file(job.logPath)
    .text()
    .catch(() => "");
  return text.length > maxChars ? `…(earlier output trimmed)\n${text.slice(-maxChars)}` : text;
}

export function killBgJob(id: string): boolean {
  const job = jobs.get(id);
  if (!job || job.status !== "running") return false;
  killProcessTree(job.pid);
  job.status = "killed";
  return true;
}

/**
 * Best-effort tree kill. A plain `proc.kill()` only signals bash — surviving
 * grandchildren keep the stdout pipe open, which is exactly the hang that
 * makes a turn look stuck. Walk the pgrep tree and signal children first.
 */
export function killProcessTree(pid: number, signal: "SIGTERM" | "SIGKILL" = "SIGTERM"): void {
  const children = (() => {
    try {
      const out = Bun.spawnSync(["pgrep", "-P", String(pid)]).stdout.toString().trim();
      return out ? out.split("\n").map((l) => Number(l.trim())).filter(Boolean) : [];
    } catch {
      return [];
    }
  })();
  for (const child of children) killProcessTree(child, signal);
  try {
    process.kill(pid, signal);
  } catch {
    /* already gone */
  }
}

/** Test seam — drop all tracked jobs. */
export function resetBgJobs(): void {
  jobs.clear();
  seq = 0;
}
