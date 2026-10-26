"""Turning PDF pages into images for the AI to read.

Kerala PSC's Malayalam papers carry a hidden text layer in a legacy (non-Unicode) font.
Given the PDF itself, a model partly reads that gibberish layer and slips letters from
other scripts into Malayalam words; given a picture of the page it reads what is printed.
"""

import io

import pypdfium2 as pdfium

PDF = "application/pdf"
RENDER_SCALE = 2  # ~144 dpi: small print stays legible, a page is ~300 KB as PNG


def pdf_to_images(pdf: bytes) -> list[tuple[bytes, str]]:
    doc = pdfium.PdfDocument(pdf)
    try:
        images = []
        for page in doc:
            buf = io.BytesIO()
            page.render(scale=RENDER_SCALE).to_pil().save(buf, format="PNG", optimize=True)
            images.append((buf.getvalue(), "image/png"))
        return images
    finally:
        doc.close()


def as_page_images(files: list[tuple[bytes, str]]) -> list[tuple[bytes, str]]:
    """PDFs become one image per page; photos pass through unchanged."""
    pages: list[tuple[bytes, str]] = []
    for data, media_type in files:
        pages.extend(pdf_to_images(data) if media_type == PDF else [(data, media_type)])
    return pages
