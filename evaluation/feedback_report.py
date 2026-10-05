"""Local-only aggregate of anonymous feedback; no API route or raw-row export."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import Config
from medsafety.feedback_store import FeedbackStore


ROOT = Path(__file__).resolve().parents[1]


def feedback_report(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"feedback database does not exist: {path}")
    return FeedbackStore(path).summary()


def main():
    parser = argparse.ArgumentParser(description="Aggregate local feedback without question text")
    parser.add_argument("--db", type=Path, default=Path(Config.FEEDBACK_DB_PATH))
    args = parser.parse_args()
    path = args.db if args.db.is_absolute() else ROOT / args.db
    print(json.dumps(feedback_report(path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
