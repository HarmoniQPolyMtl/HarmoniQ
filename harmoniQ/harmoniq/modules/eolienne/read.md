# Documentation Synthese - Module Eolien (HarmoniQ)

Le module eolien calcule une serie temporelle de puissance (instantanee) a partir de donnees meteo, puis en deduit une energie cumulee sur la periode simulee.

Fichiers cles:
- `harmoniq/modules/eolienne/calcule.py`
- `harmoniq/modules/eolienne/__init__.py`
- `harmoniq/modules/eolienne/turbine_data.py`
- `harmoniq/core/meteo.py`

## 1. Entrees du calcul

Le calcul principal est `get_parc_power(parc, meteo)`.

- `parc` contient les parametres du parc:
  - nombre_eoliennes
  - hauteur_moyenne
  - modele_turbine
  - puissance_nominal (par turbine)
- `meteo` contient la serie temporelle:
  - temperature_C
  - vitesse_vent_kmh
  - direction_vent
  - index temporel (dates)

Important:
- Le `scenario` sert a definir la periode et la granularite meteo, pas la demande electrique.

## 2. Chaine de calcul (ordre exact)

1. Selection du modele de turbine
- Recuperation des seuils (`cut_in_wind_speed`, `cut_out_wind_speed`, etc.) via `turbine_data.py`.

2. Preparation des unites
- Temperature convertie en Kelvin.
- Vitesse convertie de km/h vers m/s avant la courbe de puissance (coherent avec les courbes turbine).

3. Ajustement de la vitesse au moyeu
- Loi logarithmique:
  `v_hub = v_ref * ln(z_hub / z0) / ln(z_ref / z0)`
- Avec `z_ref = 10 m` et `z0 = 0.03`.

4. Courbe de puissance simplifiee (piecewise)
- `P = 0` si `v < cut_in` ou `v > cut_out`
- montee polynomiale entre `cut_in` et `rated`
- plateau a puissance nominale entre `rated` et `cut_out`

5. Pertes
- pertes de sillage (`wake`)
- pertes de givre (`ice`)
- pertes directionnelles calculees mais non appliquees actuellement (ligne commentee).

6. Passage au parc complet
- `puissance_parc = puissance_turbine * nombre_eoliennes`

7. Sortie
- DataFrame avec:
  - `tempsdate`
  - `vitesse_vent_kmh`
  - `direction_vent`
  - `puissance`

## 3. Sens physique de `puissance`

- `puissance` est une puissance instantanee en kW a chaque pas de temps.
- Ce n'est pas une energie.

## 4. Calcul de l'energie sur une periode

Dans le `__main__` du module eolien:
- on agrège la puissance de tous les parcs
- on estime le pas de temps `dt` en heures
- on calcule l'energie:

`E_MWh = sum(P_kW * dt_h) / 1000`

Le resume final affiche:
- puissance installee totale (MW)
- puissance moyenne (MW)
- puissance de pointe (MW)
- energie totale (MWh, GWh)
- facteur de charge implicite (%)

## 5. Utilisation par d'autres modules

- Si un module a besoin d'une serie temporelle de production: utiliser la colonne `puissance`.
- Si un module a besoin d'un bilan annuel/periode: integrer `sum(P * dt)` pour obtenir une energie.

Rappel unites:
- kW / MW = puissance
- kWh / MWh / GWh = energie

## 6. Limites actuelles a connaitre

- `rated_speed` est approximee (moyenne de `cut_in` et `cut_out`).
- le facteur `ice` est simplifie et partiellement aleatoire.
- les pertes directionnelles ne sont pas encore appliquees dans la puissance finale.

## 7. Extension Weibull (mode hybride)

Le module supporte un mode comparatif avec coefficients Weibull par parc:
- `weibull_k` (forme)
- `weibull_c` (echelle, m/s)
- `weibull_ref_year`
- `weibull_sample_count`
- `weibull_updated_at`

### Objectif
- Ne pas remplacer la serie horaire actuelle.
- Calculer en parallele une puissance moyenne attendue Weibull pour benchmark.

### Formulation
- PDF Weibull:
  `f(v; k, c) = (k / c) * (v / c)^(k - 1) * exp(-(v / c)^k)`
- Puissance moyenne attendue turbine:
  `E[P] = integral(P(v) * f(v) dv)`
- Puissance parc:
  `E[P_parc] = E[P_turbine] * nombre_eoliennes`

`P(v)` est construit:
- depuis la vraie courbe turbine (`turbine_data["power_curve"]`) si disponible,
- sinon via le fallback `piecewise_power_curve`.

### Pipeline Weibull
1. Migration non destructive des colonnes:
   - `python -m harmoniq.scripts.eolien.migrate_add_weibull_columns`
2. Backfill auto (1 an de reference, par defaut 2024):
   - `python -m harmoniq.scripts.eolien.backfill_weibull_eolien --ref-year 2024`
3. Run module eolien:
   - `python -m harmoniq.modules.eolienne.__init__`

### Sorties comparatives
Le fichier `puissance_moyenne_parc_eolien.csv` contient maintenant:
- `weibull_k`, `weibull_c`
- `puissance_moyenne_horaire_mw`
- `puissance_moyenne_weibull_mw`
- `energie_horaire_mwh`
- `energie_weibull_mwh`
- `ecart_moyenne_mw`
- `ecart_moyenne_pct`

Interpretation:
- `puissance_moyenne_horaire_mw`: moyenne issue de la serie temporelle actuelle.
- `puissance_moyenne_weibull_mw`: moyenne theorique issue de la distribution de vent.
- `ecart_moyenne_pct`: difference relative (en valeur absolue) entre les deux.
