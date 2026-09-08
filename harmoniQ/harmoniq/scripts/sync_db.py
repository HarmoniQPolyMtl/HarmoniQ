import sys
import os

# Add the project root to sys.path
project_root = r'C:\Users\Yacine\Desktop\HarmoniQ\harmoniQ'
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import sqlalchemy as sa
import pandas as pd
from harmoniq.db import schemas

# Define engines
# Use search_path=reseau so that metadata.drop_all/create_all works on the 'reseau' schema
engine_sqlite = sa.create_engine('sqlite:///C:/Users/Yacine/Desktop/HarmoniQ/harmoniQ/harmoniq/db/db.sqlite')
engine_pg = sa.create_engine('postgresql://postgres:harmoniq@localhost:5432/harmoniq', connect_args={'options': '-csearch_path=reseau'})

# The tables we want to copy from sqlite to postgres. 
tables = ['scenario', 'bus', 'line_type', 'line', 'solaire', 'eoliennes_parc', 'hydro', 'thermique', 'nucleaire']
# Note: we might also have 'quebec_offshore_mesh_meta' and 'quebec_offshore_mesh_points' in PG which weren't in SQLite, 
# dropping all might drop them. Let's just drop all SQLBase tables.

def sync_dbs():
    print("Connecting to databases...")
    
    # Check tables in sqlite
    with engine_sqlite.connect() as conn:
        res = conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        sqlite_tables = [r[0] for r in res]
        print(f"Tables in SQLite: {sqlite_tables}")

    print("Dropping and recreating PostgreSQL tables to update schema...")
    with engine_pg.begin() as conn_pg:
        # We manually drop the tables in reverse order to avoid FK issues
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.line CASCADE"))
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.line_type CASCADE"))
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.bus CASCADE"))
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.scenario CASCADE"))
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.solaire CASCADE"))
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.eoliennes_parc CASCADE"))
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.hydro CASCADE"))
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.thermique CASCADE"))
        conn_pg.execute(sa.text("DROP TABLE IF EXISTS reseau.nucleaire CASCADE"))
        # we can also just use cascade on all as dropping all

        # drop and create all using SQLAlchemy metadata
        schemas.SQLBase.metadata.create_all(conn_pg)

    for tbl in tables:
        if tbl not in sqlite_tables:
            print(f"Table {tbl} not found in SQLite, skipping...")
            continue
        
        print(f"Reading {tbl} from SQLite...")
        query = f'SELECT * FROM "{tbl}"'
        df = pd.read_sql_query(query, engine_sqlite)
        
        # Manually convert known boolean columns since read_sql_query returns them as 0/1 integers
        if 'is_offshore' in df.columns:
            df['is_offshore'] = df['is_offshore'].astype(bool)
            
        print(f"Inserting {len(df)} rows into reseau.\"{tbl}\" in PostgreSQL...")
        # Since we just recreated empty tables with correct schema, we can append
        df.to_sql(name=tbl, con=engine_pg, schema='reseau', if_exists='append', index=False)
        print(f"Done syncing {tbl}.")

if __name__ == '__main__':
    sync_dbs()
    print("Database synchronization completed successfully!")
