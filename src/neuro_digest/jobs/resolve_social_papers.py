from __future__ import annotations

import argparse
import logging

from neuro_digest.social_resolver import SocialPaperResolver


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve durable Bluesky scholarly links onto canonical Neurofeed papers"); parser.add_argument("--limit", type=int, default=1000); parser.add_argument("--log-level", default="INFO"); args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    resolved, unresolved, errors = SocialPaperResolver().resolve_pending(limit=args.limit); print(f"Social paper resolution: {resolved} resolved, {unresolved} unresolved, {errors} errors")


if __name__ == "__main__": main()
