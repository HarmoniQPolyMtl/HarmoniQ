import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from typing import Optional

import pandas as pd

from harmoniq.db.schemas import Scenario, Weather, Consomation

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ENV_FILE)


_engine = None


def _get_engine():
    """Open the DB connection lazily (no side effects at import time)."""
    global _engine
    if _engine is not None:
        return _engine

    db_url = os.getenv("DATABASE_URL", "postgresql://harmoniq:harmoniq@localhost:5432/harmoniq")
    
    _engine = create_engine(db_url, connect_args={'options': '-csearch_path=demande,public'})
    return _engine

async def get_all_sectors() -> pd.DataFrame:
    query = """
        SELECT DISTINCT m.sector
        FROM metadata m
        JOIN demande d ON d.meta_id = m.id
    """
    df = pd.read_sql_query(query, _get_engine())
    return df

async def read_demande_data(
    scenario: Scenario,
    CUID: Optional[int] = None,
) -> pd.DataFrame:
    if CUID is None:
        CUID = 1  # Default value = Total

    query = """
        SELECT d.date, d.electricity, d.gaz, m.sector
        FROM demande d
        JOIN metadata m ON d.meta_id = m.id
        WHERE m.cuid = %(CUID)s
        AND m.weather = %(weather)s
        AND m.scenario = %(scenario)s
        AND d.date BETWEEN %(start_date)s AND %(end_date)s
        ORDER BY d.date, m.sector
    """

    weather_string = Weather(scenario.weather).name
    consomation_string = Consomation(scenario.consomation).name

    params = {
        "CUID": CUID,
        "weather": weather_string,
        "scenario": consomation_string,
        "start_date": scenario.date_de_debut,
        "end_date": scenario.date_de_fin,
    }
    df = pd.read_sql_query(query, _get_engine(), params=params)
    return df


async def read_demande_data_sankey(
    scenario: Scenario,
    CUID: Optional[int] = None,
) -> pd.DataFrame:
    if CUID is None:
        CUID = 1  # Default value = Total

    query = """
        SELECT m.sector, SUM(d.electricity) AS total_electricity, SUM(d.gaz) AS total_gaz
        FROM demande d
        JOIN metadata m ON d.meta_id = m.id
        WHERE m.cuid = %(CUID)s
        AND m.weather = %(weather)s
        AND m.scenario = %(scenario)s
        AND d.date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY m.sector
        ORDER BY m.sector
    """

    weather_string = Weather(scenario.weather).name
    consomation_string = Consomation(scenario.consomation).name

    params = {
        "CUID": CUID,
        "weather": weather_string,
        "scenario": consomation_string,
        "start_date": scenario.date_de_debut,
        "end_date": scenario.date_de_fin,
    }
    df = pd.read_sql_query(query, _get_engine(), params=params)
    return df


async def read_demande_data_temporal(
    scenario: Scenario,
    CUID: Optional[int] = None,
) -> pd.DataFrame:
    if CUID is None:
        CUID = 1  # Default value = Total

    query = """
        SELECT d.date, SUM(d.electricity) AS total_electricity, SUM(d.gaz) AS total_gaz
        FROM demande d
        JOIN metadata m ON d.meta_id = m.id
        WHERE m.cuid = %(CUID)s
        AND m.weather = %(weather)s
        AND m.scenario = %(scenario)s
        AND d.date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY d.date
        ORDER BY d.date
    """
    weather_string = Weather(scenario.weather).name
    consomation_string = Consomation(scenario.consomation).name
    
    params = {
        "CUID": CUID,
        "weather": weather_string,
        "scenario": consomation_string,
        "start_date": scenario.date_de_debut,
        "end_date": scenario.date_de_fin,
    }
    df = pd.read_sql_query(query, _get_engine(), params=params)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    return df

if os.environ.get("HARMONIQ_DB") == "sqlite":
    from harmoniq.db.demande_sqlite import (
        get_all_sectors,
        read_demande_data,
        read_demande_data_sankey,
        read_demande_data_temporal,
    )

if __name__ == "__main__":
    # Test the function
    import asyncio
    scenario = Scenario(
        weather=1,
        consomation=1,
        date_de_debut="2035-01-01",
        date_de_fin="2035-01-31",
    )
    df = asyncio.run(read_demande_data(scenario, CUID=2431))
    print(df)
