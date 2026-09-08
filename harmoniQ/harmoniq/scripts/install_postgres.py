import os
import sys
import getpass
import subprocess
import platform
import urllib.request
import threading
import itertools
import time as _time
from pathlib import Path

def is_mac():
    return platform.system() == "Darwin"

def is_windows():
    return platform.system() == "Windows"

def get_psql_path():
    if not is_windows():
        return "psql"
        
    try:
        subprocess.run(["psql", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, shell=True)
        return "psql"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
        
    base_dir = Path("C:/Program Files/PostgreSQL")
    if base_dir.exists():
        for version_dir in sorted(base_dir.iterdir(), reverse=True):
            if version_dir.is_dir():
                psql_path = version_dir / "bin" / "psql.exe"
                if psql_path.exists():
                    return str(psql_path)
    return "psql"

def get_psql_cmd():
    return get_psql_path()

def run_command(cmd, env=None, check=True):
    try:
        subprocess.run(cmd, check=check, env=env, shell=is_windows())
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de: {' '.join(cmd)}")
        print(e)
        return False

def check_postgres(superpassword: str):
    """Vérifie si PostgreSQL est installé. Sinon, l'installe."""
    print("Vérification de l'installation de PostgreSQL...")
    try:
        subprocess.run([get_psql_cmd(), "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, shell=is_windows())
        print("PostgreSQL est trouvé.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("PostgreSQL n'est pas installé ou `psql` n'est pas trouvé.")

        if is_mac():
            print("Installation de PostgreSQL via Homebrew...")
            success = run_command(["brew", "install", "postgresql@17"])
            if success:
                print("Démarrage du service PostgreSQL...")
                run_command(["brew", "services", "start", "postgresql@17"])
            return success
        elif is_windows():
            print("Téléchargement de l'installateur PostgreSQL 17...")
            installer_url = "https://get.enterprisedb.com/postgresql/postgresql-17.4-1-windows-x64.exe"
            installer_path = Path.home() / "Downloads" / "postgresql-installer.exe"
            
            try:
                urllib.request.urlretrieve(installer_url, installer_path)
            except Exception as e:
                print(f"Erreur lors du téléchargement de l'installateur: {e}")
                return False

            print("Lancement de l'installateur PostgreSQL avec les droits d'administrateur...")
            print("Installation de PostgreSQL en cours (environ 7-8 minutes)...")
            
            install_args = f'--mode unattended --unattendedmodeui none --prefix "C:\\Program Files\\PostgreSQL\\17" --datadir "C:\\Program Files\\PostgreSQL\\17\\data" --superpassword "{superpassword}"'
            ps_command = f'Start-Process -FilePath "{installer_path}" -ArgumentList \'{install_args}\' -Verb RunAs -Wait'
            
            success = run_command(["powershell", "-Command", ps_command])
            
            new_psql_path = get_psql_cmd()
            
            if success and new_psql_path != "psql":
                print("Installation de PostgreSQL réussie.")
                return True
            else:
                print("L'installation de PostgreSQL a échoué ou a été annulée.")
                return False
        else:
            return False

def can_connect_as_app_user(db_user, db_password, db_host, db_port, db_name) -> bool:
    """Teste si on peut se connecter en tant qu'utilisateur applicatif."""
    test_cmd = [
        get_psql_cmd(), "-U", db_user, "-h", db_host, "-p", db_port, "-d", db_name, "-c", "SELECT 1;"
    ]
    env = os.environ.copy()
    env["PGPASSWORD"] = db_password
    result = subprocess.run(
        test_cmd, env=env, shell=is_windows(),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def get_superuser_password(pg_superpassword, pg_superuser, db_host, db_port, reason="pour continuer") -> str:
    """Retourne le mot de passe superutilisateur depuis .env ou le demande interactivement s'il est invalide."""
    
    def test_password(pwd):
        env = os.environ.copy()
        if pwd:
            env["PGPASSWORD"] = pwd
        cmd = [get_psql_cmd(), "-U", pg_superuser, "-h", db_host, "-p", db_port, "-c", "SELECT 1;"]
        res = subprocess.run(cmd, env=env, shell=is_windows(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0

    if test_password(pg_superpassword):
        return pg_superpassword

    print()
    if pg_superpassword:
        print(f"Le mot de passe '.env' pour le superutilisateur '{pg_superuser}' est incorrect.")
    else:
        print(f"Le mot de passe du superutilisateur PostgreSQL ('{pg_superuser}') est requis {reason}.")

    while True:
        pwd = getpass.getpass(f"Entrez le mot de passe pour '{pg_superuser}': ")
        if not pwd:
            print("Action annulée.")
            sys.exit(1)
        if test_password(pwd):
            return pwd
        print("Mot de passe incorrect. Veuillez réessayer.")

def start_spinner(message: str):
    """Démarre une animation d'attente dans la console."""
    done_event = threading.Event()
    def _spin():
        frames = ["|  ", "/  ", "-  ", "\\  "]
        for f in itertools.cycle(frames):
            if done_event.is_set():
                break
            sys.stdout.write(f"\r  {message} {f}")
            sys.stdout.flush()
            _time.sleep(0.12)
        sys.stdout.write("\r" + " " * 50 + "\r")  # clear the line
        sys.stdout.flush()
    t = threading.Thread(target=_spin, daemon=True)
    t.start()
    return t, done_event

