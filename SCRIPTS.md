# Scripts HarmoniQ

## Scripts principaux

### `launch-app` — Lancer le serveur web

Démarre le serveur FastAPI (via Uvicorn) et le client Angular.

```bash
launch-app           # Build le client puis lance le serveur en mode production, utilise postgre en tant que base de donnée par défaut
launch-app --debug   # Lance le serveur avec rechargement automatique + Angular dev server (ng serve)
launch-app --profile # Active le profiler de performance
launch-app --postgre # Lance le serveur en utilisant postgre en tant que base de donnée
launch-app --sqlite  # Lance le serveur en utilisant sqlite en tant que base de donnée
```

**Options :**

| Option          | Description                                              |
|-----------------|----------------------------------------------------------|
| `--debug`       | Mode debug : active les logs détaillés, le rechargement automatique d'Uvicorn et le serveur de développement Angular avec proxy |
| `--profile`     | Mode profiler : instrumente les modules pour mesurer les performances |
| `--host`        | Adresse IP du serveur (défaut : `0.0.0.0`)               |
| `--port`        | Port du serveur (défaut : `5000`)                         |
| `--workers`     | Nombre de processus de travail Uvicorn (défaut : `1`)     |
| `--skip-build`  | Ne pas reconstruire le client avant de lancer le serveur  |

Une fois lancé, l'application est accessible sur **http://localhost:5000**.
Excepté en mode debug, où le client est accessible sur **http://localhost:4200**.

---

### `init-db` — Initialiser la base de données

Le projet supporte à la fois **SQLite** et **PostgreSQL**. Par défaut, toutes les commandes ciblent **PostgreSQL**.

- **Peupler la base (avec les CSVs de référence)** :
```bash
init-db -p              # Met à jour la base de donnée PostgreSQL
init-db -p --postgre    # Met à jour la base de donnée PostgreSQL
init-db -p --sqlite     # Met à jour la base de donnée SQLite (db.sqlite)
```

- **Réinitialiser la base** :
```bash
init-db --reset             # Réinitialise la table du réseau (reseau) dans PostgreSQL
init-db --reset --postgre   # Réinitialise la table du réseau dans PostgreSQL
init-db --reset --sqlite    # Réinitialise complètement la base de donnée SQLite (db.sqlite)
```

**Options :**

| Option              | Description                                                   |
|---------------------|---------------------------------------------------------------|
| `-p`, `--populate`  | Remplit la base avec les données de référence (CSVs et Excel) |
| `-f`, `--fill`      | Remplit la base uniquement si elle est vide                    |
| `-R`, `--reset`     | Supprime toutes les tables avant de les recréer               |
| `-t`, `--test`      | Utilise la base de données de test                            |
| `--postgre`         | Force l'utilisation de PostgreSQL (par défaut)                |
| `--sqlite`          | Force l'utilisation de SQLite                                 |

Les données de référence proviennent des fichiers dans `harmoniq/db/CSVs/` et incluent : parcs éoliens, barrages hydro, centrales thermiques, centrales solaires, bus et lignes du réseau électrique.

---

### `load-db` — Télécharger la base de données

Télécharge la base de données depuis Hugging Face. PostgreSQL est la destination par défaut.

```bash
load-db             # Télécharge la base de données PostgreSQL
load-db --postgre   # Télécharge la base de données PostgreSQL
load-db --sqlite    # Télécharge la base de données SQLite (demande.db)
```

---
