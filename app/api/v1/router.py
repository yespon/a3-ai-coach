from fastapi import APIRouter, Depends

from app.api.deps import verify_csrf
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.cas import router as cas_router
from app.api.v1.routes.chat import router as chat_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.sessions import router as sessions_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
# Business routes carry session auth + CSRF protection on write methods.
# (verify_csrf is a no-op for GET/HEAD/OPTIONS.)
api_v1_router.include_router(sessions_router, dependencies=[Depends(verify_csrf)])
api_v1_router.include_router(chat_router, dependencies=[Depends(verify_csrf)])
# auth / cas are NOT CSRF-protected: login/register/exchange happen before a
# CSRF token cookie exists; /slo is a back-channel call from SID.
api_v1_router.include_router(auth_router)
api_v1_router.include_router(cas_router)
