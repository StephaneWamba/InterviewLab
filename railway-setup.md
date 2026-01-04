# Railway Deployment Setup Guide

## Overview

This guide explains how to deploy InterviewLab to Railway with multiple services:

- **API Service**: FastAPI backend
- **Agent Service**: LiveKit agent (optional, can run separately)

## Prerequisites

1. Railway account: [railway.app](https://railway.app)
2. GitHub repository connected
3. Railway CLI installed: `npm i -g @railway/cli`

## Step 1: Create Railway Project

```bash
railway login
railway init
```

## Step 2: Add Services

### PostgreSQL Database

```bash
railway add postgresql
```

Railway automatically sets `DATABASE_URL` environment variable.

### Redis Cache

```bash
railway add redis
```

Railway automatically sets `REDIS_URL` environment variable.

## Step 3: Deploy API Service

### Option A: Using Railway Dashboard

1. Go to Railway dashboard
2. Click "New Service" → "GitHub Repo"
3. Select your repository
4. Railway will detect `railway.json` automatically
5. Set environment variables (see below)

### Option B: Using Railway CLI

```bash
railway link
railway up
```

## Step 4: Configure Environment Variables

In Railway dashboard → Variables, set:

| Variable             | Description                    | Example                            |
| -------------------- | ------------------------------ | ---------------------------------- |
| `DATABASE_URL`       | Auto-set by PostgreSQL service | `postgresql://...`                 |
| `REDIS_URL`          | Auto-set by Redis service      | `redis://...`                      |
| `SECRET_KEY`         | JWT secret key                 | Generate: `openssl rand -hex 32`   |
| `OPENAI_API_KEY`     | OpenAI API key                 | `sk-...`                           |
| `LIVEKIT_URL`        | LiveKit server URL             | `wss://your-project.livekit.cloud` |
| `LIVEKIT_API_KEY`    | LiveKit API key                | `...`                              |
| `LIVEKIT_API_SECRET` | LiveKit API secret             | `...`                              |
| `ENVIRONMENT`        | Environment name               | `production`                       |
| `LOG_LEVEL`          | Logging level                  | `INFO`                             |
| `CORS_ORIGINS`       | Allowed origins                | `https://your-frontend.vercel.app` |

## Step 5: Deploy Agent Service (Optional)

The agent can run on Railway or separately.

### On Railway:

1. Create new service: `railway service create interview-agent` (or name it `agent`)
2. Link to same project: `railway link`
3. **IMPORTANT**: Configure the service manually in Railway dashboard:
   - Go to Railway dashboard → Agent service → Settings → Deploy
   - Set **Start Command** to: `python -m src.agents.interview_agent start`
   - **Disable Healthcheck**: Go to Settings → Healthcheck and disable it (LiveKit agents don't expose HTTP endpoints)
   - The service uses `Dockerfile.agent` which doesn't include a healthcheck
   - This ensures it uses the agent instead of the FastAPI server
4. Set same environment variables as API (especially LiveKit credentials)
5. Deploy: `railway up`

**Note**: Railway may not automatically detect `railway-agent.json`. Always verify:

- The start command in the dashboard matches the agent command above
- Healthcheck is disabled (agents connect via WebSocket, not HTTP)

### Separate Deployment:

Deploy agent separately (e.g., on a VPS) for better isolation.

## Step 6: Run Database Migrations

Migrations run automatically on startup (see `railway.json` startCommand).

To run manually:

```bash
railway run alembic upgrade head
```

## Step 7: Configure Domain

1. Railway dashboard → Settings → Generate Domain
2. Note the domain: `your-app.railway.app`
3. Update frontend `NEXT_PUBLIC_API_URL` to point to this domain

## Service Configuration Files

### `railway.json` (API Service)

- Builds from Dockerfile
- Runs migrations on startup
- Starts uvicorn server
- Health check on `/health`

### `railway-agent.json` (Agent Service)

- Builds from same Dockerfile
- Starts LiveKit agent
- Requires same environment variables

## Resource Limits

Default Railway configuration:

- **CPU**: 1.0 vCPU
- **Memory**: 2GB
- **Disk**: 10GB

Adjust in Railway dashboard → Settings → Resources.

## Monitoring

- **Logs**: Railway dashboard → Logs
- **Metrics**: Railway dashboard → Metrics
- **Health**: `https://your-app.railway.app/health`

## Troubleshooting

| Issue                         | Solution                                  |
| ----------------------------- | ----------------------------------------- |
| **Build fails**               | Check Dockerfile, verify dependencies     |
| **Database connection error** | Verify `DATABASE_URL` is set              |
| **Agent won't connect**       | Check LiveKit credentials                 |
| **High memory usage**         | Increase memory limit or optimize code    |
| **Port binding error**        | Ensure using `$PORT` environment variable |

## Next Steps

- [Deployment Guide](docs/DEPLOYMENT.md) - Detailed deployment instructions
- [Local Development](docs/LOCAL_DEVELOPMENT.md) - Development setup
