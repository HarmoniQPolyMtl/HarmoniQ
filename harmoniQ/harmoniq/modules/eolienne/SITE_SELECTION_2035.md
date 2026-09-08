# Sélection automatique de sites éoliens 2035 (V1)

Ce document explique comment lancer la nouvelle feature backend `site_selection_2035` du module éolien.

## 1) Objectif

La V1:
- classe les points météo ERA5 autorisés au Québec,
- simule la production avec un parc-type de `200 MW`,
- sélectionne gloutonnement de nouveaux parcs jusqu'à dépasser `10 000 MW` installés,
- génère des sorties tabulaires + une carte simple.

## 2) Pré-requis

- Environnement Python du projet activé (`venv`).
- Cache ERA5 déjà présent pour la période utilisée (`data/meteo/era5/cache/...`).
- Dépendances installées (notamment `pandas`, `numpy`, `geopandas`, `matplotlib`, `xarray`, `pyarrow`).

Optionnel offshore:
- Ajouter un GeoJSON des eaux québécoises.
- Chemin par défaut attendu:
  - `data/geography/quebec_waters.geojson`

Si ce fichier est absent, le script fonctionne quand même mais **exclut automatiquement les candidats offshore**.

## 3) Commandes d'utilisation

### A. Afficher l'aide

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.select_wind_sites_2035 --help
```

### B. Lancement standard (2015–2024)

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.select_wind_sites_2035 --start-year 2015 --end-year 2024
```

### C. Test rapide sur 1 année (ex: 2024)

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.select_wind_sites_2035 --start-year 2024 --end-year 2024
```

### D. Forcer un dossier de sortie custom

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.select_wind_sites_2035 --start-year 2015 --end-year 2024 --output-dir harmoniq/modules/eolienne/plot/site_selection_2035_run1
```

### E. Activer l'offshore avec un GeoJSON spécifique

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.select_wind_sites_2035 --start-year 2015 --end-year 2024 --waters-geojson "C:\chemin\quebec_waters.geojson"
```

### F. Modifier les paramètres métier exposés (si nécessaire)

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.select_wind_sites_2035 --start-year 2015 --end-year 2024 --park-mw 200 --target-mw 10000 --min-distance-km 20
```

## 4) Fichiers générés

Par défaut dans:
- `harmoniq/modules/eolienne/plot/site_selection_2035/`

Fichiers:
- `candidate_ranking_2035.csv`
- `candidate_ranking_2035.parquet`
- `selected_new_parks_2035.csv`
- `selected_new_parks_2035.parquet`
- `selection_summary_2035.json`
- `map_existing_vs_new_2035.png`

## 5) Lecture rapide des sorties

### `candidate_ranking_2035.csv`
Classement global des candidats avec notamment:
- `rank_global`
- `latitude`, `longitude`
- `site_type` (`onshore`/`offshore`)
- `score_annual`
- `production_annual_mwh`
- `cf_annual`
- `production_winter_mwh`
- `cf_winter`
- `is_eligible_distance`
- `exclusion_reason`
- `selected`

### `selected_new_parks_2035.csv`
Liste finale retenue avec notamment:
- `park_name` (`HQ-WIND-2035-01`, etc.)
- `selection_order`
- `global_rank`
- `installed_mw`
- `score_annual`
- `production_annual_twh`
- `production_winter_mwh`
- `cf_annual`
- `cumulative_installed_mw_after_addition`

### `selection_summary_2035.json`
Résumé du run:
- années utilisées,
- modèle de turbine de référence détecté,
- MW installés existants,
- MW finaux,
- nombre de candidats,
- nombre de parcs sélectionnés.

## 6) Notes importantes

- Le score principal est basé sur la production annuelle simulée.
- L'hiver est `décembre-janvier-février-mars`.
- Pas de Weibull dans cette feature (série horaire ERA5 directe).
- Pas d'interpolation pour les nouveaux sites.
- Distance minimale de 20 km appliquée:
  - nouveau vs existants
  - nouveau vs nouveaux déjà sélectionnés
- Arrêt glouton dès dépassement strict de `10 000 MW`.
