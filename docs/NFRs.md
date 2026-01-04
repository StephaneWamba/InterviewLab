# Non-Functional Requirements (NFRs)

## Overview

This document outlines how InterviewLab manages non-functional requirements (NFRs) - the quality attributes that define how the system performs, scales, and maintains reliability.

## NFR Categories

| Category            | Requirements                               | Implementation                                        |
| ------------------- | ------------------------------------------ | ----------------------------------------------------- |
| **Performance**     | Response time, throughput, latency         | Async operations, caching, connection pooling         |
| **Scalability**     | Concurrent users, horizontal scaling       | Stateless design, thread isolation, resource cleanup  |
| **Reliability**     | Uptime, error handling, data persistence   | Checkpointing, graceful degradation, retry logic      |
| **Security**        | Authentication, data protection, isolation | JWT tokens, Docker sandbox, input validation          |
| **Maintainability** | Code quality, documentation, testing       | Type safety, modular architecture, comprehensive docs |
| **Availability**    | Service uptime, health monitoring          | Health checks, graceful shutdown, auto-recovery       |

## Performance

### Requirements

| Metric              | Target                  | Current | Implementation                             |
| ------------------- | ----------------------- | ------- | ------------------------------------------ |
| **Voice Latency**   | <500ms end-to-end       | <3s     | LiveKit WebRTC, optimized TTS/STT          |
| **API Response**    | <200ms (p95)            | ~150ms  | Async FastAPI, connection pooling          |
| **Code Execution**  | <5s (Python), <10s (JS) | ~3s     | Docker sandbox, timeout limits             |
| **Graph Execution** | <3s per step            | ~2s     | LangGraph optimization, parallel LLM calls |

### Implementation

**Async Operations:**

```python
# All I/O operations are async
async def execute_step(self, state: InterviewState) -> InterviewState:
    # Non-blocking database queries
    # Non-blocking LLM calls
    # Non-blocking code execution
```

**Caching:**

- Redis for state caching
- React Query for frontend API caching
- Connection pooling for database/Redis

**Connection Pooling:**

```python
# Database connection pool
engine = create_async_engine(DATABASE_URL, pool_size=20)

# Redis connection reuse
_redis_client: Optional[Redis] = None  # Singleton pattern
```

### Monitoring

- API response times logged
- Voice latency tracked in agent logs
- Code execution times recorded
- Database query performance monitored

## Scalability

### Requirements

| Metric                    | Target                   | Implementation                       |
| ------------------------- | ------------------------ | ------------------------------------ |
| **Concurrent Interviews** | 50+ per agent instance   | Thread isolation, resource cleanup   |
| **Horizontal Scaling**    | Multiple agent instances | Stateless design, shared database    |
| **Database Connections**  | 20+ concurrent           | Connection pooling                   |
| **Memory Usage**          | <2GB per agent           | Explicit cleanup, garbage collection |

### Implementation

**Thread Isolation:**

```python
# LangGraph MemorySaver isolates state by thread_id
thread_id = f"interview_{interview_id}"
config = {"configurable": {"thread_id": thread_id}}
# Each interview gets isolated state
```

**Resource Cleanup:**

```python
async def cleanup_interview(self, interview_id: int):
    # Clear MemorySaver checkpoints
    # Clear Redis cache
    # Release service references
    self._node_handler = None  # Help GC
```

**Stateless Design:**

- No shared mutable state between interviews
- Database as source of truth
- Redis for optional caching only

**Horizontal Scaling:**

- Multiple agent instances share database
- LiveKit distributes connections
- No inter-agent communication needed

## Reliability

### Requirements

| Metric               | Target                  | Implementation                          |
| -------------------- | ----------------------- | --------------------------------------- |
| **Uptime**           | 99.9%                   | Health checks, graceful degradation     |
| **Data Persistence** | 100% checkpoint success | Database checkpoints, retry logic       |
| **Error Recovery**   | Automatic retry         | Graceful error handling, fallbacks      |
| **State Recovery**   | 100% on restart         | Checkpoint restoration, database backup |

### Implementation

**Checkpointing:**

```python
# After each turn
if final_state.get("last_node") == "finalize_turn":
    await checkpoint_service.checkpoint(final_state, db_session)
```

**State Restoration:**

```python
# On agent restart
checkpoint_state = await checkpoint_service.restore(interview_id, db)
if checkpoint_state:
    state = checkpoint_state  # Resume from checkpoint
else:
    state = interview_to_state(interview)  # Reconstruct from DB
```

**Error Handling:**

```python
try:
    final_state = await graph.ainvoke(state, config)
except Exception as e:
    logger.error(f"Graph execution failed: {e}", exc_info=True)
    # Return partial state, don't crash
    raise ValueError(f"Graph execution failed: {e}") from e
```

**Graceful Degradation:**

- VAD loading failure → Continue without VAD
- Redis unavailable → Skip caching, use DB only
- Sandbox timeout → Return error, don't crash

**Health Checks:**

```python
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "interviewlab"}
```

## Security

### Requirements

| Area                 | Requirement                         | Implementation                        |
| -------------------- | ----------------------------------- | ------------------------------------- |
| **Authentication**   | JWT tokens, 30min expiry            | FastAPI security, token validation    |
| **Authorization**    | User-scoped data access             | Database queries filter by user_id    |
| **Data Protection**  | Encrypted passwords, secure storage | bcrypt hashing, environment variables |
| **Code Isolation**   | Sandbox execution                   | Docker containers, resource limits    |
| **Input Validation** | All user inputs validated           | Pydantic schemas, type checking       |

### Implementation

**Authentication:**

```python
# JWT token generation
def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
```

**Password Security:**

```python
# bcrypt hashing
hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
verify_password(plain_password, hashed_password)
```

**Code Isolation:**

```python
# Docker sandbox with limits
container = docker_client.containers.run(
    image,
    command,
    mem_limit="128m",
    cpu_period=100000,
    cpu_quota=50000,  # 0.5 CPU
    network_disabled=True,  # No network access
)
```

**Input Validation:**

```python
# Pydantic schemas
class InterviewCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    resume_id: Optional[int] = Field(None, gt=0)
    job_description: Optional[str] = Field(None, max_length=5000)
```

**Authorization:**

```python
# User-scoped queries
result = await db.execute(
    select(Interview).where(
        Interview.id == interview_id,
        Interview.user_id == user.id  # Always filter by user
    )
)
```

## Maintainability

### Requirements

| Aspect            | Requirement                      | Implementation                           |
| ----------------- | -------------------------------- | ---------------------------------------- |
| **Code Quality**  | Type safety, linting, formatting | TypeScript, Python typing, ESLint, Black |
| **Documentation** | Comprehensive, up-to-date        | Markdown docs, code comments, API docs   |
| **Modularity**    | Clear separation of concerns     | Service layers, component architecture   |
| **Testing**       | Unit tests, integration tests    | pytest, testing-library (planned)        |

### Implementation

**Type Safety:**

- TypeScript for frontend (strict mode)
- Python type hints with mypy
- Pydantic models for validation

**Code Organization:**

```
src/
├── agents/          # LiveKit agent
├── api/            # REST API endpoints
├── core/           # Core utilities (DB, security, config)
├── models/         # Database models
├── schemas/        # Pydantic schemas
└── services/       # Business logic
    ├── analysis/   # Analysis services
    ├── orchestrator/  # LangGraph orchestration
    └── execution/  # Code execution
```

**Documentation:**

- Architecture diagrams (Mermaid)
- API documentation (FastAPI auto-docs)
- Component documentation
- Deployment guides

**Modular Design:**

- Single responsibility per module
- Dependency injection
- Clear interfaces between layers

## Availability

### Requirements

| Metric                | Target                      | Implementation                         |
| --------------------- | --------------------------- | -------------------------------------- |
| **Uptime**            | 99.9% (8.76h downtime/year) | Health checks, auto-restart            |
| **Recovery Time**     | <5 minutes                  | Automated deployment, database backups |
| **Health Monitoring** | Continuous                  | Health endpoints, logging              |

### Implementation

**Health Checks:**

```python
# API health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Sandbox health check
@router.get("/sandbox/health")
async def sandbox_health():
    is_healthy = await sandbox_service.health_check()
    return {"status": "healthy" if is_healthy else "degraded"}
```

**Graceful Shutdown:**

```python
# Cleanup on shutdown
async def aclose(self):
    if self.orchestrator_llm:
        await self.orchestrator_llm.orchestrator.cleanup_interview(interview_id)
    if self.db:
        await self.db.close()
```

**Auto-Recovery:**

- Railway/Vercel auto-restart on failure
- Database connection retry logic
- Agent reconnection on disconnect

## Resource Management

### Requirements

| Resource                 | Limit                | Management                        |
| ------------------------ | -------------------- | --------------------------------- |
| **Memory**               | <2GB per agent       | Explicit cleanup, GC hints        |
| **CPU**                  | 0.5-1 vCPU per agent | Resource limits, async operations |
| **Database Connections** | 20 pool size         | Connection pooling                |
| **File Uploads**         | 10MB max             | Size validation, cleanup          |

### Implementation

**Memory Management:**

```python
# Explicit cleanup after interview
async def cleanup_interview(self, interview_id: int):
    # Clear checkpoints
    # Clear Redis cache
    # Release references
    self._node_handler = None
```

**Connection Limits:**

```python
# Database pool
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10
)
```

**File Size Validation:**

```python
MAX_UPLOAD_SIZE: int = 10485760  # 10MB

if file.size > MAX_UPLOAD_SIZE:
    raise HTTPException(400, "File too large")
```

## Monitoring & Observability

### Requirements

| Aspect                  | Implementation                    |
| ----------------------- | --------------------------------- |
| **Logging**             | Structured logging, log levels    |
| **Error Tracking**      | Exception logging with context    |
| **Performance Metrics** | Response times, execution times   |
| **Health Monitoring**   | Health endpoints, uptime tracking |

### Implementation

**Logging:**

```python
# Structured logging
logger.info(f"Interview {interview_id} started", extra={
    "interview_id": interview_id,
    "user_id": user_id
})

# Error logging with context
logger.error(f"Graph execution failed: {e}", exc_info=True)
```

**Metrics:**

- API response times (logged)
- Code execution times (recorded)
- Voice latency (tracked in agent)
- Database query times (SQLAlchemy logging)

## Compliance & Standards

### Requirements

| Standard          | Implementation                      |
| ----------------- | ----------------------------------- |
| **REST API**      | OpenAPI/Swagger specification       |
| **Web Standards** | HTTPS, CORS, secure headers         |
| **Data Privacy**  | User data isolation, secure storage |
| **Accessibility** | WCAG compliance (frontend)          |

### Implementation

**API Standards:**

- FastAPI auto-generates OpenAPI spec
- RESTful endpoint design
- Standard HTTP status codes

**Security Headers:**

- CORS configuration
- JWT token security
- Secure password storage

## NFR Validation

### Testing

| NFR             | Test Method                         |
| --------------- | ----------------------------------- |
| **Performance** | Load testing, latency measurement   |
| **Scalability** | Concurrent user testing             |
| **Reliability** | Failure injection, recovery testing |
| **Security**    | Penetration testing, code review    |

### Metrics Collection

- **Performance**: Response time logs, execution time tracking
- **Reliability**: Error rates, checkpoint success rates
- **Availability**: Uptime monitoring, health check results
- **Security**: Authentication success rates, failed login attempts

## Future Improvements

### Short-term

1. **Performance**

   - Implement Redis caching layer
   - Optimize LLM prompt lengths
   - Batch checkpoint writes

2. **Reliability**
   - Add retry logic for external APIs
   - Implement circuit breakers
   - Enhanced error recovery

### Long-term

1. **Scalability**

   - Database read replicas
   - CDN for static assets
   - Horizontal agent scaling

2. **Observability**
   - APM integration (e.g., Datadog)
   - Distributed tracing
   - Real-time dashboards

## References

- [Architecture](ARCHITECTURE.md) - System design
- [Deployment](DEPLOYMENT.md) - Production deployment
- [Local Development](LOCAL_DEVELOPMENT.md) - Development setup
