import asyncio
import hashlib
import time
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import os
import glob

from typing import List, Optional
from datetime import datetime, timedelta
import pandas as pd


from harmoniq.db import schemas, engine, CRUD
from harmoniq.db.CRUD import (
    create_data,
    read_all_data,
    read_multiple_by_id,
    read_data_by_id,
    update_data,
    delete_data,
    hydrate_model
)
from harmoniq.db.demande import (
    read_demande_data, 
    read_demande_data_sankey, 
    read_demande_data_temporal,
)
from harmoniq.core import meteo
from harmoniq.core.meteo_era5 import Era5WindMapService
from harmoniq.db.engine import get_db
from harmoniq.core.fausse_données import production_aleatoire
from harmoniq.core.offshore import is_offshore_quebec


from harmoniq.modules.eolienne import InfraParcEolienne
from harmoniq.modules.reseau_v2.service import InfraReseauBis
from harmoniq.modules.solaire import InfraSolaire
from harmoniq.modules.thermique import InfraThermique
from harmoniq.modules.nucleaire import InfraNucleaire
from harmoniq.modules.hydro import InfraHydro
import json
import time

# Cache mémoire des résultats reseau_v2 (max 20 entrées, FIFO).
_reseau_cache: dict = {}
_RESEAU_CACHE_MAX = 20

def _reseau_cache_key(scenario_id: int, infra_group, resolution: str, flow_mode: str) -> str:
    ids = sorted([
        *[str(e.id) for e in (infra_group.parc_eoliens or [])],
        *[str(s.id) for s in (infra_group.parc_solaires or [])],
        *[str(h.id) for h in (infra_group.central_hydroelectriques or [])],
        *[str(t.id) for t in (infra_group.central_thermique or [])],
        *[str(n.id) for n in (infra_group.central_nucleaire or [])],
    ])
    infra_hash = hashlib.md5("|".join(ids).encode()).hexdigest()[:8]
    return f"{scenario_id}|{infra_hash}|{resolution}|{flow_mode}"

def _reseau_cache_set(key: str, value: dict) -> None:
    if key not in _reseau_cache and len(_reseau_cache) >= _RESEAU_CACHE_MAX:
        _reseau_cache.pop(next(iter(_reseau_cache)))
    _reseau_cache[key] = value

#Appel des modules de production énergétique, ainsi que d'autres modules, et crée des routes web pour chaque fonction CRUD et autre!

router = APIRouter(
    prefix="/api",
    responses={404: {"description": "Not found"}},
)
_wind_map_service = Era5WindMapService()

# Route de test
@router.get("/ping")
async def ping():
    return {"ping": "pong"}


@router.delete(
    "/scenario/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scenario and purge its on-disk caches"
)
async def delete_scenario_and_purge_cache(
    scenario_id: int,
    db: Session = Depends(get_db),
):
    # 1) Load the scenario
    scenario = await read_data_by_id(db, schemas.Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Invalider le cache mémoire reseau_v2 pour ce scénario
    keys_to_remove = [k for k in _reseau_cache if k.startswith(f"{scenario_id}|")]
    for k in keys_to_remove:
        _reseau_cache.pop(k, None)

    # Delete the scenario record from the database
    result = await delete_data(db, schemas.Scenario, scenario_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Returns 204 No Content
    return








#-----#-----#-----#-----#-----#  Creation des méthodes CRUD  #-----#-----#-----#-----#-----#

# Création des méthodes CRUD sur FastAPI
api_routers = {}

for sql_class, pydantic_classes in engine.sql_tables.items():
    table_name = sql_class.__name__
    table_name_lower = table_name.lower()

    response_class = pydantic_classes["response"]

    class_router = APIRouter(
        prefix=f"/{table_name_lower}",
        tags=[table_name],
    )
    api_routers[table_name_lower] = class_router

    # Define the endpoints within a closure
    def create_endpoints(sql_class, response_class, table_name_lower):
        @class_router.get(
            "",
            response_model=List[response_class],
            summary=f"Read all {table_name_lower}s",
        )
        async def read_all(db: Session = Depends(get_db)):
            result = await read_all_data(db, sql_class)
            return result

        @class_router.get(
            "/{item_id}",
            response_model=response_class,
            summary=f"Read a {table_name} by id",
        )
        async def read(item_id: int, db: Session = Depends(get_db)):
            result = await read_data_by_id(db, sql_class, item_id)
            if result is None:
                raise HTTPException(
                    status_code=404, detail=f"{table_name_lower} {item_id} not found"
                )
            return result

    # Call the closure to define the endpoints
    create_endpoints(sql_class, response_class, table_name_lower)

#-----#-----#-----#-----#-----#  Demande d'energie  #-----#-----#-----#-----#-----#

# Demande : permet de lire la demande d'energie
demande_router = APIRouter(
    prefix="/demande",
    tags=["Demande"],
    responses={404: {"description": "Not found"}},
)

@demande_router.post("/")
async def read_demande(
    scenario: schemas.ScenarioResponse,
    CUID: Optional[int] = None,
    db: Session = Depends(get_db),
):

    demande = await read_demande_data(scenario, CUID)
    return "ping"

@demande_router.post("/sankey")
async def read_demande_sankey(
    scenario: schemas.ScenarioResponse,
    CUID: Optional[int] = None,
    db: Session = Depends(get_db),
):

    demande = await read_demande_data_sankey(scenario, CUID)
    return demande

@demande_router.post("/temporal")
async def read_demande_temporal(
    scenario: schemas.ScenarioResponse,
    CUID: Optional[int] = None,
    db: Session = Depends(get_db),
):

    demande = await read_demande_data_temporal(scenario, CUID)
    return demande


router.include_router(demande_router)

#-----#-----#-----#-----#-----#  Lecture de la météo  #-----#-----#-----#-----#-----#

meteo_router = APIRouter(
    prefix="/meteo",
    tags=["Meteo"],
    responses={404: {"description": "Not found"}},
)

@meteo_router.post("/get_data")
def get_meteo_data(
    latitude: float,
    longitude: float,
    interpolate: bool,
    start_time: datetime,
    granularity: int,
    end_time: Optional[datetime] = None,
):
    try:
        granularity = meteo.Granularity(granularity)
    except ValueError:
        raise HTTPException(status_code=400, detail="Granularity must be 1 or 2")

    helper = meteo.WeatherHelper(
        position=schemas.PositionBase(latitude=latitude, longitude=longitude),
        interpolate=interpolate,
        start_time=start_time,
        end_time=end_time,
        granularity=granularity,
    )
    helper.load()
    csv_buffer = helper.data.to_csv()
    return StreamingResponse(
        csv_buffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=weather_data.csv"},
    )


@meteo_router.get("/offshore-check")
def check_offshore(latitude: float, longitude: float, db: Session = Depends(get_db)):
    try:
        is_off = is_offshore_quebec(latitude, longitude, db)
        return {"is_offshore": is_off}
    except Exception as e:
        return {"is_offshore": False, "error": str(e)}


@meteo_router.get("/wind-map/years")
def get_wind_map_years():
    years = _wind_map_service.get_available_years()
    if not years:
        raise HTTPException(
            status_code=404,
            detail="No ERA5 annual cache available for wind-map.",
        )
    return {
        "years": years,
        "default_year": _wind_map_service.get_default_year(years),
    }


@meteo_router.get("/wind-map/annual")
def get_wind_map_annual(year: int):
    years = _wind_map_service.get_available_years()
    if year not in years:
        raise HTTPException(
            status_code=404,
            detail=f"ERA5 wind-map data unavailable for year={year}",
        )
    try:
        return _wind_map_service.get_annual_wind_map(year=year)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

router.include_router(meteo_router)

#-----#-----#-----#-----#-----#  Infra Specific  #-----#-----#-----#-----#-----#

PRODUCTION_MAPPING = {
    "eolienneparc": (InfraParcEolienne, schemas.EolienneParc),
    "solaire": (InfraSolaire, schemas.Solaire),
    "thermique": (InfraThermique, schemas.Thermique),
    "nucleaire": (InfraNucleaire, schemas.Nucleaire),
    "hydro": (InfraHydro, schemas.Hydro),
}

def get_infra_object(infra_type, payload):
    if infra_type not in PRODUCTION_MAPPING:
        raise HTTPException(400, f"Unsupported infra: '{infra_type}'")

    infra_class, infra_schema = PRODUCTION_MAPPING[infra_type]

    sql_model_instance = hydrate_model(infra_schema, payload.infra_payload)
    return infra_class(sql_model_instance)

@router.post("/production/{infra_type}")
async def calculer_production(
    infra_type: str, 
    payload: schemas.InfraSimulationPayload
):
    scenario = hydrate_model(schemas.Scenario, payload.scenario)
    infra = get_infra_object(infra_type, payload)
    infra.charger_scenario(scenario)

    production: pd.DataFrame = infra.calculer_production()
    if production is None or production.empty:
        return []

    return json.loads(production.fillna(0).to_json(date_format='iso'))

@router.post("/cout/{infra_type}")
async def calculer_cout(
    infra_type: str, 
    payload: schemas.InfraSimulationPayload
):
    scenario = hydrate_model(schemas.Scenario, payload.scenario)
    infra = get_infra_object(infra_type, payload)
    infra.charger_scenario(scenario)
    results = {
        'cout_annuel': infra.calculer_cout_pas_de_temps(timedelta(days=365)),
        'cout_construction': infra.calculer_cout_construction(),
    }
    return results

@router.post("/emission/{infra_type}")
async def calculer_emission(
    infra_type: str, 
    payload: schemas.InfraSimulationPayload
):
    scenario = hydrate_model(schemas.Scenario, payload.scenario)
    infra = get_infra_object(infra_type, payload)
    infra.charger_scenario(scenario)
    results = {
        'co2_annuel': infra.calculer_co2_eq_pas_de_temps(timedelta(days=365)),
        'co2_construction': infra.calculer_co2_eq_construction(),
    }
    return results


#-----#-----#-----#-----#-----#  Fake Data  #-----#-----#-----#-----#-----#

faker_router = APIRouter(
    prefix="/faker",
    tags=["Faker"],
    responses={404: {"description": "Not found"}},
)


@faker_router.post("/production")
async def get_production_aleatoire(scenario: schemas.ScenarioResponse):

    production = await asyncio.to_thread(production_aleatoire, scenario)
    return production


router.include_router(faker_router)

#-----#-----#-----#-----#-----#  Production : Reseau  #-----#-----#-----#-----#-----#

reseau_router = APIRouter(
    prefix="/reseau",
    tags=["Reseau"],
    responses={404: {"description": "Not found"}},
)

@reseau_router.post("/production")
async def calculer_production_reseau(
    payload: schemas.ReseauSimulationPayload,
    is_journalier: bool = False,
    flow_mode: str = "ac",
    resolution: str = "horaire",
    db: Session = Depends(get_db),
):
    """Dispatch LOPF + flux AC via reseau_v2 (HiGHS solver).

    Retourne un dict avec :
      - production     : liste de snapshots avec total_xxx par carrier
      - violations     : lignes en surcharge thermique
      - link_flows     : flux import/export par interconnexion
      - summary        : KPIs globaux (énergie, pertes, import, export)
      - metadata       : infos simulation (cached, resolution, temps)
    """
    scenario = payload.scenario
    infra_group = payload.infra_group

    # Cache mémoire : évite de refaire le calcul si rien n'a changé
    cache_key = _reseau_cache_key(scenario.id, infra_group, resolution, flow_mode)
    if cache_key in _reseau_cache:
        cached = _reseau_cache[cache_key]
        if isinstance(cached.get("metadata"), dict):
            cached["metadata"]["cached"] = True
        return cached

    total_start = time.time()

    infra_reseau = InfraReseauBis(infra_group)
    infra_reseau.charger_scenario(scenario)

    result = await asyncio.to_thread(
        infra_reseau.calculer_production,
        db=db,
        is_journalier=is_journalier,
        flow_mode=flow_mode,
        resolution=resolution,
    )

    if not result or not result.get("production"):
        raise HTTPException(status_code=500, detail="Calcul de production échoué")

    if isinstance(result.get("metadata"), dict):
        result["metadata"]["cached"] = False
        result["metadata"]["resolution"] = resolution
        result["metadata"]["execution_time_seconds"] = time.time() - total_start

    _reseau_cache_set(cache_key, result)
    return result

@reseau_router.post("/cout")
async def calculer_cout_reseau(payload: schemas.ReseauSimulationPayload):
    infra_group = payload.infra_group
    infra_reseau = InfraReseauBis(infra_group)
    infra_reseau.charger_scenario(payload.scenario)
    return infra_reseau.calculer_cout(infra_group)

@reseau_router.post("/emission")
async def calculer_emission_reseau(payload: schemas.ReseauSimulationPayload):
    infra_group = payload.infra_group
    infra_reseau = InfraReseauBis(infra_group)
    infra_reseau.charger_scenario(payload.scenario)
    return infra_reseau.calculer_co2(infra_group)

router.include_router(reseau_router)

#/informativegame/question
#-----#-----#-----#-----#-----#-----#  Ludification   #-----#-----#-----#-----#-----#-----#
from .Ludification import selectQuestion

game_router = APIRouter(
    prefix="/jeux-informatifs",
    tags=["Jeux"],
    responses={404: {"description": "Not found"}},
)

@game_router.get("/quiz")
async def fetch_question(
    answeredQuestionList: List[int] = Query(default=[])
):
    quiz, answeredQuestionList = selectQuestion(answeredQuestionList)

    return {       
        "questions": quiz,
    "answeredQuestionList": answeredQuestionList
    }

router.include_router(game_router)

#-----#-----#-----#-----#-----#  Ajout de toutes les routes  #-----#-----#-----#-----#-----#

for _, api_router in api_routers.items():
    router.include_router(api_router)
