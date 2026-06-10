from fastapi import APIRouter, Depends

from app.api.versioning import negotiate_legacy_api_version
from app.api.v1.router import api_v1_router

legacy_api_router = APIRouter(dependencies=[Depends(negotiate_legacy_api_version)])
legacy_api_router.include_router(api_v1_router)
