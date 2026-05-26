---
name: skill-mcp-resources-prompts
description: Resource URI template patterns and prompt template design for MCP servers beyond tools
version: "1.0"
phase: "03"
lesson: "10"
tags: [mcp, resources, prompts, uri-templates, tool-design]
---

# MCP Resources and Prompts Pattern Guide

Use this guide when designing an MCP server and deciding whether a capability should be a tool, a resource, or a prompt.

## Decision Matrix

```
Question                                      Answer           Primitive
────────────────────────────────────────────  ───────────────  ─────────
Does the LLM need to decide when to use it?   Yes              Tool
Is it read-only data the client can cache?    Yes              Resource
Does it change rarely (docs, schema, config)? Yes              Resource
Is it keyed by an ID or URI pattern?          Yes              Resource
Is it a workflow the LLM should execute?      Yes              Prompt
Should multiple clients share the template?   Yes              Prompt
Does it write state or call an API?           Yes              Tool (only)
```

## Resource URI Patterns

### Static resource

```python
@mcp.resource("docs://api-reference")
def get_api_reference() -> str:
    """Full API reference documentation."""
    return Path("docs/api-reference.md").read_text()
```

Use for: documentation, changelogs, static configs, system schemas.

### Dynamic resource with URI template

```python
@mcp.resource("user://{user_id}/profile")
def get_user_profile(user_id: str) -> str:
    """User profile data addressed by user ID."""
    user = db.get_user(user_id)
    if not user:
        return f"User {user_id} not found."
    return f"Name: {user.name}\nEmail: {user.email}\nRole: {user.role}"
```

Use for: records keyed by ID, per-entity docs, per-environment configs.

### Nested path pattern

```python
@mcp.resource("config://{environment}/{service}")
def get_service_config(environment: str, service: str) -> str:
    """Configuration for a specific service in a specific environment."""
    key = f"{environment}/{service}"
    return CONFIGS.get(key, f"No config for {service} in {environment}")
```

### JSON resource (for structured data injection)

```python
@mcp.resource("db://products/all")
def get_all_products() -> str:
    """All products as JSON for LLM context injection."""
    return json.dumps(load_products(), indent=2)
```

Return type is always `str`. Serialize structured data to JSON or formatted text before returning.

## Prompt Template Patterns

### Single required argument

```python
@mcp.prompt()
def analyze_data(time_period: str) -> str:
    """Analyze data for a specific time period."""
    data = json.dumps(fetch_recent_data(), indent=2)
    return (
        f"Analyze the following data for {time_period}.\n\n"
        f"Data:\n{data}\n\n"
        "Cover: total volume, top performer, anomalies, one recommendation."
    )
```

### Multiple arguments with defaults

```python
@mcp.prompt()
def generate_report(topic: str, format: str = "bullet_points", depth: str = "summary") -> str:
    """Generate a structured report on a topic."""
    return (
        f"Generate a {depth}-level report on: {topic}\n"
        f"Output format: {format}\n"
        "Include: background, current state, key findings, next steps."
    )
```

### Prompt that injects resource data

```python
@mcp.prompt()
def review_schema_query(sql_query: str) -> str:
    """Review a SQL query against the current schema."""
    # Fetch data at render time, not at definition time
    schema = get_schema_text()
    return (
        f"Review this SQL query for correctness against the schema below.\n\n"
        f"Schema:\n{schema}\n\n"
        f"Query to review:\n{sql_query}\n\n"
        "Identify: syntax errors, incorrect column names, missing joins, performance issues."
    )
```

Key: fetch live data inside the function body, not at module load time.

## Client Usage Patterns

```python
# List and read resources
resources = await session.list_resources()
for r in resources.resources:
    content = await session.read_resource(r.uri)
    print(f"{r.uri}: {content.contents[0].text[:100]}")

# Read a URI-template resource
user_profile = await session.read_resource("user://u123/profile")

# List and render prompts
prompts = await session.list_prompts()
rendered = await session.get_prompt(
    "analyze_data",
    {"time_period": "last 30 days"},
)
# rendered.messages is a list of {role, content} dicts
# Pass directly to the LLM messages parameter
messages = [{"role": m.role, "content": m.content.text} for m in rendered.messages]
```

## Common Mistakes

- **Tool for static data:** Using a tool to return a schema or docs that never change. Define a resource so the client can cache and inject without an LLM round-trip.
- **Prompt data captured at startup:** Fetching live data in module scope and embedding it in a prompt template. The template will serve stale data. Always fetch inside the function body.
- **Missing fallback for URI template:** When the ID in `user://{user_id}` does not exist, return a clear "not found" message rather than crashing or returning an empty string. Empty returns are silently injected into context with no indication of the failure.
- **Prompt returns None:** If a prompt function returns `None` (e.g., because an if-branch falls through), the client receives an empty message list. Always return a string from every code path.
