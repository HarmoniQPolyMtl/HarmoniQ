# Weibull - Guide Complet (Module Eolien)

## 1. Objectif de ce document
Ce document explique exactement:

1. comment les coefficients Weibull sont calculés dans HarmoniQ,
2. comment les utiliser pour comparer une année cible (ex: 2024),
3. quelles commandes lancer selon que tu veux inclure ou exclure une année du fit,
4. comment interpréter les sorties.

Ce guide est aligné avec l'état actuel du code.

## 2. Rôle de Weibull dans le projet
Dans ce projet, la simulation principale des parcs éoliens reste le calcul horaire basé météo (`get_parc_power`).

Weibull sert à:

1. résumer la distribution des vents d'un parc avec deux paramètres (`k`, `c`),
2. estimer une production moyenne attendue à partir de cette distribution,
3. comparer cette estimation à la production obtenue avec les vents horaires réels.

Important:
1. Weibull n'est pas nécessaire pour faire tourner la simulation horaire.
2. Le pipeline sans Weibull reste intact et indépendant.

## 3. Rappel rapide sur les coefficients Weibull
`k` (shape):
1. contrôle la dispersion des vitesses de vent.
2. plus `k` est grand, plus les vitesses sont "concentrées" autour d'une zone.

`c` (scale, en m/s):
1. contrôle l'échelle globale des vitesses.
2. plus `c` est grand, plus la production moyenne attendue monte.

Exemple simple:
1. Parc A: `k=2.3`, `c=6.0` m/s.
2. Parc B: `k=2.3`, `c=7.5` m/s.
3. À courbe turbine identique, le parc B aura une production moyenne plus élevée.

## 4. Pipeline actuellement implémenté
## 4.1 Backfill des coefficients
Script:
`harmoniq/scripts/backfill_weibull_eolien.py`

Étapes:
1. charge ERA5 pour chaque parc et chaque année demandée,
2. convertit les vents en m/s,
3. ajuste à la hauteur du moyeu avec référence vent 100 m,
4. supprime le 29 février pour homogénéiser les années,
5. fit Weibull annuel,
6. fit Weibull saisonnier (`winter`, `spring`, `summer`, `autumn`) si demandé,
7. stocke en base:
`weibull_k`, `weibull_c`, `weibull_fit_details`, `weibull_ref_year_start`, `weibull_ref_year_end`, `weibull_granularity`, `weibull_weighting`.

## 4.2 Comparaison "sans Weibull vs avec Weibull"
Script:
`harmoniq/modules/eolienne/plot/plot_annual_with_without_weibull.py`

Étapes:
1. calcule la production horaire "sans Weibull" (référence),
2. calcule la production attendue Weibull avec les vraies power curves si disponibles,
3. construit une série "avec Weibull annual",
4. construit une série "avec Weibull seasonal" si coefficients saisonniers présents,
5. exporte CSV + PNG de comparaison.

Sorties:
1. `harmoniq/modules/eolienne/plot/production_annuelle_compare_weibull_v2.csv`
2. `harmoniq/modules/eolienne/plot/facteur_weibull_parc_v2.csv`
3. `harmoniq/modules/eolienne/plot/production_annuelle_compare_weibull_v2.png`

## 5. Commandes prêtes à l'emploi
## 5.1 Fit multi-années avec validation 2024 propre (recommandé)
Objectif:
1. entraîner sur 2015-2023,
2. tester ensuite sur 2024.

Commande fit:
```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.backfill_weibull_eolien --start-year 2015 --end-year 2023 --granularity seasonal --min-samples 500
```

Commande comparaison 2024:
```powershell
$env:MPLBACKEND='Agg'
.\venv\Scripts\python.exe -m harmoniq.modules.eolienne.plot.plot_annual_with_without_weibull --scenario-index 0 --baseline-year 2024
```

Contrôle attendu:
`Parcs dont le fit inclut l'annee de validation (2024): 0/43`

## 5.2 Fit incluant 2024 (pas une validation holdout)
Objectif:
maximiser la stabilité des coefficients, pas valider hors échantillon.

```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.backfill_weibull_eolien --start-year 2015 --end-year 2024 --granularity seasonal --min-samples 500
```

Puis:
```powershell
$env:MPLBACKEND='Agg'
.\venv\Scripts\python.exe -m harmoniq.modules.eolienne.plot.plot_annual_with_without_weibull --scenario-index 0 --baseline-year 2024
```

Cette fois, le compteur de fuite peut monter à `43/43`.

## 5.3 Mode annuel uniquement (sans saisonnalité)
```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.backfill_weibull_eolien --start-year 2015 --end-year 2023 --granularity annual --min-samples 500
```

Utilité:
1. baseline simple,
2. debug plus rapide.

## 5.4 Ajuster la contrainte d'échantillons
Par défaut `--min-samples 500`.

Exemple plus strict:
```powershell
.\venv\Scripts\python.exe -m harmoniq.scripts.eolien.backfill_weibull_eolien --start-year 2015 --end-year 2023 --granularity seasonal --min-samples 2000
```

## 6. Comment interpréter les fichiers
## 6.1 `production_annuelle_compare_weibull_v2.csv`
Colonnes principales:
1. `production_totale_sans_weibull_mw`
2. `production_totale_avec_weibull_annual_mw`
3. `production_totale_avec_weibull_seasonal_mw`

Lecture:
1. somme de colonne = énergie annuelle (MWh si pas horaire 1h),
2. comparer annual et seasonal pour voir l'effet de la saisonnalité.

## 6.2 `facteur_weibull_parc_v2.csv`
Colonnes utiles:
1. `weibull_mode`
2. `alpha_weibull_annual_profile`
3. `alpha_weibull_seasonal_profile`
4. `fit_includes_validation_year`
5. `weibull_error`

Lecture:
1. `fit_includes_validation_year=True` signifie fuite potentielle si tu valides cette même année.
2. `weibull_error` doit rester vide.

## 7. Exemple concret de stratégie de validation
Cas demandé: "simuler 2024 avec Weibull et comparer aux vrais vents 2024".

Plan recommandé:
1. fit sur 2015-2023,
2. simuler 2024 sans Weibull (référence réelle ERA5),
3. simuler 2024 avec Weibull (annual et seasonal),
4. comparer les énergies et les profils.

Pourquoi:
1. tu évites d'entraîner sur l'année test,
2. tu mesures la capacité de généralisation réelle de ton modèle Weibull.

## 8. Ce qui n'est pas impacté par Weibull
Le calcul standard sans Weibull n'est pas modifié:
1. source météo (ERA5/Open-Meteo),
2. conversion des unités,
3. calcul horaire `get_parc_power`,
4. résultats opérationnels de base sans facteur Weibull.

En clair:
1. supprimer ou désactiver Weibull n'empêche pas la simulation eolienne principale de tourner.

## 9. Bonnes pratiques
1. Utiliser `seasonal` pour des comparaisons annuelles réalistes.
2. Utiliser `annual` pour un benchmark simple.
3. Faire au moins une validation holdout (exclusion de l'année cible).
4. Vérifier systématiquement `fit_includes_validation_year` et `weibull_error`.
5. Garder la même année baseline (`--baseline-year`) quand tu compares plusieurs runs.

## 10. Dépannage rapide
`Parcs dont le fit inclut l'annee de validation (2024): 0/43`:
1. c'est normal en validation propre.
2. cela veut dire "pas de fuite".

`Parcs dont le fit inclut l'annee de validation (2024): 43/43`:
1. tu as inclus 2024 dans le fit.
2. utile pour calibration finale, pas pour validation holdout.

Écart annual/seasonal très faible:
1. possible si coefficients saisonniers proches,
2. vérifier que `weibull_mode=seasonal` pour les parcs,
3. vérifier les colonnes `alpha_weibull_winter/spring/summer/autumn`.


## 11. Section calcul pur: comment `k` et `c` sont trouves
Cette section decrit uniquement la partie mathematique/algorithmique.

### 11.1 Donnees d'entree du fit
Pour chaque parc:
1. on recupere la serie de vent ERA5 (par annee) sur la periode demandee,
2. on convertit `vitesse_vent_kmh` en m/s,
3. on ajuste a la hauteur du moyeu avec la loi log:
`v_hub = v_ref * ln(z_hub / z0) / ln(z_ref / z0)` avec `z_ref=100 m`,
4. on supprime le 29 fevrier,
5. on retire les valeurs non-finies et `v<=0`.

Resultat: un vecteur `v = {v_i}` de vitesses strictement positives en m/s.

### 11.2 Modele Weibull utilise
On suppose:
`V ~ Weibull(k, c)` avec `k>0`, `c>0`.

Densite:
`f(v; k, c) = (k/c) * (v/c)^(k-1) * exp(-(v/c)^k)` pour `v >= 0`.

### 11.3 Estimation principale: Maximum Likelihood (MLE)
Le code essaie d'abord un fit MLE (avec `loc=0` fixe).

Forme de la log-vraisemblance:
`L(k,c) = n*ln(k) - n*k*ln(c) + (k-1)*sum(ln(v_i)) - sum((v_i/c)^k)`.

Le solveur numerique retourne `(k_hat, c_hat)`:
1. `k_hat` = estimateur MLE de la forme,
2. `c_hat` = estimateur MLE de l'echelle.

Controle de validite applique:
1. `k_hat` et `c_hat` doivent etre finis,
2. `k_hat` dans un intervalle raisonnable (borne basse/haute du code),
3. `c_hat > 0`.

### 11.4 Fallback: methode des moments (si MLE echoue)
Si MLE echoue, le code passe en "moments":

1. calcul de la moyenne `mu` et de l'ecart-type `sigma`,
2. coefficient de variation cible: `cv_target = sigma / mu`,
3. resolution numerique de `k` avec:
`cv_model(k) = sqrt( Gamma(1+2/k)/Gamma(1+1/k)^2 - 1 )`,
4. on cherche `k` tel que `cv_model(k) = cv_target`,
5. puis `c = mu / Gamma(1+1/k)`.

La resolution se fait par recherche de racine (Brent).

### 11.5 Comptage d'echantillons et rejet
Le fit est refuse si:
1. `sample_count < min_samples`,
2. moments invalides (`mu<=0`, NaN, etc.),
3. parametres hors bornes.

Dans ce cas, le parc/saison est marque en echec avec message d'erreur.

### 11.6 Annual vs seasonal
Annual:
1. un seul fit sur tous les points de la fenetre.

Seasonal:
1. un fit annual (compatibilite),
2. puis 4 fits separes:
`winter`, `spring`, `summer`, `autumn`,
3. mapping mois -> saison:
`winter=(12,1,2)`, `spring=(3,4,5)`, `summer=(6,7,8)`, `autumn=(9,10,11)`.

### 11.7 Sortie stockee en base
Le JSON `weibull_fit_details` stocke au minimum:
1. `annual: {k, c, sample_count, method}`,
2. `seasonal: {winter:{...}, spring:{...}, summer:{...}, autumn:{...}}`,
3. metadata de fenetre (`ref_year_start`, `ref_year_end`, `weighting`).

### 11.8 Exemple numerique simple
Suppose qu'un parc a (apres pre-traitement):
1. `mu = 7.2 m/s`,
2. `sigma = 3.4 m/s`,
3. `cv_target = 3.4 / 7.2 = 0.4722`.

Le solveur moments peut trouver par exemple:
1. `k = 2.35`,
2. `c = mu / Gamma(1 + 1/2.35) = 8.10 m/s` (valeur illustrative).

Interpretation:
1. `k=2.35` -> regime de vent modere, pas ultra-chaotique,
2. `c=8.10` -> niveau de vent plutot bon pour la production.
