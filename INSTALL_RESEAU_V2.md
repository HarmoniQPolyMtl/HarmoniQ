# Installation de la branche `feature/reseau_v2`

Cette branche = `main` + le module de simulation réseau `reseau_v2` (LP-OPF).
Elle contient la totalité de `main` (support PostgreSQL/SQLite, Docker, etc.).

## Prérequis

- **Python 3.11 recommandé** (3.8–3.11 supporté) — `python --version`.
  numpy/pandas sont épinglés pour 3.11 ; Python 3.12+ peut casser certains modules.
- **Git** — `git --version`

## 1. Cloner et basculer sur la branche

```bash
git clone https://github.com/VortexOsxo/HarmoniQ.git
cd HarmoniQ
git checkout feature/reseau_v2
cd harmoniQ
```

## 2. Environnement virtuel

**Linux / macOS**
```bash
python3.11 -m venv venv
source venv/bin/activate
```

**Windows**
```powershell
py -3.11 -m venv venv
.\venv\Scripts\activate
```

> Vérifier : `python --version` doit afficher 3.11.x (sinon le venv n'est pas actif).
> Un venv est lié à son chemin absolu : si tu déplaces/renommes le dossier du projet,
> recrée-le (`rm -rf venv` puis les commandes ci-dessus).

## 3. Dépendances

```bash
pip install -e ".[dev]"
```

Installe entre autres `psycopg2`, `python-dotenv`, `email-validator` (requis depuis
l'intégration de `main`). **À relancer après chaque `git pull`** (les versions bougent).

## 4. Base de données — choisir SQLite ou PostgreSQL

Depuis l'intégration de `main`, **PostgreSQL est le backend par défaut**. Pour le
développement local, **SQLite est le plus simple** : un seul fichier, aucun serveur.

### Option A — SQLite (recommandé en local)

```bash
load-db --sqlite      # télécharge db.sqlite depuis Google Drive
init-db -p --sqlite   # crée le schéma + données de référence (bus, lignes, types...)
```

Pour ne pas répéter `--sqlite` à chaque commande :
```bash
export HARMONIQ_DB=sqlite          # Linux/macOS
$env:HARMONIQ_DB = "sqlite"        # Windows PowerShell
```

> Si `load-db` échoue : télécharger manuellement
> [ici](https://drive.google.com/file/d/1AChv-YwvDrE-nlYdT_aRSumKc571Cqxk/view?usp=sharing)
> et placer le fichier dans `harmoniQ/harmoniq/db/`.

### Option B — PostgreSQL

```bash
init-db -p            # utilise .env (harmoniQ/.env) ; crée user + base si besoin
```

Nécessite un serveur PostgreSQL local (port 5432). `harmoniQ/.env` porte les
identifiants. Voir aussi `scripts/install_postgres.py` et `docker-compose.yml`
(stack complète db + serveur + client).

## 5. Lancer l'application

```bash
launch-app --debug --sqlite      # ou sans --sqlite si PostgreSQL est configuré
```

- Backend : http://localhost:5000
- En `--debug`, le client Angular est aussi lancé : **UI sur http://localhost:4200**

Ensuite : créer un scénario dans l'UI (la table `scenario` est vide après un
`init-db` neuf), puis lancer une simulation réseau.

---

## Relance ultérieure

```bash
cd HarmoniQ/harmoniQ
source venv/bin/activate            # ou .\venv\Scripts\activate
export HARMONIQ_DB=sqlite           # si tu ne l'as pas mis en permanent
launch-app --debug --sqlite
```

Après un `git pull` sur la branche :
```bash
git pull origin feature/reseau_v2
pip install -e ".[dev]"            # deps peuvent avoir changé
```
Si une erreur SQL du type "no such column" ou "OperationalError" apparaît au
lancement, c'est que le schéma de la base a changé : supprimer
`harmoniq/db/db.sqlite`, puis relancer `init-db -p --sqlite`.

---

## Tests

```bash
pytest tests/unit/test_reseau_v2_dispatch_minimal.py tests/unit/test_reseau_v2_bilan_energetique.py
pytest tests/test_reseau_v2_pipeline_db.py
pytest tests/test_installation.py
```

Les tests forcent une base SQLite en mémoire (via `conftest.py`) : pas besoin de
`--sqlite`. Le fichier `tests/test_reseau_v2_pipeline_db.py` a en plus besoin de
`harmoniq/db/db.sqlite` (construit par `init-db -p --sqlite`) ; s'il est absent,
ce fichier est simplement ignoré.

Pour une vérification manuelle de bout en bout, il y a aussi
`python -m harmoniq.scripts.diagnostic_reseau_v2 --scenario_id <id>`. Ce n'est pas
un test automatique : il lance une simulation complète et imprime un rapport. Il
demande une base peuplée avec au moins un scénario et `HARMONIQ_DB=sqlite`.
