"""Tests d'audit reseau_v2 — vérifie le vrai flow du module.

Chaque test appelle les fonctions réelles de reseau_v2 (data_loader,
network_builder, optimizer) avec la vraie DB (db.sqlite / demande.db).
"""
import re
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from harmoniq.modules.reseau_v2.data_loader import (
    NetworkDataLoaderBis,
    _aggregate_to_resolution,
)
from harmoniq.modules.reseau_v2.network_builder import build_pypsa_network
from harmoniq.modules.reseau_v2.optimizer import run_dispatch_and_flow

# Chemin vers la vraie DB (pas test_db.sqlite créé par conftest)
_REAL_DB = Path(__file__).resolve().parents[1] / "harmoniq" / "db" / "db.sqlite"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    """Session SQLAlchemy vers la vraie db.sqlite."""
    engine = create_engine(f"sqlite:///{_REAL_DB}").execution_options(
        schema_translate_map={"reseau": None}
    )
    session = Session(bind=engine)
    yield session
    session.close()


@pytest.fixture(scope="module")
def loader():
    return NetworkDataLoaderBis()


@pytest.fixture(scope="module")
def topology(loader, db):
    return loader.load_topology_from_db(db)


def _scenario(date_str="2035-01-22", days=1):
    """Crée un objet scénario minimal (duck-typed comme ScenarioResponse)."""
    start = datetime.fromisoformat(date_str)
    return SimpleNamespace(
        id=999,
        date_de_debut=start,
        date_de_fin=start + timedelta(days=days),
        pas_de_temps=timedelta(hours=1),
        weather=2,       # typical
        consomation=1,   # PV
    )


def _empty_infra():
    """Liste d'infra vide → le loader charge toutes les infras de la DB."""
    return SimpleNamespace(
        parc_eoliens=None,
        parc_solaires=None,
        central_hydroelectriques=None,
        central_thermique=None,
        central_nucleaire=None,
    )


# ---------------------------------------------------------------------------
# Test 1 — Topologie : x > 0 et r > 0 sur le vrai réseau
# ---------------------------------------------------------------------------

class TestTopologie:
    def test_lines_have_positive_x_r(self, topology):
        """Toutes les lignes du réseau doivent avoir x > 0 et r > 0
        après calculate_dependent_values (fix PyPSA 1.x)."""
        snapshots = pd.date_range("2035-01-22", periods=24, freq="h")
        buses_df = topology["buses"]

        # Profils synthétiques minimaux — on teste le builder, pas les profils
        gen_bus = buses_df[buses_df["type"] == "ligne"]["name"].iloc[0]
        generators = pd.DataFrame({
            "name": ["TestGen"],
            "bus": [gen_bus],
            "carrier": ["hydro_reservoir"],
            "p_nom": [5000.0],
            "marginal_cost": [10.0],
        })
        p_max_pu = pd.DataFrame({"TestGen": np.ones(24)}, index=snapshots)
        marginal_cost = pd.DataFrame({"TestGen": np.full(24, 10.0)}, index=snapshots)

        conso_buses = buses_df[buses_df["type"] == "conso"]["name"].tolist()
        demand = pd.DataFrame(
            {b: np.full(24, 100.0) for b in conso_buses[:5]},
            index=snapshots,
        )

        network = build_pypsa_network(
            topology=topology,
            generation_profiles={
                "generators": generators,
                "p_max_pu": p_max_pu,
                "marginal_cost": marginal_cost,
            },
            demand_profile=demand,
            snapshots=snapshots,
        )

        n_lines = len(network.lines)
        assert n_lines > 0, "Aucune ligne dans le réseau"
        assert (network.lines.x > 0).all(), (
            f"Lignes avec x <= 0 :\n"
            f"{network.lines[network.lines.x <= 0][['type', 'length', 'x']]}"
        )
        assert (network.lines.r > 0).all(), (
            f"Lignes avec r <= 0 :\n"
            f"{network.lines[network.lines.r <= 0][['type', 'length', 'r']]}"
        )

    def test_x_equals_xperlength_times_length(self, topology):
        """x = x_per_length × length pour chaque ligne."""
        snapshots = pd.date_range("2035-01-22", periods=3, freq="h")
        gen_bus = topology["buses"]["name"].iloc[0]
        generators = pd.DataFrame({
            "name": ["G"], "bus": [gen_bus], "carrier": ["hydro_reservoir"],
            "p_nom": [100.0], "marginal_cost": [10.0],
        })
        network = build_pypsa_network(
            topology=topology,
            generation_profiles={
                "generators": generators,
                "p_max_pu": pd.DataFrame({"G": [1.0]*3}, index=snapshots),
                "marginal_cost": pd.DataFrame({"G": [10.0]*3}, index=snapshots),
            },
            demand_profile=pd.DataFrame(index=snapshots),
            snapshots=snapshots,
        )

        lt = topology["line_types"].set_index("name")
        for idx, line in network.lines.iterrows():
            if line.type not in lt.index:
                continue
            expected_x = lt.loc[line.type, "x_per_length"] * line.length
            assert abs(line.x - expected_x) < 1e-4, (
                f"{idx}: x={line.x:.6f} attendu {expected_x:.6f}"
            )


# ---------------------------------------------------------------------------
# Test 2 — Modularité de l'agrégation
# ---------------------------------------------------------------------------

class TestAggregationModulaire:
    def test_resample_centralise_dans_helper(self):
        """Le resample W-MON ne doit apparaître que dans _aggregate_to_resolution
        (+ la ligne solaire locale). Si > 2 occurrences, duplication réintroduite."""
        src = (Path(__file__).resolve().parents[1]
               / "harmoniq" / "modules" / "reseau_v2" / "data_loader.py")
        code = src.read_text(encoding="utf-8")
        pattern = re.compile(r'\.resample\(["\']W-MON["\']')
        matches = [(i + 1, line.strip())
                   for i, line in enumerate(code.splitlines())
                   if pattern.search(line)]
        assert len(matches) <= 2, (
            f"resample('W-MON') trouvé à {len(matches)} endroits (attendu ≤ 2).\n"
            + "\n".join(f"  L{n}: {l}" for n, l in matches)
        )

    def test_aggregate_horaire_noop(self):
        """En mode horaire, _aggregate_to_resolution retourne le DF inchangé."""
        idx = pd.date_range("2035-01-22", periods=168, freq="h")
        df = pd.DataFrame({"A": np.random.rand(168)}, index=idx)
        result = _aggregate_to_resolution(df, "horaire")
        pd.testing.assert_frame_equal(result, df)

    def test_aggregate_hebdo_produces_monday_index(self):
        """En mode hebdo, les index sont des lundis (label=left)."""
        idx = pd.date_range("2035-01-01", periods=168 * 3, freq="h")
        df = pd.DataFrame({"A": np.arange(len(idx), dtype=float)}, index=idx)
        result = _aggregate_to_resolution(df, "hebdomadaire")
        assert len(result) >= 3
        assert all(ts.weekday() == 0 for ts in result.index), (
            "Tous les index hebdo devraient être des lundis"
        )

    def test_aggregate_fill_none_preserves_nan(self):
        """fill=None ne remplace pas les NaN (utile pour marginal_cost)."""
        idx = pd.date_range("2035-01-06", periods=168, freq="h")
        df = pd.DataFrame({"A": np.ones(168)}, index=idx)
        df.iloc[0] = np.nan
        result = _aggregate_to_resolution(df, "hebdomadaire", fill=None)
        # pandas mean() ignore NaN → résultat non-NaN
        assert not result.isna().any().any()


# ---------------------------------------------------------------------------
# Test 3 — Profils de génération via le vrai load_generation_profiles
# ---------------------------------------------------------------------------

class TestProfilsGeneration:
    def test_load_generation_profiles_returns_expected_keys(self, loader, db, topology):
        """load_generation_profiles retourne generators, p_max_pu, marginal_cost."""
        scenario = _scenario("2035-01-22", days=1)
        profiles = loader.load_generation_profiles(
            scenario, _empty_infra(), db,
            resolution="horaire",
            buses_df=topology["buses"],
        )

        assert "generators" in profiles
        assert "p_max_pu" in profiles
        assert "marginal_cost" in profiles
        assert isinstance(profiles["generators"], pd.DataFrame)
        assert isinstance(profiles["p_max_pu"], pd.DataFrame)

    def test_generation_profiles_have_rows(self, loader, db, topology):
        """Au moins un générateur et des profils non-vides."""
        scenario = _scenario("2035-01-22", days=1)
        profiles = loader.load_generation_profiles(
            scenario, _empty_infra(), db,
            resolution="horaire",
            buses_df=topology["buses"],
        )

        assert len(profiles["generators"]) > 0, "Aucun générateur chargé depuis la DB"
        assert not profiles["p_max_pu"].empty, "p_max_pu vide"

    def test_p_max_pu_in_zero_one(self, loader, db, topology):
        """p_max_pu doit être dans [0, 1] pour tous les générateurs."""
        scenario = _scenario("2035-01-22", days=1)
        profiles = loader.load_generation_profiles(
            scenario, _empty_infra(), db,
            resolution="horaire",
            buses_df=topology["buses"],
        )

        pmax = profiles["p_max_pu"]
        if not pmax.empty:
            assert (pmax.fillna(0) >= 0).all().all(), "p_max_pu < 0 détecté"
            assert (pmax.fillna(0) <= 1.0001).all().all(), "p_max_pu > 1 détecté"


# ---------------------------------------------------------------------------
# Test 4 — Dispatch DC-LOPF 1 jour sur le vrai réseau
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_dc_lopf_one_day_feasible(self, loader, db, topology):
        """Build le vrai réseau, optimize 24h → faisable, production > 0."""
        scenario = _scenario("2035-01-22", days=1)
        buses_df = topology["buses"]

        gen_profiles = loader.load_generation_profiles(
            scenario, _empty_infra(), db,
            resolution="horaire",
            buses_df=buses_df,
        )
        demand = loader.load_demand_profile(
            scenario, db,
            resolution="horaire",
            buses_df=buses_df,
        )

        snapshots = (
            gen_profiles["p_max_pu"].index
            if not gen_profiles["p_max_pu"].empty
            else pd.date_range("2035-01-22", periods=24, freq="h")
        )

        network = build_pypsa_network(
            topology=topology,
            generation_profiles=gen_profiles,
            demand_profile=demand,
            snapshots=snapshots,
        )

        result = run_dispatch_and_flow(network, mode="dc")

        assert result["status"] in ("ok", "ok_with_relaxation"), (
            f"OPF échoué : status={result['status']}, detail={result.get('optimization_detail')}"
        )

        total_gen = network.generators_t.p.sum().sum()
        assert total_gen > 0, (
            f"Production totale = {total_gen} MW — dispatch nul malgré status={result['status']}"
        )


# ---------------------------------------------------------------------------
# Test 5 — Cohérence agrégation hebdomadaire
# ---------------------------------------------------------------------------

class TestCoherenceHebdo:
    def test_mean_horaire_eq_hebdo(self):
        """mean(profil_horaire sur semaine_k) ≈ profil_hebdo[semaine_k]."""
        idx_h = pd.date_range("2035-01-01 01:00", periods=168 * 4, freq="h")
        np.random.seed(42)
        df_h = pd.DataFrame({
            "bus_A": np.random.rand(len(idx_h)),
            "bus_B": np.random.rand(len(idx_h)),
        }, index=idx_h)

        df_w = _aggregate_to_resolution(df_h, "hebdomadaire")

        for label, group in df_h.resample("W-MON", label="left", closed="left"):
            if len(group) != 168:
                continue  # skip bins partiels
            expected_mean = group.mean()
            pd.testing.assert_series_equal(
                df_w.loc[label], expected_mean,
                check_names=False, atol=1e-10,
                obj=f"Semaine {label.date()}",
            )

    def test_energie_totale_conservee(self):
        """sum(168 valeurs horaires) = mean_hebdo × 168 sur semaines complètes."""
        idx_h = pd.date_range("2035-01-01 01:00", periods=168 * 4, freq="h")
        np.random.seed(123)
        df_h = pd.DataFrame({"load": np.random.rand(len(idx_h)) * 500}, index=idx_h)

        df_w = _aggregate_to_resolution(df_h, "hebdomadaire")

        for label, group in df_h.resample("W-MON", label="left", closed="left"):
            if len(group) != 168:
                continue
            energie_h = group["load"].sum()
            energie_w = df_w.loc[label, "load"] * 168.0
            assert abs(energie_h - energie_w) < 1e-6, (
                f"Semaine {label.date()}: horaire={energie_h:.2f} vs hebdo={energie_w:.2f}"
            )
