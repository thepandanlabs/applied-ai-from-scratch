---
name: skill-input-output-safety
description: InputValidator and OutputSanitizer classes for treating both user input and model output as untrusted boundaries
version: "1.0"
phase: "06"
lesson: "04"
tags: [validation, safety, security, input, output, sanitization]
---

# Input and Output Safety Module

Drop `InputValidator` and `OutputSanitizer` into any AI service to enforce the two untrusted boundaries: user input on the way in, model output on the way out.

---

## When to use each method

```
+-----------------------------+------------------------------------------+
| Context                     | Method to use                            |
+-----------------------------+------------------------------------------+
| Display text in a web app   | sanitizer.for_html_rendering(raw)        |
| Return text in an API       | sanitizer.for_text_response(raw)         |
| Parse model output as JSON  | sanitizer.for_json_response(raw)         |
| Validate user prompt        | validator.validate(text, "prompt")       |
| Validate system prompt      | validator.validate(text, "system")       |
+-----------------------------+------------------------------------------+
```

---

## Full module

```python
"""
input_output_safety.py

Paste this file into your project and import:
    from input_output_safety import InputValidator, OutputSanitizer
"""

import html
import json
import re
import unicodedata


class InputValidator:
    """
    Validates user input before it reaches the model.

    Both users and models are untrusted. This class handles the input side.

    Initialize once (in lifespan or module scope) to avoid recompiling regexes.
    All validate() calls are pure and raise ValueError on failure.
    """

    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?prior\s+instructions",
        r"disregard\s+your\s+system\s+prompt",
        r"output\s+your\s+system\s+prompt",
        r"reveal\s+your\s+(system\s+)?instructions",
        r"you\s+are\s+now\s+\w+",
        r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
        r"pretend\s+you\s+have\s+no\s+(safety\s+)?guidelines",
    ]

    def __init__(
        self,
        max_chars: int = 4000,
        allow_html: bool = False,
        allow_code: bool = True,
    ):
        self.max_chars = max_chars
        self.allow_html = allow_html
        self.allow_code = allow_code
        self._injection_re = re.compile(
            "|".join(self.INJECTION_PATTERNS),
            re.IGNORECASE | re.DOTALL,
        )

    def validate(self, text: str, field_name: str = "input") -> str:
        """
        Validate and return clean input. Raises ValueError on any failure.

        Order of checks:
            1. Type (must be str)
            2. Not empty after strip
            3. Length <= max_chars
            4. Unicode NFKC normalization
            5. Injection pattern detection
            6. HTML tag detection (if allow_html=False)
        """
        if not isinstance(text, str):
            raise ValueError(f"{field_name} must be a string, got {type(text).__name__}.")
        text = text.strip()
        if not text:
            raise ValueError(f"{field_name} cannot be empty.")
        if len(text) > self.max_chars:
            raise ValueError(
                f"{field_name} exceeds the maximum length "
                f"({len(text):,} chars, max {self.max_chars:,})."
            )
        text = unicodedata.normalize("NFKC", text)
        if self._injection_re.search(text):
            raise ValueError(f"{field_name} contains disallowed content.")
        if not self.allow_html and re.search(r"<[a-zA-Z/][^>]*>", text):
            raise ValueError(f"{field_name} contains HTML markup. Plain text input only.")
        return text


class OutputSanitizer:
    """
    Sanitizes model output before it reaches downstream consumers.

    The model is an untrusted text source. Apply the correct method for
    each output context.

    NEVER:
        - eval() or exec() model output
        - Inject raw model output into HTML without for_html_rendering()
        - Use raw model output as SQL, shell commands, or file paths
    """

    PREAMBLE_PATTERNS = [
        r"^(Sure!?|Of course!?|Certainly!?|Absolutely!?)[,!]?\s+",
        r"^Here is (the|your|a|an) (result|answer|response|JSON|text|list):?\s*",
        r"^Here's (the|your|a|an) (result|answer|response|JSON|text|list):?\s*",
        r"^As requested[,\s]+",
        r"^I'd be (happy|glad) to help[.!]\s*",
        r"^Based on your request[,\s]+",
    ]

    def __init__(self, html_escape: bool = True):
        self.html_escape = html_escape
        self._preamble_re = re.compile(
            "|".join(self.PREAMBLE_PATTERNS), re.IGNORECASE
        )

    def for_text_response(self, raw: str) -> str:
        """For plain text API responses. Strips preamble. HTML-escapes if configured."""
        clean = self._preamble_re.sub("", raw.strip(), count=1).strip()
        if self.html_escape:
            clean = html.escape(clean)
        return clean

    def for_json_response(self, raw: str) -> dict | None:
        """
        Parse model output as JSON. Strips markdown code fences.
        Returns None on parse failure -- never raises.
        Caller must handle None.
        """
        clean = raw.strip()
        # Strip markdown code fences: ```json\n...\n```
        match = re.match(r"^```(?:\w+)?\n(.*)\n```$", clean, re.DOTALL)
        if match:
            clean = match.group(1).strip()
        elif clean.startswith("```") and clean.endswith("```"):
            lines = clean.split("\n")
            if len(lines) >= 3:
                clean = "\n".join(lines[1:-1]).strip()
        try:
            return json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            return None

    def for_html_rendering(self, raw: str) -> str:
        """Always HTML-escapes. Use when inserting model output into HTML."""
        return html.escape(raw.strip())
```

---

## FastAPI integration

```python
# In lifespan (once per process):
app.state.validator = InputValidator(max_chars=4000, allow_html=False)
app.state.sanitizer = OutputSanitizer(html_escape=True)

# In a route handler:
@app.post("/generate")
async def generate(req: Request, body: GenerateRequest):
    validator = req.app.state.validator
    sanitizer = req.app.state.sanitizer

    # Validate input
    try:
        clean_prompt = validator.validate(body.prompt, "prompt")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Call model
    response = req.app.state.client.messages.create(
        model=req.app.state.model,
        max_tokens=body.max_tokens,
        messages=[{"role": "user", "content": clean_prompt}],
    )

    # Sanitize output
    safe_text = sanitizer.for_text_response(response.content[0].text)
    return {"text": safe_text}
```

---

## Threat summary

### What InputValidator catches

| Threat | Method |
|--------|--------|
| Wrong type (None, int) | `_check_type` |
| Empty or whitespace-only input | `_check_not_empty` |
| Token exhaustion (huge inputs) | `_check_length` |
| Prompt injection attempts | `_check_injection` |
| Unicode lookalike attacks | `_normalize_unicode` |
| HTML injection via input | `_check_html` |

### What OutputSanitizer catches

| Threat | Method |
|--------|--------|
| Model preamble text | `_strip_preamble` in `for_text_response` |
| JSON wrapped in code fences | `_strip_code_fences` in `for_json_response` |
| JSON parse failure (returns None) | `for_json_response` |
| HTML/script injection in output | `for_html_rendering` |

### What neither class addresses

- SQL injection via model output (use parameterized queries)
- Shell injection via model output (never pass model output to shell)
- eval() of model output (never do this)
- Downstream prompt injection (model output passed to another model call)

For these, you need application-level controls: never use model output in unsafe contexts, regardless of what sanitization has been applied.
