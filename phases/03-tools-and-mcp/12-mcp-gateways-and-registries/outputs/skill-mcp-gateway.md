---
name: skill-mcp-gateway
description: Gateway config schema, namespace routing pattern, and private registry entry format for multi-server MCP deployments
version: "1.0"
phase: "03"
lesson: "12"
tags: [mcp, gateway, registry, routing, platform]
---

# MCP Gateway Skill

Use this artifact when you need to route tool calls across multiple MCP servers behind a single entry point.

---

## Gateway Config Schema

```yaml
# gateway.yaml
gateway:
  name: "string: human-readable gateway name"
  port: 8000  # port the gateway listens on

servers:
  - name: "string: unique server identifier"
    namespace: "string: prefix used for all tools from this server (no colons)"
    url: "string: URL of the upstream MCP server"
    auth:
      type: "bearer_token | api_key | oauth2 | none"
      token_env: "ENV_VAR_NAME"   # for bearer_token
      key_env: "ENV_VAR_NAME"     # for api_key
      client_id_env: "ENV_VAR_NAME"   # for oauth2
      client_secret_env: "ENV_VAR_NAME"  # for oauth2
      token_url: "string"         # for oauth2
    health_check:
      url: "string: endpoint to GET; 200 = healthy"
      interval_seconds: 30
      timeout_seconds: 5
    tools:
      - "string: exact tool name as registered on the upstream server"
```

### Namespace Naming Rules

- Lowercase alphanumeric and hyphens only: `crm`, `data-warehouse`, `tickets`
- No colons (`:` is the delimiter between namespace and tool name)
- Globally unique within the gateway config
- Should match the team or system name for discoverability

---

## Routing Pattern

```
Client sends:  tools/call  "namespace::tool_name"  {arguments}
                           |
                           v
             Split on "::" (first occurrence only)
             left  = namespace
             right = tool_name
                           |
                           v
             Lookup namespace in server index
             - Not found:  return {"error": "unknown_namespace", ...}
             - Unhealthy:  return {"error": "server_unavailable", "retry_after_seconds": N}
             - Found:      forward (tool_name, arguments) to upstream server
                           |
                           v
             Return upstream response verbatim
```

### Routing Code Reference

```python
def route_tool_call(tool_name: str, arguments: dict, servers: dict) -> Any:
    if "::" not in tool_name:
        return {"error": "invalid_tool_name",
                "message": f"Expected 'namespace::tool_name', got '{tool_name}'"}
    namespace, raw_name = tool_name.split("::", 1)
    if namespace not in servers:
        return {"error": "unknown_namespace",
                "available": list(servers.keys())}
    return servers[namespace].call(raw_name, arguments)
```

---

## Discovery Pattern

```python
def aggregate_tools(servers: dict) -> list[dict]:
    """Prefix all tool schemas with their server namespace."""
    result = []
    for namespace, server in servers.items():
        if not server.healthy:
            continue
        for schema in server.list_tools():
            prefixed = dict(schema)
            prefixed["name"] = f"{namespace}::{schema['name']}"
            result.append(prefixed)
    return result
```

---

## Private Registry Entry Format

```yaml
# registry-entry.yaml
# Submit this file to the platform team to add your server to the gateway.

name: "crm-server"
description: "Salesforce CRM read/write via REST API"
namespace: "crm"
version: "2.1.0"
url: "http://crm-mcp.internal:8001"
health_endpoint: "http://crm-mcp.internal:8001/health"
auth_type: "bearer_token"
tools:
  - name: get_contact
    description: "Retrieve a CRM contact by ID"
    required_args: [id]
  - name: search_contacts
    description: "Search contacts by name, email, or company"
    required_args: [query]
  - name: create_contact
    description: "Create a new contact record"
    required_args: [name, email]
resources:
  - "crm://contacts/recent"
prompts:
  - "draft_outreach(contact_id)"
owner: "crm-platform-team@company.com"
sla: "99.5% uptime, p95 response < 200ms"
data_classification: "confidential"  # public | internal | confidential | restricted
```

---

## Claude Desktop Config (Gateway Mode)

```json
{
  "mcpServers": {
    "engineering-gateway": {
      "command": "python",
      "args": ["/path/to/gateway_server.py", "--config", "/path/to/gateway.yaml"],
      "env": {
        "GATEWAY_API_KEY": "your-gateway-key"
      }
    }
  }
}
```

One entry. All servers.

---

## Health Check Response Contract

Upstream servers must respond to `GET /health` with:

```json
{
  "status": "ok",
  "server": "crm-server",
  "version": "2.1.0",
  "uptime_seconds": 86400,
  "tool_count": 3
}
```

Non-200 or missing response means the gateway marks the server unhealthy and removes its tools from `tools/list` until the next successful health check.

---

## Token Rotation Procedure

1. Generate new token for the upstream server.
2. Update the environment variable referenced in `gateway.yaml` (e.g., `CRM_MCP_TOKEN`).
3. Reload the gateway config (SIGHUP or restart).
4. Verify health check passes for the affected server.
5. Revoke the old token.

No app configs change. No client restarts required.
