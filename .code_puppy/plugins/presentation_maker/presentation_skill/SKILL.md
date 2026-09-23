---
name: presentation-design
description: Create, edit, render, and visually validate editable Microsoft PowerPoint presentations.
version: 0.1.0
tags:
  - powerpoint
  - pptx
  - slides
  - presentations
---

# Microsoft PowerPoint presentations

Use this skill for every request to create or edit a presentation.

## Required workflow

1. Establish the audience, purpose, requested slide count, source material,
   template, brand rules, and delivery path. Ask only for information that
   materially changes the deck.
2. Create a short outline. Give every slide one clear purpose and remove
   repeated points before building.
3. Build a structured deck specification and call `build_presentation`.
4. Call `render_presentation`. It opens the generated file in Microsoft
   PowerPoint and exports every slide as a PNG.
5. Inspect every PNG with `load_image_for_analysis`.
6. Correct clipping, overlap, weak hierarchy, distorted images, unreadable
   charts, inconsistent spacing, and unsupported conclusions. Rebuild and
   render again after corrections.
7. Return the final `.pptx` path.

Never claim that a deck was checked in PowerPoint unless
`render_presentation` succeeded.

## Slide specification

The `build_presentation` tool accepts a JSON object with this shape:

```json
{
  "title": "Deck title",
  "layout": "LAYOUT_WIDE",
  "theme": {
    "headingFont": "Aptos Display",
    "bodyFont": "Aptos",
    "primary": "17324D",
    "text": "202124",
    "background": "F7F5F0"
  },
  "slides": [
    {
      "title": "A direct slide title",
      "elements": [
        {
          "type": "text",
          "text": "Concise body copy",
          "x": 0.8,
          "y": 1.5,
          "w": 5.2,
          "h": 1.2,
          "fontSize": 22,
          "margin": 0
        }
      ],
      "notes": ["Source: supplied research, page 12"]
    }
  ]
}
```

Coordinates and sizes use inches. A wide slide is 13.333 by 7.5 inches. A
standard slide is 10 by 7.5 inches.

Supported native elements:

- `text`: requires `text`; all other fields become PptxGenJS text options.
- `image`: requires `path`, plus `x`, `y`, `w`, and `h`.
- `table`: requires `rows` and accepts `options`.
- `chart`: requires `chartType`, `data`, and accepts `options`.
- `shape`: requires `shape` and accepts `options`.
- `line`: accepts `options`.

Keep tables, charts, text, and simple diagrams native so users can edit them
in PowerPoint. Use image assets for photographs and illustrations.

## Writing and structure

- Write for the stated audience.
- Use direct language and concrete claims.
- Use a plain topic title for setup or explanatory slides.
- Use a takeaway title only when the slide contains evidence for it.
- Avoid generic slogans, filler subtitles, and repeated three-part lists.
- Prefer one strong composition over grids of small cards.
- Keep the title slide minimal.
- Keep body text at 17 points or larger unless a supplied template requires
  another size.
- Put external source references in the relevant slide's speaker notes.
- Do not invent facts, numbers, quotations, sources, or customer evidence.

## Visual quality

- Use consistent margins, alignment, type scale, and color.
- Preserve image proportions and choose crops that support the layout.
- Reduce content before shrinking text.
- Make charts readable from presentation distance.
- Check that every visible element stays within slide bounds.
- Treat PowerPoint rendering as the final compatibility check.

