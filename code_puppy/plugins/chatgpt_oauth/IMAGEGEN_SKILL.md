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

## Reference images (visual consistency)

Pass `reference_images` to condition the result on images that already exist,
instead of generating from text alone. Use it whenever the output has to stay
visually consistent with something:

- **Same character across many images.** Conditioning on one canonical
  reference holds a face/outfit together far better than re-describing it in
  words. This is the reliable way to produce a set of portraits, expressions,
  or poses that are recognizably the same person.
- **Matching an established style,** palette, or lighting across a set of
  assets.
- **Iterating on an existing asset** — "same logo, dark background".

When references are supplied, write the `prompt` as the CHANGE you want; the
references supply the subject and style to preserve.

```text
codex_imagegen(
    prompt="Same man, same clothing and lighting, now glancing over his shoulder, anxious",
    reference_images=["portraits/sandoval/_ref.png"],
)
```

Guidance:

1. Prefer one strong reference over several weak ones; extra references dilute
   the conditioning.
2. Do not re-describe what the reference already shows unless you want it
   changed — describing the face again can fight the reference.
3. Paths must exist and be readable image files, else the call fails with a
   clear error.

## Tool

Call:

```text
codex_imagegen(prompt="A complete standalone image prompt")
codex_imagegen(prompt="The change you want", reference_images=["path/to/ref.png"])
```

The result contains:

- `success`: whether generation completed
- `path`: saved PNG path on success
- `displayed_inline`: whether iTerm2 inline display was attempted successfully
- `error`: safe failure text when generation fails
