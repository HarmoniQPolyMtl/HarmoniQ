import pvlib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import time
import json
import urllib.request
from functools import lru_cache
from typing import List

# # OBSOLETE - à garder pour référence, mais ne pas utiliser pour les calculs de production solaire (trop simpliste, ne tient pas compte de la météo, de l'albédo, du modèle bifacial, etc.). La nouvelle version utilise pvlib ModelChain pour une simulation plus réaliste.
# def get_weather_data(coordinates, year=2021):
#     tmys = []
#     for location in coordinates:
#         latitude, longitude, name, altitude, timezone, power_kw = location
#         print(f"\nRécupération des données météo horaires pour {name} en {year}...")
#         try:
#             weather, _, _ = pvlib.iotools.get_pvgis_hourly(
#                 latitude, longitude, start=year, end=year
#             )
#             weather.index.name = "utc_time"
#             tmys.append((weather, location))
#         except Exception as e:
#             print(f"Erreur pour {name}: {e}")
#             tmys.append((None, location))
#     return tmys

# #OBSOLETE - à garder pour référence, mais ne pas utiliser pour les calculs de production solaire. La nouvelle version utilise pvlib ModelChain pour une simulation plus réaliste.
# def calculate_solar_parameters(
#     weather,
#     latitude,
#     longitude,
#     altitude,
#     temperature_model_parameters,
#     module,
#     inverter,
#     surface_tilt,
#     surface_orientation,
# ):
#     solpos = pvlib.solarposition.get_solarposition(
#         time=weather.index,
#         latitude=latitude,
#         longitude=longitude,
#         altitude=altitude,
#         temperature=weather["temp_air"],
#         pressure=pvlib.atmosphere.alt2pres(altitude),
#     )
#     dni_extra = pvlib.irradiance.get_extra_radiation(weather.index)
#     airmass = pvlib.atmosphere.get_relative_airmass(solpos["apparent_zenith"])
#     pressure = pvlib.atmosphere.alt2pres(altitude)
#     am_abs = pvlib.atmosphere.get_absolute_airmass(airmass, pressure)
#     aoi = pvlib.irradiance.aoi(
#         surface_tilt,
#         surface_orientation,
#         solpos["apparent_zenith"],
#         solpos["azimuth"],
#     )
#     total_irradiance = pvlib.irradiance.get_total_irradiance(
#         surface_tilt,
#         surface_orientation,
#         solpos["apparent_zenith"],
#         solpos["azimuth"],
#         weather["dni"],
#         weather["ghi"],
#         weather["dhi"],
#         dni_extra=dni_extra,
#         model="haydavies",
#     )
#     cell_temperature = pvlib.temperature.sapm_cell(
#         total_irradiance["poa_global"],
#         weather["temp_air"],
#         weather["wind_speed"],
#         **temperature_model_parameters,
#     )
#     effective_irradiance = pvlib.pvsystem.sapm_effective_irradiance(
#         total_irradiance["poa_direct"],
#         total_irradiance["poa_diffuse"],
#         am_abs,
#         aoi,
#         module,
#     )
#     dc = pvlib.pvsystem.sapm(effective_irradiance, cell_temperature, module)
#     ac = pvlib.inverter.sandia(dc["v_mp"], dc["p_mp"], inverter)
#     return ac

# # Obsolete Conversion entre surface de panneaux et puissance produite - non utilisé pour la version en ModelChain, mais peut être utile pour des calculs rapides ou des estimations approximatives.
# def convert_solar(value, module, mode="surface_to_power"):
#     panel_efficiency = module["Impo"] * module["Vmpo"] / (1000 * module["Area"])

#     if mode == "surface_to_power":
#         power_w = value * panel_efficiency * 1000
#         power_kw = power_w / 1000
#         return power_kw
#     elif mode == "power_to_surface":
#         surface_m2 = value * 1000 / (panel_efficiency * 1000)
#         return surface_m2
#     else:
#         raise ValueError(
#             "Mode invalide. Utilisez 'surface_to_power' ou 'power_to_surface'."
#         )

# TEST DATA - Données de référence pour une centrale solaire fictive , à garder pour référence mais ne pas utiliser pour les calculs de production solaire. La nouvelle version utilise pvlib ModelChain pour une simulation plus réaliste.
nom = "varennes"
latitude = 45.6833
longitude = -73.4333
angle_panneau = 45
orientation_panneau = 180
puissance_nominal = 9.5 # mauvaise valeur
nombre_panneau = 10000 # mauvaise valeur
date_start = pd.Timestamp("2035-01-01")
date_end = pd.Timestamp("2037-06-01")

# Scénarios résidentiels : nombre de panneaux par client
PANELS_PAR_SCENARIO = {"pessimiste": 2, "neutre": 4, "optimiste": 6}
# Surface d'un panneau résidentiel standard [m²]
SURFACE_PAR_PANNEAU_M2 = 1.7

@lru_cache(maxsize=64)
def get_albedo_nasa_power(latitude: float, longitude: float) -> pd.Series:
    """
    Récupère l'albédo de surface mensuel climatologique (ALLSKY_SRF_ALB)
    depuis l'API NASA POWER (MERRA-2, résolution ~0.5°).

    Retour :
        Series de 12 valeurs indexées 1–12 (janvier–décembre), sans unité [0–1].
    """
    url = (
        "https://power.larc.nasa.gov/api/temporal/climatology/point"
        f"?parameters=ALLSKY_SRF_ALB&community=RE"
        f"&longitude={longitude}&latitude={latitude}&format=JSON"
    )
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
    monthly = data["properties"]["parameter"]["ALLSKY_SRF_ALB"]
    # L'API retourne des clés "JAN"…"DEC" + "ANN"
    _MONTH_KEYS = ["JAN","FEB","MAR","APR","MAY","JUN",
                   "JUL","AUG","SEP","OCT","NOV","DEC"]
    return pd.Series(
        {i + 1: monthly[k] for i, k in enumerate(_MONTH_KEYS)}
    )


def calculate_energy_solar_plants(
    nom: str,
    latitude: float,
    longitude: float,
    angle_panneau: float,
    orientation_panneau: float,
    nombre_panneau: int,
    date_start: pd.Timestamp,
    date_end: pd.Timestamp,
    module_ref: str = "Canadian_Solar_CS6X_300M__2013_",
    inverter_ref: str = "ABB__MICRO_0_3_I_OUTD_US_240__240V_",
    albedo_saisonnier: bool = True,
    albedo_nasa: bool = False,
    bifacial: bool = True,
    bifaciality_factor: float = 0.70,
    gcr: float = 0.40,
    hauteur_montage: float = 1.0,
    espacement_rangees: float = 5.0,
) -> pd.DataFrame:
    """
    Calcule un profil horaire d'énergie produite par une centrale solaire via pvlib ModelChain.

    Arguments obligatoires :
        - nom : nom de la centrale
        - latitude, longitude : position géographique
        - angle_panneau : inclinaison des panneaux [degrés]
        - orientation_panneau : azimut des panneaux [degrés, 180=sud]
        - nombre_panneau : nombre total de panneaux
        - date_start, date_end : période horaire demandée

    Arguments optionnels :
        - module_ref         : clé Sandia du module PV (base Sandia National Labs,
                               pvlib.pvsystem.retrieve_sam("SandiaMod"))
                               Défaut : "Canadian_Solar_CS6X_300M__2013_"  (~284W, Vmpo=35V)
                               Alternatives :
                                 "Canadian_Solar_CS5P_220M___2009_"         (~221W, Vmpo=36.3V)
                                 "SunPower_SPR_315E_WHT__2007__E__"         (~315W, Vmpo=54.7V)
                                 "SunPower_SPR_305_WHT__2007__E__"          (~305W, Vmpo=54.7V)

        - inverter_ref       : clé CEC de l'onduleur (base California Energy Commission,
                               pvlib.pvsystem.retrieve_sam("cecinverter"))
                               1 micro-onduleur modélisé par panneau — scaling = nombre_panneau
                               Défaut : "ABB__MICRO_0_3_I_OUTD_US_240__240V_"   (Paco=300W, Vdco=40V)
                               Alternatives :
                                 "ABB__MICRO_0_25_I_OUTD_US_240__240V_"    (Paco=250W, Vdco=40V)
                                 "ABB__MICRO_0_25_I_OUTD_US_208__208V_"    (Paco=250W, Vdco=40V)

        - albedo_nasa        : albédo mensuel climatologique via API NASA POWER
                               (paramètre ALLSKY_SRF_ALB, réanalyse MERRA-2, résolution ~0.5°,
                               moyenne sur toutes les années disponibles ~1981-2022)
                               Spécifique aux coordonnées du site. Prioritaire sur albedo_saisonnier.
                               Résultats mis en cache par site (lru_cache) — 1 seul appel réseau/site/session.
                               Défaut : False (pour éviter les appels réseau dans les tests), sinon True pour une meilleure précision.
                               Vérif La Prairie (45.42 N, 73.50 O) :
                                 Jan=0.36  Fév=0.42  Mar=0.34  Avr=0.16  Mai=0.13  Jun=0.15
                                 Jul=0.15  Aoû=0.15  Sep=0.15  Oct=0.14  Nov=0.14  Déc=0.27

        - albedo_saisonnier  : Par .
                               Valeurs calibrées sur NASA POWER MERRA-2, Québec sud (2025) :
                                 Jan=0.36  Fév=0.42  Mar=0.34  Avr=0.16  Mai=0.13  Jun=0.15
                                 Jul=0.15  Aoû=0.15  Sep=0.15  Oct=0.14  Nov=0.14  Déc=0.27
                               Si False : albédo fixe = 0.25 (défaut pvlib générique)

        - bifacial           : active le modèle bifacial pvlib infinite_sheds
                               Réf : Marion et al. (2017), "A Practical Irradiance Model for
                               Bifacial PV Modules", IEEE PVSC 44. Défaut : True

        - bifaciality_factor : ratio puissance face arrière / face avant [0-1]
                               Défaut : 0.70 (typique modules monocristallins PERC, source : fiches
                               Canadian Solar CS6X = 0.70, SunPower SPR-315 = 0.75)

        - gcr                : Ground Coverage Ratio = largeur_panneau / espacement_rangées [0-1]
                               Affecte l'ombrage inter-rangées et la réflexion sol (bifacial).
                               Défaut : 0.40 (valeur typique centrale au sol Québec)

        - hauteur_montage    : hauteur du centre de la rangée au-dessus du sol [m]
                               Paramètre du modèle bifacial infinite_sheds. Défaut : 1.0 m

        - espacement_rangees : distance (pitch) entre rangées [m]
                               Paramètre du modèle bifacial infinite_sheds. Défaut : 5.0 m

    Retour :
        - DataFrame avec colonnes : date, nom, Latitude, Longitude, production [kW]
    """
    # --- Modèles de référence (Sandia) ---
    sandia_modules = pvlib.pvsystem.retrieve_sam("SandiaMod")
    sapm_inverters = pvlib.pvsystem.retrieve_sam("cecinverter")
    module = sandia_modules[module_ref]
    inverter = sapm_inverters[inverter_ref]
    temp_params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]

    # --- Location et système PV ---
    location = pvlib.location.Location(
        latitude=latitude,
        longitude=longitude,
        tz="Etc/GMT+5",
        altitude=0,
    )
    system = pvlib.pvsystem.PVSystem(
        surface_tilt=angle_panneau,
        surface_azimuth=orientation_panneau,
        module_parameters=module,
        inverter_parameters=inverter,
        temperature_model_parameters=temp_params,
    )
    mc = pvlib.modelchain.ModelChain(
        system, 
        location,
        ) # Il est possible de fixer le modèle Haydavies au besoin.

    # --- Données météo TMY depuis PVGIS (année typique, 8760h) ---
    # TODO : une fois que les serveur d'hydro white list cet api (https://re.jrc.ec.europa.eu/api/), utiliser ceci à la place
    weather, _ = pvlib.iotools.get_pvgis_tmy(
        latitude, longitude, map_variables=True
    )

    # ---- Fallback method en attendant que l'api soit whitelisted ----
    #  lorsque les requêtes vers l'API PVGIS sur le serveur de prod sont bloquées
    # times = pd.date_range(start='2025-01-01', periods=8760, freq='h', tz='UTC')
    # hours = times.hour
    # is_day = (hours >= 11) & (hours <= 23)
    
    # weather = pd.DataFrame({
    #     'ghi': np.where(is_day, 500.0, 0.0),
    #     'dni': np.where(is_day, 400.0, 0.0),
    #     'dhi': np.where(is_day, 100.0, 0.0),
    #     'temp_air': np.where(is_day, 20.0, 10.0),
    #     'wind_speed': [3.0] * 8760,
    # }, index=times)
    
    # --- Albédo ---
    weather = weather.copy()
    mois = weather.index.month
    if albedo_nasa:
        nasa_monthly = get_albedo_nasa_power(latitude, longitude)
        weather["albedo"] = mois.map(nasa_monthly)
    elif albedo_saisonnier:
        # Valeurs mensuelles calibrées sur NASA POWER MERRA-2 (moyenne Québec sud)
        # utilisé par défaut pour ne pas rajouter un API.
        _ALBEDO_MENSUEL_QC = {
            1: 0.36,   # Jan — neige tassée
            2: 0.42,   # Fév — couverture neigeuse maximale
            3: 0.34,   # Mar — fonte active, neige sale
            4: 0.16,   # Avr — sol nu, humide
            5: 0.13,   # Mai — végétation jeune
            6: 0.15,   # Jun — herbe/asphalte
            7: 0.15,   # Jul
            8: 0.15,   # Aoû
            9: 0.15,   # Sep
            10: 0.14,  # Oct — feuilles tombées
            11: 0.14,  # Nov — sol nu, pas encore de neige
            12: 0.27,  # Déc — début enneigement
        }
        weather["albedo"] = mois.map(_ALBEDO_MENSUEL_QC)
    else:
        weather["albedo"] = 0.25                        # défaut pvlib

    # --- Simulation sur l'année typique ---
    mc.run_model(weather)
    ac_tmy_w = np.nan_to_num(mc.results.ac.values, nan=0.0)
    ac_tmy_w = np.maximum(ac_tmy_w, 0)  # W pour 1 module, 8760 h

    # --- Modèle bifacial (infinite_sheds) ---
    if bifacial:
        from pvlib.bifacial.infinite_sheds import get_irradiance as _bifacial_irrad
        solpos = location.get_solarposition(weather.index)
        rear = _bifacial_irrad(
            surface_tilt=angle_panneau,
            surface_azimuth=orientation_panneau,
            solar_zenith=solpos["apparent_zenith"],
            solar_azimuth=solpos["azimuth"],
            gcr=gcr,
            height=hauteur_montage,
            pitch=espacement_rangees,
            ghi=weather["ghi"],
            dhi=weather["dhi"],
            dni=weather["dni"],
            albedo=weather["albedo"],
            bifaciality=bifaciality_factor,
        )
        # Irradiance effective totale = face avant + face arrière × bifaciality
        total_eff = mc.results.effective_irradiance + rear["poa_back"] * bifaciality_factor
        dc_bi = pvlib.pvsystem.sapm(total_eff, mc.results.cell_temperature, module)
        ac_bi = pvlib.inverter.sandia(dc_bi["v_mp"], dc_bi["p_mp"], inverter)
        ac_tmy_w = np.nan_to_num(ac_bi.values, nan=0.0)
        ac_tmy_w = np.maximum(ac_tmy_w, 0)

    # PVGIS retourne des données en UTC; l'heure locale Québec est UTC-5.
    # On roll de -5 pour que le profil soit aligné sur l'heure locale.
    ac_tmy_w = np.roll(ac_tmy_w, -5)

    # --- Mise à l'échelle vers la puissance totale de la centrale ---
    # 1 simulation ModelChain = 1 module → scaling = nombre de panneaux
    scaling_factor = nombre_panneau

    # --- Répétition du profil TMY sur la période voulue ---
    datetime_index = pd.date_range(start=date_start, end=date_end, freq="h")
    n_repeats = int(np.ceil(len(datetime_index) / len(ac_tmy_w)))
    ac_tiled = np.tile(ac_tmy_w, n_repeats)[: len(datetime_index)]
    production_kw = ac_tiled * scaling_factor / 1_000  # W → kW

    return pd.DataFrame(
        {
            "date": datetime_index,
            "nom": nom,
            "Latitude": latitude,
            "Longitude": longitude,
            "production": production_kw,
        }
    )

# # Version précédente (sans ModelChain, moins précise) --- IGNORE ---
# def calculate_energy_solar_plants_old( 
#     nom : str,
#     latitude: float,
#     longitude: float,
#     angle_panneau: float,
#     orientation_panneau: float,
#     puissance_nominal: float,
#     nombre_panneau: int,
#     date_start: pd.Timestamp,
#     date_end: pd.Timestamp,
# ) -> pd.DataFrame:
#     """
#     Calcule la production énergétique des centrales solaires.
#     Returns
#     -------
#     pd.DataFrame
#         DataFrame contenant la production énergétique horaire.
#     """

#     # Initialisation des modèles
#     sandia_modules = pvlib.pvsystem.retrieve_sam("SandiaMod")
#     sapm_inverters = pvlib.pvsystem.retrieve_sam("cecinverter")

#     module = sandia_modules["Canadian_Solar_CS5P_220M___2009_"]
#     inverter = sapm_inverters["ABB__MICRO_0_25_I_OUTD_US_208__208V_"]
#     temperature_model_parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS[
#         "sapm"
#     ]["open_rack_glass_glass"]

#     # Récupération des données météo
#     weather = pvlib.iotools.get_pvgis_tmy(latitude, longitude)[0]
#     weather.index.name = "utc_time"

#     # Calcul du nombre de modules nécessaires
#     puissance_module_w = module["Impo"] * module["Vmpo"]
#     print(puissance_module_w)
#     nombre_modules = int(np.ceil((puissance_nominal * 1e6) / puissance_module_w))
#     altitude = 0  # Valeur par défaut pour l'altitude

#     # Calcul de la production
#     print(f"Calcul de la production pour {nom}")
#     ac = calculate_solar_parameters(
#         weather,
#         latitude,
#         longitude,
#         altitude,
#         temperature_model_parameters,
#         module,
#         inverter,
#         angle_panneau,
#         orientation_panneau,
#         )
#     # Mise à l'échelle selon la puissance de la centrale
#     ac_scaled = ac * nombre_modules

#     # Fixer les valeurs négatives à zéro
#     ac_scaled = np.maximum(ac_scaled, 0)

#     # Création de la plage de dates pour remplacer les datetime
#     datetime_index = pd.date_range(start=date_start, end=date_end, freq="h")

#     # Gestion des cas où la longueur de datetime_index dépasse celle de ac
#     if len(ac) < len(datetime_index):

#         # Dupliquer les données de ac pour remplir les heures supplémentaires
#         ac_extended = np.tile(ac, int(np.ceil(len(datetime_index) / len(ac))))[:len(datetime_index)]

#         # Clip les valeurs pour les heures supplémentaires
#         for i in range(len(ac), len(datetime_index)):
#             year_offset = (datetime_index[i].year - datetime_index[0].year)
#             ac_extended[i] = np.clip(ac_extended[i % len(ac)], 0, ac_extended[i % len(ac)] * year_offset)

#         # Fixer les valeurs négatives à zéro
#         ac_extended = np.maximum(ac_extended, 0)
#     else:
#         # Si datetime_index est inférieur ou égal à ac, tronquer ac
#         ac_extended = ac[:len(datetime_index)]
#         ac_extended = np.maximum(ac_extended, 0)


#     # Création du DataFrame avec la production horaire
#     resultats_centrales_df = pd.DataFrame(
#         {
#             "datetime": datetime_index,  # Utiliser la plage horaire générée
#             "production_horaire_wh": ac_extended,
#         }
#     )
#     resultats_centrales_df.set_index("datetime", inplace=True)
#     return resultats_centrales_df


def distribute_base_to_mrc(
    ra_base_df: pd.DataFrame,
    mrc_to_ra_mapping: dict,
) -> pd.DataFrame:
    """
    Distribue le profil W/m² calculé par RA vers chaque MRC de la RA.

    Chaque MRC hérite directement du profil W/m² de sa RA parente —
    pas de pondération, W/m² est déjà normalisé (indépendant de la surface).

    Arguments:
        ra_base_df        : DataFrame (datetime, mrc=nom_ra, production_w_per_m2)
                            issu de calculate_base_production_per_m2() avec coordinates_residential
        mrc_to_ra_mapping : dict {nom_mrc: nom_ra} (ex: data_solaire.mrc_to_ra)

    Retour:
        DataFrame (datetime, mrc, production_w_per_m2) au niveau MRC
    """
    regions_in_df = set(ra_base_df["mrc"].unique())
    frames = []
    for nom_mrc, nom_ra in mrc_to_ra_mapping.items():
        if nom_ra not in regions_in_df:
            continue
        ra_slice = ra_base_df[ra_base_df["mrc"] == nom_ra].copy()
        ra_slice["mrc"] = nom_mrc
        frames.append(ra_slice)
    return pd.concat(frames, ignore_index=True)


def calculate_base_production_per_m2(
    coordinates: list,
    surface_tilt: float = 30.0,
    surface_orientation: float = 180.0,
    albedo_saisonnier: bool = True,
    bifacial: bool = False,
    bifaciality_factor: float = 0.70,
    gcr: float = 0.40, # utilisé si Bifacial=True 
    hauteur_montage: float = 1.0, #utilisé si Bifacial=True
    espacement_rangees: float = 5.0, #utilisé si Bifacial=True, espacement entre les rangées de panneaux (m), utilisé pour le modèle bifacial
    reference_year: int = 2021,
) -> pd.DataFrame:
    """
    Calcule le profil horaire TMY de production en W/m² pour chaque MRC/région.

    Conceptuellement, chaque MRC est traitée comme une "centrale virtuelle" d'un
    seul module de référence placé au centre de la MRC. Le résultat est normalisé
    en W/m² en réutilisant calculate_energy_solar_plants() avec nombre_panneau=1,
    ce qui évite de dupliquer la logique pvlib.

    Arguments:
        coordinates         : liste de tuples (lat, lon, nom, altitude, timezone)
        surface_tilt        : inclinaison des panneaux [degrés]
        surface_orientation : azimut [degrés, 180=sud]
        albedo_saisonnier   : True = neige hiver (0.60) / herbe été (0.20)
        bifacial            : True = modèle bifacial (infinite_sheds) -> non utilisé pour l'instant mais disponible.
        reference_year      : année TMY de référence pour le DatetimeIndex

    Retour:
        DataFrame (datetime, mrc, production_w_per_m2) — 8760 lignes par MRC
    """
    sandia_modules = pvlib.pvsystem.retrieve_sam("SandiaMod")
    module = sandia_modules["Canadian_Solar_CS5P_220M___2009_"]
    module_area_m2 = module["Area"]                               # ~1.244 m²

    date_start = pd.Timestamp(f"{reference_year}-01-01")
    date_end   = pd.Timestamp(f"{reference_year}-12-31 23:00:00")

    frames = []
    for coord in coordinates:
        latitude, longitude, nom = coord[0], coord[1], coord[2]
        print(f"  Base W/m² → {nom}...")

        # Centrale virtuelle d'un seul module → scaling_factor = 1
        df = calculate_energy_solar_plants(
            nom=nom,
            latitude=latitude,
            longitude=longitude,
            angle_panneau=surface_tilt,
            orientation_panneau=surface_orientation,
            nombre_panneau=1,
            date_start=date_start,
            date_end=date_end,
            albedo_saisonnier=albedo_saisonnier,
            bifacial=bifacial,
            bifaciality_factor=bifaciality_factor,
            gcr=gcr,
            hauteur_montage=hauteur_montage,
            espacement_rangees=espacement_rangees,
        )

        # kW → W puis normaliser par la surface du module → W/m²
        frames.append(pd.DataFrame({
            "datetime": df["date"],
            "mrc": nom,
            "production_w_per_m2": df["production"] * 1000 / module_area_m2,
        }))

    return pd.concat(frames, ignore_index=True)


# ===========================================================================
#  PARTIE 2 — Application du scénario sur la base W/m²  (à implémenter côté réseau)
# ---------------------------------------------------------------------------
#  La base W/m² est multipliée par :
#    - m2_par_client   : surface de panneaux par client (scénario)
#    - nb_clients(mrc) : total_clients × population(mrc) / population_totale
#    - f_densite(mrc)  : facteur limitant calculé dynamiquement depuis une BD
#                        (population et superficie_km2 par MRC)
# ===========================================================================

def compute_facteur_densite(
    population: int,
    superficie_km2: float,
    m2_par_client: float,
    surface_hab_par_hab: float = 40.0,  # surface habitable par habitant [m²/hab]
    taille_menage: float = 2.3,         # taille moyenne du ménage [hab/ménage] (Stat. Can. Québec)
    eta_toit: float = 0.40,             # fraction de toit utilisable (HVAC, ombrage, orientation, neige)
) -> float:
    """
    Calcule le facteur de limitation toiture basé sur la densité de population.

    Logique :
        densite            = population / superficie_km2              [hab/km²]
        nb_etages          = paliers selon densite (5 niveaux)
        s_toit_util_hab    = (surface_hab_par_hab / nb_etages) × eta_toit   [m²/hab]
        s_toit_util_client = s_toit_util_hab × taille_menage                [m²/ménage]
        f_densite          = min(s_toit_util_client, m2_par_client) / m2_par_client

    Vaut 1.0 dans les zones rurales (le toit n'est pas limitant).
    Vaut < 1.0 dans les zones très denses (ex : Montréal centre, scénario optimiste).

    Note : taille_menage corrige l'unité hab→ménage pour aligner s_toit_util
           (calculé par habitant) avec m2_par_client (par client/ménage).

    Arguments:
        population          : population de la MRC
        superficie_km2      : superficie de la MRC [km²]
        m2_par_client       : surface totale de panneaux par client [m²]
        surface_hab_par_hab : surface habitable par habitant [m²/hab] (défaut 40)
        taille_menage       : taille moyenne du ménage québécois [hab/ménage] (défaut 2.3)
        eta_toit            : fraction de toit utilisable (orientation, ombrage, etc.)
    """
    densite = population / max(superficie_km2, 1.0)

    # Modèle à 5 paliers calé sur les densités typiques du Québec
    if densite < 50:
        nb_etages = 1.5   # Régions rurales profondes (100% maisons)
    elif densite < 500:
        nb_etages = 2.0   # Villes moyennes et banlieues très étalées
    elif densite < 1500:
        nb_etages = 2.5   # Banlieues denses et villes régionales
    elif densite < 4000:
        nb_etages = 3.0   # Grands pôles urbains mixtes (Laval, Longueuil, Québec)
    else:
        nb_etages = 4.0   # Centres urbains hyper-denses (Montréal)

    s_toit_util_hab    = (surface_hab_par_hab / nb_etages) * eta_toit  # m²/hab
    s_toit_util_client = s_toit_util_hab * taille_menage               # m²/ménage
    return min(s_toit_util_client, m2_par_client) / max(m2_par_client, 0.1)


def apply_residential_scenario(
    base_df: pd.DataFrame,
    m2_par_client: float,
    mrc_data_df: pd.DataFrame,
    total_clients: int = 125_000,
) -> pd.DataFrame:
    """
    Applique un scénario résidentiel sur la base de production W/m².

    Arguments:
        base_df        : DataFrame (datetime, mrc, production_w_per_m2)
                         Issu de calculate_base_production_per_m2()
        m2_par_client  : surface totale de panneaux par client [m²]
                         Ex : 2 panneaux × 1.7 m²/panneau = 3.4 m²
        mrc_data_df    : DataFrame avec colonnes (mrc, population, superficie_km2)
                         Chargé depuis la base de données
        total_clients  : nombre total de clients résidentiels (défaut 125 000)

    Retour:
        DataFrame avec colonnes : datetime, mrc, production_kw

    Formule :
        part_mrc      = population(mrc) / sum(population)
        nb_clients    = total_clients × part_mrc
        production_kW = production_w_per_m2 × m2_par_client × nb_clients × f_densite / 1000
    """
    pop_totale = mrc_data_df["population"].sum()

    mrc_factors = {}
    for _, row in mrc_data_df.iterrows():
        mrc = row["mrc"]
        f = compute_facteur_densite(
            population=int(row["population"]),
            superficie_km2=float(row["superficie_km2"]),
            m2_par_client=m2_par_client,
        )
        nb_clients = int(total_clients * row["population"] / pop_totale)
        mrc_factors[mrc] = {"f_densite": f, "nb_clients": nb_clients}

    result_frames = []
    for mrc, factors in mrc_factors.items():
        mrc_slice = base_df[base_df["mrc"] == mrc].copy()
        if mrc_slice.empty:
            continue

        mrc_slice["production_kw"] = (
            mrc_slice["production_w_per_m2"]
            * m2_par_client
            * factors["nb_clients"]
            * factors["f_densite"]
            / 1000.0
        )
        result_frames.append(
            mrc_slice[["datetime", "mrc", "production_kw"]]
        )

    return pd.concat(result_frames, ignore_index=True)


def cost_solar_powerplant(puissance_mw):
    """
    Calcule le coût total pour chaque centrale solaire.

    Parameters
    ----------
    coordinates_centrales : list of tuples
        Liste des coordonnées et puissances des centrales
    resultats_centrales : dict
        Dictionnaire contenant l'énergie produite par chaque centrale

    Returns
    -------
    dict
        Dictionnaire contenant le coût total en dollars pour chaque centrale
    """
    couts = {}
    # Coût de référence par MW pour le Québec
    cout_par_mw = 4_210_000  # Estimation moyenne des coûts actuels

    # Coût total prenant en compte les coûts indirects et opérationnels
    cout_total = puissance_mw * cout_par_mw

    couts[nom] = cout_total

    return couts


def calculate_installation_cost(puissance_mw):
    """
    Returns
    -------
    dict
        Dictionnaire contenant le coût d'installation pour chaque centrale
    """
    couts_installation = {}
    # Coûts de base par MW selon la taille de l'installation
    if puissance_mw < 1:
        cout_base = 4_500_000  # Plus cher pour petites installations
    elif 1 <= puissance_mw < 5:
            cout_base = 4_210_000  # Coût moyen
    else:
        cout_base = 3_900_000  # Économies d'échelle pour grandes installations

    # Facteurs d'ajustement
    facteur_echelle = 0.85  # Économies d'échelle
    facteur_complexite = 1.1  # Complexité du site et infrastructure

    # Calcul du coût d'installation avec facteurs
    cout_installation = (
        cout_base * (puissance_mw**facteur_echelle) * facteur_complexite
        )
    couts_installation[nom] = cout_installation

    return couts_installation


def calculate_lifetime(puissance_mw):
    """
    Estime la durée de vie des centrales solaires en fonction de leurs puissances installées.

    Parameters
    ----------
    coordinates_centrales : list of tuples
        Liste des coordonnées et puissances des centrales sous forme de tuples
        (latitude, longitude, nom, altitude, timezone, puissance_kw)

    Returns
    -------
    dict
        Dictionnaire contenant la durée de vie estimée pour chaque centrale
    """
    durees_vie = {}


    if puissance_mw < 1:
        duree_vie = 25  # Petites installations
    elif 1 <= puissance_mw < 10:
        duree_vie = 30  # Installations moyennes
    else:
        duree_vie = 35  # Grandes installations

    durees_vie[nom] = duree_vie

    return durees_vie


def co2_emissions_solar(
    coordinates_centrales, resultats_centrales, facteur_emission=40
):
    """
    Calcule les émissions totales de CO₂ équivalent pour chaque centrale solaire sur toute sa durée de vie.

    Parameters
    ----------
    coordinates_centrales : list of tuples
        Liste des coordonnées et puissances des centrales
    resultats_centrales : dict
        Dictionnaire contenant l'énergie produite par chaque centrale
    facteur_emission : float, optional
        Facteur d'émission en g CO₂eq/kWh basé sur l'ACV

    Returns
    -------
    dict
        Dictionnaire contenant les émissions totales de CO₂ en kg pour chaque centrale
    """
    emissions = {}
    durees_vie = calculate_lifetime(coordinates_centrales)

    for centrale in coordinates_centrales:
        nom = centrale[2]
        energie_kwh = resultats_centrales[nom]["energie_annuelle_wh"] / 1000
        duree_vie = durees_vie[nom]

        # Calcul des émissions sur toute la durée de vie
        emissions_g = energie_kwh * facteur_emission * duree_vie
        emissions[nom] = emissions_g / 1000

    return emissions


# Exemple d'utilisation
if __name__ == "__main__":
    from harmoniq.modules.solaire.data_solaire import coordinates_centrales

    DATE_START = pd.Timestamp("2035-01-01")
    DATE_END   = pd.Timestamp("2035-12-31 23:00:00")
    MOIS_LABELS = ["Jan","Fev","Mar","Avr","Mai","Jun",
                   "Jul","Aou","Sep","Oct","Nov","Dec"]

    # --- Calcul des deux centrales ---
    resultats = []
    PUISSANCE_MODULE_W = 221  # Canadian Solar CS5P-220M : Impo × Vmpo ≈ 221 W
    for lat, lon, nom_c, alt, tz, puissance_kw in coordinates_centrales:
        print(f">> Calcul de {nom_c} (appel PVGIS)...")
        df = calculate_energy_solar_plants(
            nom=nom_c,
            latitude=lat,
            longitude=lon,
            angle_panneau=30.0,
            orientation_panneau=180.0,
            nombre_panneau=int(puissance_kw * 1000 / PUISSANCE_MODULE_W),
            date_start=DATE_START,
            date_end=DATE_END,
        )
        total_gwh = df["production"].sum() / 1_000_000
        print(f"   Lignes          : {len(df)}")
        print(f"   Production ann. : {total_gwh:.3f} GWh")
        print(f"   Pic max         : {df['production'].max():,.0f} kW")
        print(df.head(6).to_string(index=False))
        resultats.append(df)

    tous = pd.concat(resultats, ignore_index=True)

    # --- Graphique 1 : production horaire — semaine de juillet ---
    fig, axes = plt.subplots(len(resultats), 1, figsize=(14, 5 * len(resultats)))
    if len(resultats) == 1:
        axes = [axes]

    for ax, df in zip(axes, resultats):
        juillet = df[pd.to_datetime(df["date"]).dt.month == 7].head(24 * 7)
        ax.fill_between(pd.to_datetime(juillet["date"]), juillet["production"], alpha=0.75)
        ax.set_title(f"{df['nom'].iloc[0]} — Production horaire (1re semaine de juillet 2035)")
        ax.set_ylabel("Production (kW)")
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("production_juillet.png", dpi=120)
    print("\n[OK] production_juillet.png sauvegarde")

    # --- Graphique 2 : production mensuelle (barres) ---
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    x = np.arange(12)
    width = 0.35

    for i, df in enumerate(resultats):
        df2 = df.copy()
        df2["mois"] = pd.to_datetime(df2["date"]).dt.month
        mensuel = df2.groupby("mois")["production"].sum() / 1_000  # MWh
        ax2.bar(x + i * width, mensuel.values, width, label=df["nom"].iloc[0], alpha=0.85)

    ax2.set_xticks(x + width / 2)
    ax2.set_xticklabels(MOIS_LABELS)
    ax2.set_ylabel("Production mensuelle (MWh)")
    ax2.set_title("Production mensuelle par centrale — 2035")
    ax2.legend()
    ax2.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig("production_mensuelle.png", dpi=120)
    print("[OK] production_mensuelle.png sauvegarde")

    # --- Graphique 3 : heatmap heure x mois (toutes centrales cumulées) ---
    tous["mois"] = pd.to_datetime(tous["date"]).dt.month
    tous["heure"] = pd.to_datetime(tous["date"]).dt.hour
    heatmap_data = tous.pivot_table(
        values="production", index="heure", columns="mois", aggfunc="mean"
    )
    heatmap_data.columns = MOIS_LABELS
    heatmap_data = heatmap_data.replace(0, np.nan)

    fig3, ax3 = plt.subplots(figsize=(12, 7))
    im = ax3.imshow(heatmap_data.values, aspect="auto", cmap="YlOrRd", origin="lower")
    fig3.colorbar(im, ax=ax3, label="Production moyenne (kW)")
    ax3.set_xticks(range(12))
    ax3.set_xticklabels(MOIS_LABELS, rotation=45)
    ax3.set_yticks(range(24))
    ax3.set_yticklabels(range(24))
    ax3.set_xlabel("Mois")
    ax3.set_ylabel("Heure de la journee")
    ax3.set_title("Heatmap production solaire moyenne — toutes centrales (kW)")
    plt.tight_layout()
    plt.savefig("production_heatmap.png", dpi=120)
    print("[OK] production_heatmap.png sauvegarde")

    plt.show()
