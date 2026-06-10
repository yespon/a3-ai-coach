import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
CONTEXT_FILE = BASE_DIR / "岗位标准化母体.history.json"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_ROOT = BASE_DIR / "uploads"
SUPPORTED_ATTACHMENT_EXTS = (
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".pdf",
)

# Load environment variables from local .env before reading os.getenv.
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_materials_dir() -> Path | None:
    raw = os.getenv("MATERIALS_DIR", "").strip()
    if not raw:
        return None

    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    return p


def get_cors_allow_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    if not raw:
        return ["*"]
    return [part.strip() for part in raw.split(",") if part.strip()]
