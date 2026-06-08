from pathlib import Path
from uuid import uuid4

from app.utils.config import settings


def ensure_storage() -> Path:
    root = Path(settings.storage_dir)
    for child in ("reports", "screenshots", "logos"):
        (root / child).mkdir(parents=True, exist_ok=True)
    return root


def storage_path(folder: str, suffix: str) -> Path:
    ensure_storage()
    return Path(settings.storage_dir) / folder / f"{uuid4().hex}{suffix}"


def public_url(path: Path) -> str:
    normalized = path.as_posix()
    return f"{settings.app_base_url.rstrip('/')}/{normalized}"
