"""CAS SSO service — ticket validation, session management, SLO parsing."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree as ET

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import AuthSessionDB

CAS_NS = {"cas": "http://www.yale.edu/tp/cas"}


async def validate_ticket(
    ticket: str, service_url: str, sid_base_url: str, timeout: int = 5
) -> tuple[str, dict]:
    """Validate CAS Service Ticket via /p3/serviceValidate.

    Returns (employee_no, attrs_dict).
    Raises HTTPException(401) on validation failure.
    """
    params = {"service": service_url, "ticket": ticket}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{sid_base_url}/p3/serviceValidate", params=params)

    root = ET.fromstring(resp.text)
    success = root.find(".//cas:authenticationSuccess", CAS_NS)
    if success is None:
        failure = root.find(".//cas:authenticationFailure", CAS_NS)
        detail = failure.text if failure is not None else "CAS validation failed"
        raise HTTPException(status_code=401, detail=detail.strip())

    employee_no = success.find("cas:user", CAS_NS).text
    attrs: dict[str, str] = {}
    attr_elements = success.findall(".//cas:attributes/*", CAS_NS)
    for el in attr_elements:
        key = el.tag.split("}")[-1]  # strip namespace
        attrs[key] = el.text
    return employee_no, attrs


def parse_session_index(saml_xml: str) -> str | None:
    """Extract original ST from SAML LogoutRequest for SLO back-channel."""
    try:
        root = ET.fromstring(saml_xml)
        si = root.find(".//{urn:oasis:names:tc:SAML:2.0:protocol}SessionIndex")
        return si.text if si is not None else None
    except ET.ParseError:
        return None


async def create_auth_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    cas_ticket: str | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
    ttl_hours: int = 8,
) -> tuple[str, AuthSessionDB]:
    """Create a new server-side session.

    Returns (raw_token, session_obj).
    raw_token is the value set in cookie; session_token in DB is SHA-256 hash.
    """
    raw_token = secrets.token_urlsafe(48)  # ~64 chars
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    now = datetime.now(UTC)
    session = AuthSessionDB(
        session_token=token_hash,
        user_id=user_id,
        cas_ticket=cas_ticket,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
        user_agent=user_agent,
        ip=ip,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return raw_token, session


async def cleanup_expired_sessions(db: AsyncSession, grace_days: int = 1) -> int:
    """Delete sessions that expired or were revoked more than grace_days ago.

    Returns the number of deleted rows.
    """
    cutoff = datetime.now(UTC) - timedelta(days=grace_days)
    result = await db.execute(
        AuthSessionDB.__table__.delete().where(
            (AuthSessionDB.expires_at < cutoff) | (AuthSessionDB.revoked_at < cutoff)
        )
    )
    await db.commit()
    return result.rowcount
