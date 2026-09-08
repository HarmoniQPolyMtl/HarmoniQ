import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Load .env from the project root (harmoniQ/)
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE)
from sqlalchemy.orm import Session, sessionmaker

import inspect
from typing import Dict
import pandas as pd

from harmoniq import DB_PATH
from harmoniq.db import schemas

# engine.py : Ce fichier est responsable de la création de l'engine SQLAlchemy et de la session de base de données.
# Il est utilisé pour se connecter à la base de données et exécuter des requêtes.

if os.environ.get("HARMONIQ_TESTING") == "True":
    test_db_url = os.environ.get("TEST_DATABASE_URL")
    DATABASE__URL = test_db_url if test_db_url else "sqlite:///:memory:"
elif os.environ.get("HARMONIQ_DB") == "sqlite":
    DATABASE__URL = f"sqlite:///{DB_PATH}"
else:
    DATABASE__URL = os.getenv("DATABASE_URL", "postgresql://harmoniq:harmoniq@localhost:5432/harmoniq")  # fallback if .env missing

connect_args = {}
if DATABASE__URL.startswith("postgresql"):
    connect_args = {'options': '-csearch_path=reseau,public'}

engine = create_engine(DATABASE__URL, connect_args=connect_args)
if DATABASE__URL.startswith("sqlite"):
    engine = engine.execution_options(schema_translate_map={"reseau": None})
    
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

non_table_class = {'Scenario'}

def _get_sql_tables(schemas_module) -> Dict[type, Dict[str, type]]:
    all_classes = [member for _, member in inspect.getmembers(schemas_module, inspect.isclass)]
    # We can also make a liste of all the real classes meaning objects representing the tables 
    base_classes = [
        cls
        for cls in all_classes
        if issubclass(cls, schemas.SQLBase) and cls is not schemas.SQLBase
    ]
    # Get corresponding pydantic, create and response classes
    sql_tables = {}
    for cls in base_classes:
        if cls.__name__ in non_table_class: continue
        base_class = [c for c in all_classes if c.__name__ == f"{cls.__name__}Base"][0]
        
        create_class_matches = [c for c in all_classes if c.__name__ == f"{cls.__name__}Create"]
        create_class = create_class_matches[0] if create_class_matches else base_class
        
        response_class_matches = [c for c in all_classes if c.__name__ == f"{cls.__name__}Response"]
        response_class = response_class_matches[0] if response_class_matches else base_class
        
        sql_tables[cls] = {
            "base": base_class,
            "create": create_class,
            "response": response_class,
        }
    return sql_tables

#In this there are four types of classes , base ones (from pydantic), create ones (for creating new objects) and response ones (for returning the data)
sql_tables = _get_sql_tables(schemas)

"""Example: print(sql_tables)
{
<class 'harmoniq.db.schemas.Bus'>: {'base': <class 'harmoniq.db.schemas.BusBase'>, 'create': <class 'harmoniq.db.schemas.BusCreate'>, 'response': <class 'harmoniq.db.schemas.BusResponse'>}, 
<class 'harmoniq.db.schemas.EolienneParc'>: {'base': <class 'harmoniq.db.schemas.EolienneParcBase'>, 'create': <class 'harmoniq.db.schemas.EolienneParcCreate'>, 'response': <class 'harmoniq.db.schemas.EolienneParcResponse'>}, 
<class 'harmoniq.db.schemas.Hydro'>: {'base': <class 'harmoniq.db.schemas.HydroBase'>, 'create': <class 'harmoniq.db.schemas.HydroCreate'>, 'response': <class 'harmoniq.db.schemas.HydroResponse'>}, 
<class 'harmoniq.db.schemas.Line'>: {'base': <class 'harmoniq.db.schemas.LineBase'>, 'create': <class 'harmoniq.db.schemas.LineCreate'>, 'response': <class 'harmoniq.db.schemas.LineResponse'>}, 
<class 'harmoniq.db.schemas.LineType'>: {'base': <class 'harmoniq.db.schemas.LineTypeBase'>, 'create': <class 'harmoniq.db.schemas.LineTypeCreate'>, 'response': <class 'harmoniq.db.schemas.LineTypeResponse'>}, 
<class 'harmoniq.db.schemas.ListeInfrastructures'>: {'base': <class 'harmoniq.db.schemas.ListeInfrastructuresBase'>, 'create': <class 'harmoniq.db.schemas.ListeInfrastructuresCreate'>, 'response': <class 'harmoniq.db.schemas.ListeInfrastructuresResponse'>}, 
<class 'harmoniq.db.schemas.Nucleaire'>: {'base': <class 'harmoniq.db.schemas.NucleaireBase'>, 'create': <class 'harmoniq.db.schemas.NucleaireCreate'>, 'response': <class 'harmoniq.db.schemas.NucleaireResponse'>}, 
<class 'harmoniq.db.schemas.Scenario'>: {'base': <class 'harmoniq.db.schemas.ScenarioBase'>, 'create': <class 'harmoniq.db.schemas.ScenarioCreate'>, 'response': <class 'harmoniq.db.schemas.ScenarioResponse'>},
<class 'harmoniq.db.schemas.Solaire'>: {'base': <class 'harmoniq.db.schemas.SolaireBase'>, 'create': <class 'harmoniq.db.schemas.SolaireCreate'>, 'response': <class 'harmoniq.db.schemas.SolaireResponse'>}, 
<class 'harmoniq.db.schemas.Thermique'>: {'base': <class 'harmoniq.db.schemas.ThermiqueBase'>, 'create': <class 'harmoniq.db.schemas.ThermiqueCreate'>, 'response': <class 'harmoniq.db.schemas.ThermiqueResponse'>}
}
"""

#Launch the session where we have the database that will evolve (it is like a dataholder where commands from the API and data will be stored and interact)

def get_db():
    """
    Crée une session de base de données pour interagir avec la base de données.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Get all MRCs , MRC stands for Municipalité Régionale de Comté

def get_all_mrcs_population(db: Session, mrc_id: int) -> pd.DataFrame:
    data = (
        db.query(schemas.InstancePopulation)
        .filter(schemas.InstancePopulation.mrc_id == mrc_id)
        .all()
    )

    df = pd.DataFrame(
        [{"annee": item.annee, "population": item.population} for item in data]
    )
    return df
