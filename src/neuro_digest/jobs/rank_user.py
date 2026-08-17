from __future__ import annotations

import argparse
import json

from neuro_digest.ranking import RankingService


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview transparent Neurofeed ranking for one user")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--ranking-config", default="config/ranking.yaml")
    parser.add_argument("--taxonomy", default="config/feature_taxonomy.yaml")
    args = parser.parse_args()
    service = RankingService(ranking_config_path=args.ranking_config, taxonomy_path=args.taxonomy)
    rows = service.rank_user(args.user_id, total=max(1, min(args.limit, 50)))
    print(json.dumps([row.to_dict() for row in rows], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
