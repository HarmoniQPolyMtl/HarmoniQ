from __future__ import annotations

import argparse
import logging
from pathlib import Path

from harmoniq.db.engine import get_db
from harmoniq.modules.eolienne.site_selection_2035 import (
    Selection2035Config,
    run_site_selection_2035,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select new Quebec wind sites (V1 greedy backend) until installed capacity exceeds 10,000 MW."
    )
    parser.add_argument("--start-year", type=int, default=2015, help="First ERA5 year (inclusive)")
    parser.add_argument("--end-year", type=int, default=2024, help="Last ERA5 year (inclusive)")
    parser.add_argument(
        "--park-mw",
        type=float,
        default=200.0,
        help="Installed capacity per new selected park (MW)",
    )
    parser.add_argument(
        "--target-mw",
        type=float,
        default=10000.0,
        help="Greedy stop threshold for installed capacity (MW)",
    )
    parser.add_argument(
        "--min-distance-km",
        type=float,
        default=20.0,
        help="Minimum distance between new parks and existing/selected parks",
    )
    parser.add_argument(
        "--waters-geojson",
        type=Path,
        default=None,
        help=(
            "Path to Quebec waters geometry GeoJSON. "
            "If missing, offshore candidates are excluded."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output folder for ranking/selection/map artifacts",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    cfg = Selection2035Config(
        start_year=args.start_year,
        end_year=args.end_year,
        park_capacity_mw=args.park_mw,
        target_installed_mw=args.target_mw,
        min_distance_km=args.min_distance_km,
        waters_geojson_path=args.waters_geojson
        if args.waters_geojson is not None
        else Selection2035Config().waters_geojson_path,
        output_dir=args.output_dir if args.output_dir is not None else Selection2035Config().output_dir,
    )

    db = next(get_db())
    outputs = run_site_selection_2035(db=db, config=cfg)
    print("----- Site Selection 2035 -----")
    print(f"Selected parks: {outputs['selected_count']}")
    print(f"Final installed MW: {outputs['final_installed_mw']:.2f}")
    print(f"Ranking CSV: {outputs['ranking_csv']}")
    print(f"Selected CSV: {outputs['selected_csv']}")
    print(f"Map PNG: {outputs['map_png']}")
    print(f"Summary JSON: {outputs['summary_json']}")


if __name__ == "__main__":
    main()
