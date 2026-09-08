import argparse
import requests
import sys
from pathlib import Path

from harmoniq import DEMANDE_PATH

HF_DATASET_BASE_URL = "https://huggingface.co/datasets/byacine121/harmoniq/resolve/main"

def download_file_with_progress(url: str, output_path: str):
    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = None

    print(f"Connexion à {url}...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        with open(output_path, "wb") as f:
            if tqdm is not None:
                with tqdm(total=total_size, unit="B", unit_scale=True, unit_divisor=1024, desc="Téléchargement") as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))
            else:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print(f"Erreur lors du téléchargement: {e}", file=sys.stderr)
        sys.exit(1)

def download_db(is_sqlite=False):
    if is_sqlite:
        filename = "demande.db"
        output_path = str(DEMANDE_PATH)
        print(f"Téléchargement de la base de données SQLite DEMANDE vers {output_path}...")
    else:
        filename = "harmoniq.sql"
        output_path = str(Path(DEMANDE_PATH).parent / filename)
        print(f"Téléchargement du dump PostgreSQL vers {output_path}...")

    url = f"{HF_DATASET_BASE_URL}/{filename}"
    download_file_with_progress(url, output_path)

def main():
    parser = argparse.ArgumentParser(description="Télécharge la base de données")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--postgre", "-p", action="store_true", default=True, help="Télécharge la base de données PostgreSQL (harmoniq.sql)")
    group.add_argument("--sqlite", "-s", action="store_true", help="Télécharge la base de données SQLite (demande.db)")

    args = parser.parse_args()
    
    # If sqlite is passed, it overrides the default postgre behavior
    download_db(is_sqlite=args.sqlite)

if __name__ == "__main__":
    main()
