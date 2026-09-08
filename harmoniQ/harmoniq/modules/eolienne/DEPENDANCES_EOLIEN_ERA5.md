# Dépendances module éolien + ERA5

## 1) Dépendances Python

### Noyau calcul éolien
- `numpy`
- `pandas`
- `scipy`
- `pandera`

### Météo (Open-Meteo + ERA5)
- `openmeteo-requests`
- `requests-cache`
- `retry-requests`
- `xarray`
- `cdsapi`
- `netCDF4`
- `pyarrow` (lecture/écriture Parquet du cache ERA5)

### Visualisation (cartes/plots éolien)
- `matplotlib`
- `geopandas`
- `shapely`

## 2) Installation rapide (commande unique)

Depuis la racine du projet:

```powershell
pip install numpy pandas scipy pandera openmeteo-requests requests-cache retry-requests xarray cdsapi netCDF4 pyarrow matplotlib geopandas shapely
```

## 3) Pré-requis CDS (Copernicus) pour ERA5

Créer le fichier `~/.cdsapirc` (Windows: `C:\Users\<ton_user>\.cdsapirc`) avec ton token CDS:

```yaml
url: https://cds.climate.copernicus.eu/api
key: <UID>:<API_TOKEN>
```

## 4) Télécharger / construire le cache ERA5

Depuis la racine du projet:

```powershell
python -m harmoniq.scripts.eolien.fetch_era5_quebec_2024 --year 2024
```

Option pour forcer un re-téléchargement:

```powershell
python -m harmoniq.scripts.eolien.fetch_era5_quebec_2024 --year 2024 --force-download
```

### Comportement vis-à-vis des données existantes

- `--year <ANNEE>` sans `--force-download`:
  - ne supprime pas les autres années déjà présentes;
  - ne remplace pas les fichiers mensuels de l'année ciblée s'ils existent déjà et sont valides (cache hit).

- `--year <ANNEE> --force-download`:
  - force le re-téléchargement de l'année ciblée;
  - remplace les fichiers mensuels bruts/caches de cette année;
  - ne touche pas aux autres années (ex: forcer 2023 ne supprime pas 2024).

## 5) Emplacements de données créées

- Brut NetCDF: `data/meteo/era5/raw/year=2024/month=MM/era5_qc_2024_MM.nc`
- Cache normalisé Parquet: `data/meteo/era5/cache/normalized/year=2024/month=MM/era5_normalized_2024_MM.parquet`
