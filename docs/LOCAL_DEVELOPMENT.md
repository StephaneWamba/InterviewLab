# Local Development

## Prerequisites

| Requirement        | Version | Installation                                           |
| ------------------ | ------- | ------------------------------------------------------ |
| **Python**         | 3.11+   | [python.org](https://www.python.org/downloads/)        |
| **Node.js**        | 18+     | [nodejs.org](https://nodejs.org/)                      |
| **PostgreSQL**     | 14+     | [postgresql.org](https://www.postgresql.org/download/) |
| **Redis**          | 7+      | [redis.io](https://redis.io/download)                  |
| **Docker**         | 20+     | [docker.com](https://www.docker.com/get-started)       |
| **LiveKit Server** | Latest  | [livekit.io](https://livekit.io/docs/deployment/)      |

## Environment Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd InterviewLab
```

### 2. Backend Setup

```bash
cd src

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r ../requirements.txt  # Or use uv/pip-tools

# Create .env file
cp .env.example .env
```

**Required Environment Variables:**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/interviewlab

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key-here

# OpenAI
OPENAI_API_KEY=sk-...

# LiveKit
LIVEKIT_URL=wss://localhost:7880
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
```

### 3. Database Setup

```bash
# Create database
createdb interviewlab

# Run migrations
alembic upgrade head
```

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env.local
cp .env.example .env.local
```

**Frontend Environment Variables:**

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_LIVEKIT_URL=ws://localhost:7880
```

### 5. LiveKit Server

**Option 1: Docker (Recommended)**

```bash
docker run -d \
  -p 7880:7880 \
  -p 7881:7881 \
  -p 7882:7882/udp \
  -e LIVEKIT_KEYS="api-key: api-secret" \
  livekit/livekit-server
```

**Option 2: Binary**

```bash
# Download from livekit.io
./livekit-server --dev
```

## Running Locally

### Development Mode

**Terminal 1: Backend API**

```bash
cd src
uvicorn main:app --reload --port 8000
```

**Terminal 2: Frontend**

```bash
cd frontend
npm run dev
```

**Terminal 3: LiveKit Agent**

```bash
cd src
python -m src.agents.interview_agent dev
```

**Terminal 4: Redis (if not running)**

```bash
redis-server
```

### Access Points

| Service            | URL                        |
| ------------------ | -------------------------- |
| **Frontend**       | http://localhost:3000      |
| **Backend API**    | http://localhost:8000      |
| **API Docs**       | http://localhost:8000/docs |
| **LiveKit Server** | ws://localhost:7880        |

## Development Workflow

### Making Changes

1. **Backend Changes**

   - Edit Python files in `src/`
   - API auto-reloads (uvicorn --reload)
   - Run tests: `pytest`

2. **Frontend Changes**

   - Edit files in `frontend/`
   - Hot reload enabled
   - Type checking: `npm run type-check`

3. **Orchestrator Changes**
   - Edit files in `src/services/orchestrator/`
   - Restart agent to pick up changes
   - Check logs for errors

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Testing

**Backend Tests:**

```bash
pytest tests/
pytest tests/ -v  # Verbose
pytest tests/ -k test_name  # Specific test
```

**Frontend Tests:**

```bash
npm test
npm run test:watch
```

## Debugging

### Backend Debugging

**Enable Debug Logging:**

```python
# src/core/logging.py
LOG_LEVEL = "DEBUG"
```

**View Logs:**

```bash
tail -f logs/interviewlab.log
```

**Database Inspection:**

```bash
psql interviewlab
SELECT * FROM interviews;
```

### Agent Debugging

**Enable Agent Logs:**

```bash
export LIVEKIT_LOG=debug
python -m src.agents.interview_agent dev
```

**Check Agent State:**

- Logs show state transitions
- Check `src/services/logging/interview_logger.py` output

### Frontend Debugging

**React DevTools:**

- Install browser extension
- Inspect component state

**Network Inspection:**

- Chrome DevTools → Network tab
- Check API requests/responses

## Common Issues

| Issue                         | Solution                                                   |
| ----------------------------- | ---------------------------------------------------------- |
| **Port already in use**       | Change port or kill process: `lsof -ti:8000 \| xargs kill` |
| **Database connection error** | Verify PostgreSQL running: `pg_isready`                    |
| **Redis connection error**    | Start Redis: `redis-server`                                |
| **Agent won't connect**       | Check LiveKit server running, verify credentials           |
| **Import errors**             | Activate venv, reinstall dependencies                      |
| **Migration conflicts**       | Reset DB: `alembic downgrade base && alembic upgrade head` |

## Code Submission Flow (Development)

```mermaid
sequenceDiagram
    participant F as Frontend
    participant A as API
    participant D as Database
    participant AG as Agent
    participant O as Orchestrator

    F->>A: POST /interviews/123/submit-code
    A->>D: Save code to interview
    A->>D: Update conversation_history
    A->>F: 200 OK

    Note over F,AG: User speaks "I submitted code"
    F->>AG: Audio stream
    AG->>O: execute_step(code=...)
    O->>O: route_from_ingest → code_review
    O->>O: Execute code in sandbox
    O->>O: Analyze code quality
    O->>D: Save results
    O->>AG: Code review response
    AG->>F: TTS audio
```

## State Inspection

**View Interview State:**

```python
# In Python shell
from src.services.data.state_manager import interview_to_state
from src.models.interview import Interview
from sqlalchemy import select

# Load interview
interview = await db.execute(select(Interview).where(Interview.id == 123))
state = interview_to_state(interview.scalar_one())
print(state)
```

**Check LangGraph State:**

- Agent logs show state transitions
- Database checkpoints contain full state
- Redis cache (if enabled) shows current state

## Performance Testing

**Load Testing:**

```bash
# Install locust
pip install locust

# Run load test
locust -f tests/load_test.py
```

**Monitor Resources:**

```bash
# CPU/Memory
htop

# Database connections
psql -c "SELECT count(*) FROM pg_stat_activity;"

# Redis memory
redis-cli info memory
```

## Next Steps

- [API Reference](API.md)
- [LangGraph Guide](LANGGRAPH.md)
- [Deployment Guide](DEPLOYMENT.md)
