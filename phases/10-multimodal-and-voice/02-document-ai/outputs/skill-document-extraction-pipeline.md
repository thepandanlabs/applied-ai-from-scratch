---
name: skill-document-extraction-pipeline
description: Production pattern for document AI including born-digital vs scanned decision tree, chunking strategies, accuracy expectations, and human review queue design
version: "1.0"
phase: "10"
lesson: "02"
tags: [document-ai, pdf, ocr, extraction, pydantic, structured-output]
---

# Document Extraction Pipeline Reference

## Path selection decision tree

```
Is the PDF born-digital (embedded text)?
  YES -> Text extraction path (pdfplumber or PyMuPDF)
  NO  -> Vision path (convert pages to images, send to vision model)

How to detect:
  text = extract_all_text(pdf)
  if len(text.strip()) > 100:
      use text path
  else:
      use vision path
```

## Cost comparison per page

| Path | Typical tokens/page | Cost at $0.25/1M (Haiku) |
|------|--------------------|-----------------------------|
| Text extraction | 2,000-6,000 | $0.0005-0.0015 |
| Vision at 768px | ~37,440 | ~$0.009 |
| Vision at 1024px | ~66,560 | ~$0.017 |

Text path is 10-20x cheaper. Use vision only when text extraction fails.

## Multi-page chunking strategies

### Strategy 1: Selective pages (contracts)

```python
# Most contract fields are on page 1 and last 3 pages
pages_to_check = [0, 1, -3, -2, -1]
selected_pages = [pages[i] for i in pages_to_check if abs(i) < len(pages)]
```

### Strategy 2: Accumulate until complete (born-digital)

```python
result = {}
for i, page_text in enumerate(pages):
    partial = extract_fields(page_text)
    result.update({k: v for k, v in partial.items() if v and k not in result})
    if all(result.get(f) for f in REQUIRED_FIELDS):
        break  # stop early, all fields found
```

### Strategy 3: Full concat (up to 100 pages born-digital)

```python
full_text = "\n\n".join(page_texts)
# ~150k chars is safe for Haiku context
result = extract_fields(full_text[:150_000])
```

## Accuracy expectations by document type

| Document type | Field accuracy | Recommended path |
|---------------|---------------|------------------|
| Born-digital contract | 95-98% | Text |
| Born-digital form | 90-95% | Text |
| Scanned contract, clean | 88-94% | Vision |
| Scanned form, printed | 85-92% | Vision |
| Scanned form, handwritten | 70-85% | Vision + human review |
| Phone photo of document | 65-82% | Vision + human review |

Field accuracy = per-field, not per-document. A 10-field doc at 95% accuracy has ~40% chance of at least one wrong field.

## Confidence-based routing queue

```python
from pydantic import BaseModel
from typing import Optional

class ExtractionResult(BaseModel):
    # ... extracted fields ...
    confidence: str  # "high" / "medium" / "low"
    extraction_notes: list[str]

def route(result: ExtractionResult, doc_id: str):
    if result.confidence == "high":
        write_to_database(doc_id, result)
    else:
        add_to_review_queue(doc_id, result, priority=result.confidence)
```

## Prompt template for contract extraction

```
Extract the following fields. Return JSON only, no markdown.

{
  "party_a": "First party name or null",
  "party_b": "Second party name or null",
  "effective_date": "ISO 8601 date or original text or null",
  "termination_clause": "Brief summary or null",
  "governing_law": "Jurisdiction or null",
  "confidence": "high | medium | low",
  "extraction_notes": ["caveats"]
}

Confidence: high = all 5 fields found clearly; medium = 3-4 or one ambiguous; low = <3 fields.
```

## Pydantic validation pattern

```python
from pydantic import BaseModel, Field
from typing import Optional

class ContractExtraction(BaseModel):
    party_a: Optional[str] = None
    party_b: Optional[str] = None
    effective_date: Optional[str] = None
    termination_clause: Optional[str] = None
    governing_law: Optional[str] = None
    confidence: str = "low"
    extraction_notes: list[str] = Field(default_factory=list)

# Usage
import json
raw_json = llm_response.strip().lstrip("```json").rstrip("```")
result = ContractExtraction(**json.loads(raw_json))
```

## Production checklist

- [ ] Implement path detection (born-digital vs scanned) before any extraction
- [ ] Log extraction path, token count, and confidence per document
- [ ] Set up a human review queue for medium/low confidence results
- [ ] Build a golden set of 30+ labeled documents for evaluation
- [ ] Track per-field accuracy separately (party name != termination clause in difficulty)
- [ ] Cap max_pages sent in vision path to control cost (5 pages is usually enough for contracts)
- [ ] Add retry with simplified prompt if JSON parsing fails
- [ ] Store raw LLM response alongside parsed result for debugging
