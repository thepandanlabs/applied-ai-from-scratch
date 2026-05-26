"""
Lesson 10-02: Document AI and Structured Extraction Pipelines
Detects PDF type (born-digital vs scanned), routes to appropriate extraction path,
and returns validated structured data using Pydantic.

Usage:
    python main.py                  # demo mode (uses embedded contract text)
    python main.py contract.pdf     # process a real PDF file

Optional dependencies:
    pip install pymupdf pydantic    # for PDF parsing
    pip install pdfplumber pydantic # alternative PDF parser
"""

import anthropic
import base64
import json
import sys
from pathlib import Path
from typing import Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    raise SystemExit("Install pydantic: pip install pydantic")


# --------------------------------------------------------------------------- #
# Output schema                                                                #
# --------------------------------------------------------------------------- #

class ContractExtraction(BaseModel):
    party_a: Optional[str] = Field(None, description="First party name")
    party_b: Optional[str] = Field(None, description="Second party name")
    effective_date: Optional[str] = Field(None, description="Contract effective date")
    termination_clause: Optional[str] = Field(None, description="Summary of termination conditions")
    governing_law: Optional[str] = Field(None, description="Governing law jurisdiction")
    confidence: str = Field("low", description="high / medium / low")
    extraction_notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# PDF type detection                                                           #
# --------------------------------------------------------------------------- #

def is_born_digital(pdf_bytes: bytes, min_text_chars: int = 100) -> bool:
    """
    Returns True if the PDF has enough embedded text for text extraction.
    Falls back to a byte-level heuristic if no PDF library is available.
    """
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_text = ""
        for page in doc:
            total_text += page.get_text()
            if len(total_text) >= min_text_chars:
                doc.close()
                return True
        doc.close()
        return False
    except ImportError:
        pass

    try:
        import pdfplumber
        import io
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total = "".join((p.extract_text() or "") for p in pdf.pages)
            return len(total) >= min_text_chars
    except ImportError:
        pass

    # Heuristic: born-digital PDFs reference /Font objects
    return b"/Font" in pdf_bytes


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a born-digital PDF."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n\n--- PAGE BREAK ---\n\n".join(pages)
    except ImportError:
        pass

    try:
        import pdfplumber
        import io
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n\n--- PAGE BREAK ---\n\n".join(pages)
    except ImportError:
        pass

    raise RuntimeError(
        "No PDF library available. Install PyMuPDF: pip install pymupdf"
    )


def pdf_pages_to_images(pdf_bytes: bytes, dpi: int = 150) -> list[bytes]:
    """Convert PDF pages to PNG images (requires PyMuPDF)."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            images.append(pix.tobytes("png"))
        doc.close()
        return images
    except ImportError:
        raise RuntimeError("Install PyMuPDF: pip install pymupdf")


# --------------------------------------------------------------------------- #
# Extraction prompt                                                            #
# --------------------------------------------------------------------------- #

EXTRACTION_PROMPT = """Extract the following fields from this contract document.
Return valid JSON only, no markdown fences, no explanation.

JSON structure:
{
  "party_a": "First party name or null",
  "party_b": "Second party name or null",
  "effective_date": "Date string or null",
  "termination_clause": "Brief summary of termination conditions or null",
  "governing_law": "Jurisdiction or null",
  "confidence": "high or medium or low",
  "extraction_notes": ["any caveats"]
}

Confidence levels:
- high: all five main fields found clearly
- medium: 3-4 fields found, or one is ambiguous
- low: fewer than 3 fields found"""


# --------------------------------------------------------------------------- #
# Extraction functions                                                         #
# --------------------------------------------------------------------------- #

def extract_from_text(
    text: str, model: str = "claude-3-5-haiku-20241022"
) -> ContractExtraction:
    """Text extraction path for born-digital PDFs."""
    client = anthropic.Anthropic()

    # Truncate to stay within context limits
    if len(text) > 150_000:
        text = text[:150_000] + "\n\n[DOCUMENT TRUNCATED]"

    message = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[
            {"role": "user", "content": f"{EXTRACTION_PROMPT}\n\nDOCUMENT TEXT:\n{text}"}
        ],
    )
    raw = message.content[0].text.strip().lstrip("```json").rstrip("```").strip()
    return ContractExtraction(**json.loads(raw))


def extract_from_images(
    page_images: list[bytes],
    model: str = "claude-3-5-haiku-20241022",
    max_pages: int = 5,
) -> ContractExtraction:
    """Vision extraction path for scanned PDFs."""
    client = anthropic.Anthropic()

    content: list[dict] = []
    for i, img_bytes in enumerate(page_images[:max_pages]):
        b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
        content.append({
            "type": "text",
            "text": f"[Page {i + 1} of {len(page_images)}]",
        })

    content.append({"type": "text", "text": EXTRACTION_PROMPT})

    message = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": content}],
    )
    raw = message.content[0].text.strip().lstrip("```json").rstrip("```").strip()
    return ContractExtraction(**json.loads(raw))


# --------------------------------------------------------------------------- #
# Demo data                                                                    #
# --------------------------------------------------------------------------- #

DEMO_CONTRACT_TEXT = """
SERVICE AGREEMENT

This Service Agreement ("Agreement") is entered into as of January 15, 2025 ("Effective Date")
between Acme Corporation, a Delaware corporation ("Party A"), and BuildRight LLC,
a California limited liability company ("Party B").

1. SERVICES. Party B agrees to provide software development services as described in Exhibit A.

2. TERM AND TERMINATION. This Agreement commences on the Effective Date and continues for
twelve (12) months. Either party may terminate this Agreement upon thirty (30) days written notice.
Party A may terminate immediately for cause if Party B materially breaches this Agreement.

3. GOVERNING LAW. This Agreement shall be governed by the laws of the State of Delaware,
without regard to its conflict of law provisions.

4. PAYMENT. Party A shall pay Party B $15,000 per month within 30 days of invoice.

5. SIGNATURES. Executed as of the date first written above.
"""

# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main():
    print("=== Lesson 10-02: Document AI and Structured Extraction Pipelines ===\n")

    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])
        if not pdf_path.exists():
            print(f"Error: file not found: {pdf_path}")
            sys.exit(1)

        print(f"Processing: {pdf_path}")
        pdf_bytes = pdf_path.read_bytes()
        print(f"File size: {len(pdf_bytes):,} bytes")

        print("\nDetecting PDF type...")
        born_digital = is_born_digital(pdf_bytes)
        print(f"  Born-digital: {born_digital}")
        print(f"  Path: {'text extraction' if born_digital else 'vision (images)'}")

        if born_digital:
            text = extract_text_from_pdf(pdf_bytes)
            print(f"  Extracted text: {len(text):,} characters")
            print("\nSending to Claude (text path)...")
            result = extract_from_text(text)
        else:
            pages = pdf_pages_to_images(pdf_bytes)
            print(f"  Pages converted to images: {len(pages)}")
            print("\nSending to Claude (vision path, first 5 pages)...")
            result = extract_from_images(pages)
    else:
        print("No PDF provided. Running demo with embedded contract text.")
        print("(Text extraction path)\n")
        result = extract_from_text(DEMO_CONTRACT_TEXT)

    print("\n--- Extraction Result ---")
    print(json.dumps(result.model_dump(), indent=2))

    print("\n--- Routing Decision ---")
    if result.confidence == "high":
        print("  -> WRITE TO DATABASE: all fields extracted with high confidence")
    elif result.confidence == "medium":
        print("  -> HUMAN REVIEW: medium confidence, verify uncertain fields")
    else:
        print("  -> HUMAN REVIEW QUEUE: low confidence, full document review needed")

    if result.extraction_notes:
        print("\n--- Notes ---")
        for note in result.extraction_notes:
            print(f"  * {note}")


if __name__ == "__main__":
    main()
