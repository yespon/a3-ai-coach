from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.cas import router as cas_router
from app.api.v1.routes.chat import router as chat_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.sessions import router as sessions_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(sessions_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(cas_router)

