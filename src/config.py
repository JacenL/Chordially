"""Application configuration, loaded from .env at the project root.

Kept tiny and dependency-light on purpose. The one thing worth stating clearly:
we load .env into os.environ ourselves rather than letting the Anthropic SDK
discover credentials, so that PRACTICEMAP_ANTHROPIC_API_KEY is the only key this
application can ever use.
"""

from __future__ import annotations

import os
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


def has_app_credentials() -> bool:
    """Whether the app's own key is configured.

    Deliberately checks only PRACTICEMAP_ANTHROPIC_API_KEY. An ambient
    ANTHROPIC_API_KEY does not count and must not make example mode look
    credentialed when it is not.
    """
    return bool(os.environ.get("PRACTICEMAP_ANTHROPIC_API_KEY", "").strip())
