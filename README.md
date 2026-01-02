# InterviewLab

Voice-based interview preparation platform with AI interviewer, resume analysis, and live coding sandbox environment.

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Package Manager**: uv
- **LLM**: OpenAI GPT-4o mini
- **Structured Output**: Instructor
- **Authentication**: Authlib (OAuth2/JWT)
- **Database**: PostgreSQL (async with SQLAlchemy)
- **Caching**: Redis
- **Containerization**: Docker (multi-stage builds)

## Features

- ✅ User authentication (JWT)
- ✅ Resume upload (PDF only)
- ✅ Resume parsing and text extraction
- ✅ AI-powered resume analysis with GPT-4o mini
- ✅ Structured data extraction (skills, experience, education, projects)

## Project Structure

```
InterviewLab/
├── src/
│   ├── api/           # API routes and endpoints
│   ├── core/          # Core configuration (database, security, logging)
│   ├── models/        # SQLAlchemy database models
│   ├── schemas/       # Pydantic schemas for validation
│   ├── services/      # Business logic services
│   └── main.py        # FastAPI application entry point
├── private/           # Documentation (gitignored)
├── docker-compose.yml # Local development setup
├── Dockerfile         # Multi-stage Docker build
└── pyproject.toml     # Project dependencies (uv)
```

## Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- uv package manager

### Environment Variables

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

Required variables:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `SECRET_KEY`: JWT secret key
- `OPENAI_API_KEY`: OpenAI API key

### Running with Docker Compose

```bash
docker-compose up --build
```

The API will be available at `http://localhost:8000`

### Local Development

1. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`

2. Install dependencies:
```bash
uv pip install -e .
```

3. Run database migrations (when Alembic is set up)

4. Start the server:
```bash
uvicorn src.main:app --reload
```

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Development

- Main branch: `main`
- Development branch: `develop`
- All documentation in `/private` folder (gitignored)

## License

MIT


