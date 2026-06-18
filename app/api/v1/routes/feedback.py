"""Public feedback endpoints — any logged-in user can submit."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.deps import get_current_user, get_db
from app.models.db_models import User
from app.services.feedback_service import create_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(
    request: Request,
    content: Annotated[str, Form(...)],
    images: Annotated[list[UploadFile], File(...)] = [],
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    files = images or []
    submission = await create_feedback(
        db,
        current_user,
        content,
        files,
        user_agent=request.headers.get("user-agent"),
        ip=(request.client.host if request.client else None),
    )
    return {"id": str(submission.id), "created_at": submission.created_at.isoformat()}
