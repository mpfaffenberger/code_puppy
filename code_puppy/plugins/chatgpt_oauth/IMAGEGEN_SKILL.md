---
name: codex-imagegen
description: Generate raster images with gpt-image-2 through Codex OAuth. Activate when the user asks to create a photo, illustration, icon, sprite, texture, product image, banner, or other raster artwork.
version: "1.0"
author: code-puppy
---

# Codex Image Generation

Use the `codex_imagegen` tool when the user asks you to create raster artwork.
The tool uses `gpt-image-2` through the user's existing Codex OAuth session,
saves the resulting PNG, and displays it inline when iTerm2 supports doing so.

## Decision rules

1. Generate an image when creation of a photo, illustration, icon, sprite,
   texture, product image, banner, concept art, or similar raster asset is an
   explicit part of the user's request.
2. Do not generate an image merely because one might decorate an otherwise
   unrelated answer.
3. Prefer ordinary code tools for diagrams that should remain editable as
   source, such as Mermaid, SVG, charts, or HTML/CSS layouts.
4. Before calling the tool, turn the user's request into a complete standalone
   visual prompt. Include subject, composition, style, lighting, colors,
   perspective, mood, and important exclusions when those details are known.
5. Do not claim that generation succeeded until the tool returns `success: true`.
6. Report the saved path after success. The image may already be visible inline,
   so do not redundantly embed it unless the user asks.
7. If authentication is missing, tell the user to run `/codex-auth`.

## Tool

Call:

```text
codex_imagegen(prompt="A complete standalone image prompt")
```

The result contains:

- `success`: whether generation completed
- `path`: saved PNG path on success
- `displayed_inline`: whether iTerm2 inline display was attempted successfully
- `error`: safe failure text when generation fails
