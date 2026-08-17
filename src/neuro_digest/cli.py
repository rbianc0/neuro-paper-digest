from __future__ import annotations

import argparse
import logging

from neuro_digest.pipeline import run


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/interests.yaml")
    p.add_argument("--output-dir", default="data")
    p.add_argument("--docs-dir", default="docs")
    p.add_argument("--lookback-days", type=int, default=7)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    candidates = run(args.config, args.output_dir, args.docs_dir, args.lookback_days)
    print(f"Wrote {len(candidates)} unique candidates")


if __name__ == "__main__":
    main()
