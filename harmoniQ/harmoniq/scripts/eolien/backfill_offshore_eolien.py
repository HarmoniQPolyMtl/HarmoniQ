from __future__ import annotations

import argparse

from harmoniq.core.offshore import (
    DEFAULT_QC_OFFSHORE_GRID_VERSION,
    is_offshore_quebec,
)
from harmoniq.db import CRUD
from harmoniq.db.engine import get_db


def backfill_eolienne_is_offshore(
    grid_version: str = DEFAULT_QC_OFFSHORE_GRID_VERSION,
    dry_run: bool = False,
) -> dict[str, int]:
    db = next(get_db())
    try:
        parcs = CRUD.read_all_eolienne_parc(db)

        updated = 0
        skipped = 0
        for parc in parcs:
            value = is_offshore_quebec(
                latitude=float(parc.latitude),
                longitude=float(parc.longitude),
                db=db,
                grid_version=grid_version,
            )
            if parc.is_offshore is value:
                skipped += 1
                continue
            parc.is_offshore = bool(value)
            updated += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()

        return {"updated": updated, "skipped": skipped, "total": len(parcs)}
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill eoliennes_parc.is_offshore from Quebec offshore mesh"
    )
    parser.add_argument(
        "--grid-version",
        type=str,
        default=DEFAULT_QC_OFFSHORE_GRID_VERSION,
        help="Offshore mesh grid_version used for classification",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute updates but rollback DB changes",
    )
    args = parser.parse_args()

    out = backfill_eolienne_is_offshore(
        grid_version=args.grid_version,
        dry_run=args.dry_run,
    )
    print("----- Offshore Backfill Eolien -----")
    print(f"grid_version: {args.grid_version}")
    print(f"total: {out['total']}")
    print(f"updated: {out['updated']}")
    print(f"skipped: {out['skipped']}")
    print(f"dry_run: {args.dry_run}")


if __name__ == "__main__":
    main()
