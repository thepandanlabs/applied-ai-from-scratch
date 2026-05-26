---
name: runbook-mcp-ecosystem
description: Production runbook for the Engineering Operations MCP ecosystem: adding servers, rotating tokens, monitoring health, and debugging tool call failures
version: "1.0"
phase: "03"
lesson: "14"
tags: [mcp, runbook, operations, gateway, incident-response]
---

# Engineering Operations MCP Ecosystem: Production Runbook

This runbook is for the engineer operating the ecosystem, not the engineer who built it. If you are reading this at 2am during an incident, go to the section that matches your situation.

---

## Quick Reference

| What you need | Where to find it |
|---------------|------------------|
| Start the gateway | `python main.py --server` |
| Run health checks | `python main.py --test` |
| Gateway config | `gateway.yaml` |
| Server credentials | `.env` file (never committed) |
| Add a new server | Section 1 below |
| Rotate a token | Section 2 below |
| Monitor health | Section 3 below |
| Debug a tool failure | Section 4 below |

---

## Section 1: Adding a New Server

### When to use this section

A team wants to add a new MCP server to the ecosystem (example: a new deployment-pipeline server from the DevOps team).

### Process

**Step 1: Review the registry entry**

The team submitting the new server must provide a completed registry entry. Required fields:

```yaml
name: "deployment-server"
namespace: "deploy"
description: "Deployment pipeline: trigger, status, rollback"
version: "1.0.0"
url: "http://deploy-mcp.internal:8004"
health_endpoint: "http://deploy-mcp.internal:8004/health"
auth_type: "bearer_token"
token_env: "DEPLOY_SERVER_TOKEN"
tools:
  - trigger_deployment(service, version)
  - get_deployment_status(deployment_id)
  - rollback_deployment(service)
owner: "devops-team@company.com"
sla: "99% uptime, p95 < 500ms"
data_classification: "internal"
```

**Step 2: Check namespace uniqueness**

```bash
grep "namespace:" gateway.yaml | grep "deploy"
# Must return no results
```

If the namespace conflicts with an existing server, work with the submitting team to choose a unique name.

**Step 3: Add to gateway config**

Add a new block to `gateway.yaml` under `servers:`:

```yaml
  - name: deployment-server
    namespace: deploy
    url: http://deploy-mcp.internal:8004
    auth:
      type: bearer_token
      token_env: DEPLOY_SERVER_TOKEN
    health_check:
      url: http://deploy-mcp.internal:8004/health
      interval_seconds: 30
      timeout_seconds: 5
```

**Step 4: Add the credential**

Add the token to the `.env` file (or secrets manager):

```bash
echo "DEPLOY_SERVER_TOKEN=<token-value>" >> .env
```

**Step 5: Reload and verify**

```bash
# Reload the gateway (SIGHUP or restart)
kill -HUP $(pgrep -f "main.py --server")

# Verify the new server appears in tools/list
python main.py --test 2>&1 | grep "deploy::"
# Expected: deploy::trigger_deployment, deploy::get_deployment_status, deploy::rollback_deployment

# Verify health check passes
python main.py --test 2>&1 | grep "deploy"
```

**Rollback if something goes wrong:**

Remove the block from `gateway.yaml`, remove the env var, reload. The ecosystem returns to its previous state.

---

## Section 2: Rotating Auth Tokens

### When to use this section

An upstream server rotated its API token, or you are rotating tokens on a schedule.

### Zero-downtime rotation procedure

Zero-downtime rotation uses token overlap: the new token is active before the old one is revoked.

**Step 1: Generate the new token**

On the upstream server or via the credentials manager, generate a new token. Do not revoke the old token yet.

**Step 2: Update the gateway credential**

```bash
# Update the env var for the affected server
# Example: rotating the code-server token
export CODE_SERVER_TOKEN=<new-token-value>

# Or update the .env file:
sed -i '' 's/CODE_SERVER_TOKEN=.*/CODE_SERVER_TOKEN=<new-token-value>/' .env
```

**Step 3: Reload the gateway**

```bash
kill -HUP $(pgrep -f "main.py --server")
```

**Step 4: Verify the new token works**

```bash
# Make a test call to the affected server
python -c "
from main import build_gateway
gw = build_gateway()
result = gw.call_tool('code::list_directory', {'path': '/'})
print('OK' if 'error' not in result else f'FAIL: {result}')
"
```

**Step 5: Revoke the old token**

Only after Step 4 confirms the new token works, revoke the old token on the upstream server.

### Token map

| Server | Namespace | Env variable | Who owns the token |
|--------|-----------|-------------|-------------------|
| code-server | code | `CODE_SERVER_TOKEN` | platform-team |
| incidents-server | incidents | `INCIDENTS_SERVER_TOKEN` | sre-team |
| metrics-server | metrics | `METRICS_SERVER_TOKEN` | observability-team |

---

## Section 3: Monitoring Health

### Gateway health status

The gateway exposes a status dict via the Python API. For HTTP health monitoring, wrap this in a `/health` endpoint:

```python
# GET /health returns:
{
  "servers": [
    {"namespace": "code",      "name": "code-server",      "healthy": true,  "tool_count": 3},
    {"namespace": "incidents", "name": "incidents-server", "healthy": true,  "tool_count": 3},
    {"namespace": "metrics",   "name": "metrics-server",   "healthy": true,  "tool_count": 2}
  ],
  "total_tools": 8
}
```

A `healthy: false` entry means that server's health check failed. Its tools are removed from `tools/list`. Agents will not attempt calls to it until health is restored.

### Alert conditions

| Condition | Severity | Action |
|-----------|----------|--------|
| Any server `healthy: false` for > 5 minutes | P2 | Page SRE, check server logs |
| Gateway process not responding | P1 | Restart gateway, page platform-team |
| Tool call error rate > 5% in 15 minutes | P2 | Check gateway logs, check upstream server |
| All servers `healthy: false` | P1 | Gateway config or network issue, page platform-team |

### Running the test suite as a health probe

```bash
# Run in CI or as a cron job
python main.py --test
echo "Exit code: $?"
# 0 = all tests passed
# 1 = one or more tests failed (ecosystem is degraded)
```

---

## Section 4: Debugging Tool Call Failures

### Step 1: Identify the failure type

```
Tool call failed. What did the error dict say?

"error": "invalid_tool_name"    -> Missing namespace prefix. Client bug.
"error": "unknown_namespace"    -> Namespace not in gateway config.
"error": "server_unavailable"   -> Health check failed for that server.
Any other error                  -> Upstream server returned an error.
```

### Step 2: Reproduce the failure

```python
from main import build_gateway

gateway = build_gateway()

# Reproduce exactly what the client called
result = gateway.call_tool("code::search_codebase", {"query": "auth"})
print(result)
```

Run this on the gateway host, not your local machine. Network and auth differences matter.

### Step 3: Isolate the component

```
Did the call reach the gateway?
  YES -> Check if namespace is in gateway config: grep "namespace:" gateway.yaml
  NO  -> Client-side configuration issue (wrong URL, wrong command)

Did the gateway route to the right server?
  YES -> Check upstream server logs for the tool call
  NO  -> Namespace mismatch: tool name prefix does not match any namespace in config

Did the upstream server respond?
  YES -> Check the response structure for error fields
  NO  -> Server health check failing: check server process, port, auth token

Did the upstream server return an error?
  YES -> The tool's handler returned an error dict. Read "error" and "message" fields.
  NO  -> Unexpected: the call succeeded but the caller received an error. Check serialization.
```

### Step 4: Common fixes

**Tool name has no namespace prefix**
- Cause: Client using old tool name format without `namespace::` prefix
- Fix: Update client to use `namespace::tool_name` format

**`unknown_namespace` error**
- Cause: Client calling a namespace that does not exist in the gateway config
- Fix: Add the server to gateway.yaml and reload, or correct the tool name

**`server_unavailable` error**
- Cause: Health check failing for that server
- Fix: Check if the server process is running, check the health endpoint directly:
  ```bash
  curl http://server-host:port/health
  ```

**Tool returns unexpected error from upstream**
- Cause: Upstream server changed its API, auth token expired, or schema mismatch
- Fix: Check server logs, verify token in .env, check if server was recently updated

**Gateway returns correct result but agent says it failed**
- Cause: Tool result is valid JSON but contains an `"error"` key, which the model interprets as failure
- Fix: Review the tool handler. Success responses should not contain an `"error"` key.

---

## Section 5: Deploying with Docker

### Build and run

```bash
cd phases/03-tools-and-mcp/14-capstone-mcp-ecosystem/code

# Build
docker build -t eng-ops-ecosystem:latest .

# Run as MCP server (default mode)
docker run -it \
  -e CODE_SERVER_TOKEN="${CODE_SERVER_TOKEN}" \
  -e INCIDENTS_SERVER_TOKEN="${INCIDENTS_SERVER_TOKEN}" \
  -e METRICS_SERVER_TOKEN="${METRICS_SERVER_TOKEN}" \
  eng-ops-ecosystem:latest

# Run tests
docker run --rm eng-ops-ecosystem:latest --test

# Run demo
docker run --rm \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  eng-ops-ecosystem:latest python main.py
```

### Claude Desktop with Docker

```json
{
  "mcpServers": {
    "eng-ops-gateway": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "CODE_SERVER_TOKEN",
        "-e", "INCIDENTS_SERVER_TOKEN",
        "-e", "METRICS_SERVER_TOKEN",
        "eng-ops-ecosystem:latest"
      ]
    }
  }
}
```

The `-i` flag keeps stdin open for stdio transport. The `-e` flags pass environment variables from the host to the container.
