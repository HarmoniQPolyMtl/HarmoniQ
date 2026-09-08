import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import uvicorn

from harmoniq.scripts.ensure_node import ensure_node_installed


def get_client_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "client"


def build_client():
    """Run npm run build in the client directory and install node if needed."""
    client_dir = get_client_dir()
    if not (client_dir / "package.json").exists():
        print(f"[launch-app] Client directory not found at {client_dir}, skipping build.")
        return

    ensure_node_installed()

    print(f"[launch-app] Installing client dependencies ({client_dir})...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=str(client_dir),
        shell=True,
    )
    if result.returncode != 0:
        print("[launch-app] npm install failed!", file=sys.stderr)
        sys.exit(result.returncode)
    print("[launch-app] Dependencies installed.")

    print(f"[launch-app] Building client ({client_dir})...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(client_dir),
        shell=True,
    )
    if result.returncode != 0:
        print("[launch-app] Client build failed!", file=sys.stderr)
        sys.exit(result.returncode)
    print("[launch-app] Client build complete.")


def start_ng_serve():
    """Start Angular dev server with proxy config for hot reloading."""
    client_dir = get_client_dir()
    if not (client_dir / "package.json").exists():
        print(f"[launch-app] Client directory not found at {client_dir}, skipping ng serve.")
        return None

    ensure_node_installed()

    print(f"[launch-app] Installing client dependencies ({client_dir})...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=str(client_dir),
        shell=True,
    )
    if result.returncode != 0:
        print("[launch-app] npm install failed!", file=sys.stderr)
        sys.exit(result.returncode)
    print("[launch-app] Dependencies installed.")

    proc = subprocess.Popen(
        ["npx", "ng", "serve", "--proxy-config", "proxy.conf.json"],
        cwd=str(client_dir),
        shell=True,
    )
    return proc


def main():
    parser = argparse.ArgumentParser(
        description="Lancer l'interface web",
    )
    mode_group = parser.add_mutually_exclusive_group()

    mode_group.add_argument(
        "--debug",
        action="store_true",
        help="Activer le mode debug",
    )
    mode_group.add_argument(
        "--profile",
        action="store_true",
        help="Activer le mode profiler",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Adresse IP du serveur",
    )
    parser.add_argument(
        "--port",
        default=5000,
        help="Port du serveur",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Nombre de processus de travail",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Ne pas reconstruire le client avant de lancer le serveur",
    )
    
    db_group = parser.add_mutually_exclusive_group()
    db_group.add_argument("--postgre", action="store_true", default=True, help="Utilise PostgreSQL (par défaut)")
    db_group.add_argument("--sqlite", action="store_true", help="Utilise SQLite")

    args = parser.parse_args()
    
    if args.sqlite:
        os.environ["HARMONIQ_DB"] = "sqlite"
        
    log_level = "DEBUG" if args.debug else "WARNING"
    os.environ.setdefault("LOG_LEVEL", log_level)
    logging.basicConfig(level=getattr(logging, log_level))
    logging.getLogger().setLevel(getattr(logging, log_level))

    ng_proc = None

    if args.debug:
        ng_proc = start_ng_serve()
    elif not args.skip_build:
        build_client()

    if args.profile:
        from harmoniq.profiler import Initializer

        import harmoniq.modules
        Initializer.init_module(harmoniq.modules)

        import harmoniq.core
        Initializer.init_module(harmoniq.core)

        import harmoniq.db
        Initializer.init_module(harmoniq.db)

        import harmoniq.webserver
        Initializer.init_module(harmoniq.webserver)
    try:
        if args.debug:
            uvicorn.run(
                "harmoniq.webserver:app", host=args.host, port=int(args.port), reload=True, workers=(args.workers)
            )
        else:
            uvicorn.run(
                "harmoniq.webserver:app",
                host=args.host,
                port=int(args.port),
                workers=1,
            )
    finally:
        if ng_proc:
            print("[launch-app] Stopping Angular dev server...")
            ng_proc.terminate()
            ng_proc.wait()
        if args.profile:
            from harmoniq.profiler import Profiler
            Profiler.report()


if __name__ == "__main__":
    main()
