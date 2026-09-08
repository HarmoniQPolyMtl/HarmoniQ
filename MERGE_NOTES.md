# Notes de passation — branche `feature/reseau_v2`

Ce document explique où en est la branche, ce qui a été fait pour la remettre au
niveau de `main`, et comment l'intégrer proprement plus tard. Il est écrit pour
quelqu'un qui reprend le projet sans avoir suivi son historique.

## 1. Où en est la branche

`feature/reseau_v2` contient maintenant tout ce qui est sur `main` (jusqu'au
commit `d1c07c4`, qui est la PR #172), plus le nouveau module de simulation
réseau `reseau_v2`, plus trois commits d'intégration. Il ne manque donc plus rien
de `main` dans cette branche.

Comptage exact par rapport à `origin/main` : 20 commits d'avance et aucun commit
de retard. Sur ces 20 commits, 16 sont du contenu et 4 sont des commits de
fusion. Comme la branche contient déjà l'intégralité de `main`, un merge de la
branche vers `main` serait un fast-forward : git avancerait simplement `main`
jusqu'au bout de la branche, sans aucun conflit.

Le point de départ commun entre les deux branches est le commit `0b1f9de`.

Les trois commits d'intégration ajoutés récemment :

- `ca40f39` : la fusion de `main` dans la branche.
- `86dd99c` : une correction dans un fichier de test, décrite à la section 5.
- le troisième (celui qui ajoute ce fichier) : réorganisation et renommage des
  tests, ajout de `INSTALL_RESEAU_V2.md` et de ces notes.

Le renommage du dossier `reseau_bis` en `reseau_v2` a déjà été fait partout
(imports, tests, route REST). Les noms de classes comme `InfraReseauBis` et
`ReseauBisViz` ont volontairement été laissés tels quels, pour ne pas casser
d'éventuels scripts externes qui les utiliseraient.

## 2. Ce que le module `reseau_v2` apporte

Le nouveau module vit dans `harmoniq/modules/reseau_v2/`. Il remplace l'ancien
dispatch par ordre de mérite par une vraie optimisation linéaire du placement de
production (LP-OPF, via PyPSA et le solveur HiGHS), suivie d'un écoulement de
puissance en courant alternatif. Il est découpé en sept sous-modules à
responsabilité unique : `data_loader`, `network_builder`, `optimizer`,
`disaggregator`, `results`, `bus_connector` et `utils/reservoir_tracker`.

Le point d'entrée HTTP est `POST /reseau/production`, exposé par
`webserver/REST.py`. L'ancien module `reseau` reste actif en parallèle, rien
n'est retiré.

Le détail complet (architecture, hypothèses, bilans, pistes d'amélioration) est
dans le rapport de design, qui se trouve hors du dépôt, dans
`../_rapport_tooling/rapport_design_reseau_v2.docx`.

## 3. Ce que la fusion de `main` a apporté dans la branche

- **Base de données SQLite ou PostgreSQL.** Le fichier `db/engine.py` choisit le
  moteur au démarrage : base SQLite en mémoire quand les tests tournent
  (`HARMONIQ_TESTING`), fichier SQLite si `HARMONIQ_DB=sqlite`, sinon PostgreSQL,
  qui est le nouveau choix par défaut. Sous PostgreSQL, toutes les tables sont
  regroupées dans un schéma SQL nommé `reseau` (un espace de noms dans la base,
  comme un dossier ; par défaut on serait dans `public`). Le code s'y adresse en
  préfixant les tables : `reseau.bus` au lieu de `bus`. SQLite n'ayant pas de
  schémas, `engine.py` retire ce préfixe à la volée pour SQLite. Nouveaux
  fichiers : `db/demande_sqlite.py`, `scripts/install_postgres.py`,
  `scripts/sync_db.py`.
- **Scripts.** Les commandes `init_database.py`, `load_database.py` et
  `lance_webserver.py` acceptent maintenant `--sqlite`, `--postgre` et `--reset`.
  Les scripts liés à l'éolien ont été regroupés sous `scripts/eolien/`. Le script
  `scripts/add_indexes.py` a été supprimé.
- **Docker.** Ajout de `docker-compose.yml`, des `Dockerfile` (serveur, client,
  base), de `client/nginx.conf`, de `harmoniQ/.env` et de `pyrefly.toml`. Cela
  permet de lancer toute la pile (base + serveur + client) en une commande, pour
  le déploiement. Ce n'est pas nécessaire pour travailler en local.
- **Dépendances** (`pyproject.toml`) : ajout de `psycopg2`, `python-dotenv` et
  `email-validator`.
- **Frontend et documentation** : modifications de `map-service.ts`,
  `create-infra-modal`, `home-page.ts`, des fichiers d'environnement Angular et de
  plusieurs fichiers `.spec.ts`, ainsi que de `README.md`, `GUIDE_DEVELOPPEUR.md`
  et `SCRIPTS.md`.

## 4. Les conflits de la fusion et comment ils ont été résolus

Un seul conflit a demandé une résolution manuelle : `.gitignore`. On a gardé la
ligne `**/harmoniq.sql` venant de `main` et retiré le bloc qui ignorait
l'outillage de génération du rapport, puisque cet outillage a été sorti du dépôt.

Deux fichiers importants se sont fusionnés automatiquement, et le résultat a été
vérifié à la main :

- `db/schemas.py` : la version de `main` apporte le schéma `reseau`, le type
  `BigInteger` pour `volume_reservoir` et des clés étrangères en `String` ; la
  version de la branche apporte la colonne `nb_ligne` sur `Line` et les champs
  Pydantic `is_user_created`, `type_intrant` et `surface_roughness_z0_m`. Les deux
  ensembles de changements sont présents dans le fichier final.
- `scripts/init_database.py` : la version de `main` apporte les options
  `--sqlite / --postgre / --reset` et la création de l'utilisateur et de la base
  PostgreSQL ; la version de la branche apporte la lecture des CSV
  `bus_db_03_26.csv` et `lines_db_03_26.csv` (séparateur `;`, décimale `,`) et la
  colonne `nb_ligne`. Là aussi, tout est présent.

Les fichiers `db/engine.py`, `db/demande.py`, `scripts/load_database.py` et
`webserver/__init__.py` n'avaient pas été modifiés par la branche : ils ont donc
été pris tels quels depuis `main`.

## 5. Une régression corrigée pendant l'intégration (`86dd99c`)

La fusion de `main` a mis toutes les tables dans le schéma SQL `reseau`. Le
fichier de test qui ouvre la base SQLite de test
(`tests/test_reseau_v2_pipeline_db.py`, ex-`test_reseau_v2_audit.py`) créait sa
propre connexion sans retirer ce préfixe de schéma, alors que `db/engine.py` le
fait pour SQLite. Résultat : les requêtes demandaient la table `reseau.bus`, que
SQLite ne connaît pas, et six tests plantaient au démarrage.

La correction ajoute `schema_translate_map={"reseau": None}` sur la connexion de
ce fichier de test. Ce fichier est propre à la branche et n'a pas vocation à
partir dans `main`.

## 6. Le point de vigilance principal

Le module `reseau_v2` a été écrit et testé avec SQLite. Depuis la fusion, les
tables sont dans le schéma `reseau`. Le retrait automatique du préfixe rend ça
transparent dans le cas général, mais tout code qui ouvre sa propre connexion à
la base, en dehors de `db/engine.py`, doit y penser : `schema_translate_map` pour
SQLite, ou le bon `search_path` pour PostgreSQL. Avant une mise en production, il
faut faire tourner le module contre une vraie base PostgreSQL pour confirmer que
tout passe.

## 7. Comment lancer les tests

Les tests unitaires du module sont dans `tests/unit/` (comme ceux de l'ancien
module réseau) :

    pytest tests/unit/test_reseau_v2_dispatch_minimal.py
    pytest tests/unit/test_reseau_v2_bilan_energetique.py

Ils sont rapides et n'ont besoin d'aucune base : tout est monté en mémoire.

Le test qui vérifie le pipeline complet contre la vraie base de topologie est
dans `tests/` :

    pytest tests/test_reseau_v2_pipeline_db.py

Celui-là a besoin du fichier `harmoniq/db/db.sqlite`, construit par
`init-db -p --sqlite`. S'il est absent (cas de la CI), le fichier est ignoré au
lieu de faire échouer la suite.

Enfin, `harmoniq/scripts/diagnostic_reseau_v2.py` n'est pas un test : c'est un
outil de vérification manuelle qui lance une simulation complète et imprime un
rapport. On le lance avec
`python -m harmoniq.scripts.diagnostic_reseau_v2 --scenario_id 1` (il faut une
base peuplée avec au moins un scénario et `HARMONIQ_DB=sqlite`).

Dernier état vérifié en local, avec le venv en Python 3.11 : les tests du module
passent (21 au total avec `test_installation`), et une simulation réseau
complète fonctionne de bout en bout en SQLite depuis l'interface. Non vérifiés :
les tests unitaires du frontend (`npm test`) et un passage complet de
`diagnostic_reseau_v2.py` (qui demande une base avec des scénarios).

## 8. Plan d'intégration vers `main`

### Pourquoi ne pas tout fusionner d'un coup

Git le permettrait sans conflit (voir section 1), mais un seul merge ferait
tomber dans `main` environ 8000 lignes d'un bloc : un module sensible au schéma
de base et des changements frontend. C'est difficile à relire et difficile
d'annuler un seul morceau si quelque chose se comporte mal en production. On
préfère donc découper.

### Le flux

Tous les fichiers backend qui existent déjà sur `main` (`REST.py`, `schemas.py`,
`init_database.py`, `hydro/calcule.py`) ne diffèrent de `main` que par du
`reseau_v2`, rien d'autre ne s'y est glissé. On peut donc remplacer chaque
fichier par la version de la branche, sans trier ligne par ligne.

Le déroulé proposé, sur une seule branche d'intégration :

1. Partir de `main` à jour et créer la branche d'intégration :

        git checkout main
        git pull
        git checkout -b integration-reseau-v2

2. Amener les fichiers de l'étape 1 depuis `feature/reseau_v2`, puis committer :

        git checkout feature/reseau_v2 -- <chemin> <chemin> ...
        git commit -m "integ 1 : preparation base et correctifs"

3. Faire de même pour l'étape 2, puis l'étape 3, un commit par étape.
4. Pousser la branche et ouvrir une pull request vers `main`.

`git checkout <branche> -- <chemin>` copie le contenu de ce chemin (fichier ou
dossier) depuis la branche indiquée. On ne rejoue pas les commits de
`feature/reseau_v2` : son historique mélange plusieurs sujets dans un même commit.

Si l'équipe préfère des relectures plus courtes, chaque étape peut être sa propre
branche et sa propre pull request, au lieu de tout mettre sur
`integration-reseau-v2`.

### Étape 1 — préparation base et correctifs

Remplacer par la version de la branche :

- `harmoniQ/harmoniq/modules/hydro/calcule.py`
- `harmoniQ/harmoniq/db/schemas.py`
- `harmoniQ/harmoniq/scripts/init_database.py`
- `harmoniQ/harmoniq/db/CSVs/line_types.csv`

Ajouter (fichiers neufs) :

- `harmoniQ/harmoniq/db/CSVs/bus_db_03_26.csv`
- `harmoniQ/harmoniq/db/CSVs/lines_db_03_26.csv`

### Étape 2 — le module et sa route

Ajouter (neufs) :

- le dossier `harmoniQ/harmoniq/modules/reseau_v2/` en entier
- `harmoniQ/tests/unit/test_reseau_v2_dispatch_minimal.py`
- `harmoniQ/tests/unit/test_reseau_v2_bilan_energetique.py`
- `harmoniQ/tests/test_reseau_v2_pipeline_db.py`
- `harmoniQ/harmoniq/scripts/diagnostic_reseau_v2.py`

Remplacer par la version de la branche :

- `harmoniQ/harmoniq/webserver/REST.py` (elle ajoute la route
  `POST /reseau/production` et son cache ; les classes `ReseauSimulationPayload`
  et `SimulationInfraGroup` existent déjà sur `main`)

L'ancien module `reseau` reste en place à côté.

### Étape 3 — faire pointer l'interface web sur la nouvelle route

L'application Angular (`client/`) appelle aujourd'hui l'ancienne route réseau ;
avec ces fichiers elle appelle `POST /reseau/production`. Remplacer par la
version de la branche :

- `client/src/app/services/reseau-service.ts`
- `client/src/app/services/infrastrutures-service.ts`
- `client/src/app/services/infra-detail-service.ts`
- `client/src/app/services/graph-services/simulation-temporal-graph-service.ts`
- `client/src/app/pages/simulation-page/simulation-page.ts`
- `client/src/app/pages/docs-page/docs-page.ts`
- `client/src/app/data/documentation.data.ts`
- `client/src/app/components/quebec-map/quebec-map.html`
- `client/src/app/components/quebec-map/quebec-map.css`
- `client/src/app/components/commons/granularity-selector/granularity-selector.ts`

### Étape 4 — plus tard, retrait de l'ancien module

Une fois que `reseau_v2` a fait ses preuves : supprimer le dossier
`harmoniQ/harmoniq/modules/reseau/` et retirer à la main les quelques lignes de
`harmoniQ/harmoniq/webserver/REST.py` qui référencent encore l'ancien module.

### Après l'intégration

Une fois ces pull requests passées dans `main`, la branche `feature/reseau_v2`
n'a plus de raison d'exister : on peut la supprimer. Pour les évolutions
suivantes du réseau, on repart d'une branche neuve tirée de `main`, plutôt que de
continuer sur celle-ci.

Le backlog d'améliorations est détaillé dans la section 7 du rapport de design :
compensation réactive et AC-OPF, stabilité dynamique, critère N-1, stockage par
batterie, couverture de tests, et surtout l'autoproduction solaire résidentielle,
qui est déjà codée dans `harmoniq/modules/solaire/` mais pas encore branchée sur
le pipeline réseau. C'est le genre de fonctionnalité à reprendre dans une branche
neuve tirée de `main`.

## 9. Divers

- Le filigrane « API KEY REQUIRED » sur la carte vient du fond de carte CARTO
  (`map-service.ts`, tuiles `basemaps.cartocdn.com`). Il est identique sur `main`,
  purement visuel, et n'a aucun lien avec cette branche. Pour l'enlever : passer
  sur des tuiles OpenStreetMap sans clé, ou créer un compte CARTO.
- `INSTALL_RESEAU_V2.md` donne la procédure d'installation et de lancement à
  jour, en mode SQLite.
- L'outillage de génération du rapport (`generate_rapport.js`, `node_modules/`,
  le `.docx`) a été sorti du dépôt et rangé dans `../_rapport_tooling/`.
