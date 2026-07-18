---
name: cheatsheet
description: Show the //flux pipeline cheatsheet (all stages, colorized)
exec: python3 ~/.code_puppy/scripts/flux_cheatsheet.py
---

# //flux/cheatsheet

Renders the //flux pipeline cheatsheet -- a colorized view of every pipeline
stage (A/B/C/D) sourced from the canonical `pipeline.md` doc.

> **Note:** code-puppy executes this command via the `exec:` frontmatter hook,
> which runs `~/.code_puppy/scripts/flux_cheatsheet.py` and streams its ANSI
> output back through the message bus. The body below is reference docs only --
> it is not sent to the AI when the script is wired up.
