from fastapi import APIRouter, Depends

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.sessions import router as sessions_router
from app.api.versioning import negotiate_legacy_api_version

api_router = APIRouter(dependencies=[Depends(negotiate_legacy_api_version)])
api_router.include_router(health_router)
api_router.include_router(sessions_router)
api_router.include_router(chat_router)
