/** Label a group of collapsed tool steps, Claude-Code style ("Ran 3 shell commands"). */
export function labelForGroup(steps: string[]): string {
  if (!steps.length) return "";
  const category = (s: string): string =>
    s.startsWith("$") ? "shell" :
    s.startsWith("read ") ? "read" :
    s.startsWith("listed ") ? "list" :
    s.startsWith("grep ") ? "search" :
    s.startsWith("created ") || s.startsWith("edited ") ? "edit" : "tool";
  const cats = new Set(steps.map(category));
  const n = steps.length;
  if (cats.size === 1) {
    const c = [...cats][0];
    const noun: Record<string, [string, string]> = {
      shell: ["shell command", "shell commands"],
      read: ["file read", "file reads"],
      list: ["directory listing", "directory listings"],
      search: ["search", "searches"],
      edit: ["file edit", "file edits"],
      tool: ["tool call", "tool calls"],
    };
    const [one, many] = noun[c!] ?? ["tool call", "tool calls"];
    return `Ran ${n} ${n === 1 ? one : many}`;
  }
  return `Ran ${n} tool call${n === 1 ? "" : "s"}`;
}
