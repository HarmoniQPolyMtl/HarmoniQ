"""Test unitaire du chemin build + optimisation de reseau_v2, sur un réseau jouet.

On construit à la main la plus petite topologie possible (2 bus, 1 ligne, 1 type
de ligne) et des profils de charge/production minimaux, puis on appelle
build_pypsa_network suivi d'une optimisation sur un seul bloc de temps.

Ce qu'il contrôle :
  - test_build_and_optimize_one_chunk : l'OPF renvoie un dispatch strictement
    positif. Sans cette vérification, une régression silencieuse (par exemple un
    changement de type de colonne pandas) peut faire renvoyer 0 MW partout sans
    lever la moindre erreur — le test le rendrait alors visible.
  - test_etranger_bus_has_no_load : le bus « Étranger » (marché externe) ne porte
    aucune charge.

Rapide et sans dépendance externe : aucune base de données réelle, tout est monté
en mémoire.
"""
import pandas as pd
import numpy as np
import pypsa

from harmoniq.modules.reseau_v2.network_builder import build_pypsa_network


def _minimal_topology():
    """Topologie minimale : 2 bus + 1 ligne."""
    buses = pd.DataFrame({
        "name": ["Bus1", "Conso1"],
        "v_nom": [735, 315],
        "type": ["ligne", "conso"],
        "x": [53.7, 45.5],
        "y": [-77.7, -73.6],
        "control": ["PQ", "PQ"],
    })
    lines = pd.DataFrame({
        "name": ["L1"],
        "bus0": ["Bus1"],
        "bus1": ["Conso1"],
        "type": ["735kV_line"],
        "length": [100.0],
        "s_nom": [2000.0],
    })
    line_types = pd.DataFrame({
        "name": ["735kV_line"],
        "f_nom": [60.0],
        "r_per_length": [0.0108],
        "x_per_length": [0.328],
    })
    return {"buses": buses, "lines": lines, "line_types": line_types}


def _minimal_profiles(snapshots):
    """1 générateur hydro, dispatch possible sur tous les snapshots."""
    generators = pd.DataFrame({
        "name": ["Hydro1"],
        "bus": ["Bus1"],
        "carrier": ["hydro_reservoir"],
        "p_nom": [500.0],
        "marginal_cost": [10.0],
    })
    p_max_pu = pd.DataFrame(
        {"Hydro1": np.ones(len(snapshots))},
        index=snapshots,
    )
    marginal_cost = pd.DataFrame(
        {"Hydro1": np.full(len(snapshots), 10.0)},
        index=snapshots,
    )
    return {"generators": generators, "p_max_pu": p_max_pu, "marginal_cost": marginal_cost}


def _minimal_demand(snapshots):
    """Demande constante de 200 MW sur Conso1."""
    return pd.DataFrame(
        {"Conso1": np.full(len(snapshots), 200.0)},
        index=snapshots,
    )


def test_build_and_optimize_one_chunk():
    """Build + optimize → la production totale doit être > 0."""
    snapshots = pd.date_range("2035-01-01", periods=24, freq="h")

    network = build_pypsa_network(
        topology=_minimal_topology(),
        generation_profiles=_minimal_profiles(snapshots),
        demand_profile=_minimal_demand(snapshots),
        snapshots=snapshots,
    )

    status, _ = network.optimize(
        solver_name="highs",
        pyomo=False,
    )

    assert status == "ok", f"OPF failed with status: {status}"

    total_gen = network.generators_t.p.sum().sum()
    assert total_gen > 0, (
        f"Production totale = {total_gen} MW — le dispatch est nul. "
        "Vérifier la compatibilité pandas/PyPSA (ArrowStringArray ?)."
    )


def test_etranger_bus_has_no_load():
    """Les bus Étranger ne doivent pas recevoir de Load."""
    snapshots = pd.date_range("2035-01-01", periods=3, freq="h")

    buses = pd.DataFrame({
        "name": ["Bus1", "Conso1", "Interco2", "Etranger2"],
        "v_nom": [735, 315, 230, 230],
        "type": ["ligne", "conso", "ligne", "conso"],
        "x": [53.7, 45.5, 48.0, 48.0],
        "y": [-77.7, -73.6, -66.4, -66.4],
        "control": ["PQ", "PQ", "PQ", "PQ"],
    })
    lines = pd.DataFrame({
        "name": ["L1", "L_interco_backbone", "L_interco_foreign"],
        "bus0": ["Bus1", "Bus1", "Interco2"],
        "bus1": ["Conso1", "Interco2", "Etranger2"],
        "type": ["735kV_line", "230kV_line", "230kV_line"],
        "length": [100.0, 200.0, 3.0],
        "s_nom": [2000.0, 400.0, 400.0],
    })
    line_types = pd.DataFrame({
        "name": ["735kV_line", "230kV_line"],
        "f_nom": [60.0, 60.0],
        "r_per_length": [0.0108, 0.0108],
        "x_per_length": [0.328, 0.328],
    })
    topology = {"buses": buses, "lines": lines, "line_types": line_types}

    network = build_pypsa_network(
        topology=topology,
        generation_profiles=_minimal_profiles(snapshots),
        demand_profile=_minimal_demand(snapshots),
        snapshots=snapshots,
    )

    load_buses = set(network.loads.bus)
    assert "Etranger2" not in load_buses, (
        "Un Load a été créé sur le bus Étranger — "
        "la demande québécoise ne doit pas être assignée aux bus étrangers."
    )
    assert "Conso1" in load_buses, "Le bus Conso1 devrait avoir un Load."
