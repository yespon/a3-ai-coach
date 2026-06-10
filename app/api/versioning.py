from fastapi import Header, HTTPException, Query, Response

_SUPPORTED_VERSION = "1"


def negotiate_legacy_api_version(
    response: Response,
    x_api_version: str | None = Header(default=None),
    api_version: str | None = Query(default=None),
) -> None:
    requested = x_api_version or api_version or _SUPPORTED_VERSION

    if requested != _SUPPORTED_VERSION:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 API 版本: {requested}，当前仅支持 v{_SUPPORTED_VERSION}",
        )

    # Explicitly expose negotiation outcome for legacy /api callers.
    response.headers["x-api-version"] = _SUPPORTED_VERSION
    response.headers["x-api-legacy"] = "true"
