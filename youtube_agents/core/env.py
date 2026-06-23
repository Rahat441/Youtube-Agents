"""Small .env loader used by local CLI runs."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(paths: list[Path] | None = None) -> None:
    """Load KEY=VALUE lines into the environment without overriding existing values."""
    if paths is None:
        root = Path(__file__).resolve().parents[2]
        paths = [root / ".env", root.parent / ".env", root.parent / "Youtube-Ai_v2" / ".env"]

    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

