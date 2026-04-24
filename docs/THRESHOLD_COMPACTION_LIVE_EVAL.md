# Threshold Compaction Live Evaluation

This note records the live model comparison run used to sanity-check the new
opt-in `compaction_strategy=threshold` implementation against Code Puppy's
legacy compaction strategies.

The reusable benchmark harness is `scripts/live_compaction_qa_eval.py`. The
live run artifacts were generated outside the repository under
`/tmp/code-puppy-live-compare-10` to avoid committing large synthetic
transcripts and model answer files.

## Method

- Ran 10 matched transcript variants with varied context pressure.
- Each variant was compacted through 10 compaction cycles.
- Compared:
  - `threshold`: new threshold compaction path through `_compaction.compact()`.
  - `truncation`: legacy truncation path through `_compaction.compact()`.
  - `summarization`: legacy summarization path through `_compaction.compact()`.
  - `live_summarization_surrogate`: a successful-summary baseline where
    GPT-5.4 summarized the legacy older region, then a separate evaluator
    scored summary plus protected tail.
- Legacy runs used the production behavior that protects a recent tail up to
  `protected_token_count`, clipped to 75% of the active model window, and still
  applied the existing 50k-token huge-message filter.
- Each evaluator saw only one compacted transcript prompt and returned a JSON
  extraction of resumability-critical facts.
- Hidden facts per test: goal, current error key, next action, 3 constraints,
  3 active files, and 3 invalidated hypotheses.

The local environment did not have an OpenAI API key available for the harness
to call directly, so GPT-5.4 subagents were used as isolated live evaluators.

## Results

| Strategy | Normalized recall | Exact recall | Average prompt tokens |
| --- | ---: | ---: | ---: |
| `threshold` | 117/120, 97.5% | 117/120, 97.5% | 49.6k |
| `live_summarization_surrogate` | 99/120, 82.5% | 78/120, 65.0% | 38.3k |
| `truncation` | 78/120, 65.0% | 76/120, 63.3% | 37.1k |
| `summarization` | 75/120, 62.5% | 73/120, 60.8% | 37.1k |

The local production `summarization` prompts were byte-identical to
`truncation` for all 10 variants because the configured summarization path fell
back to truncation. The surrogate row is included to show the likely upper
bound for successful legacy summarization under the same split/protected-tail
model.

## Per-Test Normalized Scores

| Test | Threshold | Truncation | Local summarization | Live summary surrogate |
| --- | ---: | ---: | ---: | ---: |
| 1 | 12/12 | 9/12 | 7/12 | 10/12 |
| 2 | 12/12 | 6/12 | 6/12 | 11/12 |
| 3 | 11/12 | 6/12 | 6/12 | 9/12 |
| 4 | 12/12 | 9/12 | 9/12 | 9/12 |
| 5 | 12/12 | 8/12 | 8/12 | 9/12 |
| 6 | 11/12 | 8/12 | 7/12 | 11/12 |
| 7 | 12/12 | 8/12 | 8/12 | 11/12 |
| 8 | 12/12 | 8/12 | 8/12 | 10/12 |
| 9 | 11/12 | 8/12 | 8/12 | 10/12 |
| 10 | 12/12 | 8/12 | 8/12 | 9/12 |

## Field-Level Normalized Recall

| Field | Threshold | Truncation | Local summarization | Live summary surrogate |
| --- | ---: | ---: | ---: | ---: |
| Goal | 10/10 | 10/10 | 9/10 | 10/10 |
| Current error key | 7/10 | 4/10 | 4/10 | 4/10 |
| Next action | 10/10 | 10/10 | 10/10 | 10/10 |
| Constraints | 30/30 | 12/30 | 12/30 | 27/30 |
| Active files | 30/30 | 24/30 | 22/30 | 26/30 |
| Invalidated hypotheses | 30/30 | 18/30 | 18/30 | 22/30 |

## Interpretation

The threshold strategy substantially outperformed the legacy methods for
resumability. It preserved all goals, constraints, active files, invalidated
hypotheses, and next actions across the 10-cycle run. The only misses were
3/10 current-error-key extractions, all in MCP restart variants where the
durable/masked signal exposed nearby failure text instead of the exact final
assertion key.

The next practical improvement target is the observation key-signal extractor:
prefer exact final assertion/error identifiers over intermediate failure text
when masking tool-return observations.

## Verification Commands

The committed harness file passed:

```bash
uv run ruff check scripts/live_compaction_qa_eval.py
uv run ruff format --check scripts/live_compaction_qa_eval.py
uv run python -m py_compile scripts/live_compaction_qa_eval.py
```
