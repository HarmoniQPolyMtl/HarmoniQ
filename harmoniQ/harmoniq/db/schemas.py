from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, Table, Enum, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator
from sqlalchemy.sql.schema import ForeignKey
from sqlalchemy import MetaData

import pandera.pandas as pa
from pydantic import BaseModel, TypeAdapter, Field, field_validator, validator
from pydantic import ConfigDict
from typing import List, Optional
from datetime import datetime, timedelta, date
import isodate
from enum import Enum as PyEnum

# schemas.py : Ce fichier contient les modèles de données utilisés pour la base de données.
# Il contient des classes pour chaque table de la base de données, ainsi que des schémas Pydantic pour la validation et la sérialisation des données.

#-----#-----#-----#-----# SQLAlchemy Base #-----#-----#-----#-----#

metadata = MetaData(schema="reseau")
SQLBase = declarative_base(metadata=metadata)

#-----#-----#-----#-----# Latitude Longitude Base #-----#-----#-----#-----#

class PositionBase(BaseModel):
    """Pydantic modèle de base pour les positions"""

    latitude: float
    longitude: float

    def __repr__(self):
        return f"({self.latitude}, {self.longitude})"


class InfrastructureBase(BaseModel): # TODO make the other classes inherit
    nom: str
    latitude: float
    longitude: float
    puissance_nominal: float
    # TODO, make cost and GHG data necissary

"""
Notion de "Enum ou PyEnum" pour les types de données:
- Enum est une classe de base pour créer des énumérations en Python.
- Exemples d'utilisation : Enum("Nom", "Valeur1 Valeur2 Valeur3")
- Type d'objet : Enum
"""


class Weather(PyEnum):
    warm = 1
    typical = 2
    cold = 3


class Consomation(PyEnum):
    PV = 1  # Typique
    UB = 2  # Conservateur


class DateTimeString(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            return value.isoformat()
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return datetime.fromisoformat(value)
        return value


class TimeDeltaString(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            return isodate.duration_isoformat(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return isodate.parse_duration(value)
        return value

#-----#-----#-----#-----# Scenario Base #-----#-----#-----#-----#

class Scenario(SQLBase):
    __tablename__ = "scenario"

    id = Column(Integer, primary_key=True)
    nom = Column(String)
    description = Column(String)
    date_de_debut = Column(DateTimeString)
    date_de_fin = Column(DateTimeString)
    pas_de_temps = Column(TimeDeltaString)
    weather = Column(Enum(Weather))
    consomation = Column(Enum(Consomation))


class ScenarioBase(BaseModel):
    nom: str
    description: Optional[str] = None
    date_de_debut: datetime = Field(
        ..., description="Date de début de la simulation (YYYY-MM-DD)"
    )
    date_de_fin: datetime = Field(
        ..., description="Date de fin de la simulation (YYYY-MM-DD)"
    )
    pas_de_temps: timedelta = Field(
        ..., description="Pas de temps de la simulation (ISO 8601 duration)"
    )
    weather: Weather = Weather.typical
    consomation: Consomation = Consomation.PV

    @field_validator("date_de_debut", "date_de_fin", mode="before")
    def parse_datetime(cls, value):
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise ValueError(f"Invalid datetime format: {value}")
        return value

    @field_validator("pas_de_temps", mode="before")
    def parse_timedelta(cls, value):
        if isinstance(value, str):
            try:
                return isodate.parse_duration(value)
            except ValueError:
                raise ValueError(f"Invalid timedelta format: {value}")
        return value


class ScenarioResponse(ScenarioBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ── Simulation payload models ─────────────────────────────────────────────────
class InfraPayload(BaseModel):
    """
    Minimal representation of a locally-created (user-defined) infrastructure.
    All type-specific fields are accepted via model_config extra='allow'.
    """
    nom: str
    latitude: float
    longitude: float

    model_config = ConfigDict(extra="allow")


class SimulationInfraGroup(BaseModel):
    """
    Request body for POST /reseau/production.

    Each field is a list of full infrastructure objects (either DB-sourced or
    locally created — the backend treats them identically).
    """
    nom: str = ""
    parc_eoliens: Optional[List['EolienneParcBase']] = None
    parc_solaires: Optional[List['SolaireBase']] = None
    central_hydroelectriques: Optional[List['HydroBase']] = None
    central_thermique: Optional[List['ThermiqueBase']] = None
    central_nucleaire: Optional[List['NucleaireBase']] = None

class InfraSimulationPayload(BaseModel):
    scenario: ScenarioResponse
    infra_payload: InfraPayload

class ReseauSimulationPayload(BaseModel):
    scenario: ScenarioResponse
    infra_group: SimulationInfraGroup

#-----#-----#-----#-----# Eolienne Base #-----#-----#-----#-----#

class TurbineModel(str, PyEnum):
    GE_1_5SLE = "GE 1.5SLE"
    E92_2_35 = "E92-2.35"
    E82_2_0 = "E82-2.0"
    E138_4_2 = "E138-4.2"
    E82_2_3 = "E82-2.3"
    E126_4_0 = "E126-4.0"
    MM92 = "MM92"
    NM48_750 = "NM48/750"
    E70_2_3 = "E70-2.3"
    S3_2_MM114 = "3.2-MM114"
    V80_1_8 = "V80-1.8"
    SWT_3_2_113 = "SWT 3.2-113"
    V117_3_45 = "V117-3.45"
    E82_3_0 = "E82-3.0"
    MM82 = "MM82"
    GE_2_2_107 = "GE 2.2-107"
    MM92_CCV = "MM92 CCV"


class EolienneParcBase(BaseModel):
    id: Optional[int] = None
    nom: str = Field(..., description="Nom du parc éolien")
    latitude: float = Field(..., description="Latitude moyenne des éoliennes (degrés)")
    longitude: float = Field(
        ..., description="Longitude moyenne des éoliennes (degrés)"
    )
    nombre_eoliennes: int = Field(..., description="Nombre d'éoliennes dans le parc", json_schema_extra={"suggestion": 12},)
    capacite_total: float = Field(..., description="Capacité totale du parc (MW)", json_schema_extra={"suggestion": 24.6},)
    hauteur_moyenne: float = Field(
        ..., description="Hauteur moyenne des éoliennes du parc (m)", json_schema_extra={"suggestion": 80},)
    modele_turbine: TurbineModel = Field(
        ..., description="Modele de turbine utilise dans le parc", json_schema_extra={"suggestion": TurbineModel.MM92}
    )
    is_offshore: bool = Field(False, description="Indique si le parc est situe en mer (offshore)")

    puissance_nominal: float = Field(
        ..., description="Puissance nominale des turbines dans le parc (kW)", json_schema_extra={"suggestion": 2000}
    )
    weibull_k: Optional[float] = Field(
        None, description="Coefficient de forme Weibull k (optionnel)"
    )
    weibull_c: Optional[float] = Field(
        None, description="Coefficient d'echelle Weibull c en m/s (optionnel)"
    )
    weibull_ref_year: Optional[int] = Field(
        None, description="Annee de reference utilisee pour le fit Weibull"
    )
    weibull_sample_count: Optional[int] = Field(
        None, description="Nombre d'echantillons utilises pour estimer Weibull"
    )
    weibull_updated_at: Optional[str] = Field(
        None, description="Horodatage ISO de la derniere mise a jour des coefficients"
    )
    weibull_ref_year_start: Optional[int] = Field(
        None, description="Annee de debut utilisee pour le fit Weibull multi-annees"
    )
    weibull_ref_year_end: Optional[int] = Field(
        None, description="Annee de fin utilisee pour le fit Weibull multi-annees"
    )
    weibull_granularity: Optional[str] = Field(
        None, description="Granularite du fit Weibull (ex: annual_v1, seasonal_v1)"
    )
    weibull_weighting: Optional[str] = Field(
        None, description="Strategie de ponderation temporelle du fit Weibull"
    )
    weibull_fit_details: Optional[str] = Field(
        None, description="Details JSON du fit Weibull (annual + seasonal)"
    )
    surface_roughness_z0_m: Optional[float] = Field(
        0.03, description="Longueur de rugosite de surface (m) - Onshore: 0.03, Offshore: 0.0001"
    )
    is_user_created: bool = False

    model_config = ConfigDict(from_attributes=True)


class EolienneParcCreate(EolienneParcBase):
    pass


class EolienneParcResponse(EolienneParcBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class EolienneParc(SQLBase):
    __tablename__ = "eoliennes_parc"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    nombre_eoliennes = Column(Integer)
    capacite_total = Column(Float)
    hauteur_moyenne = Column(Float)
    modele_turbine = Column(String)
    puissance_nominal = Column(Float)
    weibull_k = Column(Float, nullable=True)
    weibull_c = Column(Float, nullable=True)
    weibull_ref_year = Column(Integer, nullable=True)
    weibull_sample_count = Column(Integer, nullable=True)
    weibull_updated_at = Column(String, nullable=True)
    weibull_ref_year_start = Column(Integer, nullable=True)
    weibull_ref_year_end = Column(Integer, nullable=True)
    weibull_granularity = Column(String, nullable=True)
    weibull_weighting = Column(String, nullable=True)
    weibull_fit_details = Column(String, nullable=True)
    is_offshore = Column(Boolean, default=False)



class QuebecOffshoreMeshMetaBase(BaseModel):
    grid_version: str
    resolution_m: int
    crs: str
    origin_x: float
    origin_y: float
    source: str
    generated_at: str


class QuebecOffshoreMeshMetaCreate(QuebecOffshoreMeshMetaBase):
    pass


class QuebecOffshoreMeshMetaResponse(QuebecOffshoreMeshMetaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class QuebecOffshoreMeshMeta(SQLBase):
    __tablename__ = "quebec_offshore_mesh_meta"

    id = Column(Integer, primary_key=True, index=True)
    grid_version = Column(String, unique=True, nullable=False, index=True)
    resolution_m = Column(Integer, nullable=False)
    crs = Column(String, nullable=False)
    origin_x = Column(Float, nullable=False)
    origin_y = Column(Float, nullable=False)
    source = Column(String, nullable=False)
    generated_at = Column(String, nullable=False)


class QuebecOffshoreMeshPointBase(BaseModel):
    grid_version: str
    ix: int
    iy: int
    latitude: float
    longitude: float
    resolution_m: int


class QuebecOffshoreMeshPointCreate(QuebecOffshoreMeshPointBase):
    pass


class QuebecOffshoreMeshPointResponse(QuebecOffshoreMeshPointBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class QuebecOffshoreMeshPoint(SQLBase):
    __tablename__ = "quebec_offshore_mesh_points"
    __table_args__ = (
        UniqueConstraint("grid_version", "ix", "iy", name="uq_qc_offshore_grid_ix_iy"),
    )

    id = Column(Integer, primary_key=True, index=True)
    grid_version = Column(String, nullable=False, index=True)
    ix = Column(Integer, nullable=False, index=True)
    iy = Column(Integer, nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    resolution_m = Column(Integer, nullable=False)

#-----#-----#-----#-----# Solaire Base #-----#-----#-----#-----#

class Solaire(SQLBase):
    __tablename__ = "solaire"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    angle_panneau = Column(Integer)
    orientation_panneau = Column(Integer)
    nombre_panneau = Column(Integer)
    puissance_nominal = Column(Float)
    annee_commission = Column(Integer, nullable=True)
    panneau_type = Column(String, nullable=True)
    materiau_panneau = Column(String, nullable=True)


class SolaireBase(BaseModel):
    id: Optional[int] = None
    nom: str = Field(..., description="Nom du parc solaire")
    latitude: float = Field(..., description="Latitude du parc solaire (degrés)")
    longitude: float = Field(..., description="Longitude du parc solaire (degrés)")
    angle_panneau: int = Field(
        ...,
        description="Angle d'inclinaison des panneaux comrpis entre 0° et 90° - 0° est un panneau parfaitement plat - Choisir un angle égal à la latitude est une bonne approximation", json_schema_extra={"suggestion": 45},
    )
    orientation_panneau: int = Field(
        ..., description="Orientation des panneaux (degrés) - 180° est plein sud", json_schema_extra={"suggestion": 180},
    )
    puissance_nominal: float = Field(
        ..., description="Puissance nominale du parc solaire (MW) - Maximum de 25 MW pour un parc", json_schema_extra={"suggestion": 20}
    )
    nombre_panneau: int = Field(
        ..., description="Nombre de panneaux solaires dans le parc", json_schema_extra={"suggestion": 60000}
    )
    annee_commission: Optional[int] = None
    panneau_type: Optional[str] = None
    materiau_panneau: Optional[str] = None
    is_user_created: bool = False

    model_config = ConfigDict(from_attributes=True)


#-----#-----#-----#-----# Hydro Base #-----#-----#-----#-----#

class HydroBase(BaseModel):
    id: Optional[int] = None
    nom: str
    longitude: float
    latitude: float
    type_barrage: str
    puissance_nominal: float
    hauteur_chute: float
    nb_turbines: int
    debits_nominal: float
    modele_turbine: str
    volume_reservoir: int
    nb_turbines_maintenance: int
    id_HQ: int
    annee_commission: Optional[int] = None
    materiau_conduite: Optional[str] = None
    maintenance: Optional[str] = None
    regulation: Optional[str] = None
    is_user_created: bool = False

    model_config = ConfigDict(from_attributes=True)


class Hydro(SQLBase):
    __tablename__ = "hydro"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String)
    longitude = Column(Float)
    latitude = Column(Float)
    type_barrage = Column(String)
    puissance_nominal = Column(Float)
    hauteur_chute = Column(Float)
    nb_turbines = Column(Integer)
    debits_nominal = Column(Float)
    modele_turbine = Column(String)
    volume_reservoir = Column(BigInteger)
    nb_turbines_maintenance = Column(Integer)
    id_HQ = Column(Integer)
    annee_commission = Column(Integer, nullable=True)
    materiau_conduite = Column(String, nullable=True)
    maintenance = Column(String, nullable=True)
    regulation = Column(String, nullable=True)


#-----#-----#-----#-----# Thermique Base #-----#-----#-----#-----#

class TypeIntrantThermique(str, PyEnum):
    GAZ_NATUREL = "Gaz naturel"
    CHARBON = "Charbon"
    DIESEL = "Diesel"
    BIOMASSE = "Biomasse"


class ThermiqueBase(BaseModel):
    id: Optional[int] = None
    nom: str = Field(..., description="Nom de la centrale thermique")
    latitude: float = Field(
        ..., description="Latitude de la centrale thermique (degrés)"
    )
    longitude: float = Field(
        ..., description="Longitude de la centrale thermique (degrés)"
    )
    type_intrant: TypeIntrantThermique = Field(
        ..., description="Type d'intrant de la centrale thermique", json_schema_extra={"suggestion": TypeIntrantThermique.BIOMASSE}
    )
    puissance_nominal: float = Field(
        ..., description="Puissance nominal de la centrale en MW", json_schema_extra={"suggestion": 400} 
    )
    semaine_maintenance: int = Field(
        ...,
        description="Semaine de maintenance où la centrale thermique est à l'arrêt - Choisir une semaine entre 10 et 22 pour le printemps puisqu'il s'agit d'une période de faible consommation",
        json_schema_extra={"suggestion": 15}
    )
    annee_commission: Optional[int] = None
    type_generateur: Optional[str] = None
    is_user_created: bool = False

    model_config = ConfigDict(from_attributes=True)


class Thermique(SQLBase):
    __tablename__ = "thermique"

    id = Column(Integer, primary_key=True, index=True)

    nom = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    puissance_nominal = Column(Float)
    type_intrant = Column(String)
    semaine_maintenance = Column(Integer)
    annee_commission = Column(Integer, nullable=True)
    type_generateur = Column(Integer, nullable=True)

#-----#-----#-----#-----# Nucleaire Base #-----#-----#-----#-----#

class NucleaireBase(BaseModel):
    id: Optional[int] = None
    nom: str = Field(..., description="Nom de la centrale nucléaire")
    latitude: float = Field(
        ..., description="Latitude de la centrale nucléaire (degrés)"
    )
    longitude: float = Field(
        ..., description="Longitude de la centrale nucléaire (degrés)"
    )
    puissance_nominal: float = Field(
        ..., description="Puissance nominale de la centrale nucléaire (MW) - Chosir un multiple de 300 (1 réacteur SMR = 300 MW)", json_schema_extra={"suggestion": 1200},
    )
    semaine_maintenance: int = Field(
        ..., description="Semaine de maintenance où la centrale nucléaire est à l'arrêt - Choisir une semaine entre 10 et 22 pour le printemps puisqu'il s'agit d'une période de faible consommation", json_schema_extra={"suggestion": 20},
    )
    annee_commission: Optional[int] = None
    type_generateur: Optional[str] = None
    type_intrant: Optional[int] = None
    is_user_created: bool = False

    model_config = ConfigDict(from_attributes=True)


class Nucleaire(SQLBase):
    __tablename__ = "nucleaire"

    id = Column(Integer, primary_key=True, index=True)

    nom = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    puissance_nominal = Column(Float)
    semaine_maintenance = Column(Integer)
    annee_commission = Column(Integer, nullable=True)
    type_generateur = Column(Integer, nullable=True)

#-----#-----#-----#-----# Bus Base #-----#-----#-----#-----#

class BusControlType(str, PyEnum):
    """Enumération des types de contrôle de bus"""

    PV = "PV"
    PQ = "PQ"
    slack = "slack"


class BusType(str, PyEnum):
    """Enumération des types de bus"""

    prod = "prod"
    conso = "conso"
    line = "ligne"


class Bus(SQLBase):
    __tablename__ = "bus"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=True)
    v_nom = Column(Integer)
    type = Column(Enum(BusType))
    x = Column(Float)
    y = Column(Float)
    control = Column(Enum(BusControlType))
    reseau_type = Column(String, nullable=True)

    lines_from = relationship(
        "Line", back_populates="bus_from", foreign_keys="Line.bus0"
    )
    lines_to = relationship("Line", back_populates="bus_to", foreign_keys="Line.bus1")


class BusBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    v_nom: int
    type: BusType
    x: float
    y: float
    control: BusControlType
    reseau_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BusCreate(BusBase):
    pass


class BusResponse(BusBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

#-----#-----#-----#-----# Line Base #-----#-----#-----#-----#

class LineType(SQLBase):
    __tablename__ = "line_type"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    f_nom = Column(Integer)
    r_per_length = Column(Float)
    x_per_length = Column(Float)

    lines = relationship("Line", back_populates="line_type")


class LineTypeBase(BaseModel):
    name: str
    f_nom: int
    r_per_length: float
    x_per_length: float

    model_config = ConfigDict(from_attributes=True)


class LineTypeCreate(LineTypeBase):
    pass


class LineTypeResponse(LineTypeBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class Line(SQLBase):
    __tablename__ = "line"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    bus0 = Column(String, ForeignKey("bus.name"))
    bus1 = Column(String, ForeignKey("bus.name"))
    type = Column(String, ForeignKey("line_type.name"))
    capital_cost = Column(Float)
    length = Column(Float)
    s_nom = Column(Float)
    nb_ligne = Column(Integer, nullable=True)
    reseau_type = Column(String, nullable=True)

    bus_from = relationship("Bus", back_populates="lines_from", foreign_keys=[bus0])
    bus_to = relationship("Bus", back_populates="lines_to", foreign_keys=[bus1])
    line_type = relationship("LineType", back_populates="lines")


class LineBase(BaseModel):
    name: str
    bus0: str
    bus1: str
    type: str
    capital_cost: float
    length: float
    s_nom: float
    nb_ligne: Optional[int] = None
    reseau_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LineCreate(LineBase):
    pass


class LineResponse(LineBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


weather_schema = pa.DataFrameSchema(
    columns={
        "longitude": pa.Column(
            pa.Float, checks=pa.Check.greater_than(-180), nullable=False
        ),
        "latitude": pa.Column(
            pa.Float, checks=pa.Check.greater_than(-90), nullable=False
        ),
        "temperature_C": pa.Column(pa.Float, nullable=False),
        "min_tempature_C": pa.Column(
            pa.Float, nullable=True
        ),  # Pour les données journalières
        "max_temperature_C": pa.Column(
            pa.Float, nullable=True
        ),  # Pour les données journalières
        "pluie_mm": pa.Column(pa.Float, nullable=True),
        "neige_cm": pa.Column(pa.Float, nullable=True),
        "precipitation_mm": pa.Column(pa.Float, nullable=False),
        "neige_accumulee_cm": pa.Column(pa.Float, nullable=True),
        "direction_vent": pa.Column(pa.Float, nullable=False),
        "vitesse_vent_kmh": pa.Column(pa.Float, nullable=False),
        "humidite": pa.Column(pa.Float, nullable=True),
        "pression": pa.Column(pa.Float, nullable=True),
        "point_de_rosee": pa.Column(pa.Float, nullable=True),
    },
    index=pa.Index(pa.DateTime, name="datetemps"),
    strict=True,
)

InfraPayload.model_rebuild()
SimulationInfraGroup.model_rebuild()
