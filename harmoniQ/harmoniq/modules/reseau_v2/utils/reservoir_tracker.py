"""Suivi des niveaux de réservoir après dispatch LP-OPF.

Pipeline d'exécution :

1. L'OPF dispatche chaque barrage-réservoir (``generators_t.p`` en MW).
2. ``compute_reservoir_levels()`` convertit ce dispatch en décharge (m³/s),
   charge les apports naturels depuis les CSV hydro, et applique le bilan
   hydraulique pas à pas pour chaque snapshot.
3. La sortie (fraction [0-1]) peut être visualisée ou réinjectée dans
   l'OPF via ``water_value_cost()`` pour un dispatch sensible au niveau d'eau.

Example:
    from harmoniq.modules.reseau_v2.utils.reservoir_tracker import (
        compute_reservoir_levels,
        water_value_cost,
    )

    levels = compute_reservoir_levels(network, db)
    costs = water_value_cost(levels.iloc[-1].values)
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pypsa

from harmoniq.modules.hydro import APPORT_DIR as _APPORT_DIR

logger = logging.getLogger("ReservoirTracker")

# Niveau initial par défaut si non fourni.
# 80% correspond au niveau typique HQ en début d'année (après automne humide,
# avant le tirage hivernal). Valeur consensuelle retenue faute de données
# temps-réel publiques sur le remplissage des réservoirs.
_DEFAULT_INITIAL_LEVEL = 0.80

# Apport naturel par défaut si le CSV est absent (m³/s)
_DEFAULT_INFLOW_M3S = 15.0


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def compute_reservoir_levels(
    network: pypsa.Network,
    db: Any,
    initial_levels: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Calcule les niveaux de réservoir à chaque snapshot après le dispatch OPF.

    Pour chaque barrage-réservoir présent dans ``generators_t.p``, applique
    le bilan hydraulique pas à pas :

        V[t+1] = clamp(V[t] + inflow(t)×Δt − discharge(t)×Δt, 0, V_max)

    où ``inflow(t)`` est l'apport naturel journalier (m³/s) issu du CSV hydro,
    ``discharge(t) = debit_max × (P_dispatch[t] / P_max)`` (m³/s),
    ``Δt = snapshot_weightings × 3 600 s``, et ``V_max`` est le volume de la DB.

    :param network: Réseau PyPSA après ``run_dispatch_and_flow()``. ``generators_t.p``
        doit être renseigné.
    :param db: Session SQLAlchemy pour lire les barrages (type_barrage, volume, etc.).
    :param initial_levels: Dict ``{nom_barrage: fraction [0-1]}``. Défaut : 0.70.
    :returns: DataFrame index = snapshots, colonnes = noms des barrages-réservoirs,
        valeurs = fraction [0-1] du volume utile.
    """
    from harmoniq.db.CRUD import read_all_hydro

    if initial_levels is None:
        initial_levels = {}

    snapshots = network.snapshots
    if len(snapshots) == 0:
        return pd.DataFrame()

    # Δt par snapshot en secondes (snapshot_weightings.generators = heures/snapshot)
    dt_seconds = (network.snapshot_weightings.generators * 3600.0).values

    # Dispatch OPF par générateur [MW]
    gen_p = network.generators_t.get("p", pd.DataFrame())
    if gen_p.empty:
        logger.warning(
            "generators_t.p vide — aucun dispatch OPF disponible pour le suivi réservoir."
        )
        return pd.DataFrame()

    # Charger les barrages depuis la DB
    try:
        barrages = read_all_hydro(db)
    except Exception as exc:
        logger.error("Impossible de charger les barrages depuis la DB : %s", exc)
        return pd.DataFrame()

    reservoir_dams = [b for b in barrages if b.type_barrage == "Reservoir"]
    if not reservoir_dams:
        logger.warning("Aucun barrage de type 'Reservoir' trouvé en DB.")
        return pd.DataFrame()

    result = pd.DataFrame(index=snapshots, dtype=float)

    for dam in reservoir_dams:
        nom = dam.nom

        # Le nom du générateur PyPSA correspond directement à dam.nom
        if nom not in gen_p.columns:
            logger.debug("Barrage '%s' absent de generators_t.p — ignoré.", nom)
            continue

        volume_max = float(dam.volume_reservoir)
        if volume_max <= 0:
            logger.warning("Barrage '%s' : volume_reservoir=0 — ignoré.", nom)
            continue

        # Puissance et débit disponibles (hors turbines en maintenance)
        nb_dispo = max(1, dam.nb_turbines - dam.nb_turbines_maintenance)
        ratio_dispo = nb_dispo / max(1, dam.nb_turbines)
        p_max_mw = float(dam.puissance_nominal) * ratio_dispo
        debit_max_m3s = float(dam.debits_nominal) * nb_dispo

        # Apport naturel aligné sur les snapshots [m³/s]
        apport_m3s = _load_inflow(dam, snapshots)

        # Dispatch réel de l'OPF [MW]
        dispatch_mw = gen_p[nom].reindex(snapshots, fill_value=0.0).values

        # Bilan hydraulique pas à pas
        volume_courant = initial_levels.get(nom, _DEFAULT_INITIAL_LEVEL) * volume_max
        volumes = np.empty(len(snapshots))

        for i in range(len(snapshots)):
            inflow_m3   = apport_m3s[i] * dt_seconds[i]

            # Fraction de turbinage : dispatch réel / capacité max disponible
            fraction    = (dispatch_mw[i] / p_max_mw) if p_max_mw > 0 else 0.0
            fraction    = float(np.clip(fraction, 0.0, 1.0))
            discharge_m3 = debit_max_m3s * fraction * dt_seconds[i]

            volume_courant = volume_courant + inflow_m3 - discharge_m3
            volume_courant = float(np.clip(volume_courant, 0.0, volume_max))
            volumes[i] = volume_courant

        result[nom] = volumes / volume_max  # fraction [0-1]

    logger.info(
        "Suivi réservoir : %d/%d barrages calculés sur %d snapshots.",
        len(result.columns), len(reservoir_dams), len(snapshots),
    )
    return result


# ---------------------------------------------------------------------------
# Water value : niveau → coût marginal
# ---------------------------------------------------------------------------

def water_value_cost(niveaux: np.ndarray, regulation: str = "Pluriannuel") -> np.ndarray:
    """Calcule le coût marginal de l'eau ($/MWh) en fonction du niveau de réservoir.

    Deux courbes selon le type de régulation :

    **Pluriannuel** (réservoirs multi-années — ex. Robert-Bourassa) :
    - Seuil critique : 50% → comportement agressif, on refuse de descendre sous la moitié
    - niveau = 1.0  →  5 $/MWh  (réservoir plein)
    - niveau = 0.50 → 25 $/MWh  (seuil critique, croissance exponentielle en dessous)
    - niveau = 0.0  → 35 $/MWh  (réservoir vide)

    **Annuel** (réservoirs à recharge annuelle — ex. La Grande-4) :
    - Seuil critique : 5% → peut être davantage exploité (fonte printanière garantit le rechargement)
    - niveau = 1.0  →  1 $/MWh  (réservoir plein, eau peu précieuse)
    - niveau = 0.05 →  8 $/MWh  (seuil critique)
    - niveau = 0.0  → 12 $/MWh  (réservoir vide)

    :param niveaux: Tableau de niveaux de réservoir [0-1].
    :param regulation: "Annuel" ou "Pluriannuel" (insensible à la casse). Défaut : "Pluriannuel".
    :returns: Tableau de coûts marginaux en $/MWh.
    """
    niveaux = np.clip(np.asarray(niveaux, dtype=float), 0.0, 1.0)
    couts   = np.zeros_like(niveaux)

    if regulation.strip().lower() == "annuel":
        # Réservoir annuel : seuil critique 40% — plancher pédagogique pour montrer
        # la nécessité de renforcer le réseau (objectifs HQ 2035-2050).
        # L'import devient compétitif à 40% de fill, rendant la déplétion visible.
        # niveau=1.0 → 1 $/MWh | niveau=0.40 → 15 $/MWh | niveau=0.0 → 25 $/MWh
        COUT_MIN       = 1.0
        COUT_CRITIQUE  = 15.0  # = prix import Ontario → LP importe dès 40% fill
        COUT_MAX       = 25.0
        SEUIL_CRITIQUE = 0.40

        below = niveaux < SEUIL_CRITIQUE
        above = ~below

        # Linéaire au-dessus du seuil critique
        facteur_above = (1.0 - niveaux[above]) / (1.0 - SEUIL_CRITIQUE)
        couts[above] = COUT_MIN + (COUT_CRITIQUE - COUT_MIN) * facteur_above

        # Linéaire en dessous du seuil critique (descente rapide vers COUT_MAX)
        facteur_below = (SEUIL_CRITIQUE - niveaux[below]) / SEUIL_CRITIQUE
        couts[below]  = COUT_CRITIQUE + (COUT_MAX - COUT_CRITIQUE) * facteur_below

    else:  # Pluriannuel (défaut) : protection agressive ≥ 80%
        # Seuil critique remonté à 80% pour montrer la contrainte structurelle HQ 2035-2050.
        # En dessous de 80% : falaise exponentielle (import/thermique toujours préférés).
        # niveau=1.0 →  5 $/MWh | niveau=0.80 → ~8.75 $/MWh | niveau<0.80 → exponentielle
        COUT_MIN       = 5.0
        COUT_MAX       = 35.0
        SEUIL_CRITIQUE = 0.80

        below = niveaux < SEUIL_CRITIQUE
        facteur_below = (SEUIL_CRITIQUE - niveaux[below]) / SEUIL_CRITIQUE
        couts[below]  = COUT_MIN + (COUT_MAX - COUT_MIN) * np.exp(2 * facteur_below)

        above = ~below
        facteur_above = (1.0 - niveaux[above]) / (1.0 - SEUIL_CRITIQUE)
        couts[above]  = COUT_MIN + (COUT_MAX / 4 - COUT_MIN) * facteur_above

    return np.round(np.clip(couts, 0.0, 105.0), 2)


# ---------------------------------------------------------------------------
# Feed-forward chunk-par-chunk : données précalculées par barrage
# ---------------------------------------------------------------------------

@dataclass
class ReservoirDamFeed:
    """Métadonnées d'un barrage réservoir pour le feed-forward hydraulique chunk-par-chunk.

    Pré-chargé une seule fois avant l'optimisation via ``build_reservoir_feed_data``.
    L'optimiseur met à jour ``current_level`` après chaque chunk.
    """
    nom: str
    p_max_mw: float
    debit_max_m3s: float
    volume_max_m3: float
    apport_m3s: np.ndarray      # un m³/s par snapshot (toute l'année, aligné positionellement)
    current_level: float = 0.70  # niveau courant [0-1], mis à jour chunk par chunk
    ratio_dispo: float = 1.0     # (nb_turbines - nb_maintenance) / nb_turbines
    regulation: str = "Pluriannuel"  # "Annuel" ou "Pluriannuel" — détermine la courbe water value


def build_reservoir_feed_data(
    network: pypsa.Network,
    db: Any,
    initial_levels: Optional[Dict[str, float]] = None,
) -> List[ReservoirDamFeed]:
    """Pré-charge les données de feed-forward pour tous les barrages réservoirs.

    À appeler une seule fois après ``creer_reseau()``, avant ``run_dispatch_and_flow()``.
    Le résultat est passé à l'optimiseur qui met à jour ``current_level`` après chaque chunk.

    :param network: Réseau PyPSA construit (snapshots requis).
    :param db: Session SQLAlchemy pour lire les barrages depuis la DB.
    :param initial_levels: Dict ``{nom_barrage: fraction [0-1]}``. Défaut : 0.70.
    :returns: Liste de :class:`ReservoirDamFeed`, un élément par barrage réservoir
        présent dans ``network.generators``.
    """
    from harmoniq.db.CRUD import read_all_hydro

    if initial_levels is None:
        initial_levels = {}

    snapshots = network.snapshots
    if len(snapshots) == 0:
        return []

    try:
        barrages = read_all_hydro(db)
    except Exception as exc:
        logger.warning("build_reservoir_feed_data : impossible de charger les barrages : %s", exc)
        return []

    reservoir_dams = [b for b in barrages if b.type_barrage == "Reservoir"]
    result: List[ReservoirDamFeed] = []

    for dam in reservoir_dams:
        nom = dam.nom

        # Vérifier que ce barrage existe dans le réseau PyPSA
        if nom not in network.generators.index:
            continue

        volume_max = float(dam.volume_reservoir)
        if volume_max <= 0:
            continue

        nb_dispo = max(1, dam.nb_turbines - dam.nb_turbines_maintenance)
        ratio_dispo = nb_dispo / max(1, dam.nb_turbines)
        p_max_mw = float(dam.puissance_nominal) * ratio_dispo
        debit_max_m3s = float(dam.debits_nominal) * nb_dispo

        apport = _load_inflow(dam, snapshots)
        initial_level = initial_levels.get(nom, _DEFAULT_INITIAL_LEVEL)

        result.append(ReservoirDamFeed(
            nom=nom,
            p_max_mw=p_max_mw,
            debit_max_m3s=debit_max_m3s,
            volume_max_m3=volume_max,
            apport_m3s=apport,
            current_level=initial_level,
            ratio_dispo=ratio_dispo,
            regulation=str(getattr(dam, "regulation", None) or "Pluriannuel").strip(),
        ))

    logger.info(
        "build_reservoir_feed_data : %d barrages réservoirs préchargés pour le feed-forward OPF.",
        len(result),
    )
    return result


# ---------------------------------------------------------------------------
# Chargement apport naturel
# ---------------------------------------------------------------------------

def _load_inflow(dam: Any, snapshots: pd.DatetimeIndex) -> np.ndarray:
    """Charge l'apport naturel journalier (m³/s) aligné sur les snapshots.

    Lit ``{_APPORT_DIR}/{dam.id_HQ}.csv`` (colonnes : time, streamflow) et
    construit une climatologie moyenne par (mois, jour) sur tout l'historique,
    puis réindexe chaque snapshot sur son (mois, jour). Cette approche est
    indépendante de l'année de simulation (compatible avec des scénarios futurs).

    Si le fichier est absent, retourne ``_DEFAULT_INFLOW_M3S`` pour tous les snapshots.

    :param dam: Objet barrage avec les attributs ``id_HQ`` et ``nom``.
    :param snapshots: Index temporel du réseau.
    :returns: Tableau NumPy de débits (m³/s), un par snapshot.
    """
    apport_path = _APPORT_DIR / f"{dam.id_HQ}.csv"

    if not apport_path.exists():
        logger.debug(
            "CSV apport naturel absent pour '%s' (id_HQ=%s) — défaut %.0f m³/s.",
            dam.nom, dam.id_HQ, _DEFAULT_INFLOW_M3S,
        )
        return np.full(len(snapshots), _DEFAULT_INFLOW_M3S)

    try:
        df = pd.read_csv(apport_path, parse_dates=["time"]).set_index("time")["streamflow"]
        # Aligner par JOUR DE L'ANNÉE (month + day) pour être indépendant de l'année
        # de simulation. Les CSV vont jusqu'à ~2022 ; un scénario 2035 ne peut pas
        # être aligné par date absolue (method="nearest" donnerait dec-2022 partout).
        # On calcule la moyenne climatologique par (mois, jour) sur tout l'historique,
        # puis on réindexe chaque snapshot sur son (mois, jour).
        df_clim = df.groupby([df.index.month, df.index.day]).mean()
        df_clim.index.names = ["month", "day"]
        aligned = np.array([
            df_clim.get((ts.month, ts.day), _DEFAULT_INFLOW_M3S)
            for ts in snapshots
        ], dtype=float)
        aligned = np.where(np.isnan(aligned), _DEFAULT_INFLOW_M3S, aligned)
        return aligned
    except Exception as exc:
        logger.warning(
            "Erreur chargement apport '%s' : %s — défaut %.0f m³/s.",
            dam.nom, exc, _DEFAULT_INFLOW_M3S,
        )
        return np.full(len(snapshots), _DEFAULT_INFLOW_M3S)
