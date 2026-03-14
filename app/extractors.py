"""Material conversion and text extraction: MarkItDown, DOCX headers,
antiword (.doc), Tesseract OCR (scanned PDFs)."""
import os
import shutil
import subprocess
import tempfile
import zipfile
import logging
from typing import Optional
import defusedxml.ElementTree as ET
from markitdown import MarkItDown

from app.text_processors import (
    _fix_cid_characters,
    _is_reversed_hebrew,
    _fix_reversed_hebrew,
)

logger = logging.getLogger("case-dms.extractors")

# File type classification
_FILE_TYPE_MAP = {
    '.pdf': 'pdf',
    '.doc': 'other', '.docx': 'other', '.pptx': 'other', '.html': 'other', '.htm': 'other', '.txt': 'other',
    '.jpg': 'image', '.jpeg': 'image', '.png': 'image', '.tiff': 'image', '.tif': 'image',
    '.bmp': 'image', '.webp': 'image', '.gif': 'image',
    '.mp3': 'audio', '.wav': 'audio', '.m4a': 'audio', '.ogg': 'audio', '.flac': 'audio', '.aac': 'audio',
    '.mp4': 'video', '.avi': 'video', '.mov': 'video', '.mkv': 'video', '.webm': 'video', '.wmv': 'video',
    '.csv': 'table', '.xlsx': 'table', '.xls': 'table', '.tsv': 'table',
}


def classify_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return _FILE_TYPE_MAP.get(ext, 'other')


def _get_md_converter() -> MarkItDown:
    return MarkItDown(enable_plugins=False)


# --- DOCX header extraction ---
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _extract_text_from_xml(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""
    texts = []
    for wt in root.iter(f"{{{_W_NS}}}t"):
        t = wt.text
        if t:
            texts.append(t)
    return " ".join(texts)


def extract_docx_headers(file_path: str) -> str:
    if not file_path.lower().endswith((".docx", ".doc")):
        return ""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            header_texts = []
            header_files = sorted(
                name for name in zf.namelist()
                if name.startswith("word/header") and name.endswith(".xml")
            )
            if not header_files:
                return ""
            for hf in header_files:
                xml_bytes = zf.read(hf)
                text = _extract_text_from_xml(xml_bytes)
                if text.strip():
                    header_texts.append(text.strip())
            return "\n".join(header_texts)
    except zipfile.BadZipFile:
        return ""
    except Exception as e:
        logger.error("Failed to extract DOCX headers: %s", e)
        return ""


# --- Tesseract/Poppler path detection ---
_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
_POPPLER_PATHS = [
    r"C:\poppler\poppler-25.12.0\Library\bin",
    r"C:\poppler\Library\bin",
    r"C:\poppler\bin",
    r"C:\Program Files\poppler\Library\bin",
]
_LOCAL_TESSDATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tessdata")


def _find_tesseract() -> Optional[str]:
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, timeout=5)
        return "tesseract"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    for path in _TESSERACT_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _find_poppler_bin() -> Optional[str]:
    try:
        subprocess.run(["pdftoppm", "-v"], capture_output=True, timeout=5)
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    for path in _POPPLER_PATHS:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "pdftoppm.exe")):
            return path
    return None


def _extract_pdf_via_ocr(file_path: str) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        logger.info("OCR dependencies not installed — skipping OCR")
        return ""

    tesseract_cmd = _find_tesseract()
    if not tesseract_cmd:
        logger.warning("Tesseract OCR not found")
        return ""
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    poppler_bin = _find_poppler_bin()

    if os.path.isdir(_LOCAL_TESSDATA) and os.path.isfile(os.path.join(_LOCAL_TESSDATA, "heb.traineddata")):
        os.environ["TESSDATA_PREFIX"] = _LOCAL_TESSDATA

    MAX_OCR_PAGES = 30
    OCR_DPI = 150

    try:
        try:
            from pypdf import PdfReader
            total_pages = len(PdfReader(file_path).pages)
        except Exception:
            total_pages = 999

        pages_to_process = min(total_pages, MAX_OCR_PAGES)
        base_kwargs = {"dpi": OCR_DPI}
        if poppler_bin:
            base_kwargs["poppler_path"] = poppler_bin

        all_text = []
        for page_num in range(1, pages_to_process + 1):
            try:
                images = convert_from_path(file_path, first_page=page_num, last_page=page_num, **base_kwargs)
                if images:
                    page_text = pytesseract.image_to_string(images[0], lang="heb+eng")
                    del images
                    if page_text.strip():
                        all_text.append(page_text.strip())
                else:
                    del images
            except Exception:
                continue

        return "\n\n".join(all_text)
    except Exception as e:
        logger.error("OCR extraction failed for %s: %s", file_path, e)
        return ""


def _extract_image_via_vision(file_path: str) -> str:
    """Extract description and text from image via LLM vision API (Gemini)."""
    try:
        from app.config import settings
        if not settings.GOOGLE_API_KEY:
            return ""
        from app.llm_service import describe_image
        logger.info("Vision API: describing image %s", os.path.basename(file_path))
        return describe_image(file_path, provider="gemini")
    except Exception as e:
        logger.warning("Vision API failed for %s: %s", os.path.basename(file_path), e)
        return ""


def _extract_image_text(file_path: str) -> str:
    """Extract text from image via OCR."""
    try:
        import pytesseract
    except ImportError:
        return ""

    tesseract_cmd = _find_tesseract()
    if not tesseract_cmd:
        return ""
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    if os.path.isdir(_LOCAL_TESSDATA) and os.path.isfile(os.path.join(_LOCAL_TESSDATA, "heb.traineddata")):
        os.environ["TESSDATA_PREFIX"] = _LOCAL_TESSDATA

    try:
        from PIL import Image
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang="heb+eng")
        del img
        return text
    except Exception as e:
        logger.error("Image OCR failed for %s: %s", file_path, e)
        return ""


def _extract_table_text(file_path: str) -> str:
    """Convert CSV/TSV to markdown table."""
    import csv

    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.xlsx':
        try:
            converter = _get_md_converter()
            result = converter.convert(file_path)
            return result.text_content or ""
        except Exception:
            return ""

    delimiter = '\t' if ext == '.tsv' else ','
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f, delimiter=delimiter)
            rows = []
            for i, row in enumerate(reader):
                if i >= 500:
                    rows.append(["... (truncated)"])
                    break
                rows.append(row)

        if not rows:
            return ""

        # Build markdown table
        header = rows[0]
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for row in rows[1:]:
            # Pad/truncate to match header length
            padded = row[:len(header)] + [""] * max(0, len(header) - len(row))
            lines.append("| " + " | ".join(padded) + " |")
        return "\n".join(lines)
    except Exception as e:
        logger.error("Table extraction failed for %s: %s", file_path, e)
        return ""


def convert_to_markdown(file_path: str) -> str:
    """Convert any supported file to Markdown text."""
    ext = os.path.splitext(file_path)[1].lower()
    file_type = _FILE_TYPE_MAP.get(ext, 'other')
    logger.info("Converting to Markdown: %s (ext=%s, type=%s)", file_path, ext, file_type)

    text = ""

    # Handle by file type
    if file_type == 'image':
        # Try LLM vision first (Gemini), fallback to OCR
        vision_text = _extract_image_via_vision(file_path)
        if vision_text and vision_text.strip():
            # Also try OCR and merge if available
            ocr_text = _extract_image_text(file_path)
            if ocr_text and ocr_text.strip() and ocr_text.strip() not in vision_text:
                text = f"{vision_text}\n\n**OCR טקסט נוסף:**\n{ocr_text}"
            else:
                text = vision_text
        else:
            text = _extract_image_text(file_path)
        if not text.strip():
            text = f"[Image file: {os.path.basename(file_path)}]"
        return text

    if file_type == 'audio':
        # Audio transcription will be handled by transcription.py in Phase 2
        return f"[Audio file: {os.path.basename(file_path)} — transcription pending]"

    if file_type == 'video':
        # Video transcription will be handled in Phase 2
        return f"[Video file: {os.path.basename(file_path)} — transcription pending]"

    if file_type == 'table' and ext != '.xlsx':
        text = _extract_table_text(file_path)
        if text.strip():
            return text

    # Primary extraction via MarkItDown (PDF, DOCX, PPTX, XLSX, HTML, etc.)
    try:
        converter = _get_md_converter()
        result = converter.convert(file_path)
        text = result.text_content or ""
        del converter, result
    except Exception as e:
        err_name = type(e).__name__
        if "UnsupportedFormat" in err_name:
            logger.info("MarkItDown does not support this format: %s", file_path)
        else:
            logger.error("MarkItDown conversion failed: %s", e)

    # Fallback: scanned PDFs via OCR
    if not text.strip() and ext == ".pdf":
        logger.info("PDF text is empty — attempting OCR fallback: %s", file_path)
        text = _extract_pdf_via_ocr(file_path)

    # Post-processing
    if text and 'cid:' in text:
        text = _fix_cid_characters(text)

    if text and _is_reversed_hebrew(text):
        text = _fix_reversed_hebrew(text)

    # DOCX header enrichment
    header_text = extract_docx_headers(file_path)
    if header_text:
        text = f"[\u05db\u05d5\u05ea\u05e8\u05ea \u05d4\u05de\u05e1\u05de\u05da / Document Header]\n{header_text}\n\n{text}"

    return text
