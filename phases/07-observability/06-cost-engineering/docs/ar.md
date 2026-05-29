# هندسة التكلفة: محاسبة الـ Tokens واللوحات

> جهّز أولًا (instrument). حسّن ثانيًا. لا تخمّن أبدًا أي استدعاء هو المكلف.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** المرحلة 07 الدرسان 01 و05 (أساسيات المراقبة، تسجيل طلبات LLM)
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- حساب تكلفة LLM لكل طلب من حقول الاستخدام (usage) في الـ API لمستويات نماذج Claude
- تجميع التكاليف حسب النموذج والميزة والمستخدم باستخدام SQLite
- بناء تقرير تفصيلي للتكلفة معروض كجدول ASCII
- تحديد المصادر الثلاثة الرئيسية لتجاوزات تكلفة LLM وعلاجاتها
- إعداد تنبيه ميزانية يُطلَق حين يتجاوز الإنفاق الشهري المتوقَّع حدًّا معيّنًا

---

## المشكلة

تُطلَق ميزة LLM لديك. بعد ثلاثة أشهر، تظهر في فاتورة بنيتك التحتية بند: 4,200 دولار الشهر الماضي لاستدعاءات API الخاصة بالذكاء الاصطناعي. يسألك مديرك التقني (CTO) أي ميزة تقود أكبر تكلفة. تفتح كودك. كل فريق أجرى استدعاءات API مباشرة. لم يتتبّع أحد الـ tokens. لم يتتبّع أحد أي نقطة نهاية استدعت أي نموذج. ليس لديك جواب.

تبدأ بالتخمين: "غالبًا ميزة التلخيص، فهي تستخدم الكثير من الـ tokens." أنت مخطئ. إنه مُصنِّف نيّة البحث (search-intent classifier) الذي يعمل عند كل ضغطة مفتاح لأن مطوّرًا ضبطه ليُطلَق على `onChange` بدل `onBlur`. كنت ستمسك هذا في الأسبوع الأول لو كان لديك محاسبة تكلفة. بدل ذلك وجدته في الشهر الثالث، بعد إنفاق 12,600 دولار.

هندسة التكلفة ليست عن البخل. إنها عن فهم أين تذهب أموالك كي تستطيع إجراء مفاضلات مدروسة: ادفع أكثر للجودة حيث تهم، وادفع أقل للمهام البسيطة، وامسك العلل (bugs) قبل أن تكلّف آلاف الدولارات.

---

## المفهوم

### من أين تأتي تكاليف LLM

```
+---------------------------+-------------------+---------------------------+
| Cost Source               | Typical Impact    | Fix                       |
+---------------------------+-------------------+---------------------------+
| Long system prompts       | 30-60% of input   | Prompt caching (L07)      |
|   repeated on every call  | tokens per call   |                           |
+---------------------------+-------------------+---------------------------+
| Verbose model outputs     | 2-5x output cost  | Explicit length            |
|   (no max length control) | vs needed         | instructions in prompt    |
+---------------------------+-------------------+---------------------------+
| Wrong model tier          | 5-20x cost ratio  | Route simple tasks        |
|   (Opus for simple tasks) | vs correct tier   | to Haiku or Sonnet        |
+---------------------------+-------------------+---------------------------+
| Missing cache hits        | Cache reads cost  | Use cache_control          |
|   (cacheable data re-sent)| 10% of writes     | breakpoints (L07)         |
+---------------------------+-------------------+---------------------------+
| High call frequency       | Multiplies all    | Debounce, batch,          |
|   (per-keystroke callers) | above             | or async queue            |
+---------------------------+-------------------+---------------------------+
```

### نموذج تسعير Claude (مرجع 2026)

```
Model                        Input ($/1M)  Output ($/1M)  Cache write  Cache read
---------------------------  -----------  -------------  -----------  ----------
claude-3-5-haiku-20241022       $0.80         $4.00         $1.00       $0.08
claude-3-5-sonnet-20241022      $3.00        $15.00         $3.75       $0.30
claude-opus-4-5                $15.00        $75.00        $18.75       $1.50
```

تكلّف tokens المُخرَج 4-5 أضعاف tokens المُدخَل لكل مليون. هذا يعني أن الاستجابات المُسهَبة مكلفة على نحو غير متناسب. نموذج يُخرِج 500 token حيث كان 100 يكفي يُنفق 5 أضعاف على المُخرَج وحده.

### نموذج بيانات محاسبة التكلفة

```
                    +------------------+
                    |  LLM API Call    |
                    |  (each request)  |
                    +------------------+
                           |
          +----------------+----------------+
          |                |                |
    model tier        feature_name      user_id
    (for cost/token)  (for breakdown)   (for per-user)
          |                |                |
    +----------+    +----------+    +----------+
    | by model |    |by feature|    | by user  |
    | report   |    | report   |    | report   |
    +----------+    +----------+    +----------+
          \              |              /
           \             |             /
            +------------+------------+
                         |
               monthly projection
               budget alert threshold
```

---

## البناء

### الخطوة 1: حاسبة التكلفة

```python
from dataclasses import dataclass

# Pricing per 1M tokens (USD, 2026)
PRICING = {
    "claude-3-5-haiku-20241022": {
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,
        "cache_read": 0.08,
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-opus-4-5": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
}


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """
    Compute the USD cost of a single API call.
    Returns cost in dollars (e.g., 0.00034 for a typical short Haiku call).
    """
    prices = PRICING.get(model, PRICING["claude-3-5-haiku-20241022"])
    cost = (
        (input_tokens * prices["input"])
        + (output_tokens * prices["output"])
        + (cache_write_tokens * prices["cache_write"])
        + (cache_read_tokens * prices["cache_read"])
    ) / 1_000_000
    return round(cost, 8)
```

### الخطوة 2: مخزن التكلفة في SQLite

```python
import sqlite3
from datetime import datetime, timezone

DB_PATH = "llm_costs.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS llm_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    model TEXT NOT NULL,
    feature_name TEXT NOT NULL DEFAULT 'unknown',
    user_id TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    latency_ms REAL
);
"""

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_SQL)
    conn.commit()
    return conn


def record_cost(
    conn: sqlite3.Connection,
    model: str,
    input_tokens: int,
    output_tokens: int,
    feature_name: str = "unknown",
    user_id: str | None = None,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    latency_ms: float | None = None,
) -> float:
    """Record a single API call's cost. Returns the computed cost_usd."""
    cost = compute_cost(
        model, input_tokens, output_tokens, cache_write_tokens, cache_read_tokens
    )
    conn.execute(
        """INSERT INTO llm_costs
           (ts, model, feature_name, user_id, input_tokens, output_tokens,
            cache_write_tokens, cache_read_tokens, cost_usd, latency_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            model,
            feature_name,
            user_id,
            input_tokens,
            output_tokens,
            cache_write_tokens,
            cache_read_tokens,
            cost,
            latency_ms,
        ),
    )
    conn.commit()
    return cost
```

> **اختبار من الواقع:** يسألك رئيس المنتج: "هل تستطيع إخباري كم تكلّفنا ميزة البحث بالذكاء الاصطناعي لكل مستخدم شهريًا مقابل ميزة التلخيص بالذكاء الاصطناعي؟" استعرض بالضبط البيانات التي ستحتاجها في مخطط قاعدة بياناتك للإجابة عن هذا السؤال، وما إذا كان المخطط أعلاه كافيًا.

### الخطوة 3: تقرير تفصيل التكلفة

```python
def cost_report(conn: sqlite3.Connection) -> str:
    """
    Generate an ASCII cost breakdown report.
    Shows total cost by model, by feature, and top users.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("LLM COST REPORT")
    lines.append("=" * 60)

    # Total
    row = conn.execute(
        "SELECT SUM(cost_usd), SUM(input_tokens), SUM(output_tokens), COUNT(*) FROM llm_costs"
    ).fetchone()
    total_cost, total_in, total_out, total_calls = row
    lines.append(f"\nTotal calls : {total_calls:,}")
    lines.append(f"Total cost  : ${total_cost or 0:.4f}")
    lines.append(f"Input tokens: {total_in or 0:,}")
    lines.append(f"Output tokens: {total_out or 0:,}")

    # By model
    lines.append("\n--- By Model ---")
    lines.append(f"{'Model':<35} {'Calls':>6} {'Cost ($)':>10} {'% Total':>8}")
    lines.append("-" * 62)
    for model, calls, cost in conn.execute(
        "SELECT model, COUNT(*), SUM(cost_usd) FROM llm_costs GROUP BY model ORDER BY cost_usd DESC"
    ):
        pct = (cost / total_cost * 100) if total_cost else 0
        lines.append(f"{model:<35} {calls:>6} {cost:>10.4f} {pct:>7.1f}%")

    # By feature
    lines.append("\n--- By Feature ---")
    lines.append(f"{'Feature':<25} {'Calls':>6} {'Cost ($)':>10} {'Avg Cost':>10}")
    lines.append("-" * 55)
    for feat, calls, cost in conn.execute(
        "SELECT feature_name, COUNT(*), SUM(cost_usd) FROM llm_costs GROUP BY feature_name ORDER BY cost_usd DESC"
    ):
        avg = cost / calls if calls else 0
        lines.append(f"{feat:<25} {calls:>6} {cost:>10.4f} {avg:>10.6f}")

    # Top users by cost
    lines.append("\n--- Top 5 Users by Cost ---")
    lines.append(f"{'User ID':<20} {'Calls':>6} {'Cost ($)':>10}")
    lines.append("-" * 40)
    for uid, calls, cost in conn.execute(
        "SELECT COALESCE(user_id, 'anonymous'), COUNT(*), SUM(cost_usd) "
        "FROM llm_costs GROUP BY user_id ORDER BY cost_usd DESC LIMIT 5"
    ):
        lines.append(f"{str(uid):<20} {calls:>6} {cost:>10.4f}")

    return "\n".join(lines)
```

### الخطوة 4: تنبيه الميزانية

```python
from datetime import date


def monthly_projection(conn: sqlite3.Connection) -> float:
    """Project current month's total cost to end-of-month."""
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    days_elapsed = today.day
    days_in_month = 30  # approximate

    row = conn.execute(
        "SELECT SUM(cost_usd) FROM llm_costs WHERE ts >= ?",
        (month_start,),
    ).fetchone()
    cost_so_far = row[0] or 0.0

    if days_elapsed == 0:
        return 0.0
    return cost_so_far / days_elapsed * days_in_month


def check_budget_alert(
    conn: sqlite3.Connection,
    monthly_budget_usd: float,
    alert_threshold: float = 0.8,
) -> dict:
    """
    Returns alert status if projected spend exceeds threshold * budget.
    alert_threshold=0.8 means alert at 80% of budget.
    """
    projection = monthly_projection(conn)
    ratio = projection / monthly_budget_usd if monthly_budget_usd > 0 else 0
    return {
        "projected_monthly_usd": round(projection, 4),
        "budget_usd": monthly_budget_usd,
        "utilization_pct": round(ratio * 100, 1),
        "alert": ratio >= alert_threshold,
        "message": (
            f"ALERT: Projected spend ${projection:.2f} is "
            f"{ratio*100:.0f}% of ${monthly_budget_usd:.2f} monthly budget"
            if ratio >= alert_threshold
            else "Within budget"
        ),
    }
```

---

## الاستخدام

يغلّف صنف `CostAccounting` ما سبق في واجهة واحدة متماسكة، ويضيف عارض جدول ASCII خاليًا من `pandas` كي يعمل التقرير دون أي مكتبات إضافية.

```python
class CostAccounting:
    """
    High-level interface to cost tracking.
    Use this in your FastAPI middleware or LLM wrapper.
    """

    def __init__(self, db_path: str = "llm_costs.db"):
        self.conn = init_db(db_path)

    def track(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        feature_name: str = "unknown",
        user_id: str | None = None,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
        latency_ms: float | None = None,
    ) -> float:
        """Record a call. Returns cost in USD."""
        return record_cost(
            self.conn,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            feature_name=feature_name,
            user_id=user_id,
            cache_write_tokens=cache_write_tokens,
            cache_read_tokens=cache_read_tokens,
            latency_ms=latency_ms,
        )

    def report(self) -> str:
        return cost_report(self.conn)

    def budget_alert(self, monthly_budget_usd: float) -> dict:
        return check_budget_alert(self.conn, monthly_budget_usd)
```

تدمج `CostAccounting.track()` عند الطبقة نفسها التي فيها logger طلبات LLM (L05). كلاهما يشترك في حقول الاستخدام نفسها من استجابة الـ API.

**كيف تبدو إضافة هذا إلى مجموعة أدواتك (stack):**

```python
accounting = CostAccounting()

# In your API call wrapper:
cost = accounting.track(
    model=response.model,
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens,
    feature_name="search_intent_classifier",
    user_id=current_user.id,
)
```

> **نقلة في المنظور:** يقول مدير تقني (CTO) في شركة ناشئة: "ننفق 400 دولار شهريًا على استدعاءات LLM. هذا لا شيء - نجني 40,000 دولار شهريًا من الإيرادات. لماذا نبني نظام محاسبة تكلفة الآن؟" عند أي نسبة إيراد-إلى-تكلفة-ذكاء-اصطناعي يتوقف التجهيز عن كونه اختياريًا، وما الإشارة التشغيلية (لا حدّ بالدولار) التي تخبرك بالجواب؟

---

## التسليم

**المُخرَج (Artifact):** `outputs/skill-cost-dashboard.md`

يُنتج هذا الدرس صنف `CostAccounting` مدعومًا بـ SQLite. الصنف جاهز للإدراج (drop-in) في أي مشروع. لحجم الإنتاج (ملايين الاستدعاءات يوميًا)، استبدل backend الخاص بـ SQLite بجدول سلاسل زمنية (time-series) في Postgres أو بمخزن عمودي (columnar store) مثل ClickHouse: تبقى الواجهة نفسها.

تقرير ASCII مناسب لبوت ملخّص يومي في Slack أو لمهمة cron تُرسل ملخصات التكلفة بالبريد لفريق الهندسة. لا حاجة لواجهة أمامية (frontend).

---

## التقييم

**التحقق 1: تكلفة كل استدعاء دقيقة**

تحقّق من صيغة التكلفة مقابل صفحة تسعير Anthropic المنشورة. لاستدعاء Haiku بـ 100 token مُدخَل و50 token مُخرَج:

```python
cost = compute_cost("claude-3-5-haiku-20241022", 100, 50)
# Expected: (100 * 0.80 + 50 * 4.00) / 1_000_000
# = (80 + 200) / 1_000_000 = 0.00000028
assert abs(cost - 0.00000028) < 1e-10
```

**التحقق 2: تفصيل الميزة قابل للاستعلام**

بعد تسجيل 10 استدعاءات بـ `feature_name="search"` و5 بـ `feature_name="summarize"`، يجب أن يُظهر التقرير صفّين في تفصيل الميزات بأعداد استدعاءات وتكاليف دقيقة.

**التحقق 3: تنبيه الميزانية يُطلَق عند الحد الصحيح**

```python
alert = check_budget_alert(conn, monthly_budget_usd=100.0, alert_threshold=0.8)
# If projected >= $80, alert["alert"] should be True
```

**التحقق 4: روافع التكلفة الثلاث الرئيسية مرئية**

بعد أسبوع من بيانات الإنتاج:
- شغّل تفصيل النماذج: إذا لم يكن أرخص نموذج لديك هو من يعالج أكثر الاستدعاءات، فتلك مشكلة توجيه (routing) تستحق التحقيق
- شغّل تفصيل الميزات: إذا شكّلت ميزة واحدة أكثر من 50% من التكلفة، انظر إلى تردد استدعائها وطول الـ prompt الخاص بها
- استعلم `SELECT AVG(output_tokens) FROM llm_costs GROUP BY feature_name`: أي ميزة متوسطها 1,000+ token مُخرَج مرشّحة لتعليمات طول صريحة
