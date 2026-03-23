"""Unified file handling: text extraction, OCR, and VLM preparation.

Three modes:
- extract_text(path) -> str: PDF (pdfplumber/PyPDF2), image (pytesseract OCR), text/CSV
- prepare_for_vlm(path) -> str: fetch URL or read local file, base64 encode as data URL
- process(path) -> ProcessedFile: both text AND VLM-ready data URL when applicable

Also handles base64 file decoding and batch processing for HTTP upload workflows.
"""

import base64
import io
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class ProcessedFile:
    """Result of processing a file through FileProcessor."""

    text: str = ""
    data_url: Optional[str] = None
    mime_type: str = ""
    pages: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class FileProcessor:
    """Process and extract data from files (PDFs, images, text/CSV).

    Supports three usage patterns:
    - extract_text(): get plain text from any supported file type
    - prepare_for_vlm(): get a data URL for sending images to vision LLMs
    - process(): get both text and data URL in a single call

    Also provides static utility methods for base64 decoding, file saving,
    and batch processing of uploaded attachments.
    """

    # ========================================================================
    # High-level API
    # ========================================================================

    @staticmethod
    def extract_text(file_path: Union[str, Path]) -> str:
        """Extract plain text from a file.

        Supports PDF (pdfplumber primary, PyPDF2 fallback), images (pytesseract OCR),
        and text/CSV files (direct read).

        Args:
            file_path: Path to the file

        Returns:
            Extracted text content
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        mime_type = FileProcessor._guess_mime_type(file_path)

        if mime_type == "application/pdf":
            result = FileProcessor._extract_pdf(str(file_path))
            return result.get("full_text", "")

        elif mime_type.startswith("image/"):
            result = FileProcessor._extract_image(str(file_path), mime_type)
            return result.get("text", "")

        elif mime_type in ("text/plain", "text/csv"):
            return file_path.read_text(encoding="utf-8", errors="ignore")

        else:
            logger.warning(f"Unsupported file type for text extraction: {mime_type}")
            return ""

    @staticmethod
    async def prepare_for_vlm(image_source: Union[str, Path]) -> Optional[str]:
        """Prepare an image as a data URL for vision language models.

        Handles three input types:
        - data: URL (passed through)
        - http/https URL (fetched and base64 encoded)
        - Local file path (read and base64 encoded)

        Args:
            image_source: Path, URL, or data URL of the image

        Returns:
            data URL string (e.g., "data:image/png;base64,...") or None
        """
        if not image_source:
            return None

        image_source = str(image_source)

        # Already a data URL
        if image_source.startswith("data:image/"):
            return image_source

        # HTTP/HTTPS URL
        if image_source.startswith("http://") or image_source.startswith("https://"):
            logger.info(f"Fetching image from URL: {image_source}")
            try:
                import httpx

                async with httpx.AsyncClient() as http_client:
                    response = await http_client.get(image_source)
                    response.raise_for_status()
                    image_bytes = response.content

                    content_type = response.headers.get("content-type", "")
                    img_format = FileProcessor._detect_image_format(
                        content_type, image_source
                    )

                    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
                    data_url = f"data:image/{img_format};base64,{encoded_image}"
                    logger.info("Fetched and encoded image from URL")
                    return data_url
            except Exception as e:
                logger.error(f"Failed to fetch image: {e}")
                raise

        # Local file path
        try:
            image_path = Path(image_source)
            if not image_path.exists():
                raise FileNotFoundError(f"Image file not found: {image_source}")

            with open(image_path, "rb") as f:
                encoded_image = base64.b64encode(f.read()).decode("utf-8")

            img_format = image_path.suffix.lstrip(".") or "png"
            if img_format == "jpg":
                img_format = "jpeg"

            data_url = f"data:image/{img_format};base64,{encoded_image}"
            logger.info("Encoded local image to base64")
            return data_url
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            raise

    @staticmethod
    def process(file_path: Union[str, Path]) -> ProcessedFile:
        """Process a file and return both text and VLM-ready data URL.

        For PDFs: extracts text with page info, no data URL.
        For images: extracts OCR text AND prepares data URL.
        For text/CSV: reads content, no data URL.

        Args:
            file_path: Path to the file

        Returns:
            ProcessedFile with text, optional data_url, mime_type, and pages
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return ProcessedFile(error=f"File not found: {file_path}")

        mime_type = FileProcessor._guess_mime_type(file_path)
        result = ProcessedFile(mime_type=mime_type)

        try:
            if mime_type == "application/pdf":
                pdf_data = FileProcessor._extract_pdf(str(file_path))
                result.text = pdf_data.get("full_text", "")
                result.pages = pdf_data.get("pages", [])

            elif mime_type.startswith("image/"):
                img_data = FileProcessor._extract_image(str(file_path), mime_type)
                result.text = img_data.get("text", "")

                # Also prepare for VLM
                try:
                    with open(file_path, "rb") as f:
                        encoded = base64.b64encode(f.read()).decode("utf-8")
                    img_format = file_path.suffix.lstrip(".") or "png"
                    if img_format == "jpg":
                        img_format = "jpeg"
                    result.data_url = f"data:image/{img_format};base64,{encoded}"
                except Exception as e:
                    logger.warning(f"Could not prepare image for VLM: {e}")

            elif mime_type in ("text/plain", "text/csv"):
                result.text = file_path.read_text(encoding="utf-8", errors="ignore")

            else:
                result.error = f"Unsupported file type: {mime_type}"
                logger.warning(result.error)

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error processing {file_path}: {e}")

        return result

    # ========================================================================
    # Attachment handling (base64 upload workflows)
    # ========================================================================

    @staticmethod
    def decode_base64_file(content_base64: str) -> bytes:
        """Decode a base64-encoded file.

        Args:
            content_base64: Base64-encoded file content

        Returns:
            Decoded file bytes
        """
        try:
            return base64.b64decode(content_base64)
        except Exception as e:
            logger.error(f"Error decoding base64: {e}")
            raise ValueError(f"Invalid base64 content: {e}") from e

    @staticmethod
    def save_file(filename: str, file_bytes: bytes, temp_dir: str = "/tmp") -> str:
        """Save a file to disk.

        Args:
            filename: Original filename
            file_bytes: File content as bytes
            temp_dir: Directory to save file to

        Returns:
            Path to saved file
        """
        try:
            Path(temp_dir).mkdir(parents=True, exist_ok=True)
            file_path = Path(temp_dir) / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(file_bytes)
            logger.debug(f"Saved file: {file_path}")
            return str(file_path)
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            raise

    @staticmethod
    def process_attachment(
        filename: str, content_base64: str, mime_type: str
    ) -> Dict[str, Any]:
        """Process a single base64-encoded attached file.

        Args:
            filename: Original filename
            content_base64: Base64-encoded content
            mime_type: MIME type of the file

        Returns:
            Dictionary with file metadata and extracted data
        """
        try:
            logger.info(f"Processing file: {filename} ({mime_type})")
            file_bytes = FileProcessor.decode_base64_file(content_base64)
            file_size = len(file_bytes)
            logger.debug(f"File size: {file_size} bytes")

            file_path = FileProcessor.save_file(filename, file_bytes)
            extracted_data = FileProcessor._extract_content(
                file_path, filename, mime_type, file_bytes
            )

            return {
                "success": True,
                "filename": filename,
                "mime_type": mime_type,
                "size": file_size,
                "path": file_path,
                "extracted_data": extracted_data,
            }
        except Exception as e:
            logger.error(f"Error processing attachment {filename}: {e}")
            return {"success": False, "filename": filename, "error": str(e)}

    @staticmethod
    def process_files(files: List[Dict[str, str]]) -> Dict[str, Any]:
        """Process all attached files from an upload.

        Args:
            files: List of file dicts with filename, content_base64, mime_type

        Returns:
            Dictionary with processing results
        """
        logger.info(f"Processing {len(files)} files...")

        results = {
            "success": True,
            "total_files": len(files),
            "processed_files": [],
            "failed_files": [],
            "extracted_data": {},
        }

        for file_data in files:
            try:
                filename = file_data.get("filename")
                content_base64 = file_data.get("content_base64")
                mime_type = file_data.get("mime_type", "application/octet-stream")

                if not filename or not content_base64:
                    logger.warning("File missing filename or content")
                    results["failed_files"].append(
                        {
                            "filename": filename or "unknown",
                            "error": "Missing filename or content",
                        }
                    )
                    continue

                result = FileProcessor.process_attachment(
                    filename, content_base64, mime_type
                )

                if result.get("success"):
                    results["processed_files"].append(result)
                    results["extracted_data"][filename] = result.get(
                        "extracted_data", {}
                    )
                else:
                    results["failed_files"].append(result)
                    results["success"] = False
            except Exception as e:
                logger.error(f"Error processing file: {e}")
                results["failed_files"].append(
                    {"filename": file_data.get("filename", "unknown"), "error": str(e)}
                )
                results["success"] = False

        logger.info(
            f"File processing complete: "
            f"{len(results['processed_files'])} successful, "
            f"{len(results['failed_files'])} failed"
        )
        return results

    # ========================================================================
    # Private extraction methods
    # ========================================================================

    @staticmethod
    def _extract_content(
        file_path: str, filename: str, mime_type: str, file_bytes: bytes
    ) -> Dict[str, Any]:
        """Extract content from a file based on its type."""
        try:
            if mime_type == "application/pdf":
                return FileProcessor._extract_pdf(file_path)
            elif mime_type.startswith("image/"):
                return FileProcessor._extract_image(file_path, mime_type)
            elif mime_type in ["text/plain", "text/csv"]:
                return {
                    "type": "text",
                    "content": file_bytes.decode("utf-8", errors="ignore"),
                }
            else:
                logger.warning(f"Unknown mime type: {mime_type}")
                return {
                    "type": "unknown",
                    "message": f"File type {mime_type} not yet supported for extraction",
                }
        except Exception as e:
            logger.error(f"Error extracting content from {filename}: {e}")
            return {"type": "error", "error": str(e)}

    @staticmethod
    def _extract_pdf(file_path: str) -> Dict[str, Any]:
        """Extract text from a PDF file using pdfplumber (primary) or PyPDF2 (fallback)."""
        try:
            try:
                import pdfplumber

                with pdfplumber.open(file_path) as pdf:
                    pages_data = []
                    full_text = []

                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text()
                        full_text.append(text)
                        tables = page.extract_tables()
                        pages_data.append(
                            {
                                "page_number": i + 1,
                                "text": text,
                                "has_tables": len(tables) > 0 if tables else False,
                                "table_count": len(tables) if tables else 0,
                            }
                        )

                    return {
                        "type": "pdf",
                        "page_count": len(pdf.pages),
                        "full_text": "\n\n---PAGE BREAK---\n\n".join(full_text),
                        "pages": pages_data,
                        "message": "PDF text extracted. Use full_text for LLM processing.",
                    }
            except ImportError:
                logger.warning("pdfplumber not installed, attempting fallback...")

                try:
                    from PyPDF2 import PdfReader

                    reader = PdfReader(file_path)
                    pages_data = []
                    full_text = []

                    for i, page in enumerate(reader.pages):
                        text = page.extract_text()
                        full_text.append(text)
                        pages_data.append({"page_number": i + 1, "text": text})

                    return {
                        "type": "pdf",
                        "page_count": len(reader.pages),
                        "full_text": "\n\n---PAGE BREAK---\n\n".join(full_text),
                        "pages": pages_data,
                        "message": "PDF text extracted (PyPDF2). Some formatting may be lost.",
                    }
                except ImportError:
                    logger.warning("No PDF library available")
                    return {
                        "type": "pdf",
                        "error": "PDF extraction requires pdfplumber or PyPDF2",
                        "message": "Please install: pip install pdfplumber",
                    }
        except Exception as e:
            logger.error(f"Error extracting PDF: {e}")
            return {"type": "pdf", "error": str(e)}

    @staticmethod
    def _extract_image(file_path: str, mime_type: str) -> Dict[str, Any]:
        """Extract text from an image using OCR (pytesseract)."""
        try:
            try:
                import pytesseract
                from PIL import Image

                image = Image.open(file_path)
                text = pytesseract.image_to_string(image)

                return {
                    "type": "image",
                    "mime_type": mime_type,
                    "text": text,
                    "size": f"{image.width}x{image.height}",
                    "message": "OCR text extracted. Accuracy depends on image quality.",
                }
            except ImportError:
                logger.warning("pytesseract not installed")
                return {
                    "type": "image",
                    "error": "OCR requires pytesseract",
                    "message": "Please install: pip install pytesseract pillow",
                }
        except Exception as e:
            logger.error(f"Error extracting image: {e}")
            return {"type": "image", "error": str(e)}

    # ========================================================================
    # Utilities
    # ========================================================================

    @staticmethod
    def _guess_mime_type(file_path: Path) -> str:
        """Guess MIME type from file extension."""
        suffix = file_path.suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".txt": "text/plain",
            ".csv": "text/csv",
            ".log": "text/plain",
            ".md": "text/plain",
        }
        return mime_map.get(suffix, "application/octet-stream")

    @staticmethod
    def _detect_image_format(content_type: str, url: str) -> str:
        """Detect image format from content-type header or URL."""
        if "png" in content_type or url.endswith(".png"):
            return "png"
        elif (
            "jpeg" in content_type
            or "jpg" in content_type
            or url.endswith((".jpg", ".jpeg"))
        ):
            return "jpeg"
        elif "gif" in content_type or url.endswith(".gif"):
            return "gif"
        elif "webp" in content_type or url.endswith(".webp"):
            return "webp"
        return "png"  # default
