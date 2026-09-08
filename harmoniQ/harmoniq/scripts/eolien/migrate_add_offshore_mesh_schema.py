"""
Add offshore mesh tables and eoliennes_parc.is_offshore in an idempotent way.
"""

from harmoniq.db.engine import engine
from harmoniq.db.schemas import SQLBase


EOLIENNE_TABLE = "eoliennes_parc"
IS_OFFSHORE_COLUMN = "is_offshore"


def migrate() -> None:
    SQLBase.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        table_info = conn.exec_driver_sql(f"PRAGMA table_info({EOLIENNE_TABLE})").fetchall()
        existing_columns = {row[1] for row in table_info}
        if IS_OFFSHORE_COLUMN in existing_columns:
            print(f"[skip] {EOLIENNE_TABLE}.{IS_OFFSHORE_COLUMN} already exists")
        else:
            conn.exec_driver_sql(
                f"ALTER TABLE {EOLIENNE_TABLE} ADD COLUMN {IS_OFFSHORE_COLUMN} BOOLEAN"
            )
            print(f"[ok] added {EOLIENNE_TABLE}.{IS_OFFSHORE_COLUMN} (BOOLEAN)")

    print("Offshore mesh schema migration complete.")


def main() -> None:
    migrate()


if __name__ == "__main__":
    main()
