"""Main API v1 router."""

from fastapi import APIRouter

from src.api.v1.endpoints import auth, resumes, interviews, voice, sandbox

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(interviews.router, prefix="/interviews", tags=["interviews"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(sandbox.router, prefix="/sandbox", tags=["sandbox"])


