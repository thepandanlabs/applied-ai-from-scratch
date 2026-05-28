# كشف البيانات الشخصية (PII) وتنقيحها (Redaction)

> الـ regex يلتقط البيانات الشخصية (PII) المهيكلة. ويفوّت البيانات الشخصية السياقية. استخدم الـ regex للـ 80% السهلة، والـ LLM للـ 20% الصعبة في خطوط الأنابيب عالية الخطورة.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 08-01-owasp-llm-top-10, 08-04-sensitive-info-disclosure
**الوقت:** ~45 دقيقة
**المرحلة:** 08 - الأمان والحواجز الوقائية

## أهداف التعلّم

- سرد فئات البيانات الشخصية (PII) القابلة للكشف بالـ regex مقابل تلك التي تتطلب فهمًا دلاليًا
- بناء PIIRedactor بأنماط للبريد الإلكتروني والهاتف والـ SSN وأرقام بطاقات الائتمان
- تطبيق إبدال الأسماء المستعارة (pseudonymization) بديلًا عن التنقيح (redaction) الكامل
- إضافة احتياط (fallback) قائم على الـ LLM للبيانات الشخصية السياقية التي لا يستطيع الـ regex التقاطها
- شرح متى تُستخدم presidio لكشف البيانات الشخصية بمستوى الإنتاج

---

## الشعار

وجود بيانات شخصية (PII) في سياق النموذج يعني وجودها في سجلّاتك وآثارك (traces) وربما في بيانات تدريب نموذجك. نقّحها قبل أن تدخل.

---

## المشكلة

شركتك تنشر مساعدًا ذكيًا لمديري الموارد البشرية. الموظفون يقدّمون تذاكر الدعم عبر المساعد. خلال ستة أسابيع، تقع ثلاث حوادث خصوصية:

1. تذكرة تحتوي على رقم الضمان الاجتماعي (SSN) لموظف. المساعد يعالجها، فيظهر الـ SSN في آثار المراقبة (observability traces) للـ LLM لديك، ولوحة Langfuse لديك تحتوي الآن على أرقام SSN مرئية لفريق الهندسة بأكمله.

2. مدير يلصق تقييم أداء في المحادثة يتضمن أسماء ورواتب وتفاصيل إجازات مرضية. هذا السياق يدخل نافذة سياق النموذج ويظهر حرفيًا في الملخّص المولَّد الذي يُرسَل بالبريد إلى أصحاب مصلحة إضافيين.

3. موظف يذكر "call me at my direct line: 555-867-5309" في تذكرة. النموذج يدرج رقم الهاتف هذا في ملخّص رد يُسجَّل في مستودع بياناتك، الذي يحتفظ بالبيانات لمدة 7 سنوات.

لم تتطلب أي من هذه الحوادث اختراقًا أمنيًا. عالج البيانات نظامٌ تعامل مع كل سلسلة نصية على أنها آمنة بالتساوي للاحتفاظ بها. الإصلاح هو كشف البيانات الشخصية وتنقيحها قبل أن تدخل سياق النموذج وقبل أن تظهر في السجلّات.

يوجد منهجان. الـ regex يلتقط البيانات الشخصية المهيكلة: الـ SSN يبدو دائمًا بالشكل NNN-NN-NNNN، وبطاقة الائتمان تتبع دائمًا نمط الـ 16 رقمًا القابل للكشف عبر Luhn، والبريد الإلكتروني يطابق دائمًا `[text]@[domain]`. وهو يفوّت البيانات الشخصية السياقية: "call John at the downtown office" تحتوي اسمًا وموقعًا ضمنيًا لن يلتقطه أي regex.

---

## المفهوم

### فئات البيانات الشخصية (PII) وطرق الكشف

```
CATEGORY         FORMAT            DETECTION METHOD     REDACTION TARGET
---------------------------------------------------------------------------
Email address    user@domain.com   Regex (reliable)     [EMAIL]
Phone number     +1-NNN-NNN-NNNN   Regex (reliable)     [PHONE]
US SSN           NNN-NN-NNNN       Regex (reliable)     [SSN]
Credit card      16 digits/groups  Regex + Luhn check   [CREDIT_CARD]
IP address       NNN.NNN.NNN.NNN   Regex (reliable)     [IP_ADDRESS]
---------------------------------------------------------------------------
Person name      "John Smith"      NER / LLM required   [NAME]
Street address   "123 Main St"     NER / LLM required   [ADDRESS]
Organization     "Acme Corp"       NER / LLM required   [ORG]
Medical info     Context-dependent LLM required          [MEDICAL]
---------------------------------------------------------------------------
```

### التنقيح (Redaction) مقابل إبدال الأسماء المستعارة (Pseudonymization)

استراتيجيتان للتعامل مع البيانات الشخصية المكتشفة:

```
REDACTION                         PSEUDONYMIZATION
---------------------------------------------------
Replace with label:               Replace with consistent fake:
  john.smith@corp.com               user_0042@example.com
  -> [EMAIL]                        name_007 (always the same for "John Smith")

Pros: simple, no data retained    Pros: context preserved for analysis
Cons: breaks conversational        Cons: mapping table must be stored securely
      context when the model
      needs to reference the
      entity again

Use for: logs, traces             Use for: model context where coherence matters
         external APIs                     anonymized datasets
         training data
```

### أين تُطبَّق تنقيح البيانات الشخصية

```
User Input -> [PII Redact] -> Model Context -> Model -> Output -> [PII Redact] -> Response/Log
                                                                        |
                                                               Logs should never
                                                               contain original PII
```

طبّق التنقيح عند نقطتين: قبل أن يدخل المدخل سياق النموذج (حماية النموذج)، وقبل أن يُسجَّل المخرَج أو يُخزَّن (حماية خط أنابيب بياناتك).

---

## البناء

### الخطوة 1: أنماط regex للبيانات الشخصية المهيكلة

```python
# code/main.py
"""
PII Detection and Redaction - Phase 08 Lesson 08
appliedaifromscratch.com

Demonstrates: PIIRedactor with regex patterns and LLM fallback.
Regex handles structured PII (email, phone, SSN, credit card).
LLM handles contextual PII (names, addresses) in high-risk pipelines.

pip install anthropic
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from typing import Iterator


@dataclass
class PIIMatch:
    """A detected PII instance in text."""
    category: str          # e.g. "email", "ssn"
    original: str          # the matched text
    start: int             # character offset in original text
    end: int               # character offset in original text
    redacted_label: str    # e.g. "[EMAIL]"


# ---------------------------------------------------------------------------
# Regex patterns for structured PII
# ---------------------------------------------------------------------------
# Ordered by specificity: more specific patterns before less specific ones.

_PII_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Credit card: 13-16 digits in groups (Visa, MC, Amex, Discover)
    # Must come before generic number patterns.
    (
        "credit_card",
        re.compile(
            r"\b(?:4[0-9]{12}(?:[0-9]{3})?|"           # Visa
            r"(?:5[1-5][0-9]{2}|222[1-9]|22[3-9][0-9]|2[3-6][0-9]{2}|27[01][0-9]|2720)[0-9]{12}|"  # Mastercard
            r"3[47][0-9]{13}|"                           # Amex
            r"(?:6011|65[0-9]{2}|64[4-9][0-9])[0-9]{12})\b",  # Discover
        ),
        "[CREDIT_CARD]",
    ),
    # US Social Security Number: NNN-NN-NNNN or NNN NN NNNN
    (
        "ssn",
        re.compile(r"\b(?!000|666|9\d{2})\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b"),
        "[SSN]",
    ),
    # Email address
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL]",
    ),
    # Phone number: US formats +1-NNN-NNN-NNNN, (NNN) NNN-NNNN, NNN.NNN.NNNN
    (
        "phone",
        re.compile(
            r"(?:\+?1[-.\s]?)?"        # optional country code
            r"(?:\(?\d{3}\)?[-.\s]?)"  # area code
            r"\d{3}[-.\s]?\d{4}\b"
        ),
        "[PHONE]",
    ),
    # IPv4 address
    (
        "ip_address",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
            r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
        ),
        "[IP_ADDRESS]",
    ),
]
```

### الخطوة 2: صنف الـ PIIRedactor

```python
class PIIRedactor:
    """
    Detects and redacts structured PII using regex patterns.
    Optionally falls back to an LLM for contextual PII detection.

    Usage:
        redactor = PIIRedactor()
        clean_text = redactor.redact("Contact john@acme.com or call 555-123-4567")
        # -> "Contact [EMAIL] or call [PHONE]"
    """

    def __init__(
        self,
        patterns: list[tuple[str, re.Pattern, str]] | None = None,
        pseudonymize: bool = False,
    ):
        """
        Args:
            patterns: List of (category, compiled_regex, label) tuples.
                      Defaults to _PII_PATTERNS.
            pseudonymize: If True, replace PII with consistent pseudonyms
                          instead of generic labels.
        """
        self._patterns = patterns if patterns is not None else _PII_PATTERNS
        self._pseudonymize = pseudonymize
        self._pseudo_map: dict[str, str] = {}  # original -> pseudonym
        self._counters: dict[str, int] = {}     # category -> count

    def detect(self, text: str) -> list[PIIMatch]:
        """
        Return all PII matches in text, sorted by start position.
        Does not modify the text.
        """
        matches: list[PIIMatch] = []
        for category, pattern, label in self._patterns:
            for m in pattern.finditer(text):
                matches.append(PIIMatch(
                    category=category,
                    original=m.group(),
                    start=m.start(),
                    end=m.end(),
                    redacted_label=label,
                ))
        # Sort by start position; for overlapping matches, keep the earlier one
        matches.sort(key=lambda m: (m.start, -len(m.original)))
        return self._remove_overlaps(matches)

    def redact(self, text: str) -> str:
        """
        Replace detected PII with labels or pseudonyms.
        Processes matches right-to-left to preserve character offsets.
        """
        matches = self.detect(text)
        # Process right-to-left so earlier replacements don't shift later offsets
        result = text
        for match in reversed(matches):
            replacement = self._get_replacement(match)
            result = result[:match.start] + replacement + result[match.end:]
        return result

    def redact_report(self, text: str) -> tuple[str, list[dict]]:
        """
        Return (redacted_text, list_of_redactions).
        The report shows what was found and replaced, useful for auditing.
        """
        matches = self.detect(text)
        redacted = self.redact(text)
        report = [
            {
                "category": m.category,
                "original": m.original[:4] + "****",  # show only first 4 chars in report
                "label": m.redacted_label,
                "position": (m.start, m.end),
            }
            for m in matches
        ]
        return redacted, report

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_replacement(self, match: PIIMatch) -> str:
        if not self._pseudonymize:
            return match.redacted_label

        # Pseudonymization: consistent mapping for the same original value
        if match.original not in self._pseudo_map:
            count = self._counters.get(match.category, 0) + 1
            self._counters[match.category] = count
            self._pseudo_map[match.original] = f"{match.category}_{count:04d}"
        return self._pseudo_map[match.original]

    @staticmethod
    def _remove_overlaps(matches: list[PIIMatch]) -> list[PIIMatch]:
        """Remove overlapping matches, keeping the first (leftmost) match."""
        result: list[PIIMatch] = []
        last_end = -1
        for m in matches:
            if m.start >= last_end:
                result.append(m)
                last_end = m.end
        return result
```

### الخطوة 3: احتياط (fallback) قائم على الـ LLM للبيانات الشخصية السياقية

```python
import anthropic
import json

LLM_PII_PROMPT = """You are a PII detection system. Identify all personally identifiable information in the following text.

Return a JSON array of detections. Each detection has:
- "type": one of [person_name, street_address, organization, medical_info, other_pii]
- "text": the exact substring containing PII
- "reason": one sentence explaining why this is PII

Return only the JSON array, no other text. Return [] if no PII is found.

Text to analyze:
"""


def llm_pii_check(
    text: str,
    client: anthropic.Anthropic,
) -> list[dict]:
    """
    Use Claude to detect contextual PII that regex cannot catch.
    Returns list of detected PII with type, text, and reason.

    Use for: names, addresses, organizational affiliations, medical information.
    Do not use for: structured PII (email, SSN) - regex is faster and cheaper.
    """
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": LLM_PII_PROMPT + text[:3000],
            }
        ],
    )

    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []  # fail open for PII detection (don't block legitimate requests)


def redact_with_llm_fallback(
    text: str,
    redactor: PIIRedactor,
    client: anthropic.Anthropic,
) -> tuple[str, list[dict]]:
    """
    Full PII redaction pipeline:
    1. Regex handles structured PII (fast, $0)
    2. LLM handles contextual PII (slow, API cost)

    Returns (fully_redacted_text, combined_detection_report).
    """
    # Step 1: regex redaction
    regex_redacted, regex_report = redactor.redact_report(text)

    # Step 2: LLM check on the regex-redacted text
    # Pass the already-redacted text so the LLM sees [EMAIL] not the actual email
    llm_detections = llm_pii_check(regex_redacted, client)

    # Step 3: replace LLM-detected spans in the regex-redacted text
    result = regex_redacted
    for detection in llm_detections:
        pii_text = detection.get("text", "")
        pii_type = detection.get("type", "other_pii").upper()
        if pii_text and pii_text in result:
            result = result.replace(pii_text, f"[{pii_type}]", 1)

    return result, regex_report + llm_detections
```

> **اختبار من الواقع:** الـ PIIRedactor لديك ينقّح أرقام SSN والبريد الإلكتروني بنجاح. مستخدم يرسل: "Please process the claim for Margaret Chen, born 1975, living near Riverside Drive." الـ regex لديك لا يجد شيئًا - لا SSN، ولا بريد إلكتروني، ولا هاتف. احتياط الـ LLM يكتشف "Margaret Chen" كاسم شخص و"Riverside Drive" كجزء عنوان. لكن نظامك منشور كمنظّف سجلّات أحادي الاتجاه، لا كمحادثة موجّهة للمستخدم. استدعاء الـ LLM لكل سطر سجلّ يكلّف 300$ شهريًا ويضيف 500ms لكل سطر. ما المفاضلة الصحيحة؟ لتنظيف سجلّات بيانات عالية الحجم ومنخفضة الخطورة، الاكتفاء بالـ regex مناسب. أضِف احتياط الـ LLM فقط لفئات السجلّات المحددة التي تحتوي على بيانات شخصية عالية الخطورة (تذاكر الموارد البشرية، السجلّات الطبية، الوثائق القانونية). جزّئ حسب حساسية البيانات، لا حسب الحجم.

---

## الاستخدام

### presidio لكشف البيانات الشخصية بمستوى الإنتاج

`presidio` من Microsoft يوفّر محلّل بيانات شخصية كامل قائم على الـ NER يتعامل مع الأسماء والعناوين والعديد من الأنواع المهيكلة في حزمة واحدة:

```python
# pip install presidio-analyzer presidio-anonymizer
# python -m spacy download en_core_web_lg
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

def redact_with_presidio(text: str, language: str = "en") -> str:
    results = analyzer.analyze(text=text, language=language)
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text

# Example
text = "Send the results to john.doe@company.com or call (555) 123-4567."
print(redact_with_presidio(text))
# -> "Send the results to <EMAIL_ADDRESS> or call <PHONE_NUMBER>."
```

```
CUSTOM REGEX REDACTOR          PRESIDIO
-----------------------------------------------------
No dependencies (stdlib)       pip install + spacy model (~300MB)
Fast: regex only               Slower: NER model on CPU ~100ms
Catches structured PII only    Catches names, addresses, orgs
Works offline                  Works offline
Customizable patterns          Customizable recognizers + NLP pipeline
Zero ML overhead               ML-based NER (higher recall for names)
```

Presidio هو الخيار الصحيح عندما:
- تحتاج إلى كشف أسماء الأشخاص والعناوين بشكل موثوق
- بياناتك تحتوي على لغات مختلطة (presidio يدعم أكثر من 20 لغة)
- تريد مكتبة مُختبَرة جيدًا ومدقَّقة لأغراض الامتثال

> **نقلة في المنظور:** يسألك الـ CISO "لماذا لا نوجّه النموذج ببساطة إلى ألا يُخرج بيانات شخصية في ردوده؟ يبدو ذلك أبسط من خط أنابيب تنقيح." ما الذي تفوّته تعليمة على مستوى النموذج ويلتقطه منقّح على مستوى الكود؟ تعليمة النموذج تؤثر على المخرَج. وهي لا تؤثر على كيفية التعامل مع البيانات الشخصية بمجرد دخولها نافذة سياق النموذج. الـ SSN في المدخل أصبح بالفعل في سياق النموذج، وبالفعل في آثارك، وبالفعل في لوحة مراقبة الـ LLM لديك. المنقّح يحمي قبل استدعاء النموذج (upstream). إضافةً إلى ذلك، يمكن تجاوز تعليمات النموذج عبر حقن الموجّهات. منقّح على مستوى الكود يعمل خارج النموذج ولا يمكن تجاوزه بالتلاعب بسلوك النموذج.

---

## التسليم

مُخرَج هذا الدرس هو `outputs/skill-pii-redactor.md`: مرجع لكشف البيانات الشخصية وتنقيحها مع أنماط regex، واستراتيجية إبدال الأسماء المستعارة، ودليل دمج presidio.

---

## التقييم

**اختبار الاستدعاء/التغطية (recall) للبيانات الشخصية المهيكلة:** أنشئ مجموعة اختبار من 50 سلسلة نصية، تحتوي كل واحدة على حالة بيانات شخصية واحدة بالضبط بتنسيق مختلف. مرّرها عبر المنقّح. يجب اكتشاف كل حالة. أي تفويت هو سلبي خاطئ. وسّع أو أصلِح نمط الـ regex المقابل.

**اختبار الدقة (precision):** مرّر 50 سلسلة نصية حميدة (أرقام طلبات، رموز منتجات، رموز بريدية) عبر المنقّح. احسب الإيجابيات الخاطئة (نصوص غير شخصية صُنّفت كبيانات شخصية). معدل إيجابيات خاطئة فوق 1% يخلق احتكاكًا. أضِف أنماط نظر أمامي سلبي (negative lookahead) لتقليل المطابقة المفرطة على الأرقام.

**اختبار اتساق إبدال الأسماء المستعارة:** عالج عنوان البريد الإلكتروني نفسه في سلسلتين نصيتين مختلفتين. يجب أن يكون الاسم المستعار متطابقًا في الحالتين. إذا لم يكن كذلك، فالربط (mapping) ليس حتميًا. هذا مهم عندما يحتاج النموذج إلى الحفاظ على اتساق الهوية عبر الأدوار (turns).

**تدقيق السجلّات:** أسبوعيًا، عيّن 10 إدخالات سجلّ خام من نظام مراقبة الـ LLM لديك. إذا احتوى أي منها على سلاسل بتنسيق SSN، أو عناوين بريد إلكتروني، أو أرقام هواتف، فإن خط أنابيب التنقيح لديك فيه فجوة. حدّد أي مسار كود تجاوز التنقيح وأضِف استدعاء تنقيح.

**تغطية Presidio مقابل regex:** شغّل منقّح الـ regex لديك وpresidio معًا على مجموعة الاختبار نفسها المكوّنة من 100 جملة. قارِن الاستدعاء/التغطية. أي حالة يلتقط فيها presidio بيانات شخصية فوّتها الـ regex لديك هي مرشّحة لإضافة نمط مخصص أو لتحويل خط الأنابيب إلى presidio.
