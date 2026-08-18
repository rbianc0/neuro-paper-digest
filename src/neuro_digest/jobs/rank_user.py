from __future__ import annotations

import argparse
import json

from neuro_digest.ranking import rank_for_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Neurofeed ranking v1 for one user without creating a digest")
    parser.add_argument("user_id")
    parser.add_argument("--config", default="config/ranking.yaml")
    args = parser.parse_args()
    ranked = rank_for_user(args.user_id, config_path=args.config)
    print(json.dumps([item.to_dict() for item in ranked], indent=2, default=str))


if __name__ == "__main__":
    main()
