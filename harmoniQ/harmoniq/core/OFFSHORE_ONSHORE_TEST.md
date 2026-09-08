# Test Offshore / Onshore (Québec)

Ce document explique comment tester rapidement si une position `(latitude, longitude)` est en mer (`offshore`) ou sur terre (`onshore`) pour le Québec.

Le test est basé sur le maillage 1 km stocké en base de données, donc il est léger et rapide (lookup par cellule), sans opération géométrique lourde à chaque appel.

## 1) Prérequis (une seule fois)

Depuis la racine du projet:

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.migrate_add_offshore_mesh_schema
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.build_quebec_offshore_mesh --resolution-m 1000 --grid-version qc_mer_1km_v1
```

Optionnel (si vous voulez remplir `is_offshore` pour les parcs éoliens déjà existants):

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.backfill_offshore_eolien --grid-version qc_mer_1km_v1
```

## 2) API à utiliser dans un module

Fonction commune:

```python
from harmoniq.core.offshore import is_offshore_quebec
```

Signature:

```python
is_offshore_quebec(latitude: float, longitude: float, db: Session, grid_version: str = "qc_mer_1km_v1") -> bool
```

## 3) Exemple simple (1 point)

```python
from harmoniq.core.offshore import is_offshore_quebec
from harmoniq.db.engine import get_db

lat = 48.4
lon = -69.2

db = next(get_db())
try:
    offshore = is_offshore_quebec(latitude=lat, longitude=lon, db=db)
finally:
    db.close()

site_type = "offshore" if offshore else "onshore"
print(site_type)
```

## 4) Exemple efficace (plusieurs points)

Réutiliser la même session DB pour un lot de points:

```python
from harmoniq.core.offshore import is_offshore_quebec
from harmoniq.db.engine import get_db

points = [
    (48.4, -69.2),
    (46.8, -71.2),
    (47.5, -61.5),
]

db = next(get_db())
try:
    results = []
    for lat, lon in points:
        offshore = is_offshore_quebec(latitude=lat, longitude=lon, db=db)
        results.append(
            {
                "latitude": lat,
                "longitude": lon,
                "is_offshore": offshore,
                "site_type": "offshore" if offshore else "onshore",
            }
        )
finally:
    db.close()
```

## 5) Bonnes pratiques performance

1. Ouvrir la session DB une fois par lot, pas une fois par point.
2. Si vous testez souvent les mêmes coordonnées, ajouter un cache mémoire local (dict) dans votre module.
3. Si l’infrastructure est persistée en base, stocker le booléen (`is_offshore`) au create/update pour éviter de recalculer.

## 6) Erreur fréquente

Si vous obtenez une erreur du type:

`Offshore mesh metadata not found for grid_version='qc_mer_1km_v1'`

cela signifie que le maillage n’a pas encore été généré/chargé. Relancer les commandes de la section **Prérequis**.
