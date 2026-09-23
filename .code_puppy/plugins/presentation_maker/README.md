# Presentation Maker plugin

This project plugin adds a `presentation-maker` agent to Code Puppy. The agent
creates editable Microsoft PowerPoint `.pptx` files, opens them in Microsoft
PowerPoint, exports every slide as a PNG, and inspects those previews before
delivery.

LibreOffice is not used. Rendering requires Microsoft PowerPoint on macOS or
Windows.

## Requirements

- Code Puppy running from this repository
- Node.js 18 or newer
- Microsoft PowerPoint for macOS or Windows
- Permission for the terminal to automate Microsoft PowerPoint

## Install the renderer dependency

From the repository root, install the pinned renderer packages into the
plugin's hidden runtime directory:

```bash
npm install \
  --prefix .code_puppy/plugins/presentation_maker/.state/node \
  --no-save \
  'pptxgenjs@3.12.0' \
  'pdfjs-dist@3.11.174' \
  '@napi-rs/canvas@0.1.68'
```

The `.state` directory is excluded from both git and Code Puppy's project
plugin trust hash. Installing or updating runtime packages there does not make
the plugin appear modified.

You can place the runtime elsewhere by setting:

```bash
export CODE_PUPPY_PRESENTATION_RUNTIME=/absolute/path/to/runtime
```

That directory must contain `node_modules/pptxgenjs`, `node_modules/pdfjs-dist`,
and `node_modules/@napi-rs/canvas`.

## Trust and load the plugin

Start Code Puppy in this repository and run:

```text
/plugins
```

Select `presentation_maker`, press Enter, and type `trust`. Project plugins are
disabled until this trust step succeeds. Code Puppy hot-loads the plugin, so a
restart is not required.

Switch to the agent:

```text
/agent presentation-maker
```

Then make a request such as:

```text
Create a 7-slide Microsoft PowerPoint for engineering leadership about our
Q4 platform migration. Use the material in docs/migration-plan.md and save it
as output/q4-platform-migration.pptx.
```

The agent will build the `.pptx`, open it in Microsoft PowerPoint, export slide
previews, inspect them, and revise the deck when needed.

## Supported content

The builder creates native PowerPoint text, images, tables, charts, shapes, and
lines. These objects remain editable in Microsoft PowerPoint. Image paths and
output paths must stay inside the active project directory.

The default output format is widescreen 16:9. The deck specification can use
`LAYOUT_STANDARD` for 4:3 presentations.

## Microsoft PowerPoint automation

On macOS, `render_presentation` uses JavaScript for Automation to open the deck
in Microsoft PowerPoint and export a PDF into Office's private temporary
directory. The plugin's isolated Node runtime then converts each
PowerPoint-rendered page to PNG. The first run may trigger a macOS Automation
permission prompt for the terminal application.

On Windows, the tool uses PowerShell and the Microsoft PowerPoint COM API.

Rendering returns an error on other operating systems because Microsoft
PowerPoint desktop automation is unavailable there. PPTX generation still
works anywhere Node.js and PptxGenJS are available.

## Troubleshooting

If `build_presentation` reports that the renderer dependency is missing, rerun
the npm installation command above.

If macOS blocks rendering, open **System Settings → Privacy & Security →
Automation** and allow your terminal to control Microsoft PowerPoint.

If PowerPoint exports no preview images, open the generated `.pptx` manually
once and confirm that PowerPoint is activated and licensed.

If the plugin appears as changed after editing its source, trust it again from
`/plugins`. Runtime files under `.state` do not affect trust.
