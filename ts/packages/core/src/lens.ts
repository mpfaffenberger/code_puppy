/**
 * Lens — Mist's explainability & interpretability ledger.
 *
 * Answers "why did this small command burn 80k tokens?": every turn records a
 * structured trace of model requests (tokens in/out, thinking share, stop
 * reason), tool calls (duration, output size, previews, errors, hook blocks),
 * subagents (with their OWN token attribution), and engine events
 * (auto-continues, request-cap exits, compactions).
 *
 * Token semantics (important):
 * - `inputTokens`/`outputTokens` are the API's real usage numbers.
 * - THINKING IS INCLUDED in outputTokens — providers bill reasoning as output.
 *   `estThinkingTokens` (chars/3.5 over thinking deltas) separates the share
 *   so /lens can show how much of the spend was reasoning vs. visible text.
 * - Billed input = Σ per-request input (the WHOLE history is resent every
 *   request — the usual culprit when a short prompt costs a lot).
 */

export interface ToolCallLens {
  name: string;
  /** Display label (e.g. `$ seq 1 4`, `edited foo.ts`). */
  label: string;
  ms: number;
  outputChars: number;
  /** First ~1500 chars of the tool result (full output lives in history). */
  outputPreview: string;
  isError: boolean;
  blockedByHook: boolean;
}

export interface RequestLens {
  index: number;
  ms: number;
  inputTokens: number;
  /** Includes thinking — see estThinkingTokens for the reasoning share. */
  outputTokens: number;
  estThinkingTokens: number;
  thinkingMs: number;
  stopReason: string;
  textChars: number;
  toolCalls: ToolCallLens[];
}

export interface SubagentLens {
  id: string;
  label: string;
  task: string;
  steps: number;
  inputTokens: number;
  outputTokens: number;
  ms: number;
  reportChars: number;
  error?: string;
}

export interface CompactionLens {
  beforeTokens: number;
  afterTokens: number;
  summarized: number;
}

export interface TurnLens {
  prompt: string;
  startedAt: string;
  ms: number;
  requests: RequestLens[];
  subagents: SubagentLens[];
  autoContinues: number;
  capHit: boolean;
  compactions: CompactionLens[];
}

export interface LensTotals {
  requests: number;
  toolCalls: number;
  subagents: number;
  /** Σ per-request input — what the provider actually billed. */
  billedInputTokens: number;
  outputTokens: number;
  estThinkingTokens: number;
  /** input_tokens of the LAST request — the live context size. */
  finalContextTokens: number;
  toolMs: number;
  modelMs: number;
  toolErrors: number;
  hookBlocks: number;
}

export function lensTotals(turn: TurnLens): LensTotals {
  let billed = 0;
  let out = 0;
  let think = 0;
  let toolCalls = 0;
  let toolMs = 0;
  let modelMs = 0;
  let errors = 0;
  let blocks = 0;
  for (const r of turn.requests) {
    billed += r.inputTokens;
    out += r.outputTokens;
    think += r.estThinkingTokens;
    modelMs += r.ms;
    for (const t of r.toolCalls) {
      toolCalls += 1;
      toolMs += t.ms;
      if (t.isError) errors += 1;
      if (t.blockedByHook) blocks += 1;
    }
  }
  // Subagent traffic is attributed separately AND included in nothing else —
  // child requests never appear in the parent's request list.
  for (const s of turn.subagents) {
    billed += s.inputTokens;
    out += s.outputTokens;
  }
  return {
    requests: turn.requests.length,
    toolCalls,
    subagents: turn.subagents.length,
    billedInputTokens: billed,
    outputTokens: out,
    estThinkingTokens: think,
    finalContextTokens: turn.requests[turn.requests.length - 1]?.inputTokens ?? 0,
    toolMs,
    modelMs,
    toolErrors: errors,
    hookBlocks: blocks,
  };
}

const esc = (s: string): string =>
  s.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

const fmt = (n: number): string => n.toLocaleString("en-US");

/**
 * Self-contained interactive HTML report — no external assets, opens in any
 * browser. Timeline of requests with token bars (input / output / thinking
 * share), expandable tool calls with output previews, subagent cards.
 */
export function renderLensHtml(turns: TurnLens[], sessionId: string): string {
  const rows = turns
    .map((turn, ti) => {
      const t = lensTotals(turn);
      const maxTok = Math.max(1, ...turn.requests.map((r) => r.inputTokens + r.outputTokens));
      const reqRows = turn.requests
        .map((r) => {
          const thinkPct = r.outputTokens ? Math.min(100, Math.round((r.estThinkingTokens / r.outputTokens) * 100)) : 0;
          const tools = r.toolCalls
            .map(
              (c) => `
        <details class="tool ${c.isError ? "err" : ""}${c.blockedByHook ? " blocked" : ""}">
          <summary><code>${esc(c.name)}</code> ${esc(c.label.slice(0, 100))}
            <span class="meta">${c.ms}ms · ${fmt(c.outputChars)} chars${c.isError ? " · ERROR" : ""}${c.blockedByHook ? " · BLOCKED BY HOOK" : ""}</span>
          </summary>
          <pre>${esc(c.outputPreview) || "(empty output)"}</pre>
        </details>`,
            )
            .join("");
          return `
      <div class="req">
        <div class="reqhead">
          <span class="idx">#${r.index + 1}</span>
          <span class="bar"><span class="in" style="width:${(r.inputTokens / maxTok) * 100}%"></span><span class="out" style="width:${(r.outputTokens / maxTok) * 100}%"></span></span>
          <span class="meta">in ${fmt(r.inputTokens)} · out ${fmt(r.outputTokens)}${r.estThinkingTokens ? ` (≈${thinkPct}% thinking)` : ""} · ${r.ms}ms · ${esc(r.stopReason)}</span>
        </div>
        ${tools}
      </div>`;
        })
        .join("");
      const subs = turn.subagents
        .map(
          (s) => `
      <details class="sub${s.error ? " err" : ""}">
        <summary>◇ ${esc(s.label)} <span class="meta">${s.steps} steps · in ${fmt(s.inputTokens)} · out ${fmt(s.outputTokens)} · ${s.ms}ms${s.error ? " · FAILED" : ""}</span></summary>
        <pre>task: ${esc(s.task.slice(0, 500))}${s.error ? `\nerror: ${esc(s.error)}` : ""}</pre>
      </details>`,
        )
        .join("");
      const flags = [
        turn.autoContinues ? `⟳ ${turn.autoContinues} auto-continue(s)` : "",
        turn.capHit ? "⏸ request cap hit" : "",
        ...turn.compactions.map((c) => `⇣ compacted ${fmt(c.beforeTokens)} → ${fmt(c.afterTokens)}`),
      ]
        .filter(Boolean)
        .join(" · ");
      return `
  <section>
    <h2>Turn ${ti + 1}: <span class="prompt">${esc(turn.prompt.slice(0, 120))}</span></h2>
    <div class="cards">
      <div class="card"><b>${fmt(t.billedInputTokens)}</b><span>billed input tok</span></div>
      <div class="card"><b>${fmt(t.outputTokens)}</b><span>output tok</span></div>
      <div class="card"><b>${fmt(t.estThinkingTokens)}</b><span>≈ thinking tok</span></div>
      <div class="card"><b>${fmt(t.finalContextTokens)}</b><span>context size</span></div>
      <div class="card"><b>${t.requests}</b><span>model requests</span></div>
      <div class="card"><b>${t.toolCalls}</b><span>tool calls</span></div>
      <div class="card"><b>${t.subagents}</b><span>subagents</span></div>
      <div class="card"><b>${Math.round(t.modelMs / 1000)}s / ${Math.round(t.toolMs / 1000)}s</b><span>model / tool time</span></div>
    </div>
    ${flags ? `<p class="flags">${flags}</p>` : ""}
    ${reqRows}
    ${subs ? `<h3>Subagents</h3>${subs}` : ""}
  </section>`;
    })
    .join("");

  return `<!doctype html><meta charset="utf-8"><title>Mist Lens — ${esc(sessionId.slice(0, 8))}</title>
<style>
  body{background:#14171f;color:#e8edf7;font:14px/1.5 ui-monospace,monospace;max-width:960px;margin:2rem auto;padding:0 1rem}
  h1{color:#a8d3e1} h2{color:#e5b8d1;font-size:1rem;margin:2rem 0 .5rem} h3{color:#a8d3e1;font-size:.9rem}
  .prompt{color:#e8edf7;font-weight:400}
  .cards{display:flex;flex-wrap:wrap;gap:.5rem;margin:.5rem 0}
  .card{background:#1c2130;border:1px solid #2a3145;border-radius:6px;padding:.4rem .7rem;text-align:center}
  .card b{display:block;color:#a8d3e1;font-size:1rem} .card span{color:#8a93a6;font-size:.7rem}
  .flags{color:#d4af5a}
  .req{border-left:2px solid #2a3145;margin:.4rem 0;padding:.2rem .6rem}
  .reqhead{display:flex;align-items:center;gap:.6rem}
  .idx{color:#8a93a6} .meta{color:#8a93a6;font-size:.8rem}
  .bar{display:inline-flex;width:180px;height:8px;background:#1c2130;border-radius:4px;overflow:hidden}
  .bar .in{background:#5b8dd9} .bar .out{background:#6FAE94}
  details{margin:.25rem 0 .25rem 1rem} summary{cursor:pointer;color:#b3e4e6}
  details.err summary{color:#ff6b6b} details.blocked summary{color:#d4af5a}
  pre{background:#10131b;border:1px solid #2a3145;border-radius:6px;padding:.6rem;white-space:pre-wrap;word-break:break-word;color:#c7cddc;max-height:320px;overflow:auto}
  .sub summary{color:#e5b8d1}
</style>
<h1>◆ Mist Lens <span class="meta">session ${esc(sessionId.slice(0, 8))} · ${turns.length} turn(s)</span></h1>
<p class="meta">Blue = input tokens (whole history resent per request) · green = output (thinking included; ≈share shown). Click any tool or subagent to expand.</p>
${rows}`;
}
