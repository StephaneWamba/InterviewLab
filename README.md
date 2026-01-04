# InterviewLab

**Problem:** Traditional technical interview practice often lacks realism, immediate feedback, and interactive voice-based engagement.

**Solution:** InterviewLab delivers AI-driven technical interviews using real-time voice conversations, live code execution, and in-depth feedback, powered by LangGraph and LiveKit.

---

**Python** `3.11+` **TypeScript** `5.0+` **LangGraph** `0.0.40+` **License** `GNU` **Status** `Portfolio-Project`

Portfolio Project — Production-ready codebase demonstrating AI system architecture.

## Aim

Provide candidates with realistic interview practice through:

- **Natural voice conversations** with AI interviewer
- **Live code execution** in isolated sandbox
- **Comprehensive feedback** on communication, technical knowledge, problem-solving, and code quality
- **Resume-based questions** tailored to candidate background

## High-Level Architecture

```mermaid
graph TB
    subgraph "Frontend"
        FE[Next.js React App]
    end

    subgraph "Backend API"
        API[FastAPI Server]
        ORCH[LangGraph Orchestrator]
    end

    subgraph "Voice Infrastructure"
        LK[LiveKit Server]
        AGENT[LiveKit Agent]
        TTS[OpenAI TTS]
        STT[OpenAI STT]
    end

    subgraph "Services"
        SB[Docker Sandbox]
        LLM[GPT-4o-mini]
        DB[(PostgreSQL)]
        REDIS[(Redis Cache)]
    end

    FE -->|HTTP/REST| API
    FE -->|WebSocket| LK
    API -->|HTTP| LK
    API -->|SQL| DB
    API -->|Cache| REDIS
    LK -->|WebSocket| AGENT
    AGENT -->|LangGraph| ORCH
    ORCH -->|API| LLM
    ORCH -->|Docker| SB
    AGENT -->|API| TTS
    AGENT -->|API| STT
```

### Core Components

| Component        | Technology     | Purpose                               |
| ---------------- | -------------- | ------------------------------------- |
| **Orchestrator** | LangGraph      | State machine managing interview flow |
| **Agent**        | LiveKit Agents | Real-time voice agent (STT/TTS)       |
| **LLM**          | GPT-4o-mini    | Question generation, decision making  |
| **Sandbox**      | Docker         | Isolated code execution               |
| **Database**     | PostgreSQL     | Interview state, checkpoints          |
| **Cache**        | Redis          | State caching, session management     |

## How It Works

### Interview Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as API
    participant LK as LiveKit
    participant AG as Agent
    participant O as Orchestrator
    participant LLM as GPT-4o-mini

    U->>F: Start Interview
    F->>A: POST /interviews
    A->>LK: Create Room
    F->>LK: Connect (WebSocket)
    LK->>AG: Bootstrap Agent
    AG->>O: Initialize
    O->>LLM: Generate Greeting
    LLM->>O: Response
    O->>AG: next_message
    AG->>LK: TTS Audio
    LK->>U: Hear Greeting

    loop Conversation
        U->>LK: Speak
        LK->>AG: STT Text
        AG->>O: execute_step(user_response)
        O->>LLM: Detect Intent
        O->>LLM: Decide Next Action
        O->>LLM: Generate Response
        O->>AG: Response
        AG->>U: TTS Audio
    end
```

### State Management

- **LangGraph MemorySaver**: In-memory state per interview (`thread_id`)
- **Database Checkpoints**: Persistent state after each turn
- **Reducers**: Append-only fields (conversation_history, questions_asked)
- **Single Writer**: Critical fields (next_message, phase) written by one node

## Current Performance

### Strengths

- ✅ **Real-time voice** with <3s latency
- ✅ **State persistence** via checkpoints
- ✅ **Concurrent interviews** (isolated by thread_id)
- ✅ **Code execution** in isolated Docker containers
- ✅ **Comprehensive feedback** with skill breakdowns

## Project Structure

```
InterviewLab/
├── src/                    # Backend (Python/FastAPI)
│   ├── agents/            # LiveKit agent implementation
│   │   ├── interview_agent.py      # Agent entrypoint
│   │   ├── orchestrator_llm.py    # Custom LLM adapter
│   │   └── resources.py            # Resource management
│   ├── api/               # REST API endpoints
│   │   └── v1/
│   │       └── endpoints/ # Interviews, resumes, voice, sandbox
│   ├── core/              # Core utilities
│   │   ├── config.py     # Settings management
│   │   ├── database.py   # SQLAlchemy setup
│   │   └── security.py   # JWT authentication
│   ├── models/            # Database models (User, Interview, Resume)
│   ├── schemas/           # Pydantic request/response schemas
│   └── services/          # Business logic
│       ├── analysis/      # Response/code/feedback analysis
│       ├── analytics/     # Analytics service
│       ├── data/          # Checkpoints, state management
│       ├── execution/     # Docker sandbox execution
│       ├── logging/       # Interview logging
│       ├── orchestrator/  # LangGraph orchestration
│       │   ├── graph.py           # Graph definition
│       │   ├── nodes.py           # Node handler
│       │   ├── control_nodes.py   # Flow control nodes
│       │   ├── action_nodes.py    # Response generation nodes
│       │   └── types.py           # State schema
│       └── voice/         # LiveKit voice services
├── frontend/              # Frontend (Next.js/React)
│   ├── app/              # Next.js App Router
│   │   ├── (auth)/       # Login, register
│   │   └── dashboard/    # Protected routes
│   ├── components/       # React components
│   │   ├── interview/    # Voice, sandbox, transcription
│   │   ├── analytics/    # Charts and metrics
│   │   └── ui/           # shadcn/ui components
│   ├── lib/              # Utilities
│   │   ├── api/          # API client & endpoints
│   │   └── store/        # Zustand stores
│   └── hooks/            # Custom React hooks
├── docs/                  # Documentation
│   ├── ARCHITECTURE.md   # System architecture
│   ├── API.md            # API reference
│   ├── FRONTEND.md       # Frontend guide
│   ├── LANGGRAPH.md      # Orchestration guide
│   └── ...               # Other docs
├── alembic/              # Database migrations
├── docker-compose.yml    # Local development
├── Dockerfile            # Production image
└── pyproject.toml        # Python dependencies
```

### Key Directories

| Directory                        | Purpose                 | Key Files                                                           |
| -------------------------------- | ----------------------- | ------------------------------------------------------------------- |
| `src/agents/`                    | LiveKit agent           | `interview_agent.py`, `orchestrator_llm.py`                         |
| `src/services/orchestrator/`     | LangGraph state machine | `graph.py`, `nodes.py`, `control_nodes.py`, `action_nodes.py`       |
| `src/services/analysis/`         | LLM-based analysis      | `response_analyzer.py`, `code_analyzer.py`, `feedback_generator.py` |
| `src/services/execution/`        | Code sandbox            | `sandbox_service.py`                                                |
| `frontend/components/interview/` | Interview UI            | `voice-video.tsx`, `sandbox.tsx`                                    |
| `frontend/lib/api/`              | API integration         | `client.ts`, `interviews.ts`, `voice.ts`                            |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System architecture and component relationships
- [API Reference](docs/API.md) - REST API endpoints
- [Frontend](docs/FRONTEND.md) - Next.js frontend architecture and development
- [Voice Infrastructure](docs/VOICE_INFRASTRUCTURE.md) - LiveKit setup and agent architecture
- [User Guide](docs/USER_GUIDE.md) - How to use InterviewLab
- [Local Development](docs/LOCAL_DEVELOPMENT.md) - Setup and development workflow
- [LangGraph Guide](docs/LANGGRAPH.md) - State, nodes, and orchestration
- [Deployment](docs/DEPLOYMENT.md) - Railway and Vercel deployment

## Quick Start

```bash
# Backend
cd src
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Agent (requires LiveKit server)
python -m src.agents.interview_agent
```

See [Local Development](docs/LOCAL_DEVELOPMENT.md) for detailed setup.

## Tech Stack

### Backend
- **FastAPI** - Modern async web framework
- **Python 3.11+** - Programming language
- **LangGraph 0.0.40+** - State machine orchestration
- **SQLAlchemy 2.0+** - ORM with async support
- **Alembic** - Database migrations
- **LiveKit Agents** - Real-time voice agents
- **OpenAI GPT-4o-mini** - LLM for question generation
- **Instructor** - Structured LLM outputs
- **PostgreSQL** - Primary database
- **Redis** - Caching and state management
- **Docker** - Code sandbox execution

### Frontend
- **Next.js 16.1** - React framework
- **TypeScript 5.0+** - Type safety
- **React 19.2** - UI library
- **Tailwind CSS 4** - Styling
- **Zustand** - State management
- **TanStack Query** - Data fetching
- **Monaco Editor** - Code editor
- **Framer Motion** - Animations
- **LiveKit Client** - WebRTC integration

### Deployment
- **Railway** - Backend and agent hosting
- **Vercel** - Frontend hosting

## License

GNU General Public License v3.0
