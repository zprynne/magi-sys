"""Write the event JSON Schema to ``schema/magi-events.schema.json``.

Usage: ``uv run magi-schema`` (or ``--check`` to fail if the file is stale).
"""

from __future__ import annotations

import argparse
import sys

from magi.events import json_schema_text
from magi.paths import SCHEMA_FILE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = parser.parse_args(argv)

    text = json_schema_text()
    if args.check:
        current = SCHEMA_FILE.read_text() if SCHEMA_FILE.exists() else ""
        if current != text:
            print(f"{SCHEMA_FILE} is stale; run `uv run magi-schema`.", file=sys.stderr)
            return 1
        print(f"{SCHEMA_FILE} is up to date.")
        return 0

    SCHEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_FILE.write_text(text)
    print(f"wrote {SCHEMA_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
