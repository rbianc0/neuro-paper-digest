from __future__ import annotations

import argparse
import logging

from neuro_digest.feedback import refresh_feedback_models


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Neurofeed learned preference representations from append-only feedback events")
    parser.add_argument("--config", default="config/feedback.yaml")
    parser.add_argument("--taxonomy", default="config/feature_taxonomy.yaml")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    users, papers = refresh_feedback_models(config_path=args.config, taxonomy_path=args.taxonomy)
    print(f"Refreshed learned models for {users} users from {papers} effective feedback-paper signals")


if __name__ == "__main__":
    main()
