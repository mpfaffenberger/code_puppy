# Showcase: Canvas LMS Grading Assistant (Built with Code Puppy )

> A community showcase of a real-world tool built end-to-end with Code Puppy:
> a CLI that helps an instructor audit, download, and pre-grade student
> submissions from the Canvas LMS — with a human-review-first workflow.

## What it does

A single Python CLI (`main.py`) wrapping the Canvas REST API with these commands:

| Command | Purpose |
|---|---|
| `list-courses` | List courses where you are the teacher |
| `list-assignments <course_id>` | Show assignments (incl. rubrics) |
| `list-modules <course_id>` | Show course modules and items |
| `find-student <course_id> <query>` | Search students by name |
| `check-ungraded <course_id>` | Find assignments with ungraded submissions |
| `check-announcements <course_id>` | Search course announcements |
| `download-submissions <course_id> <assignment_id> --dir X` | Bulk-download attachments per student |
| `gradebook-analytics <course_id>` | Class averages, missing work, at-risk students (pandas) |
| `auto-grade <course_id> <assignment_id> --dir X` | **Preview** scores + feedback per submission |
| `full-audit <course_id> <assignment_id>` | Submission status/lateness audit table |

## Key design decisions (the interesting part)

1. **Human-in-the-loop, always.** The tool *never* posts grades automatically.
   `auto-grade` produces a preview report; the instructor reviews everything
   before anything touches Canvas. This was a hard project mandate.

2. **Content-aware analyzers per assignment type.** Instead of grading by
   "did they submit a file," each lab has an analyzer:
   - **Excel labs**: opens the `.xlsx` and inspects the internal XML/formula
     structure — verifies `=SUM(...)` and subtraction formulas actually exist,
     charts are present, and data is sorted. A PDF export of a spreadsheet
     can't be formula-verified, so it gets a standardized format deduction.
   - **PDF report labs**: text extraction + per-section checks against the
     lab requirements.
   - **Programming lab**: parses the submitted report for required program
     behavior (input handling, overtime math, formatted output).

3. **Fairness protocols encoded as policy, not vibes.**
   - *Standardized deductions*: fixed point values per error type, applied
     identically to every student.
   - *Repetitive Error Protocol*: if >25% of the class misses the same
     requirement, the penalty is waived or halved (exposed as a
     `--waive-sorting / --no-waive-sorting` flag).
   - *Late policy*: flat 10%, cross-checked against Canvas's `late` flag
     **and** the actual timestamps (Canvas's flag alone can be wrong).
   - *Needs-review flag*: anything ambiguous is marked `!!! NEEDS MANUAL
     REVIEW !!!` rather than silently scored.

4. **Encouraging feedback generation.** Comments lead with positives and list
   deductions transparently, matching an intro-course leniency policy.

5. **Zero secrets in code.** Canvas URL + API token live in a local `.env`
   (`python-dotenv`); student submissions are downloaded into a git-ignored
   directory and never leave the instructor's machine.

## Architecture

```
main.py                      # entry point
canvas_utils/
  client.py                  # Canvas REST client (pagination via Link headers,
                             #   courses, assignments, submissions, gradebook,
                             #   overrides, quiz retakes, announcements)
  cli.py                     # argparse subcommands
  grader.py                  # policy engine: routing, late penalties,
                             #   format validation, feedback composer
  analyzers.py               # per-lab content analyzers (xlsx XML, PDF text)
  lab6_analyzer.py           # dedicated analyzer for the programming lab
```

Dependencies: `requests`, `python-dotenv`, `pandas`, plus openpyxl/pypdf-style
parsing for submission content.

## How Code Puppy helped

- Iteratively built the Canvas client from the raw REST docs, including the
  Link-header pagination gotcha.
- Wrote each lab analyzer by inspecting real (local) submission files and
  turning rubric language into checkable assertions.
- Encoded the grading guidelines document (`CANVAS_GUIDELINES.md`) into the
  policy engine so the rules are versioned alongside the code.

## Privacy note

This showcase intentionally contains **no code that embeds institution names,
course IDs, student data, or credentials**. If you build something similar:
keep tokens in `.env`, git-ignore your submissions directory, and never commit
student work (FERPA!).
