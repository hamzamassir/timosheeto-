"""Read .env without logging values."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"Missing {path.name}. Copy .env.example and fill it in.")
    env: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def ensure_keys(path: Path, keys: list[str]) -> list[str]:
    """Append keys that are absent. Existing values are left untouched."""
    existing = read_env(path)
    missing = [key for key in keys if key not in existing]
    if not missing:
        return []
    text = path.read_text()
    addition = "" if text.endswith("\n") or not text else "\n"
    addition += "".join(f"{key}=\n" for key in missing)
    path.write_text(text + addition)
    return missing
