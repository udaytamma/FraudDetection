"""CLI wrapper for the offline replay framework."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.replay import replay


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay historical evidence with an ML model")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--model-path", required=True, help="Path to model file")
    parser.add_argument("--model-type", default="xgb_classifier", help="xgb_classifier or lgbm_classifier")
    parser.add_argument("--threshold", type=float, default=0.7, help="Decision threshold")
    parser.add_argument("--postgres-url", default=None, help="Override Postgres URL")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)

    results = replay(
        start=start,
        end=end,
        model_path=args.model_path,
        model_type=args.model_type,
        threshold=args.threshold,
        postgres_url=args.postgres_url,
    )

    print(json.dumps(results.to_dict(), indent=2))


if __name__ == "__main__":
    main()
