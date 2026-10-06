# Command history persistence

Command history uses prompt_toolkit's FileHistory format: a timestamp comment
followed by `+`-prefixed lines. One submission is one record, including embedded
blank lines and trailing newlines. A literal leading `+` gets another `+` on disk;
the reader removes only that format prefix. Deliberate repeated submissions stay
separate records; there is no content-based deduplication.

## Persistence owners

Persist when input is captured or created, not when a model turn is dispatched:

- `RunningLineEditor._submit` records raw editor input before routing, including
  slash commands, shell commands, exits, now-mode steers, and queued submissions.
- Classic input calls `config.save_command_to_history` immediately after input.
- `PauseController.request_steer` records newly created queue/programmatic input.
  Callers pass `history_recorded=True` for editor-owned input and runtime requeues.
  Draining, deferring, or replacing the queue itself does not record history.
- Queued-turn editor saves record changed drafts; unchanged recall, restore, or
  submission does not create another record. New additions use `request_steer`.
- A slash command's generated prompt is distinct from the captured command. Idle
  expansions are recorded by the interactive loop; mid-run expansions use queue
  insertion. The `/steer` command passes `history_recorded=True` because its raw
  command was already captured.

`config.save_command_to_history` delegates to `HistoryStore`, rather than writing
another serialization. The input owner writes even if subsequent processing
returns early or fails. History read and write failures are best-effort and must
not interrupt input handling. All history write failures now log at debug level
without emitting a user-facing error, including config/classic writes that
previously emitted an error. A failed write can therefore leave a submission
absent from recall. Ownership means the write was attempted, not that storage
succeeded. Command-history capture is not an execution audit log.

## Existing files

Valid formatted entries remain readable without rewriting. No migration or
cleanup of existing user history is performed by this change.

Older files may mix formatted entries and plain-text records. A plain record
starting with `+` is indistinguishable from a formatted record at the same byte
sequence. Removing marker characters, guessing record provenance, or silently
rewriting such files cannot guarantee lossless recovery. This fix prevents new
mixed-format records; it does not claim to recover ambiguous old records.

The legacy `command_line/history_manager.py` utility is not the active editor
reader and remains unchanged. Retention, rotation, caching, and historical-file
repair are outside this correctness fix.
