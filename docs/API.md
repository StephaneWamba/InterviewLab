# API Reference

Base URL: `https://api.interviewlab.com/api/v1`

Authentication: Bearer token in `Authorization` header

## Endpoints Overview

| Category | Endpoints | Description |
|----------|-----------|-------------|
| **Auth** | `/auth/register`, `/auth/login` | User authentication |
| **Interviews** | `/interviews/*` | Interview lifecycle management |
| **Sandbox** | `/sandbox/*` | Code execution and submission |
| **Voice** | `/voice/*` | LiveKit tokens, TTS, STT |
| **Resumes** | `/resumes/*` | Resume upload and analysis |

## Interviews

### Create Interview

```http
POST /interviews/
Content-Type: application/json
Authorization: Bearer <token>

{
  "title": "Senior Python Engineer Interview",
  "resume_id": 123,
  "job_description": "Looking for senior Python engineer..."
}
```

**Response:**
```json
{
  "id": 456,
  "title": "Senior Python Engineer Interview",
  "status": "pending",
  "created_at": "2024-01-15T10:00:00Z"
}
```

### Start Interview

```http
POST /interviews/{id}/start
Authorization: Bearer <token>
```

**Response:**
```json
{
  "interview_id": 456,
  "room_name": "interview-456",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "url": "wss://livekit.example.com"
}
```

### Submit Code

```http
POST /interviews/{id}/submit-code
Content-Type: application/json
Authorization: Bearer <token>

{
  "code": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
  "language": "python"
}
```

**Response:**
```json
{
  "message": "Code submitted successfully",
  "execution_result": {
    "stdout": "",
    "stderr": "",
    "exit_code": 0
  }
}
```

### Get Interview State

```http
GET /interviews/{id}/state
Authorization: Bearer <token>
```

**Response:**
```json
{
  "interview_id": 456,
  "turn_count": 5,
  "phase": "technical",
  "conversation_history": [...],
  "questions_asked": [...],
  "code_submissions": [...]
}
```

### Complete Interview

```http
POST /interviews/{id}/complete
Authorization: Bearer <token>
```

**Response:**
```json
{
  "interview_id": 456,
  "status": "completed",
  "feedback": {
    "overall_score": 0.85,
    "communication_score": 0.90,
    "technical_score": 0.80,
    "problem_solving_score": 0.85,
    "code_quality_score": 0.75,
    "skill_breakdown": {...}
  }
}
```

## Sandbox

### Execute Code

```http
POST /sandbox/execute
Content-Type: application/json
Authorization: Bearer <token>

{
  "code": "print('Hello, World!')",
  "language": "python",
  "timeout_seconds": 30
}
```

**Response:**
```json
{
  "stdout": "Hello, World!\n",
  "stderr": "",
  "exit_code": 0,
  "execution_time_ms": 150
}
```

### Submit Code to Interview

```http
POST /interviews/{id}/submit-code
Content-Type: application/json
Authorization: Bearer <token>

{
  "code": "def solve(): ...",
  "language": "python"
}
```

## Voice

### Get LiveKit Token

```http
POST /voice/token
Content-Type: application/json
Authorization: Bearer <token>

{
  "room_name": "interview-456",
  "participant_name": "John Doe",
  "can_publish": true,
  "can_subscribe": true
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "room_name": "interview-456",
  "url": "wss://livekit.example.com"
}
```

### Text-to-Speech

```http
POST /voice/tts
Content-Type: application/json
Authorization: Bearer <token>

{
  "text": "Hello, welcome to your interview!",
  "voice": "alloy",
  "model": "tts-1-hd"
}
```

**Response:**
```json
{
  "audio_base64": "UklGRiQAAABXQVZFZm10...",
  "text": "Hello, welcome to your interview!",
  "voice": "alloy",
  "model": "tts-1-hd"
}
```

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message",
  "status_code": 400
}
```

### Common Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 404 | Not Found |
| 500 | Internal Server Error |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `/interviews/*` | 10 requests/minute |
| `/sandbox/execute` | 20 requests/minute |
| `/voice/tts` | 30 requests/minute |

