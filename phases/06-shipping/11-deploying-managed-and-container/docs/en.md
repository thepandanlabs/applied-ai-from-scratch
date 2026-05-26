# Deploying: Managed and Container Paths

> For an AI service under 10k requests/day, a managed platform costs less in engineering hours than the infra savings from running your own containers.

**Type:** Learn
**Languages:** Python
**Prerequisites:** 05-docker-image-ai-app, 06-config-and-secrets
**Time:** ~60 min
**Learning Objectives:**
- Distinguish managed platforms (Railway, Render, Fly.io) from container platforms (AWS ECS, GCP Cloud Run)
- Deploy the Phase 06 FastAPI service to Railway or Render via CLI
- Configure health checks, environment variables, and log access
- Apply a decision framework to choose the right deployment path for a given service

---

## MOTTO

**Get to a working URL first. Optimize infrastructure later, if ever.**

---

## THE PROBLEM

You have a working FastAPI service that wraps Claude. It has a Dockerfile. It works locally. Now you need to deploy it so other people can use it.

You open AWS documentation. Three hours later you have read about VPCs, IAM roles, ECS task definitions, ALB target groups, and security groups. You have not deployed anything. Your service is still running only on your laptop.

The core mistake is solving the wrong problem. The problem is not "how do I become an infrastructure engineer." The problem is "how do I get a URL that accepts HTTP requests and forwards them to my FastAPI app." A managed platform solves that problem in under 15 minutes.

There are two categories of deployment for AI services. Managed platforms (Railway, Render, Fly.io) take your Dockerfile, run it, give you a URL, handle TLS, restart crashed containers, and expose logs. You pay per second of CPU and RAM. You do not configure networking. Container platforms (AWS ECS/Fargate, GCP Cloud Run) give you more control: custom VPCs, fine-grained IAM, autoscaling policies, multi-region routing. They are appropriate when you hit limits the managed platforms cannot solve.

Most AI services never hit those limits. The decision tree is simpler than the infrastructure blogs make it look.

---

## THE CONCEPT

### Managed vs Container: The Decision Tree

```
Your AI service needs to be deployed.
           |
           v
Is traffic > 10k requests/day OR do you have
a dedicated DevOps/platform team?
           |
          NO ----> Use a managed platform (Railway / Render / Fly.io)
           |         - Dockerfile in, URL out
           |         - No VPC, no IAM, no ALB config
           |         - ~$5-50/month for typical AI service
           |         - Time to working URL: 15-30 minutes
           |
          YES
           |
           v
Do you need custom networking (VPC, private
subnets), compliance controls, or multi-region?
           |
          NO ----> GCP Cloud Run or AWS App Runner
           |         - Serverless containers, scale to zero
           |         - More config than managed, less than ECS
           |         - Good for bursty traffic patterns
           |
          YES ----> AWS ECS/Fargate or GCP GKE
                     - Full control, full responsibility
                     - Team needs infra expertise
                     - 2-4 hours to first deploy
```

### Platform Comparison

```
+------------------+----------+-----------+----------+----------+
|                  | Railway  | Render    | Fly.io   | Cloud Run|
+------------------+----------+-----------+----------+----------+
| Dockerfile       | YES      | YES       | YES      | YES      |
| Time to URL      | 10 min   | 15 min    | 20 min   | 30 min   |
| Scale to zero    | YES      | YES       | NO       | YES      |
| Persistent disk  | add-on   | YES       | YES      | NO       |
| Free tier        | trial    | YES       | trial    | YES      |
| CLI deploy       | railway  | render    | flyctl   | gcloud   |
| Custom domains   | YES      | YES       | YES      | YES      |
| Best for         | demos    | APIs      | latency  | GCP stack|
+------------------+----------+-----------+----------+----------+
```

### What a Deployment Actually Needs

Every deployment of the Phase 06 FastAPI service requires four things:

1. A Dockerfile that builds and starts the app (lesson 05)
2. Environment variables (ANTHROPIC_API_KEY at minimum)
3. A health check endpoint (`GET /health` returning 200)
4. A port the platform routes traffic to (default: 8000)

```
Platform reads Dockerfile
         |
         v
Builds container image
         |
         v
Injects env vars from dashboard / CLI
         |
         v
Starts container, maps port 8000 to HTTPS URL
         |
         v
Health check: GET /health -> 200 OK
         |
         v
Traffic routed to your URL
```

---

## BUILD IT

### Step 1: Add a Health Check to Your FastAPI App

Every platform pings a health endpoint to decide if your container is ready for traffic. Without it, deployments fail silently.

```python
# Add this to your main.py (from lesson 02)
@app.get("/health")
async def health() -> dict[str, str]:
    """Health check. Platforms call this to verify the container is running."""
    return {"status": "ok"}
```

### Step 2: Verify Your Dockerfile

```dockerfile
# Dockerfile (from lesson 05, reproduced for reference)
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PORT env var is set by most managed platforms (default 8000)
ENV PORT=8000
EXPOSE 8000

# Use sh -c so $PORT is expanded at runtime
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
```

```txt
# requirements.txt
fastapi
uvicorn[standard]
anthropic
pydantic
python-dotenv
```

### Step 3: Deploy to Railway

Railway is the fastest path from Dockerfile to URL.

```bash
# Install Railway CLI
curl -fsSL https://railway.app/install.sh | sh

# Log in
railway login

# Initialize a new project in your service directory
railway init

# Set your secret env vars (never in Dockerfile or code)
railway variables set ANTHROPIC_API_KEY=sk-ant-...

# Deploy
railway up
# Railway builds your Dockerfile, starts the container, prints the URL.
# Typical time: 2-4 minutes.
```

Railway auto-detects your Dockerfile. It sets `PORT` automatically and routes HTTPS traffic to it.

### Step 4: Deploy to Render (alternative)

```bash
# Install Render CLI
npm install -g @render-com/cli
# or download from https://render.com/docs/cli

render login

# Create a render.yaml in your project root:
```

```yaml
# render.yaml
services:
  - type: web
    name: ai-service
    runtime: docker
    healthCheckPath: /health
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false   # Render will prompt you to set this securely
```

```bash
render deploy
# Render reads render.yaml, builds the Docker image, deploys it.
```

> **Real-world check:** Both Railway and Render build your Docker image on their servers. This means your `ANTHROPIC_API_KEY` is never in the image layer. The platform injects it as an environment variable at runtime. If you ever see an API key hard-coded in a Dockerfile or committed to git, it is compromised and must be rotated immediately. Managed platforms enforce this pattern by design.

### Step 5: Read Logs

Logs are the primary debugging tool for deployed services. Every platform exposes them via CLI and dashboard.

```bash
# Railway: stream logs from the running deployment
railway logs

# Render: stream logs
render logs --service ai-service

# GCP Cloud Run (for later)
gcloud run services logs read ai-service --region us-central1 --tail 50
```

Look for:
- `Application startup complete` from uvicorn (service is running)
- `GET /health 200` lines (platform health checks passing)
- `4xx` lines (client errors: bad input, auth failures)
- `5xx` lines (server errors: unhandled exceptions, model API errors)

---

## USE IT

`railway up` and `render deploy` each run a multi-step process that you could do manually with `docker build`, `docker push`, and a container runtime command. The managed platform collapses that into one command and handles the rest.

```bash
# What railway up does under the hood:
# 1. Sends your project files to Railway's build servers
# 2. Runs: docker build -t <your-project>:<hash> .
# 3. Pushes the image to Railway's internal registry
# 4. Creates a new deployment with the image
# 5. Injects env vars from the dashboard/CLI
# 6. Starts the container, waits for health check to pass
# 7. Routes traffic from your-project.railway.app to the container
# 8. Keeps the old container running until the new one is healthy (zero-downtime)

# You run one command. The platform runs those 8 steps.
```

The same flow on AWS ECS requires you to: create an ECR repository, configure an IAM role with push permissions, build and push the image yourself, create a task definition JSON, create or update an ECS service, wait for the service to stabilize, and check the target group health in the ALB console.

> **Perspective shift:** Managed platforms are not a shortcut for people who do not know AWS. They are the correct tool for a service that does not need AWS-level control. Engineers who "graduate" from Railway to ECS often discover they are spending 30% of their time on infrastructure that Railway handled automatically. The question is not "is Railway real infrastructure." The question is "does my service need what ECS provides." For most AI services, the answer is no.

---

## SHIP IT

The reusable artifact is `outputs/skill-deployment-decision-guide.md`. It contains:
- The managed vs container decision tree
- Platform comparison table
- Railway and Render deployment checklists
- Environment variable checklist for AI services
- Log patterns to watch for

---

## EVALUATE IT

**Test 1: Health check.** After deploying, `curl https://your-service.railway.app/health`. Verify HTTP 200 and `{"status": "ok"}`. If the platform shows the deployment as failed, this is the first thing to check.

**Test 2: Generate endpoint.** `curl -X POST https://your-service.railway.app/generate -H 'Content-Type: application/json' -d '{"prompt": "Say hello."}'`. Verify a valid JSON response with a `text` field.

**Test 3: Secrets are not in the image.** Run `railway run printenv | grep ANTHROPIC`. Verify the key appears as an environment variable, not as a build arg or file. Never commit API keys to git.

**Test 4: Logs stream.** While curling the generate endpoint, run `railway logs` in another terminal. Verify you see access logs with the request path, method, and status code.

**Test 5: Crash recovery.** Temporarily set `ANTHROPIC_API_KEY` to an invalid value. Make a request. Verify the service returns a 500 error and the platform restarts the container (or keeps it running if the error is handled). Check logs for the error details.

**Test 6: Cost estimate.** After 24 hours of light usage (a few requests), check the Railway or Render usage dashboard. Calculate projected monthly cost. Compare to the cost of running the equivalent on an EC2 t3.micro ($8.35/month). Factor in the time saved on infrastructure management.
