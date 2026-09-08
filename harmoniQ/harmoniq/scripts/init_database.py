import pandas as pd
from pathlib import Path
from pathlib import Path
import itertools
import argparse
import subprocess
import sys
import platform
import os
import getpass
from dotenv import load_dotenv
from tqdm import tqdm

# Load .env from the project root (harmoniQ/)
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE)
import sys

if "--sqlite" in sys.argv:
    os.environ["HARMONIQ_DB"] = "sqlite"

from harmoniq.scripts.install_postgres import check_postgres, get_psql_cmd, is_windows, can_connect_as_app_user, get_superuser_password, start_spinner, run_command

from harmoniq.db.engine import engine, get_db
from harmoniq.db.schemas import SQLBase
from harmoniq.db import schemas
from harmoniq.db import CRUD

id_gen = itertools.count(1)

CURRENT_DIR = Path(__file__).parent
CSV_DIR = CURRENT_DIR / ".." / "db" / "CSVs"
DB_DIR = CURRENT_DIR / ".." / "db"

# Credentials loaded from .env
PG_SUPERUSER = os.getenv("POSTGRES_SUPERUSER", "postgres")
PG_SUPERPASSWORD = os.getenv("POSTGRES_SUPERPASSWORD", "")
DB_USER = os.getenv("DB_USER", "harmoniq")
DB_PASSWORD = os.getenv("DB_PASSWORD", "harmoniq")
DB_NAME = os.getenv("DB_NAME", "harmoniq")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

def setup_database_and_user():
    """Crée l'utilisateur et la base de données si absents. Saute si déjà configurés."""
    if can_connect_as_app_user(DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME):
        print(f"L'utilisateur '{DB_USER}' et la base '{DB_NAME}' existent déjà. Aucune configuration requise.")
        return True

    print("Configuration de la base de données PostgreSQL...")
    superpassword = get_superuser_password(PG_SUPERPASSWORD, PG_SUPERUSER, DB_HOST, DB_PORT, "pour créer l'utilisateur et la base")

    env = os.environ.copy()
    env["PGPASSWORD"] = superpassword

    print(f"Création de l'utilisateur '{DB_USER}'...")
    create_user_cmd = [
        get_psql_cmd(), "-U", PG_SUPERUSER, "-h", DB_HOST, "-p", DB_PORT, "-c",
        f"CREATE USER {DB_USER} WITH PASSWORD '{DB_PASSWORD}';"
    ]
    subprocess.run(create_user_cmd, env=env, shell=is_windows(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    create_db_cmd = [
        get_psql_cmd(), "-U", PG_SUPERUSER, "-h", DB_HOST, "-p", DB_PORT, "-c",
        f"CREATE DATABASE {DB_NAME} OWNER {DB_USER};"
    ]
    print(f"Création de la base de données '{DB_NAME}'...")
    subprocess.run(create_db_cmd, env=env, shell=is_windows(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    grant_cmd = [
        get_psql_cmd(), "-U", PG_SUPERUSER, "-h", DB_HOST, "-p", DB_PORT, "-c",
        f"GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};"
    ]
    subprocess.run(grant_cmd, env=env, shell=is_windows(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True



def init_db(reset=False, is_sqlite=False):
    """Initialise la base de données avec le fichier.sql"""
    if is_sqlite:
        from harmoniq import DB_PATH
        print(f"Initialisation de la base SQLite à {DB_PATH}")
        if reset:
            print("Réinitialisation de la base de données SQLite (suppression du fichier)...")
            try:
                os.remove(DB_PATH)
                print("Ancien fichier DB supprimé.")
            except FileNotFoundError:
                pass
        
        print("Création du schéma dans SQLite...")
        SQLBase.metadata.create_all(engine)
        print("Schéma SQLite créé avec succès.")
        return True

    global PG_SUPERPASSWORD
    if not check_postgres(PG_SUPERPASSWORD):
        print("Erreur critique: PostgreSQL n'a pas pu être installé ou configuré.")
        sys.exit(1)

    setup_database_and_user()

    print("Initialisation de la base de données...")
    sql_file = DB_DIR / "harmoniq.sql"

    if not sql_file.exists():
        print("harmoniq.sql introuvable. Téléchargement depuis Hugging Face...")
        sql_file.parent.mkdir(parents=True, exist_ok=True)

        url = "https://huggingface.co/datasets/byacine121/harmoniq/resolve/main/harmoniq.sql"
        
        import requests, tempfile, shutil
        tmp_file = Path(tempfile.gettempdir()) / "harmoniq_download.sql"
        tmp_file.unlink(missing_ok=True)

        print(f"Connexion à {url}...")
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))

            with open(tmp_file, "wb") as f:
                with tqdm(total=total_size, unit="B", unit_scale=True, unit_divisor=1024, desc="Téléchargement") as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))
                        
            print("Déplacement du fichier vers le projet...")
            shutil.move(str(tmp_file), str(sql_file))
            print("Téléchargement terminé.")
        except Exception as e:
            print(f"Erreur : le téléchargement a échoué. {e}", file=sys.stderr)
            tmp_file.unlink(missing_ok=True)
            return False

    # Build the superuser env once (needed for reset + load + grants)
    PG_SUPERPASSWORD = get_superuser_password(PG_SUPERPASSWORD, PG_SUPERUSER, DB_HOST, DB_PORT, "pour importer les données")
    env_pg = os.environ.copy()
    env_pg["PGPASSWORD"] = PG_SUPERPASSWORD

    if reset:
        print("Réinitialisation de la base de données...")
        reset_cmd = [
            get_psql_cmd(), "-U", PG_SUPERUSER, "-h", DB_HOST, "-d", DB_NAME, "-p", DB_PORT, "-c",
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public; DROP SCHEMA IF EXISTS reseau CASCADE; DROP SCHEMA IF EXISTS demande CASCADE;"
        ]
        run_command(reset_cmd, env=env_pg)

    # ── Stream harmoniq.sql to psql with a progress bar ────────────────────
    file_size = sql_file.stat().st_size
    psql_cmd = [get_psql_cmd(), "-U", PG_SUPERUSER, "-h", DB_HOST, "-d", DB_NAME, "-p", DB_PORT]

    load_success = False
    try:
        proc = subprocess.Popen(
            psql_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env_pg,
            shell=False,
        )
        with open(sql_file, "rb") as f:
            with tqdm(
                total=file_size,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc="  harmoniq.sql",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]",
                colour="cyan",
            ) as bar:
                chunk_size = 256 * 1024  # 256 KB
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    try:
                        proc.stdin.write(chunk)
                        proc.stdin.flush()
                    except OSError:
                        break
                    bar.update(len(chunk))

        try:
            proc.stdin.close()
        except OSError:
            pass

        t, _done = start_spinner("Finalisation (index, sequences...)")
        proc.wait()
        _done.set()
        t.join()

        stderr_output = proc.stderr.read().decode('utf-8', errors='replace')
        if proc.returncode != 0:
            print(f"\n[Erreur psql] Code {proc.returncode}:")
            print(stderr_output.strip())
            with open("psql_error.txt", "w", encoding="utf-8") as err_f:
                err_f.write(stderr_output)
            
        load_success = proc.returncode == 0
    except Exception as e:
        print(f"Erreur lors du chargement: {e}")
        load_success = False

    if load_success:
        print("Chargement terminé. Attribution des permissions...")
        # Three separate -c calls to avoid concatenation issues
        for grant_sql in [
            f"GRANT ALL ON SCHEMA public, reseau, demande TO {DB_USER};",
            f"GRANT ALL ON ALL TABLES IN SCHEMA public, reseau, demande TO {DB_USER};",
            f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public, reseau, demande TO {DB_USER};",
        ]:
            subprocess.run(
                [get_psql_cmd(), "-U", PG_SUPERUSER, "-h", DB_HOST, "-d", DB_NAME, "-p", DB_PORT, "-c", grant_sql],
                env=env_pg, shell=is_windows(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        print("Permissions accordées.")
    else:
        print("Le chargement de la base a échoué.")

    return load_success


def fill_thermique():
    df = pd.read_csv(
        CSV_DIR / "centrale_thermique.csv", delimiter=";", encoding="utf-8"
    )

    db = next(get_db())

    for _, row in df.iterrows():
        existing = db.query(schemas.Thermique).filter(schemas.Thermique.nom == row["nom"]).first()
        if existing:
            continue

        CRUD.create_thermique(
            db,
            schemas.ThermiqueBase(
                id=next(id_gen),
                nom=row["nom"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                puissance_nominal=row["puissance_MW"],
                type_intrant=row["type"],
                semaine_maintenance=row["semaine_maintenance"],
            ),
        )
        print(f"Centrale {row['nom']} ajoutée à la base de données")


def fill_solaire():
    df = pd.read_csv(
        CSV_DIR / "centrales_solaires.csv", delimiter=";", encoding="utf-8"
    )

    db = next(get_db())

    for _, row in df.iterrows():
        existing = db.query(schemas.Solaire).filter(schemas.Solaire.nom == row["nom"]).first()
        if existing:
            continue
            
        CRUD.create_solaire(
            db,
            schemas.SolaireBase(
                id=next(id_gen),
                nom=row["nom"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                puissance_nominal=row["puissance_nominal_MW"],
                angle_panneau=row["angle_panneau"],
                orientation_panneau=row["orientation_panneau"],
                nombre_panneau=row["nombre_panneau"],
            ),
        )
        print(f"Centrale solaire {row['nom']} ajoutée à la base de données")


def fill_parc_eoliennes():
    db = next(get_db())

    try:
        station_df = pd.read_excel(CSV_DIR / "Wind_Turbine_Database_FGP.xlsx")
    except Exception as e:
        print(f"Erreur lors de l'ouverture du fichier Excel: {e}")
        return

    station_df = station_df[station_df["Province_Territoire"] == "Québec"]

    project_names = station_df["Project Name"].unique()
    for project_name in project_names:
        existing = db.query(schemas.EolienneParc).filter(schemas.EolienneParc.nom == project_name).first()
        if existing:
            continue
            
        try:
            project_df = station_df[station_df["Project Name"] == project_name]
            average_lat = project_df["Latitude"].mean()
            average_lon = project_df["Longitude"].mean()
            project_capacity = project_df["Total Project Capacity (MW)"].unique()
            if len(project_capacity) > 1:
                print(f"Projet {project_name} a plusieurs capacités, c'est suspect")

            project_capacity = project_capacity[0]

            for _, row in project_df.iterrows():
                hub_height = row["Hub Height (m)"]

                if isinstance(hub_height, str) and "-" in hub_height:
                    hub_height = sum(map(int, hub_height.split("-"))) / 2
                    project_df["Hub Height (m)"] = project_df["Hub Height (m)"].replace(
                        row["Hub Height (m)"], hub_height
                    )

            eolienne_parc = schemas.EolienneParcBase(
                id=next(id_gen),
                nom=project_name,
                latitude=average_lat,
                longitude=average_lon,
                nombre_eoliennes=len(project_df),
                capacite_total=project_capacity,
                hauteur_moyenne=project_df["Hub Height (m)"].mean(),
                modele_turbine=project_df["Model"].unique()[0],
                puissance_nominal=project_df["Turbine Rated Capacity (kW)"].unique()[0],
            )

            CRUD.create_eolienne_parc(db, eolienne_parc)
            print(f"Projet {project_name} ajouté à la base de données")
        except Exception as e:
            print(f"Erreur lors de l'ajout du projet {project_name}")
            print(e)


def fill_hydro():
    """Remplit la table bus à partir du fichier CSV"""
    db = next(get_db())

    file_path = CSV_DIR / "Info_Barrages.csv"
    barrages_df = pd.read_csv(file_path)

    count = 0
    for _, row in barrages_df.iterrows():
        existing = (
            db.query(schemas.Hydro).filter(schemas.Hydro.nom == row["Nom"]).first()
        )
        if existing:
            continue

        db_hydro = schemas.HydroBase(
            id=next(id_gen),
            nom=row["Nom"],
            puissance_nominal=row["Puissance_Installee_MW"],
            type_barrage=row["Type"],
            latitude=row["Longitude"],
            longitude=row["Latitude"],
            hauteur_chute=row["Hauteur_de_chute_m"],
            debits_nominal=row["Debits_nom_m3s"],
            modele_turbine=row["Type_turbine"],
            nb_turbines=row["Nb_turbines"],
            nb_turbines_maintenance=row["nb_turbines_maintenance"],
            volume_reservoir=row["Volume_reservoir"],
            id_HQ=row["id_HQ"],
            maintenance=row.get("Maintenance"),
            regulation=row.get("Regulation"),
        )
        count += 1
        CRUD.create_hydro(db, db_hydro)
        print(f"Barrage '{db_hydro.nom}' ajouté à la base de données")

    if count > 0:
        print(f"{count} barrages ajoutés à la base de données")


def fill_line_types():
    """Remplit la table line_type à partir du fichier CSV"""
    from harmoniq.db.schemas import LineType
    db = next(get_db())

    file_path = CSV_DIR / "line_types.csv"
    line_types_df = pd.read_csv(file_path)

    count = 0
    for _, row in line_types_df.iterrows():
        existing = db.query(LineType).filter(LineType.name == row["name"]).first()
        if existing:
            continue

        db_line_type = schemas.LineTypeBase(
            name=row["name"],
            f_nom=int(row["f_nom"]),
            r_per_length=float(row["r_per_length"]),
            x_per_length=float(row["x_per_length"]),
        )

        CRUD.create_line_type(db, db_line_type)
        count += 1
        print(f"Type de ligne '{db_line_type.name}' ajouté à la base de données")

    if count > 0:
        print(f"{count} types de ligne ajoutés à la base de données")


BUS_RESEAU_TYPE_MAP = {
    'Bus': 'Transport',
    'Eolienne': 'Éoliennes',
    'Solaire': 'Solaire',
    'Thermique': 'Thermique',
    'Reservoir': 'Hydroélectrique',
    'Fil de l\'eau': 'Hydroélectrique',
    'Conso': 'Consommation',
}

LINE_RESEAU_TYPE_MAP = {
    'Bus': 'Transport',
    'Eolienne': 'Éoliennes',
    'Solaire': 'Solaire',
    'Thermique': 'Thermique',
    'Hydro': 'Hydroélectrique',
    'Conso': 'Consommation',
}

BUS_TYPE_CSV_MAP = {
    'Bus': 'ligne',
    'Eolienne': 'prod',
    'Solaire': 'prod',
    'Thermique': 'prod',
    'Reservoir': 'prod',
    'Fil de l\'eau': 'prod',
    'Conso': 'conso',
}


def fill_buses():
    """Remplit la table bus à partir du fichier CSV bus_db_03_26.csv"""
    db = next(get_db())

    file_path = CSV_DIR / "bus_db_03_26.csv"
    buses_df = pd.read_csv(file_path, sep=";", decimal=",")

    count = 0
    for _, row in buses_df.iterrows():
        bus_id = str(row['id'])
        display_name = str(row['name'])
        existing = db.query(schemas.Bus).filter(schemas.Bus.name == bus_id).first()
        if existing:
            continue

        csv_type_col = row.get('type', 'line')  # 'line', 'prod', 'conso'
        csv_category = row.get('type.1', 'Bus')  # 'Bus', 'Eolienne', etc.
        reseau_type = BUS_RESEAU_TYPE_MAP.get(csv_category, 'Transport')

        # Map CSV type values to BusType enum values
        bus_type_val = csv_type_col
        if bus_type_val == 'line':
            bus_type_val = 'ligne'

        db_bus = schemas.BusCreate(
            name=bus_id,
            display_name=display_name,
            v_nom=int(row['v_nom']),
            type=schemas.BusType(bus_type_val),
            x=float(row['y']),
            y=float(row['x']),
            control=schemas.BusControlType(row['control']),
            reseau_type=reseau_type,
        )

        count += 1
        CRUD.create_bus(db, db_bus)
        print(f"Bus '{db_bus.name}' ajouté à la base de données")

    if count > 0:
        print(f"{count} bus ajoutés à la base de données")


def fill_lines():
    """Remplit la table line à partir du fichier lines_db_03_26.csv"""
    db = next(get_db())

    file_path = CSV_DIR / "lines_db_03_26.csv"
    lines_df = pd.read_csv(file_path, sep=";", decimal=",")

    count = 0
    for _, row in lines_df.iterrows():
        try:
            line_name = row['name']
            existing = (
                db.query(schemas.Line).filter(schemas.Line.name == line_name).first()
            )
            if existing:
                continue

            bus_from = (
                db.query(schemas.Bus).filter(schemas.Bus.name == row["bus0"]).first()
            )
            if not bus_from:
                print(
                    f"Bus de départ {row['bus0']} non trouvé pour la ligne {line_name}"
                )
                continue

            bus_to = (
                db.query(schemas.Bus).filter(schemas.Bus.name == row["bus1"]).first()
            )
            if not bus_to:
                print(
                    f"Bus d'arrivée {row['bus1']} non trouvé pour la ligne {line_name}"
                )
                continue

            line_type_name = row.get('type.1', '735kV_line')  # the actual line type
            line_type = (
                db.query(schemas.LineType)
                .filter(schemas.LineType.name == line_type_name)
                .first()
            )
            if not line_type:
                print(
                    f"Type de ligne {line_type_name} non trouvé pour la ligne {line_name}"
                )
                continue

            csv_category = row['type']  # 'Bus', 'Eolienne', 'Solaire', etc.
            reseau_type = LINE_RESEAU_TYPE_MAP.get(csv_category, 'Transport')

            nb_ligne = int(row["nb_ligne"])

            db_line = schemas.LineCreate(
                name=line_name,
                bus0=row["bus0"],
                bus1=row["bus1"],
                type=line_type_name,
                length=float(row["length"]),
                capital_cost=float(row["capital_cost"]),
                s_nom=float(row["s_nom"]),
                nb_ligne=nb_ligne,
                reseau_type=reseau_type,
            )
            count += 1
            CRUD.create_line(db, db_line)
            print(f"Ligne '{db_line.name}' ajouté à la base de données")
        except Exception as e:
            print(f"Erreur lors de l'ajout de la ligne {row['name']}: {e}")

    if count > 0:
        print(f"{count} lignes ajoutées à la base de données")


def check_if_empty():
    db = next(get_db())
    tables = [
        schemas.EolienneParc,
        schemas.Hydro,
        schemas.Bus,
        schemas.Line,
        schemas.LineType,
        schemas.Thermique,
        schemas.Solaire,
    ]

    for table in tables:
        if db.query(table).first():
            return False

    return True


def fill_network():
    """Remplit les tables du réseau électrique (line_type, bus, line)"""
    print("Collecte des types de lignes...")
    fill_line_types()

    print("Collecte des bus...")
    fill_buses()

    print("Collecte des lignes...")
    fill_lines()


def populate_db():
    print("Collecte des éoliennes")
    fill_parc_eoliennes()

    print("Collecte des données du réseau électrique :")
    fill_network()

    print("Collecte des données du réseau hydro :")
    fill_hydro()

    print("Collecte des centrales thermiques")
    fill_thermique()

    print("Collecte des centrales solaires")
    fill_solaire()


def main():
    parser = argparse.ArgumentParser(description="Initialise la base de données")
    parser.add_argument(
        "-t", "--test", action="store_true", help="Utilise la base de données de test"
    )
    parser.add_argument(
        "-R", "--reset", action="store_true", help="Réinitialise la base de données"
    )
    parser.add_argument(
        "-f",
        "--fill",
        action="store_true",
        help="Remplit la base de données si elle est vide",
    )
    parser.add_argument(
        "-p",
        "--populate",
        action="store_true",
        help="Remplit la base de données avec des données de référence",
    )
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--postgre", action="store_true", default=True, help="Utilise PostgreSQL (par défaut)")
    group.add_argument("--sqlite", action="store_true", help="Utilise SQLite")

    args = parser.parse_args()

    print("Initialisation de la base de données")
    init_db(args.reset, is_sqlite=args.sqlite)

    if args.fill:
        if check_if_empty():
            populate_db()
        else:
            print("La base de données est déjà remplie")

    if args.populate:
        populate_db()


if __name__ == "__main__":
    main()

