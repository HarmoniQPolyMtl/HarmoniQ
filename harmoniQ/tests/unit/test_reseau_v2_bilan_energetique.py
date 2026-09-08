"""Test unitaire de l'extraction des indicateurs de bilan énergétique.

On monte à la main un réseau PyPSA minimal (un bus Québec, un bus interconnexion,
un bus étranger, un barrage, un lien vers le marché externe), on force un
déséquilibre offre/demande, puis on vérifie ce que extract_kpis en déduit.

Ce qu'il contrôle :
  - test_deficit_import_positive      : demande > production locale => import > 0.
  - test_surplus_export_positive      : production locale > demande => export > 0.
  - test_interco_unavailable_zero_flows: lien d'interconnexion à capacité nulle
    => import et export nuls.
  - test_balance_near_zero            : quand l'offre couvre exactement la demande,
    l'erreur de bilan reste quasi nulle.

Rapide et sans dépendance externe : aucune base de données, tout est monté en mémoire.
"""
import pandas as pd
import pypsa

from harmoniq.modules.reseau_v2.results import extract_kpis


def _make_network(snapshots):
    n = pypsa.Network()
    n.set_snapshots(snapshots)

    n.add("Bus", "QC")
    n.add("Bus", "Interco")
    n.add("Bus", "Etranger1")

    n.add("Load", "QC_load", bus="QC", p_set=0.0)

    n.add(
        "Generator",
        "Hydro1",
        bus="QC",
        carrier="hydro_reservoir",
        p_nom=200.0,
    )

    n.add(
        "Link",
        "link_Interco_Etranger1",
        bus0="Interco",
        bus1="Etranger1",
        p_nom=1000.0,
        p_min_pu=-1.0,
        p_max_pu=1.0,
        efficiency=1.0,
    )

    return n


def test_deficit_import_positive():
    snapshots = pd.date_range("2035-01-01", periods=3, freq="h")
    n = _make_network(snapshots)

    n.generators_t.p = pd.DataFrame({
        "Hydro1": [50.0, 50.0, 50.0],
    }, index=snapshots)

    n.loads_t.p_set = pd.DataFrame({
        "QC_load": [100.0, 100.0, 100.0],
    }, index=snapshots)

    n.links_t.p0 = pd.DataFrame({
        "link_Interco_Etranger1": [-50.0, -50.0, -50.0],
    }, index=snapshots)

    kpis = extract_kpis(n)
    prod = kpis["production_df"]

    assert (prod["total_import"] > 0).all()
    assert (prod["total_export"] == 0).all()
    assert kpis["summary"]["max_abs_balance_error_mw"] <= 1.0


def test_surplus_export_positive():
    snapshots = pd.date_range("2035-05-01", periods=3, freq="h")
    n = _make_network(snapshots)

    n.generators_t.p = pd.DataFrame({
        "Hydro1": [120.0, 120.0, 120.0],
    }, index=snapshots)

    n.loads_t.p_set = pd.DataFrame({
        "QC_load": [80.0, 80.0, 80.0],
    }, index=snapshots)

    n.links_t.p0 = pd.DataFrame({
        "link_Interco_Etranger1": [40.0, 40.0, 40.0],
    }, index=snapshots)

    kpis = extract_kpis(n)
    prod = kpis["production_df"]

    assert (prod["total_export"] > 0).all()
    assert (prod["total_import"] == 0).all()
    assert kpis["summary"]["max_abs_balance_error_mw"] <= 1.0


def test_interco_unavailable_zero_flows():
    snapshots = pd.date_range("2035-02-01", periods=2, freq="h")
    n = pypsa.Network()
    n.set_snapshots(snapshots)
    n.add("Bus", "QC")
    n.add("Load", "QC_load", bus="QC", p_set=0.0)
    n.add("Generator", "Hydro1", bus="QC", carrier="hydro_reservoir", p_nom=100.0)

    n.generators_t.p = pd.DataFrame({
        "Hydro1": [100.0, 100.0],
    }, index=snapshots)
    n.loads_t.p_set = pd.DataFrame({
        "QC_load": [100.0, 100.0],
    }, index=snapshots)

    kpis = extract_kpis(n)
    prod = kpis["production_df"]

    assert (prod["total_import"] == 0).all()
    assert (prod["total_export"] == 0).all()


def test_balance_near_zero():
    snapshots = pd.date_range("2035-03-01", periods=4, freq="h")
    n = _make_network(snapshots)

    n.generators_t.p = pd.DataFrame({
        "Hydro1": [90.0, 90.0, 90.0, 90.0],
    }, index=snapshots)

    n.loads_t.p_set = pd.DataFrame({
        "QC_load": [90.0, 90.0, 90.0, 90.0],
    }, index=snapshots)

    n.links_t.p0 = pd.DataFrame({
        "link_Interco_Etranger1": [0.0, 0.0, 0.0, 0.0],
    }, index=snapshots)

    kpis = extract_kpis(n)
    assert kpis["summary"]["n_balance_violations"] == 0
    assert kpis["summary"]["max_abs_balance_error_mw"] <= 1.0
