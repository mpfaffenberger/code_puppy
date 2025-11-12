# PDF Support in Code Puppy

Code Puppy now supports PDF document ingestion! You can drag and drop PDF files directly into the terminal, just like you do with images.

## How It Works

When you drop a PDF file into Code Puppy's terminal, the system will:

1. **Automatically detect** the PDF file extension (`.pdf`)
2. **Parse the PDF** to extract text content from all pages
3. **Extract metadata** like title, author, and subject
4. **Format the content** in a structured way for the AI
5. **Include it in your prompt** automatically

## Usage Examples

### Basic PDF Analysis

```bash
>>> Summarize /path/to/document.pdf
```

The PDF content will be automatically extracted and included in your prompt to the AI.

### Multiple PDFs

```bash
>>> Compare /path/to/doc1.pdf and /path/to/doc2.pdf
```

### PDFs with Spaces in Names

The terminal escape sequences are handled automatically:

```bash
>>> Analyze /path/to/my\ document\ with\ spaces.pdf
```

### Mixed Attachments

You can even mix PDFs with images:

```bash
>>> Compare the chart in image.png with the data in report.pdf
```

## What Gets Extracted

For each PDF, Code Puppy extracts:

- **File name** - The name of the PDF document
- **Page count** - Total number of pages
- **Metadata** - Author, title, subject, and other document properties
- **Full text content** - All readable text from every page

The extracted content is formatted as structured markdown and appended to your prompt automatically.

## Technical Details

### Library Used

Code Puppy uses the `pypdf` library (version 5.1.0+), which is:
- Pure Python (no external dependencies)
- Lightweight and fast
- Well-maintained and reliable

### Supported PDF Features

- ✅ Text extraction from all pages
- ✅ Metadata extraction
- ✅ Multi-page documents
- ✅ Password-protected PDFs (with limitations)
- ✅ Scanned PDFs with embedded text layers

### Limitations

- OCR is not supported for image-only PDFs
- Complex layouts may have text ordering issues
- Some advanced PDF features (forms, annotations) are not extracted

## Error Handling

If a PDF cannot be parsed:
- A warning will be displayed
- The prompt will continue without the PDF content
- Other attachments will still be processed

## Example Session

```bash
🐶 code-puppy [code-puppy] [gpt-4] (~/Documents) >>> 

What are the key findings in research_paper.pdf

[dim]Attachments detected -> PDFs: 1[/dim]

AGENT RESPONSE: 
Based on the research paper, here are the key findings:
...
```

## Implementation

The PDF parsing functionality is implemented in:
- `code_puppy/tools/pdf_parser.py` - Core PDF parsing logic
- `code_puppy/command_line/attachments.py` - Integration with attachment system
- Tests in `tests/test_pdf_parser.py` and `tests/test_pdf_attachments.py`

## Future Enhancements

Potential future improvements:
- OCR support for scanned documents
- Image extraction from PDFs
- Table extraction and formatting
- Better handling of complex layouts
- PDF generation capabilities

