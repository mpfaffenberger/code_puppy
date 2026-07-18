---
name: cheatsheet
description: Show the //flux pipeline cheatsheet (all stages, colorized)
exec: {python} {script:flux_cheatsheet.py} --docs {command:flux/_docs}
---

# /flux/cheatsheet

Renders the //flux pipeline cheatsheet -- a colorized view of every pipeline
stage (A/B/C/D) sourced from the canonical `pipeline.md` doc.

> **Note:** code-puppy executes this command via the `exec:` frontmatter hook,
> which runs the bundled `flux_cheatsheet.py` (resolved under code-puppy's
> config dir) and streams its ANSI output back through the message bus. The
> body below is reference docs only -- it is not sent to the AI when the script
> is wired up.
