**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 08-eval-harnesses, 09-ci-for-prompts
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- تطبيق تقييمات على مستوى المكوّنات (component-level) لنقاط الفشل الثلاث في خط أنابيب RAG: الاسترجاع (retrieval)، والأمانة (faithfulness)، وصلة الإجابة (answer relevance)
- بناء تقييمات للمسار (trajectory) والإنهاء (termination) لأنظمة الوكلاء (agents)
- الجمع بين RAGAS ومنظومة (harness) مخصّصة لتقييم نظام متعدّد الخطوات بالكامل
- تشخيص حالات الفشل باستخدام درجات المكوّنات بدل الدرجات الشاملة (end-to-end) وحدها

---

## MOTTO

**عندما يفشل خط أنابيب، تحتاج أن تعرف أي مرحلة انكسرت. الدرجات الشاملة تخفي موقع المشكلة.**

---

## المشكلة

يسجّل روبوت RAG لديك 0.91 على "جودة الإجابة" في تقييمك الشامل (end-to-end). المستخدمون يشتكون من إجابات خاطئة. تنظر في 10 حالات فاشلة وكلها حصلت على درجة جودة 0.88-0.92. تقييمك لم يلتقط شيئاً.

المشكلة أن "جودة الإجابة" رقم واحد لخط أنابيب من ثلاث مراحل. لا تستطيع أن تقول من درجة 0.88 ما إذا كان الاسترجاع أعاد مقاطع (chunks) سيئة، أو أن المولّد تجاهل مقاطع جيدة، أو أن الإجابة ببساطة لم تعالج السؤال.

تنطبق المشكلة ذاتها على الوكلاء (agents). يجري وكيل 4 استدعاءات أدوات للإجابة عن سؤال. تنجح اختبارات الوحدة لكل أداة. لكن التقييم الشامل يُظهر معدّل فشل 30%. لماذا؟ لأن الفشل ليس في أي أداة منفردة. إنه في التسلسل: استدعى الوكيل الأدوات الصحيحة بالترتيب الخاطئ، أو استدعى أداة مرّتين بينما كان عليه التوقّف، أو أنهى قبل أن يحصل على المعلومة التي يحتاجها.

تتطلّب الأنظمة متعدّدة الخطوات تقييمات على مستوى المكوّنات. تحصل كل مرحلة على درجتها الخاصة. عندما ينكسر شيء، تعرف بالضبط أين تنظر.

---

## المفهوم

### ثلاثية RAG

لكل خط أنابيب RAG ثلاثة أنماط فشل متمايزة. تسمّيها ثلاثية RAG (RAG Triad):

```
                    USER QUESTION
                          |
            +-------------v--------------+
            |      RETRIEVAL             |  <- Failure 1
            |  Context Relevance         |
            |  "Did we fetch the right   |
            |   chunks?"                 |
            +-------------+--------------+
                          |
            retrieved chunks
                          |
            +-------------v--------------+
            |      GENERATION            |  <- Failure 2
            |  Faithfulness              |
            |  "Does the answer stay     |
            |   grounded in the chunks?" |
            +-------------+--------------+
                          |
            generated answer
                          |
            +-------------v--------------+
            |      RELEVANCE             |  <- Failure 3
            |  Answer Relevance          |
            |  "Does the answer address  |
            |   the original question?"  |
            +-----------------------------+
```

هذه المقاييس الثلاثة مستقلّة. يمكن لنظام أن يملك:
- صلة سياق عالية لكن أمانة منخفضة (استرجع مقاطع ممتازة، ثم هلوس)
- صلة سياق منخفضة لكن أمانة عالية (استرجع مقاطع سيئة، وبقي متمسّكاً بها: خاطئ بثقة)
- أمانة عالية وصلة سياق عالية لكن صلة إجابة منخفضة (متمسّك بمقاطع ذات صلة لكنه لم يجب عن السؤال الفعلي)

### تقييمات مسار الوكيل (Trajectory)

لا ينتج الوكلاء مخرَجاً واحداً. ينتجون تسلسلاً من استدعاءات الأدوات إضافة إلى إجابة نهائية.

```
Expected trajectory:  [search_web, read_url, summarize]
Actual trajectory:    [search_web, search_web, read_url]
```

قد تكون الإجابة النهائية سليمة. لكن الوكيل أهدر استدعاءً ولم يتّبع النمط الصحيح. على نطاق واسع، الاستدعاءات المهدورة تكلّف مالاً ووقتاً.

ثلاثة أنماط لتقييم المسار:

```
EXACT MATCH           PARTIAL CREDIT         TERMINATION CHECK
-----------           --------------         -----------------
Did it call the       Right tools,           Did it stop when
exact right tools     wrong order?           it should have?
in the right order?   Penalize lightly.      Too early or too late?

Score: 0 or 1         Score: fraction        Score: 0 or 1
                      of tools matched
```

### المكوّنات مقابل الشامل: كلاهما ضروري

```
COMPONENT EVALS                    END-TO-END EVAL
-----------------------            ---------------
Which stage broke?                 Did the user get a good answer?
Fast to debug                      Hard to debug
May miss cross-stage failures      Catches emergent failures
Required for RAG + agents          Required for final quality gate
```

كلاهما ضروري. تقييمات المكوّنات تخبرك أين تصلح. التقييمات الشاملة تخبرك إن كان الإصلاح قد نجح.

---

## البناء

### تقييمات مكوّنات RAG

```python
# code/main.py
import json
import re
from anthropic import Anthropic

client = Anthropic()

# --- Eval 1: Context Relevance (Retrieval Quality) ---

def eval_retrieval(
    question: str,
    retrieved_chunks: list[str],
    relevant_chunks: list[str]  # from golden retrieval set
) -> dict:
    """
    Precision@k and Recall@k for retrieved chunks vs ground truth relevant chunks.
    Uses simple substring overlap as relevance signal (replace with embeddings in production).
    """
    def is_relevant(chunk: str, relevant: list[str], threshold: float = 0.5) -> bool:
        for ref in relevant:
            words_chunk = set(chunk.lower().split())
            words_ref = set(ref.lower().split())
            if not words_ref:
                continue
            overlap = len(words_chunk & words_ref) / len(words_ref)
            if overlap >= threshold:
                return True
        return False

    k = len(retrieved_chunks)
    relevant_retrieved = sum(1 for c in retrieved_chunks if is_relevant(c, relevant_chunks))

    precision_at_k = relevant_retrieved / k if k > 0 else 0.0
    recall_at_k = relevant_retrieved / len(relevant_chunks) if relevant_chunks else 0.0

    return {
        "precision_at_k": round(precision_at_k, 3),
        "recall_at_k": round(recall_at_k, 3),
        "k": k,
        "relevant_retrieved": relevant_retrieved,
        "total_relevant": len(relevant_chunks)
    }
```

```python
# --- Eval 2: Faithfulness (Generation Grounded in Context?) ---

def eval_faithfulness(answer: str, retrieved_chunks: list[str]) -> dict:
    """
    Check what fraction of factual claims in the answer appear in the retrieved chunks.
    Uses simple word overlap as a first-pass approximation.
    For production: use LLM to extract claims, then check each claim against chunks.
    """
    # Approximation: does each sentence in the answer have word overlap with chunks?
    combined_context = " ".join(retrieved_chunks).lower()
    context_words = set(combined_context.split())

    sentences = [s.strip() for s in re.split(r'[.!?]', answer) if s.strip()]
    if not sentences:
        return {"faithfulness": 0.0, "grounded_sentences": 0, "total_sentences": 0}

    grounded = 0
    for sentence in sentences:
        words = set(sentence.lower().split())
        # Remove stopwords proxy: only consider words > 4 chars
        content_words = {w for w in words if len(w) > 4}
        if not content_words:
            grounded += 1  # treat short/stopword sentences as neutral
            continue
        overlap = len(content_words & context_words) / len(content_words)
        if overlap >= 0.4:  # 40% of content words appear in context
            grounded += 1

    faithfulness = grounded / len(sentences)
    return {
        "faithfulness": round(faithfulness, 3),
        "grounded_sentences": grounded,
        "total_sentences": len(sentences)
    }
```

```python
# --- Eval 3: Answer Relevance (Answers the Question?) ---

def eval_answer_relevance(question: str, answer: str) -> dict:
    """
    LLM judge: does this answer address the question?
    Returns score 0.0-1.0 and reasoning.
    """
    prompt = f"""Does the following answer address the question asked?

Question: {question}

Answer: {answer}

Rate on a scale of 0 to 1:
- 1.0: Fully addresses the question
- 0.7: Partially addresses it, missing key aspects
- 0.3: Tangentially related but doesn't answer the question
- 0.0: Completely off-topic

Respond with JSON only:
{{"score": <float>, "reasoning": "<one sentence>"}}"""

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()

    result = json.loads(text)
    return {
        "answer_relevance": round(float(result["score"]), 3),
        "reasoning": result["reasoning"]
    }
```

### تقييمات مسار الوكيل (Trajectory)

```python
# --- Eval 4: Trajectory Eval ---

def eval_trajectory(
    expected_tools: list[str],
    actual_tools: list[str]
) -> dict:
    """
    Compare expected vs actual tool call sequences.

    Returns:
    - exact_match: 1.0 if sequences are identical
    - tool_coverage: fraction of expected tools that appear anywhere in actual
    - order_score: fraction of expected tools that appear in correct relative order
    - extra_calls: number of unexpected tool calls
    """
    exact = 1.0 if expected_tools == actual_tools else 0.0

    # Tool coverage: which expected tools appeared at all?
    actual_set = set(actual_tools)
    coverage = sum(1 for t in expected_tools if t in actual_set) / len(expected_tools) if expected_tools else 0.0

    # Order score: longest common subsequence length / expected length
    def lcs_length(a: list, b: list) -> int:
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i-1] == b[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        return dp[m][n]

    lcs = lcs_length(expected_tools, actual_tools)
    order_score = lcs / len(expected_tools) if expected_tools else 0.0

    extra_calls = max(0, len(actual_tools) - len(expected_tools))

    return {
        "exact_match": exact,
        "tool_coverage": round(coverage, 3),
        "order_score": round(order_score, 3),
        "extra_calls": extra_calls
    }


# --- Eval 5: Termination Eval ---

def eval_termination(
    trace: list[dict],  # list of {type: "tool_call"|"final_answer", tool: str, ...}
    should_have_stopped_at: int  # 1-indexed step number
) -> dict:
    """
    Did the agent stop at the right step?

    Cases:
    - Stopped too early: final_answer before expected step
    - Stopped correctly: final_answer at expected step
    - Looped: ran past expected step without stopping
    - Never stopped: no final_answer in trace
    """
    final_answer_at = None
    for i, step in enumerate(trace):
        if step.get("type") == "final_answer":
            final_answer_at = i + 1  # 1-indexed
            break

    if final_answer_at is None:
        return {"termination": "never_stopped", "score": 0.0, "steps": len(trace)}
    elif final_answer_at < should_have_stopped_at:
        return {"termination": "too_early", "score": 0.5, "actual_step": final_answer_at, "expected_step": should_have_stopped_at}
    elif final_answer_at == should_have_stopped_at:
        return {"termination": "correct", "score": 1.0, "actual_step": final_answer_at}
    else:
        return {"termination": "looped", "score": 0.3, "actual_step": final_answer_at, "expected_step": should_have_stopped_at}
```

### شغّلها على مسارات نموذجية

```python
def demo():
    # --- RAG trace example ---
    question = "What is the capital of the Roman Empire?"
    retrieved_chunks = [
        "Rome was the capital of the Roman Empire from its founding until 286 AD.",
        "The Roman Empire covered much of Europe, North Africa, and the Middle East.",
        "Constantinople became the eastern capital in 330 AD under Constantine."
    ]
    relevant_chunks = [
        "Rome was the capital of the Roman Empire from its founding until 286 AD.",
        "Constantinople became the eastern capital in 330 AD under Constantine."
    ]
    answer = "The capital of the Roman Empire was Rome. Later, Constantinople became a second capital in the eastern part of the empire."

    print("=== RAG Component Evals ===")
    retrieval = eval_retrieval(question, retrieved_chunks, relevant_chunks)
    faithfulness = eval_faithfulness(answer, retrieved_chunks)
    relevance = eval_answer_relevance(question, answer)

    print(f"Context Relevance:  precision={retrieval['precision_at_k']:.2f}  recall={retrieval['recall_at_k']:.2f}")
    print(f"Faithfulness:       {faithfulness['faithfulness']:.2f}  ({faithfulness['grounded_sentences']}/{faithfulness['total_sentences']} sentences grounded)")
    print(f"Answer Relevance:   {relevance['answer_relevance']:.2f}  ({relevance['reasoning']})")

    # --- Agent trajectory example ---
    print("\n=== Agent Trajectory Evals ===")
    expected_tools = ["search_knowledge_base", "read_document", "summarize"]
    actual_tools_good = ["search_knowledge_base", "read_document", "summarize"]
    actual_tools_bad = ["search_knowledge_base", "search_knowledge_base", "read_document"]

    traj_good = eval_trajectory(expected_tools, actual_tools_good)
    traj_bad = eval_trajectory(expected_tools, actual_tools_bad)
    print(f"Good trajectory:  exact={traj_good['exact_match']}  coverage={traj_good['tool_coverage']}  order={traj_good['order_score']}  extra={traj_good['extra_calls']}")
    print(f"Bad trajectory:   exact={traj_bad['exact_match']}  coverage={traj_bad['tool_coverage']}  order={traj_bad['order_score']}  extra={traj_bad['extra_calls']}")

    # --- Termination eval ---
    trace_good = [
        {"type": "tool_call", "tool": "search"},
        {"type": "tool_call", "tool": "read"},
        {"type": "final_answer", "content": "The answer is..."}
    ]
    trace_looping = [
        {"type": "tool_call", "tool": "search"},
        {"type": "tool_call", "tool": "search"},
        {"type": "tool_call", "tool": "search"},
        {"type": "tool_call", "tool": "search"}
    ]

    term_good = eval_termination(trace_good, should_have_stopped_at=3)
    term_loop = eval_termination(trace_looping, should_have_stopped_at=3)
    print(f"\nTermination (correct): {term_good}")
    print(f"Termination (looping): {term_loop}")

if __name__ == "__main__":
    demo()
```

> **اختبار من الواقع:** يسجّل نظام RAG لديك 0.95 في صلة الإجابة لكن المستخدمين يقولون إن الإجابات غالباً خاطئة. تحسب أيضاً الأمانة (faithfulness): 0.62. ماذا يخبرك هذا المزيج عن موقع الفشل، وما الذي تصلحه أولاً؟ صلة الإجابة العالية تعني أن الإجابات تعالج الموضوع الصحيح. الأمانة المنخفضة (0.62) تعني أن 38% من محتوى الإجابة غير متجذّر (grounded) في المقاطع المسترجعة: النموذج يهلوس. الإجابات في صلب الموضوع لكنها غير متجذّرة وقائعياً. أصلح مرحلة التوليد أولاً: أضف تعليمات تجذير أقوى إلى الـ prompt، أو أضف فحصاً بعد التوليد، أو خفّض الـ temperature. لا تُصلح الاسترجاع؛ المشكلة ليست هناك.

---

## الاستخدام

### RAGAS لتقييمات RAG

يوفّر RAGAS مقاييس ثلاثية RAG ذاتها مع تنفيذات أكثر تطوّراً:

```python
# pip install ragas
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from datasets import Dataset

# Prepare your RAG traces in RAGAS format
data = {
    "question": ["What is the capital of the Roman Empire?"],
    "answer": ["The capital was Rome, later Constantinople became the eastern capital."],
    "contexts": [["Rome was the capital from founding until 286 AD.", "Constantinople became eastern capital in 330 AD."]],
    "ground_truth": ["Rome was the capital, with Constantinople as the eastern capital after 330 AD."]
}

dataset = Dataset.from_dict(data)
results = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision])
print(results)
# Output: {"faithfulness": 0.85, "answer_relevancy": 0.92, "context_precision": 0.90}
```

يستخدم RAGAS استدعاءات LLM داخلياً لحساب الأمانة وصلة الإجابة، وهو أدقّ من التقريب القائم على التداخل (overlap) من البناء الخام. ويتعامل مع الحالات الحدّية، والإجابات متعدّدة الجمل، والتجذير الجزئي بشكل صحيح.

لتسجيل مسار الوكيل (trajectory logging) في Braintrust:

```python
import braintrust

# Log each tool call as a span
with braintrust.start_span(name="agent_run") as span:
    for tool_call in agent_trace:
        with span.start_span(name=tool_call["tool"]) as tool_span:
            tool_span.log(input=tool_call["input"], output=tool_call["output"])
    
    # Custom trajectory scorer
    expected = ["search_knowledge_base", "read_document", "summarize"]
    actual = [step["tool"] for step in agent_trace if step["type"] == "tool_call"]
    traj = eval_trajectory(expected, actual)
    span.log(scores={"trajectory_order": traj["order_score"]})
```

**RAGAS مقابل المخصّص للوكلاء:**

```
RAGAS                              CUSTOM
-----                              ------
Designed for RAG pipelines         Required for agent trajectory evals
Opinionated, fast to set up        More work, but fits your specific agent
Faithfulness uses LLM calls        You control what "correct" means
context_precision is well-tested   Your trajectory eval knows your tools
Does not handle tool sequences     Handles any multi-step pattern
```

القاعدة العملية: استخدم RAGAS لـ RAG. ابنِ تقييمات مخصّصة للوكلاء. تقييم الوكيل خاصّ بالنظام لأن تسلسل الأدوات الصحيح يعتمد على منطق تطبيقك، لا على مقياس عام.

> **نقلة في المنظور:** نجح وكيلك في كل اختبارات الوحدة (كل أداة اختُبرت باستقلالية)، لكن التقييمات الشاملة تُظهر معدّل فشل 30%. ما الفجوة بين اختبارات مستوى الأداة وتقييمات المسار، ولماذا لا يستطيع أحدهما أن يحلّ محلّ الآخر؟ تتحقّق اختبارات الوحدة من كل أداة بمعزل: عند هذا المدخل، أعِد هذا المخرج. لا تستطيع اختبار ما إذا كان الوكيل يستدعي الأدوات الصحيحة بالترتيب الصحيح عند استعلام مستخدم حقيقي. يمكن لأداة أن تعمل بشكل مثالي ومع ذلك تسبّب فشل الوكيل إن استُدعيت في الوقت الخاطئ، أو استُدعيت مرّتين بينما تكفي مرّة، أو لم تُستدعَ أبداً بينما كان يجب أن تُستدعى. تختبر تقييمات المسار اتخاذ الوكيل للقرار عبر تسلسل من الخطوات. الاختباران متعامدان (orthogonal).

---

## التسليم

ناتج هذا الدرس هو `outputs/skill-multistep-eval.md`: دليل كامل لتقييم أنظمة RAG والوكلاء باستخدام ثلاثية RAG وأنماط تقييم المسار.

---

## التقييم

**كيف تعرف أن تقييماتك متعدّدة الخطوات تعمل:**

اختبار عزل المكوّنات: اكسر مكوّناً واحداً عمداً. أعِد مقاطع عشوائية من المسترجِع (تجاهل الاستعلام). تحقّق أن صلة السياق تهبط نحو 0 بينما تبقى الأمانة مستقرّة مؤقّتاً (لا يزال المولّد متجذّراً في المقاطع العشوائية، لكنها الخاطئة) وتهبط صلة الإجابة أيضاً. إن تحرّكت مقاييسك في الاتجاه المتوقّع، فهي تقيس باستقلالية.

فحص تغطية المسار: اسرد أكثر خمسة أنماط فشل شيوعاً لوكيلك من سجلّات الإنتاج (أداة خاطئة، أداة صحيحة بترتيب خاطئ، استدعاء مزدوج، إنهاء مبكّر، حلقة لانهائية). تحقّق أن تقييم المسار لديك يملك حالة اختبار لكل واحد منها. تقييم المسار الذي يفحص فقط التطابق التام للتسلسل سيفوّت حالات فشل الائتمان الجزئي (partial-credit).

الارتباط برضا المستخدم: شغّل تقييمات المكوّنات لديك على 50 مساراً حقيقياً. اجمع بشكل منفصل تقييمات رضا المستخدم أو إشارات الإعجاب/عدم الإعجاب للمسارات ذاتها. احسب الارتباط بين كل درجة مكوّن ورضا المستخدم. ارتباط الأمانة العالي يؤكّد أن المقياس يقيس شيئاً يهتمّ به المستخدمون. الارتباط المنخفض يعني أن المقياس لا يلتقط نمط الفشل الحقيقي.

معايرة RAGAS: يستخدم RAGAS مقيّماً بأسلوب LLM داخلياً. شغّل RAGAS على 10 حالات تعرف فيها تقييم الأمانة الصحيح يدوياً. إن اتّفق RAGAS مع تقييماتك اليدوية بنسبة 80% على الأقل، فهو معايَر لمجالك. إن لم يفعل، فاستخدم prompt أمانة مخصّصاً مضبوطاً على مجال محتواك.
