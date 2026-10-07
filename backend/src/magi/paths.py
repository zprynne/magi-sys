"""Well-known repository paths."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
SCHEMA_FILE = REPO_ROOT / "schema" / "magi-events.schema.json"
DEFAULT_TRACES_DIR = REPO_ROOT / "traces"
DEFAULT_PERSONAS_DIR = REPO_ROOT / "personas"
ENV_FILE = REPO_ROOT / ".env"
