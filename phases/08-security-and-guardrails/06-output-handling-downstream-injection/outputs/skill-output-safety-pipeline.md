---
name: skill-output-safety-pipeline
description: Reference card for safely handling model output before it reaches SQL databases, HTML renderers, or shell commands. Use when reviewing code that passes model output to any execution context.
version: "1.0"
phase: "08"
lesson: "06"
tags: [security, owasp-llm05, sql-injection, xss, command-injection, output-handling]
---

# Skill: Output Safety Pipeline

## Purpose

You are an applied AI security advisor specializing in output handling. Use this skill when reviewing code that passes model output to downstream systems, or when implementing any feature that uses model output in a SQL query, HTML page, or shell command.

---

## The Core Rule

**Treat model output like user input for every downstream system.**

A model is a text generator. It does not enforce security policies. Any string a malicious user could craft, the model could also generate -- either through jailbreaking or prompt injection in retrieved content.

---

## The Three Injection Vectors

```
MODEL OUTPUT
     |
     +---> SQL context    → parameterized queries + allowlists for column names
     +---> HTML context   → html.escape() or bleach.clean() with allowlist
     +---> Shell context  → allowlist validation + list form + shell=False
```

---

## Safe Patterns by Context

### SQL: Values

Always use parameterized queries. Never string-interpolate.

```python
# WRONG - injection possible
query = f"SELECT * FROM orders WHERE status = '{model_output}'"

# RIGHT - driver binds value as data, never as SQL
conn.execute("SELECT * FROM orders WHERE status = ?", (model_output,))
# psycopg2: use %s placeholder
cur.execute("SELECT * FROM orders WHERE status = %s", (model_output,))
```

### SQL: Column and Table Names

Column names cannot be parameterized. Use an allowlist.

```python
ALLOWED_COLUMNS = frozenset({"status", "created_at", "total_amount"})

if model_output not in ALLOWED_COLUMNS:
    raise ValueError(f"Invalid column: {model_output!r}")
query = f"SELECT * FROM orders ORDER BY {model_output}"  # safe after allowlist
```

### HTML: Plain Text

```python
import html
safe = html.escape(model_output, quote=True)
rendered = f"<div>{safe}</div>"
```

### HTML: Rich Text (formatted output)

```python
import bleach
ALLOWED_TAGS = ["b", "i", "em", "strong", "p", "ul", "ol", "li", "br", "code"]
safe = bleach.clean(model_output, tags=ALLOWED_TAGS, attributes={}, strip=True)
```

### Shell: Subprocess

```python
ALLOWED_VALUES = frozenset({"report_a", "report_b"})

if model_output not in ALLOWED_VALUES:
    raise ValueError(f"Not in allowlist: {model_output!r}")

# list form: shell is never invoked, no shell metacharacter interpretation
subprocess.run(["my_script.sh", model_output], shell=False, timeout=30)
```

---

## Never Use

| Pattern | Why it is unsafe |
|---------|-----------------|
| `f"SELECT ... WHERE x = '{model_output}'"` | SQL injection |
| `f"<div>{model_output}</div>"` | XSS |
| `subprocess.run(f"cmd {model_output}", shell=True)` | Command injection |
| `eval(model_output)` | Arbitrary code execution |
| `exec(model_output)` | Arbitrary code execution |
| `os.system(model_output)` | Command injection |

---

## Code Review Checklist

Search for these patterns before merging any code that uses model output:

- `shell=True` with a variable derived from model output
- f-strings containing model output variables before SQL keywords
- `innerHTML =` or equivalent in frontend code with model output
- `eval(` or `exec(` with model output
- `.format(` called on a SQL string with model output

Each hit requires a comment explaining the safe pattern being used, or must be replaced.

---

## Diagnostic Questions

When reviewing a code path that uses model output:

1. Where does this output go next? (SQL, HTML, shell, log, file)
2. Is the output treated as data or as code/markup by the destination?
3. What is the worst-case payload if an attacker controls this string?
4. Which safe pattern applies to this context?

---

## Testing

**SQL injection:** Pass `"' OR '1'='1"` as a status filter. Safe code returns 0 rows. Vulnerable code returns all rows.

**XSS:** Pass `"<script>alert(1)</script>"` as content. Safe code shows the literal text in the browser. Vulnerable code triggers the alert.

**Shell injection:** Pass `"report; echo pwned"` as a report name. Safe code raises ValueError. Vulnerable code executes both commands.
