# Deployment Configuration Guide

## Architecture Overview

```
Frontend (Vercel) → API (Railway) → Database/Redis
     ↓                                    ↓
LiveKit Server ← Agent (Railway) → Database/Redis
```

## ✅ What's Already Configured

### API Service (Railway)
- ✅ Database connection (PostgreSQL)
- ✅ Redis connection
- ✅ LiveKit credentials (creates rooms, generates tokens)
- ✅ OpenAI API key
- ✅ All environment variables set

### Agent Service (Railway)
- ✅ Connected to LiveKit server
- ✅ Database connection (PostgreSQL)
- ✅ Redis connection
- ✅ LiveKit credentials (connects to LiveKit)
- ✅ OpenAI API key
- ✅ All environment variables set

## 🔧 Required Configuration

### 1. Frontend (Vercel) Environment Variables

In your Vercel project settings, add:

```bash
NEXT_PUBLIC_API_URL=https://your-api-service.railway.app
```

**Important**: 
- Replace `your-api-service.railway.app` with your actual Railway API service URL
- This must be the **public URL** of your API service (not the agent service)
- The frontend uses this to:
  - Get authentication tokens
  - Fetch interview data
  - Get LiveKit access tokens
  - Submit code to sandbox

### 2. CORS Configuration (API Service)

The API service needs to allow requests from your Vercel frontend domain.

**Option A: Update CORS in code** (if you want to restrict origins):
```python
# In src/main.py, update CORS_ORIGINS
CORS_ORIGINS = [
    "https://your-frontend.vercel.app",
    "https://your-frontend-domain.com",
]
```

**Option B: Keep current setting** (allows all origins - fine for development):
- Current setting: `allow_origins=["*"]` - this works but is less secure

### 3. Verify Environment Variables Match

Both API and Agent services should have **identical** values for:
- `LIVEKIT_URL` - Must be the same LiveKit server URL
- `LIVEKIT_API_KEY` - Must be the same API key
- `LIVEKIT_API_SECRET` - Must be the same secret
- `DATABASE_URL` - Should point to the same database
- `REDIS_URL` - Should point to the same Redis instance
- `OPENAI_API_KEY` - Should be the same (for consistent LLM behavior)

## 🔄 How Communication Works

### Frontend → API
1. Frontend calls `POST /api/v1/voice/token` with room name
2. API creates LiveKit room (if needed) and generates access token
3. API returns token + LiveKit URL to frontend

### Frontend → LiveKit
1. Frontend uses token + URL to connect via WebSocket
2. LiveKit routes audio/video between frontend and agent

### LiveKit → Agent
1. When a room is created/joined, LiveKit notifies the agent
2. Agent connects to the room automatically
3. Agent extracts interview ID from room name (`interview-{id}`)
4. Agent loads interview data from database

### Agent → Database
- Agent reads interview state from PostgreSQL
- Agent updates conversation history in database
- Agent uses Redis for caching (if configured)

## ✅ Verification Checklist

### API Service
- [ ] Service is running and healthy
- [ ] `/health` endpoint returns 200
- [ ] Can create LiveKit rooms via API
- [ ] Can generate access tokens

### Agent Service
- [ ] Service is running (no healthcheck needed)
- [ ] Logs show "registered worker" message
- [ ] Connected to LiveKit server
- [ ] Can access database

### Frontend (Vercel)
- [ ] `NEXT_PUBLIC_API_URL` is set to Railway API URL
- [ ] Can authenticate users
- [ ] Can fetch interviews
- [ ] Can get voice tokens
- [ ] Can connect to LiveKit

### LiveKit Server
- [ ] Agent is registered and connected
- [ ] Rooms can be created
- [ ] WebSocket connections work

## 🐛 Troubleshooting

### Agent not joining rooms
- Check agent logs for connection errors
- Verify `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` match between API and Agent
- Ensure agent can access database (check `DATABASE_URL`)

### Frontend can't get tokens
- Verify `NEXT_PUBLIC_API_URL` is correct
- Check API service is accessible from internet
- Verify CORS allows your Vercel domain
- Check API logs for authentication errors

### Frontend can't connect to LiveKit
- Verify token is valid (check API logs)
- Check LiveKit URL is correct
- Ensure WebSocket connections aren't blocked
- Check browser console for connection errors

### Agent can't access database
- Verify `DATABASE_URL` is correct in agent service
- Check database allows connections from Railway
- Verify database credentials are correct

## 📝 Environment Variables Summary

### API Service (Railway)
```
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
OPENAI_API_KEY=...
SECRET_KEY=...
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Agent Service (Railway)
```
DATABASE_URL=postgresql://... (same as API)
REDIS_URL=redis://... (same as API)
LIVEKIT_URL=wss://your-project.livekit.cloud (same as API)
LIVEKIT_API_KEY=... (same as API)
LIVEKIT_API_SECRET=... (same as API)
OPENAI_API_KEY=... (same as API)
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Frontend (Vercel)
```
NEXT_PUBLIC_API_URL=https://your-api-service.railway.app
```

## 🎯 Next Steps

1. **Set `NEXT_PUBLIC_API_URL` in Vercel** to your Railway API URL
2. **Test the flow**:
   - Create an interview in frontend
   - Start the interview
   - Verify agent joins the room
   - Test voice conversation
3. **Monitor logs** in both Railway services to ensure everything works


