# InterviewLab

<div align="center">
  <img src="frontend/public/landing-page.png" alt="Landing Page" width="100%"/>
  <br/><br/>
  <img src="frontend/public/interview.png" alt="Interview Interface" width="100%"/>
  <br/><br/>
  <img src="frontend/public/resumes.png" alt="Resumes Page" width="100%"/>
</div>

**Problem:** Traditional technical interview practice often lacks realism, immediate feedback, and interactive voice-based engagement.

**Solution:** InterviewLab delivers AI-driven technical interviews using real-time voice conversations, live code execution, and in-depth feedback, powered by LangGraph and LiveKit.

---

**Python** `3.11+` **TypeScript** `5.0+` **LangGraph** `0.0.40+` **LiveKit** `0.11.0+` **OpenAI** `1.0.0+` **License** `GNU` **Status** `Portfolio-Project`

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
    subgraph Frontend
        FE[Next.js React App]
    end

    subgraph Backend
        API[FastAPI Server]
        ORCH[LangGraph Orchestrator]
    end

    subgraph Voice
        LK[LiveKit Server]
        AGENT[LiveKit Agent]
        TTS[OpenAI TTS]
        STT[OpenAI STT]
    end

    subgraph Services
        SB[Docker Sandbox]
        LLM[GPT-4o-mini]
        DB[PostgreSQL]
        REDIS[Redis Cache]
    end

    FE -->|HTTP REST| API
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
    F->>A: POST interviews
    A->>LK: Create Room
    F->>LK: Connect WebSocket
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
        AG->>O: execute_step
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
│   ├── agents/            # LiveKit agent logic
│   ├── api/               # REST API implementation
│   │   └── v1/
│   │       └── endpoints/ # Endpoints for interviews, resumes, voice, sandbox
│   ├── core/              # Configuration, database, and authentication utilities
│   ├── models/            # Database models for core entities
│   ├── schemas/           # Pydantic schemas for data validation
│   └── services/          # Business logic and subsystems
│       ├── analysis/      # Interview response and code analysis
│       ├── analytics/     # Analytics functionality
│       ├── data/          # Checkpointing and state management
│       ├── execution/     # Secure code sandboxing
│       ├── logging/       # Interview activity logging
│       ├── orchestrator/  # State orchestration using LangGraph
│       └── voice/         # LiveKit voice management
├── frontend/              # Frontend (Next.js + React)
│   ├── app/              # App routing and authentication
│   ├── components/       # UI components (interview, analytics, UI kit)
│   ├── lib/              # API client and store utilities
│   └── hooks/            # Custom React hooks
├── docs/                  # Documentation and guides
├── alembic/               # Database migration scripts
├── docker-compose.yml     # Local dev orchestration
├── Dockerfile             # Production build configuration
└── pyproject.toml         # Backend dependencies and settings
```

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
