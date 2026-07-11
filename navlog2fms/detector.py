import fitz  # pymupdf
import pytesseract
from PIL import Image

import pdfplumber

from navlog2fms.models import CommonRoute
import navlog2fms.parsers as parser_registry


def _extract_text_pdfplumber(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        return page.extract_text() or ""


def _ocr_page(pdf_path: str, page_num: int = 0, scale: float = 2.0) -> str:
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img, config="--psm 6")


def load_and_detect(pdf_path: str) -> CommonRoute:
    """Detect navlog format and parse it, returning a CommonRoute.

    Tries native text extraction first; falls back to OCR for image-based PDFs.
    """
    text = _extract_text_pdfplumber(pdf_path)
    if not text.strip():
        text = _ocr_page(pdf_path)

    return parser_registry.detect_and_parse(pdf_path, text)
