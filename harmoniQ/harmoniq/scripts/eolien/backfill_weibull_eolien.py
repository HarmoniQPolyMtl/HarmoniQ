"""
Backfill Weibull coefficients (annual + seasonal) from multi-year ERA5 weather.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

import numpy as np
import pandas as pd

from harmoniq.core.meteo_era5 import Era5WeatherProvider
from harmoniq.db import CRUD
from harmoniq.db.engine import get_db
from harmoniq.modules.eolienne.calcule import adjust_wind_speed
from harmoniq.modules.eolienne.weibull.Weibull_calcule import (
    SEASON_ORDER,
    drop_feb29_from_index,
    estimate_weibull_coefficients,
    month_to_season,
)

WIND_REFERENCE_HEIGHT_M = 100.0


def _year_range(start_year: int, end_year: int) -> list[int]:
    if end_year < start_year:
        raise ValueError(f"Invalid year interval: start_year={start_year} end_year={end_year}")
    return list(range(start_year, end_year + 1))


def _load_era5_point_year(provider: Era5WeatherProvider, parc, year: int) -> pd.DataFrame:
    start = datetime(year, 1, 1, 0, 0, 0)
    end = datetime(year, 12, 31, 23, 0, 0)
    meteo = provider.get_weather_point(
        latitude=float(parc.latitude),
        longitude=float(parc.longitude),
        start=start,
        end=end,
        tz_out="UTC",
    ).copy()
    if meteo.empty:
        raise ValueError(f"No ERA5 rows returned for year={year}")

    idx = pd.to_datetime(meteo.index, utc=True).tz_localize(None)
    meteo.index = idx
    meteo = drop_feb29_from_index(meteo)
    return meteo


def _build_hub_wind_series(provider: Era5WeatherProvider, parc, years: list[int]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for year in years:
        meteo = _load_era5_point_year(provider=provider, parc=parc, year=year)
        v_ms = meteo["vitesse_vent_kmh"].astype(float).to_numpy() / 3.6
        # ERA5 wind speed is referenced at 100 m.
        v_hub_ms = adjust_wind_speed(v_ms, WIND_REFERENCE_HEIGHT_M, float(parc.hauteur_moyenne))
        frame = pd.DataFrame(
            {"wind_speed_ms": v_hub_ms},
            index=meteo.index,
        )
        frame["year"] = int(year)
        frame["month"] = frame.index.month.astype(int)
        frame["season"] = frame["month"].map(month_to_season)
        frames.append(frame)

    if not frames:
        raise ValueError("No meteo frames built")

    out = pd.concat(frames).sort_index()
    out = out[np.isfinite(out["wind_speed_ms"].to_numpy())]
    out = out[out["wind_speed_ms"] > 0]
    return out


def _fit_entry(samples: np.ndarray, min_samples: int) -> dict:
    k, c, sample_count, method = estimate_weibull_coefficients(samples, min_samples=min_samples)
    return {
        "k": float(k),
        "c": float(c),
        "sample_count": int(sample_count),
        "method": str(method),
    }


def _fit_details(df: pd.DataFrame, min_samples: int, granularity: str) -> tuple[dict, dict]:
    annual_entry = _fit_entry(df["wind_speed_ms"].to_numpy(dtype=float), min_samples=min_samples)
    seasonal: dict[str, dict] = {}
    if granularity == "seasonal":
        for season in SEASON_ORDER:
            season_values = (
                df.loc[df["season"] == season, "wind_speed_ms"]
                .to_numpy(dtype=float)
            )
            seasonal[season] = _fit_entry(season_values, min_samples=min_samples)
    return annual_entry, seasonal


def _serialize_fit_details(
    annual_entry: dict,
    seasonal_entries: dict[str, dict],
    start_year: int,
    end_year: int,
    weighting: str,
    granularity: str,
) -> str:
    payload = {
        "version": "seasonal_v1" if granularity == "seasonal" else "annual_v1",
        "ref_year_start": int(start_year),
        "ref_year_end": int(end_year),
        "weighting": str(weighting),
        "annual": annual_entry,
        "seasonal": seasonal_entries,
    }
    return json.dumps(payload, ensure_ascii=True)


def backfill_weibull(
    start_year: int = 2015,
    end_year: int = 2024,
    min_samples: int = 500,
    granularity: str = "seasonal",
) -> None:
    if granularity not in {"annual", "seasonal"}:
        raise ValueError(f"Unsupported granularity={granularity}. Expected annual|seasonal")

    years = _year_range(start_year=start_year, end_year=end_year)
    provider = Era5WeatherProvider()
    for year in years:
        provider.ensure_year_cached(year=year)

    db = next(get_db())
    parks = CRUD.read_all_eolienne_parc(db)
    total = len(parks)

    success = 0
    failed = 0
    seasonal_success = 0

    for park in parks:
        try:
            wind_df = _build_hub_wind_series(provider=provider, parc=park, years=years)
            annual_entry, seasonal_entries = _fit_details(
                wind_df, min_samples=min_samples, granularity=granularity
            )

            park.weibull_k = float(annual_entry["k"])
            park.weibull_c = float(annual_entry["c"])
            # Legacy compatibility: keep ref_year as latest year of the fitting window.
            park.weibull_ref_year = int(end_year)
            park.weibull_sample_count = int(annual_entry["sample_count"])
            park.weibull_updated_at = datetime.utcnow().isoformat()

            park.weibull_ref_year_start = int(start_year)
            park.weibull_ref_year_end = int(end_year)
            park.weibull_granularity = "seasonal_v1" if granularity == "seasonal" else "annual_v1"
            park.weibull_weighting = "equal_years"
            park.weibull_fit_details = _serialize_fit_details(
                annual_entry=annual_entry,
                seasonal_entries=seasonal_entries,
                start_year=start_year,
                end_year=end_year,
                weighting="equal_years",
                granularity=granularity,
            )

            db.add(park)
            db.commit()
            success += 1
            if granularity == "seasonal" and len(seasonal_entries) == len(SEASON_ORDER):
                seasonal_success += 1

            msg = (
                f"[ok] park_id={park.id} name={park.nom} "
                f"annual(k={annual_entry['k']:.4f}, c={annual_entry['c']:.4f}, "
                f"samples={annual_entry['sample_count']}, method={annual_entry['method']})"
            )
            if granularity == "seasonal":
                missing = [s for s in SEASON_ORDER if s not in seasonal_entries]
                if missing:
                    msg += f" seasonal_missing={','.join(missing)}"
                else:
                    msg += " seasonal=4/4"
            print(msg)
        except Exception as exc:
            db.rollback()
            failed += 1
            print(f"[fail] park_id={park.id} name={park.nom}: {exc}")

    refreshed = CRUD.read_all_eolienne_parc(db)
    non_null = sum(1 for p in refreshed if p.weibull_k is not None and p.weibull_c is not None)
    coverage = (non_null / total * 100.0) if total else 0.0

    print("----- Weibull Backfill Summary -----")
    print(f"years: {start_year}-{end_year}")
    print(f"granularity: {granularity}")
    print(f"total parks: {total}")
    print(f"success: {success}")
    print(f"failed: {failed}")
    print(f"non-null annual k/c: {non_null} ({coverage:.2f}%)")
    if granularity == "seasonal":
        print(f"seasonal complete (4 seasons): {seasonal_success}/{success}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill Weibull coefficients for wind parks from ERA5 multi-year cache"
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2015,
        help="Start year for Weibull fitting window (inclusive)",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2024,
        help="End year for Weibull fitting window (inclusive)",
    )
    parser.add_argument(
        "--granularity",
        choices=["annual", "seasonal"],
        default="seasonal",
        help="Fit annual-only or annual+seasonal Weibull coefficients",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=500,
        help="Minimum number of valid wind samples required for each fit",
    )
    args = parser.parse_args()
    backfill_weibull(
        start_year=args.start_year,
        end_year=args.end_year,
        min_samples=args.min_samples,
        granularity=args.granularity,
    )


if __name__ == "__main__":
    main()
