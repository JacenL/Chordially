"""Application configuration, loaded from .env at the project root.

Kept tiny and dependency-light on purpose. The one thing worth stating clearly:
we load .env into os.environ ourselves rather than letting the Anthropic SDK
discover credentials, so that PRACTICEMAP_ANTHROPIC_API_KEY is the only key this
application can ever use.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_env(path: Path | None = None, override: bool = False) -> dict[str, str]:
    """Read KEY=VALUE lines from .env into os.environ. Missing file is fine."""
    target = path or ENV_PATH
    loaded: dict[str, str] = {}
    if not target.exists():
        return loaded
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return loaded


def resolve_work_dir() -> Path:
    """Where generated, uncommitted data lives: rendered upload pages, caches.

    Order: PRACTICEMAP_WORK_DIR if set; otherwise work/ under the project root,
    which .gitignore excludes; otherwise, when the project tree is read-only
    (serverless hosts such as Vercel mount the code read-only and offer only
    the system temp directory), a chordially-work/ directory under that temp
    directory. The fallback is per-instance and not durable, which matches how
    uploads are already held: in memory, for the life of the process.
    """
    override = os.environ.get("PRACTICEMAP_WORK_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    candidate = PROJECT_ROOT / "work"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write-probe"
        probe.touch()
        probe.unlink()
        return candidate
    except OSError:
        return Path(tempfile.gettempdir()) / "chordially-work"


# .env is read here, before WORK_DIR is fixed, so a PRACTICEMAP_WORK_DIR set in
# .env applies to modules imported before the app calls load_env() itself.
# load_env() never overrides variables already in the environment, so the
# later call in src/app/main.py is harmless.
load_env()
WORK_DIR = resolve_work_dir()


def has_app_credentials() -> bool:
    """Whether the app's own key is configured.

    Deliberately checks only PRACTICEMAP_ANTHROPIC_API_KEY. An ambient
    ANTHROPIC_API_KEY does not count and must not make example mode look
    credentialed when it is not.
    """
    return bool(os.environ.get("PRACTICEMAP_ANTHROPIC_API_KEY", "").strip())
