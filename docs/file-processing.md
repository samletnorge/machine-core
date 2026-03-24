# File Processing

`FileProcessor` provides unified file handling for text extraction, OCR, and VLM (Vision Language Model) preparation. It handles PDFs, images, and text files through a consistent interface.

## Quick Start

```python
from machine_core import FileProcessor

# Extract text from any supported file
text = FileProcessor.extract_text("/path/to/document.pdf")
print(text)

# Prepare an image for a vision LLM
data_url = await FileProcessor.prepare_for_vlm("/path/to/photo.jpg")
# "data:image/jpeg;base64,/9j/4AAQ..."

# Get both text and VLM data
result = FileProcessor.process("/path/to/receipt.png")
print(result.text)       # OCR text
print(result.data_url)   # base64 data URL
print(result.mime_type)   # "image/png"
```

## ProcessedFile

Return type of `FileProcessor.process()`:

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | Extracted text (empty string if extraction failed) |
| `data_url` | `str \| None` | Base64 data URL for VLM (`data:image/...;base64,...`) |
| `mime_type` | `str` | Detected MIME type |
| `pages` | `list[dict]` | Page-level data for PDFs |
| `error` | `str \| None` | Error message if processing failed |

## Text Extraction

### PDF Files

```python
text = FileProcessor.extract_text("invoice.pdf")
```

Uses **pdfplumber** as the primary extractor (with table detection), falling back to **PyPDF2** if pdfplumber fails. For multi-page PDFs, pages are separated by `---PAGE BREAK---`.

The internal `_extract_pdf()` method returns structured data:

```python
{
    "full_text": "Page 1 content\n---PAGE BREAK---\nPage 2 content",
    "pages": [
        {"page_num": 1, "text": "Page 1 content", "tables": [...]},
        {"page_num": 2, "text": "Page 2 content", "tables": []},
    ]
}
```

### Images (OCR)

```python
text = FileProcessor.extract_text("receipt.png")
```

Uses **pytesseract** for OCR. Requires Tesseract to be installed on the system:

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract
```

### Text Files

```python
text = FileProcessor.extract_text("data.csv")
```

Directly reads `.txt`, `.csv`, `.log`, `.md` files as UTF-8 text.

### Supported Formats

| Extension | MIME Type | Method |
|-----------|----------|--------|
| `.pdf` | `application/pdf` | pdfplumber + PyPDF2 fallback |
| `.png` | `image/png` | pytesseract OCR |
| `.jpg`, `.jpeg` | `image/jpeg` | pytesseract OCR |
| `.gif` | `image/gif` | pytesseract OCR |
| `.webp` | `image/webp` | pytesseract OCR |
| `.bmp` | `image/bmp` | pytesseract OCR |
| `.tiff`, `.tif` | `image/tiff` | pytesseract OCR |
| `.txt` | `text/plain` | Direct read |
| `.csv` | `text/csv` | Direct read |
| `.log` | `text/plain` | Direct read |
| `.md` | `text/markdown` | Direct read |

## VLM Preparation

`prepare_for_vlm()` converts any image source into a base64 data URL suitable for pydantic-ai's `ImageUrl` type.

```python
# Local file
url = await FileProcessor.prepare_for_vlm("/path/to/image.jpg")
# "data:image/jpeg;base64,/9j/4AAQ..."

# HTTP URL (fetches and converts)
url = await FileProcessor.prepare_for_vlm("https://example.com/photo.png")
# "data:image/png;base64,iVBOR..."

# Data URL (passthrough)
url = await FileProcessor.prepare_for_vlm("data:image/png;base64,iVBOR...")
# "data:image/png;base64,iVBOR..."  (returned as-is)
```

This is what `BaseAgent._process_image()` calls internally when you pass `image_paths` to `run_query()`.

## Batch File Processing

For processing multiple uploaded files (e.g., from an HTTP API):

```python
# Single file (base64-encoded)
result = FileProcessor.process_attachment(
    filename="invoice.pdf",
    content_base64="JVBERi0xLjQK...",
    mime_type="application/pdf",
)
# {"content": "extracted text...", "file_path": "/tmp/invoice.pdf"}

# Multiple files
files = [
    {"name": "invoice.pdf", "content": "JVBERi0xLjQK...", "mime_type": "application/pdf"},
    {"name": "receipt.png", "content": "iVBORw0K...", "mime_type": "image/png"},
]
results = FileProcessor.process_files(files)
# {"invoice.pdf": {"content": "...", "file_path": "..."}, "receipt.png": {...}}
```

### process_attachment(filename, content_base64, mime_type)

| Parameter | Type | Description |
|-----------|------|-------------|
| `filename` | `str` | Original filename |
| `content_base64` | `str` | Base64-encoded file content |
| `mime_type` | `str` | MIME type of the file |

Decodes the base64 content, saves to a temp file, extracts text, and returns `{"content": str, "file_path": str}`.

### process_files(files)

| Parameter | Type | Description |
|-----------|------|-------------|
| `files` | `list[dict]` | List of `{"name", "content", "mime_type"}` dicts |

Returns `dict[filename, {"content", "file_path"}]`.

## Integration with BaseAgent

`BaseAgent._process_image()` delegates to `FileProcessor.prepare_for_vlm()`. When you call:

```python
result = await agent.run_query("What's in this image?", image_paths=["/path/to/img.jpg"])
```

Internally:
1. Each path in `image_paths` is passed to `FileProcessor.prepare_for_vlm()`.
2. The resulting data URLs are wrapped in `ImageUrl` objects.
3. These are included in the message content sent to the LLM.

## Real-World Example: ai-accounting-agent

The HTTP server processes file attachments before sending them to the agent:

```python
from machine_core import FileProcessor

@app.post("/solve")
async def solve(request: SolveRequest):
    # Process uploaded files
    file_contents = {}
    if request.files:
        file_contents = FileProcessor.process_files(request.files)

    # Include file text in the prompt
    file_context = ""
    for fname, data in file_contents.items():
        file_context += f"\n--- {fname} ---\n{data['content']}\n"

    prompt = f"{request.prompt}\n\nAttached files:{file_context}"
    response = await coordinator.handle(prompt)
    return {"answer": response}
```

## Utility Functions

### decode_base64_file(content_base64) -> bytes

Decodes a base64 string to bytes. Handles both standard and URL-safe base64.

### save_file(filename, file_bytes, temp_dir="/tmp") -> str

Saves bytes to a temporary file and returns the file path.
