"""
Add Weibull columns to eoliennes_parc in a non-destructive and idempotent way.
"""

from harmoniq.db.engine import engine


TABLE_NAME = "eoliennes_parc"
WEIBULL_COLUMNS = {
    "weibull_k": "FLOAT",
    "weibull_c": "FLOAT",
    "weibull_ref_year": "INTEGER",
    "weibull_sample_count": "INTEGER",
    "weibull_updated_at": "TEXT",
    "weibull_ref_year_start": "INTEGER",
    "weibull_ref_year_end": "INTEGER",
    "weibull_granularity": "TEXT",
    "weibull_weighting": "TEXT",
    "weibull_fit_details": "TEXT",
}


def migrate() -> None:
    with engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.exec_driver_sql(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        }

        for column_name, column_type in WEIBULL_COLUMNS.items():
            if column_name in existing:
                print(f"[skip] {TABLE_NAME}.{column_name} already exists")
                continue
            sql = f"ALTER TABLE {TABLE_NAME} ADD COLUMN {column_name} {column_type}"
            conn.exec_driver_sql(sql)
            print(f"[ok] added {TABLE_NAME}.{column_name} ({column_type})")

    print("Weibull schema migration complete.")


def main() -> None:
    migrate()


if __name__ == "__main__":
    main()
