# Boot trace

Boot trace records timed spans for Code Puppy CLI startup and session work.
Use it to find which phases and plugin imports take the most time. This page
covers how to enable tracing, the output format, the ranked report, and the
contract for host applications that read trace output.

## Enable tracing

Set `CODE_PUPPY_BOOT_TRACE` before you start the CLI. The value selects where
trace events go:

| Value | Result |
|---|---|
| `stderr` | Trace lines go to standard error, tagged with a prefix. |
| An absolute path, such as `/tmp/run-1.jsonl` | Trace events go to a new JSONL file. |
| Unset, empty, `0`, or `off` | Tracing is disabled. |
| Anything else | Tracing is silently disabled. |

Tracing reads the variable once, when the boot-trace module first loads. Relative
paths and `~` are not expanded. Use an absolute path.

## File output rules

When you choose a file, the CLI creates it exclusively. These rules apply:

- The parent directory must already exist. The CLI never creates directories.
- The file must not exist. The CLI never overwrites, appends to, rotates, or
  uploads a trace.
- On POSIX systems, the file mode is `0600`.
- On Windows, the file inherits the directory's access control list. The CLI
  does not claim `chmod`-equivalent privacy there.
- You own the file. Delete it when you finish. Choose one new file per run.

## Stderr line format

Each stderr trace line starts with `CODE_PUPPY_BOOT_TRACE ` (note the trailing
space), followed by compact JSON and a newline. The CLI writes nothing to
standard output for tracing.

File lines contain the same JSON, without the prefix.

## Event schema (version 1)

Every event carries these required fields:

| Field | Meaning |
|---|---|
| `v` | Schema version. This page documents `1`. |
| `bootId` | Random per-process identifier, as 32 hex characters. |
| `seq` | 1-based sequence number within the boot. |
| `phase` | Dotted, lowercase phase name, such as `cli.parse`. |
| `span` | Process-unique short identifier, as hex. |
| `kind` | `start`, `end`, `error`, `skip`, or `mark`. |
| `tMonoMs` | Milliseconds since the recorder started. Monotonic. |
| `tWallMs` | Unix time in milliseconds. Diagnostic only. |
| `attrs` | Object of allowed attributes. It may be empty. |

A complete span has a `start` event and one terminal event with the same
`span`, `phase`, and `parent`. Terminal events have `durMs`, which is
milliseconds from start to end. `reason` appears only on `skip` events.

Here is an example from the schema:

```json
{"v":1,"bootId":"uuid4-hex","seq":12,"phase":"plugin.import","span":"a","parent":"9","kind":"end","tMonoMs":81.4,"tWallMs":1790000000000,"durMs":7.2,"attrs":{"tier":"installed","plugin":"acp"},"unit":{"n":1,"of":70}}
```

Optional `unit` values give progress within a batch, as `{"n":..,"of":..}`.
They are not an overall percentage.

### Allowed attributes

Unknown attribute keys are dropped. The allowed keys are:

- `plugin`: a reviewed plugin name, or `h:` followed by 16 lowercase hex characters.
- `tier`: `installed`, `builtin`, `user`, or `project`.
- `count`: a nonnegative integer.
- `cached` and `network_attempted`: booleans.
- `outcome`: `ok`, `error`, `timeout`, `tls`, `dns`, `other`, `remote`,
  `fallback`, `unavailable`, or `control_exit`.
- `exceptionClass`: an identifier of up to 64 ASCII characters. It never carries a message.

### Units

- `durMs`: milliseconds, finite and nonnegative.
- `tMonoMs`: milliseconds since the recorder started.
- `tWallMs`: integer Unix milliseconds.

## Drop marks, sequence gaps, and incomplete traces

The recorder uses a bounded queue of 512 events and drops the newest events
when the queue is full. It never blocks the CLI. When events are dropped, the
writer emits a `boot.dropped` mark with a top-level `dropped` field. That value
is the cumulative count of discarded events. The recorder discards events
produced after shutdown is requested, or after the sink disables itself,
silently: that leaves no sequence gap and no drop mark, so a lost tail shows up
as an unmatched start (an incomplete trace) in the report, never as a gap.

A trace is incomplete when any of these conditions occur:

- A sequence number is missing.
- A `boot.dropped` mark appears.
- A line is malformed.
- A span has no terminal event, or a terminal event does not match its start.

An incomplete trace is not a boot failure. The CLI does not wait for the trace
writer at exit, so the tail of a trace can be lost.

## Privacy

Trace output never contains paths, URLs, model names, user names, tokens,
headers, environment values, or exception messages. Plugin names that come
from users or projects are hashed with a per-run salt, so the same plugin
gets different identifiers in different runs.

## Ranked report

Run the report script to rank spans by duration:

```sh
python3 scripts/boot_trace_report.py trace.jsonl
python3 scripts/boot_trace_report.py - < stderr.log
python3 scripts/boot_trace_report.py trace.jsonl --boot-id <id> --top 10
```

The script uses only the Python standard library. It doesn't import
`code_puppy`.

Input can be a JSONL file, a stderr capture, or `-` for standard input. Tagged
lines and untagged JSON lines are read. Untagged, non-JSON lines in a capture
that also contains tagged lines are ignored as noise. In a file with no tagged
lines, non-JSON lines count as malformed.

Each line is limited to 2,048 bytes, including the tag and newline. Longer lines
are counted as malformed and are never parsed or printed.

If the input holds more than one boot, pass `--boot-id`. The report never mixes
boots. The default `--top` is 20.

The report prints:

- **Phases.** Completed `end` and `error` spans, sorted by `durMs` descending.
  Ties are broken by start order. The `plugin.import` phase is excluded.
- **Plugins.** Completed `plugin.import` spans, listed as tier, identity,
  duration, and status. An unknown tier prints as `?`. An invalid identity
  prints as `invalid`.
- **Skipped spans.** A count only. Skips are not ranked as slow work.
- **Status.** `ok` or `error`, plus `outcome=` when the value is valid.
- **Incomplete warnings.** Counts only.

The report prints no totals and no percentages. Don't add nested durations
together.

Two labels mark session-lifetime spans. The `boot` and `cli.handle_args` spans
show `(session lifetime, not boot-ready)` because they cover the whole session.

The phase list is open-ended. The report tolerates phases it does not know.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | The trace is complete. |
| `1` | The trace is incomplete. The report is still printed. |
| `2` | Invocation error. The input is unreadable, has no usable v1 events, needs `--boot-id`, names an unknown boot, or passes an invalid `--top`. |

## Handoff contract for host applications

A host application that launches the CLI and reads its trace should follow
these rules:

- Measure elapsed time with the host's own clock, around the CLI process.
  The CLI's `tMonoMs` clock is unrelated to the host clock. Don't compare them.
- Treat `tWallMs` as diagnostic only. The wall clock can jump. Never subtract
  it to compute a duration or a percentage.
- Don't treat `boot` or `cli.handle_args` as readiness. They span the session
  lifetime. For an ACP session, the duration is not startup duration.
- Expect bounded lines. Lines over 2,048 bytes are dropped and counted.
- Tolerate damaged lines, missing events, unknown phases, unknown attributes,
  and unknown schema versions. Skip what you don't understand.
- Tolerate best-effort delivery. A stalled sink, a crash, or an abrupt exit
  can lose events. An incomplete trace is not a failure.

## Attribution caveats

Read these caveats before you act on a ranking:

- Shared or nested imports are charged to the first importer.
- Import wrappers include ownership finalization and cleanup. They cannot
  isolate every nested library.
- Already-imported modules are warm, so they do not appear as cold cost.
- Queue and writer startup add diagnostic overhead.
- Time before Python starts, interpreter startup, and package initialization
  is invisible.
- The ranking does not show whether time is spent on CPU, disk, antivirus, or
  network work. Use other measurements for that.
- ACP session duration is not startup duration.
