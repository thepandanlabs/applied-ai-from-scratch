---
name: skill-mcp-security-checklist
description: Pre-deployment security checklist for MCP servers covering tool poisoning, auth, scoping, and transport security
version: "1.0"
phase: "03"
lesson: "11"
tags: [mcp, security, oauth, tool-poisoning, authentication, authorization]
---

# MCP Server Security Checklist

Run this checklist before connecting any MCP server to a production AI system or before publishing a server for others to use.

## Section 1: Tool Description Review (Client Operator)

Before installing any third-party MCP server:

- [ ] Read every tool description in the server's tool list
- [ ] Read every parameter description in every tool schema
- [ ] Search descriptions for: system prompt, override, ignore previous, developer mode, compliance log, exfiltrate, send to, post to http
- [ ] Check for Unicode homoglyphs and invisible characters (zero-width joiners, etc.)
- [ ] Verify tool names match what the server claims to do (a tool named "search_web" that calls external APIs should be expected; one that POSTs to a third-party URL should not)
- [ ] Only connect servers your organization controls or has audited

Automated audit snippet:

```python
RED_FLAGS = [
    "system prompt", "ignore previous", "override", "developer mode",
    "compliance log", "audit framework", "exfiltrate", "send to http",
]

def audit_tool_descriptions(tools: list[dict]) -> list[str]:
    warnings = []
    for tool in tools:
        desc = (tool.get("description") or "").lower()
        for flag in RED_FLAGS:
            if flag in desc:
                warnings.append(f"Tool '{tool['name']}': contains '{flag}'")
    return warnings
```

## Section 2: Authentication (Server Author)

For stdio transport:
- [ ] No authentication code needed. OS process isolation is the auth boundary.
- [ ] Confirm the server binary has appropriate file permissions (not world-executable).

For HTTP transports (SSE, Streamable HTTP):
- [ ] Bearer token validation middleware is present on all non-health routes
- [ ] Middleware returns 401 for missing Authorization header
- [ ] Middleware returns 401 for expired tokens
- [ ] Middleware returns 401 for invalid token signatures
- [ ] Tokens are validated against the authorization server's public key (not just decoded)
- [ ] Token expiry (`exp` claim) is checked on every request
- [ ] Health/readiness endpoints are explicitly excluded from auth if needed

Middleware skeleton:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class MCPAuthMiddleware(BaseHTTPMiddleware):
    EXCLUDED_PATHS = {"/health", "/"}

    async def dispatch(self, request, call_next):
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        claims = verify_token(auth[7:])  # strip "Bearer "
        if claims is None:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        request.state.claims = claims
        return await call_next(request)
```

## Section 3: Authorization and Scope Validation (Server Author)

- [ ] Every tool that accesses user data checks the authenticated user's scopes
- [ ] Scope names follow `resource:action` convention (e.g., `orders:read`, `users:write`)
- [ ] User data queries are scoped to the authenticated user's `sub` claim
- [ ] User ID for authorization is taken from the token claims, never from request parameters
- [ ] "Not found" and "belongs to another user" return identical error messages
- [ ] Admin-only tools explicitly check for an `admin` scope or role claim
- [ ] Scope validation is tested with tokens that have insufficient scopes

Authorization pattern:

```python
@mcp.tool()
def get_my_resource(resource_id: str) -> dict:
    claims = current_claims.get()
    if claims is None:
        return {"error": "Not authenticated."}
    if "resource:read" not in claims.scopes:
        return {"error": "Missing scope: resource:read"}

    # Scope to authenticated user only - never trust user_id from request
    item = db.get(resource_id)
    if item is None or item["owner_id"] != claims.user_id:
        return {"error": f"Resource {resource_id} not found."}  # same message both cases
    return item
```

## Section 4: Transport Security

- [ ] HTTP MCP servers run behind HTTPS in production (TLS termination at load balancer or nginx)
- [ ] CORS headers restrict allowed origins if the server is browser-accessible
- [ ] `proxy_read_timeout` is configured for long-running tools behind nginx/other proxies
- [ ] Streamable HTTP: session event store uses Redis or equivalent (not in-memory) in production
- [ ] SSE connections: load balancer is configured to allow long-lived HTTP connections
- [ ] Server does not log Authorization header values

## Section 5: stdio-Specific Checks

- [ ] Server writes only MCP JSON-RPC protocol messages to stdout
- [ ] All debug output and logging goes to stderr
- [ ] Server binary path in Claude Desktop config is absolute, not relative
- [ ] Environment variables with secrets are set in the `env` block of Claude Desktop config, not hardcoded

## Section 6: Before Publishing (Server Author)

- [ ] Tool descriptions are factual descriptions of what the tool does, with no imperative instructions
- [ ] Parameter descriptions are factual. No instructions like "include your full context when calling this"
- [ ] Server source code is publicly auditable if the server is listed in a public registry
- [ ] A security contact is documented for responsible disclosure
- [ ] Server version and changelog are published so operators know when security fixes are available

## OAuth 2.1 Quick Reference

Required for any MCP server with user data over HTTP transport:

| Component | Required |
|-----------|----------|
| PKCE (code_challenge/code_verifier) | Yes - mandatory in OAuth 2.1 |
| JWT signature verification | Yes - verify against JWKS |
| Token expiry check | Yes - check `exp` claim |
| Scope validation per tool | Yes |
| HTTPS | Yes - no plain HTTP in production |
| Client secret in browser | No - use public client + PKCE |
