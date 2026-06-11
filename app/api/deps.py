from fastapi import Header

from app.core.logger import get_component_logger

LOGGER = get_component_logger(component="chatbot")


def get_current_user_id(x_user_id: str = Header(default="anonymous")) -> str:
    """Extract caller identity from X-User-ID header.

    Defaults to 'anonymous' so existing clients keep working without change.
    When authentication is added, replace this with a JWT/session validator.
    """
    uid = x_user_id.strip()
    return uid if uid else "anonymous"
