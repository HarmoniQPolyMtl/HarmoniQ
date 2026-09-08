from __future__ import annotations

import argparse
import logging

from harmoniq.core.meteo_era5 import Era5WeatherProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Download/cache ERA5 (Quebec, 1.5deg grid)")
    parser.add_argument("--year", type=int, default=2024, help="Target year to cache")
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force monthly re-download even if raw files already exist",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    provider = Era5WeatherProvider()
    provider.ensure_year_cached(year=args.year, force_download=args.force_download)
    print(f"ERA5 cache ready for year={args.year}")


if __name__ == "__main__":
    main()
