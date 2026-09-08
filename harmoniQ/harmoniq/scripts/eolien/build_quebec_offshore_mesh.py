from __future__ import annotations

import argparse
import math
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely
from pyproj import Transformer
from sqlalchemy.orm import Session

from harmoniq import PROJECT_ROOT
from harmoniq.core.offshore import DEFAULT_QC_OFFSHORE_GRID_VERSION
from harmoniq.db import schemas
from harmoniq.db.engine import get_db
from harmoniq.db.schemas import SQLBase


CKAN_PACKAGE_SHOW_URL = "https://www.donneesquebec.ca/recherche/api/3/action/package_show"
CERQ_PACKAGE_ID = "cadre-ecologique-de-reference"
CERQ_SHP_HINT = "cerq_shp.zip"
CERQ_LEVEL2_FILENAME = "CR_NIV_02_S.shp"
WORKING_CRS = "EPSG:32198"

MARITIME_REGION_NAMES = {
    "estuaire du saint-laurent",
    "chenal laurentien central",
    "plate-forme de la cote-nord",
    "plate-forme et chenal d'anticosti",
    "plate-forme des iles de la madeleine",
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    no_accents = no_accents.replace("’", "'")
    return " ".join(no_accents.lower().strip().split())


def _fetch_resource_url(package_id: str, url_hint: str) -> str:
    response = requests.get(
        CKAN_PACKAGE_SHOW_URL,
        params={"id": package_id},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN package_show failed for package '{package_id}'")

    resources = payload.get("result", {}).get("resources", [])
    hint = str(url_hint).lower()
    for resource in resources:
        url = str(resource.get("url", "")).strip()
        name = str(resource.get("name", "")).strip().lower()
        if hint in url.lower() or hint in name:
            return url

    raise RuntimeError(
        f"No matching resource found in package '{package_id}' for hint '{url_hint}'"
    )


def _download_file(url: str, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=240, stream=True) as response:
        response.raise_for_status()
        with target_path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_obj.write(chunk)
    return target_path


def _extract_zip(zip_path: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    if not any(extract_dir.iterdir()):
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
    return extract_dir


def _load_cerq_level2(cerq_extract_dir: Path) -> gpd.GeoDataFrame:
    candidates = list(cerq_extract_dir.rglob(CERQ_LEVEL2_FILENAME))
    if not candidates:
        raise FileNotFoundError(
            f"Could not find {CERQ_LEVEL2_FILENAME} in {cerq_extract_dir}"
        )
    gdf = gpd.read_file(candidates[0])
    if gdf.empty:
        raise ValueError("CERQ level-2 layer is empty")
    if gdf.crs is None:
        gdf = gdf.set_crs(WORKING_CRS)
    return gdf


def _select_maritime_polygons(cerq_level2: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    name_candidates = [col for col in cerq_level2.columns if "NOM" in col.upper()]
    if not name_candidates:
        raise ValueError("Could not find name column in CERQ level-2 layer")
    name_col = name_candidates[0]

    if "P_TERRE" not in cerq_level2.columns:
        raise ValueError("CERQ level-2 layer is missing expected column 'P_TERRE'")

    names_normalized = cerq_level2[name_col].map(_normalize_text)
    mask_name = names_normalized.isin(MARITIME_REGION_NAMES)
    mask_water = pd.to_numeric(cerq_level2["P_TERRE"], errors="coerce").fillna(100.0) <= 20.0
    selected = cerq_level2.loc[mask_name & mask_water].copy()
    if selected.empty:
        raise ValueError(
            "No maritime CERQ polygons matched the configured Saint-Laurent/Golfe filters"
        )

    selected = selected.to_crs(WORKING_CRS)
    dissolved = selected.dissolve().reset_index(drop=True)
    return dissolved


def _build_offshore_mesh(
    waters_geometry: gpd.GeoDataFrame,
    resolution_m: int,
) -> tuple[pd.DataFrame, float, float]:
    if resolution_m <= 0:
        raise ValueError("resolution_m must be > 0")

    waters = waters_geometry.to_crs(WORKING_CRS)
    waters_union = waters.geometry.unary_union
    min_x, min_y, max_x, max_y = waters.total_bounds
    origin_x = math.floor(float(min_x) / float(resolution_m)) * float(resolution_m)
    origin_y = math.floor(float(min_y) / float(resolution_m)) * float(resolution_m)

    xs = np.arange(origin_x + resolution_m / 2.0, float(max_x), float(resolution_m))
    ys = np.arange(origin_y + resolution_m / 2.0, float(max_y), float(resolution_m))
    if xs.size == 0 or ys.size == 0:
        raise ValueError("No mesh candidates generated from waters extent")

    grid_x, grid_y = np.meshgrid(xs, ys)
    points = shapely.points(grid_x.ravel(), grid_y.ravel())
    offshore_mask = shapely.intersects(points, waters_union)

    offshore_x = grid_x.ravel()[offshore_mask]
    offshore_y = grid_y.ravel()[offshore_mask]
    if offshore_x.size == 0:
        raise ValueError("Offshore mesh is empty after spatial filtering")

    ix = np.floor((offshore_x - origin_x) / float(resolution_m)).astype(int)
    iy = np.floor((offshore_y - origin_y) / float(resolution_m)).astype(int)

    to_wgs84 = Transformer.from_crs(WORKING_CRS, "EPSG:4326", always_xy=True)
    lon, lat = to_wgs84.transform(offshore_x, offshore_y)

    mesh_df = pd.DataFrame(
        {
            "ix": ix,
            "iy": iy,
            "x_center_m": offshore_x,
            "y_center_m": offshore_y,
            "latitude": lat,
            "longitude": lon,
        }
    ).drop_duplicates(subset=["ix", "iy"])

    return mesh_df, origin_x, origin_y


def _store_mesh_in_db(
    db: Session,
    mesh_df: pd.DataFrame,
    grid_version: str,
    resolution_m: int,
    origin_x: float,
    origin_y: float,
    source: str,
) -> None:
    SQLBase.metadata.create_all(bind=db.get_bind())

    (
        db.query(schemas.QuebecOffshoreMeshPoint)
        .filter(schemas.QuebecOffshoreMeshPoint.grid_version == grid_version)
        .delete(synchronize_session=False)
    )
    (
        db.query(schemas.QuebecOffshoreMeshMeta)
        .filter(schemas.QuebecOffshoreMeshMeta.grid_version == grid_version)
        .delete(synchronize_session=False)
    )

    meta_row = schemas.QuebecOffshoreMeshMeta(
        grid_version=grid_version,
        resolution_m=int(resolution_m),
        crs=WORKING_CRS,
        origin_x=float(origin_x),
        origin_y=float(origin_y),
        source=source,
        generated_at=pd.Timestamp.utcnow().isoformat(),
    )
    db.add(meta_row)
    db.flush()

    records = mesh_df[["ix", "iy", "latitude", "longitude"]].to_dict(orient="records")
    chunk_size = 10_000
    for start in range(0, len(records), chunk_size):
        chunk = records[start : start + chunk_size]
        for row in chunk:
            row["grid_version"] = grid_version
            row["resolution_m"] = int(resolution_m)
        db.bulk_insert_mappings(schemas.QuebecOffshoreMeshPoint, chunk)
    db.commit()


def build_quebec_offshore_mesh(
    grid_version: str = DEFAULT_QC_OFFSHORE_GRID_VERSION,
    resolution_m: int = 1000,
    raw_dir: Path = PROJECT_ROOT / "data" / "geography" / "raw",
    waters_geojson_out: Path = PROJECT_ROOT / "data" / "geography" / "quebec_waters.geojson",
    mesh_parquet_out: Path = PROJECT_ROOT / "data" / "geography" / "quebec_offshore_mesh_1km.parquet",
    persist_db: bool = True,
) -> dict[str, object]:
    cerq_url = _fetch_resource_url(CERQ_PACKAGE_ID, CERQ_SHP_HINT)
    raw_zip_path = raw_dir / "CERQ_SHP.zip"
    _download_file(cerq_url, raw_zip_path)
    cerq_extract_dir = raw_dir / "CERQ_SHP"
    _extract_zip(raw_zip_path, cerq_extract_dir)

    cerq_level2 = _load_cerq_level2(cerq_extract_dir)
    waters = _select_maritime_polygons(cerq_level2)
    mesh_df, origin_x, origin_y = _build_offshore_mesh(waters, resolution_m=resolution_m)

    waters_geojson_out.parent.mkdir(parents=True, exist_ok=True)
    waters.to_crs("EPSG:4326").to_file(waters_geojson_out, driver="GeoJSON")
    mesh_parquet_out.parent.mkdir(parents=True, exist_ok=True)
    mesh_df.to_parquet(mesh_parquet_out, index=False)

    if persist_db:
        db = next(get_db())
        try:
            _store_mesh_in_db(
                db=db,
                mesh_df=mesh_df,
                grid_version=grid_version,
                resolution_m=resolution_m,
                origin_x=origin_x,
                origin_y=origin_y,
                source=f"{CERQ_PACKAGE_ID}:{cerq_url}",
            )
        finally:
            db.close()

    return {
        "grid_version": grid_version,
        "resolution_m": int(resolution_m),
        "offshore_points_count": int(len(mesh_df)),
        "origin_x": float(origin_x),
        "origin_y": float(origin_y),
        "waters_geojson": waters_geojson_out,
        "mesh_parquet": mesh_parquet_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build Quebec offshore mesh (1km default), export geometry artifacts, and store points in DB."
        )
    )
    parser.add_argument(
        "--grid-version",
        type=str,
        default=DEFAULT_QC_OFFSHORE_GRID_VERSION,
        help="Grid version key stored in DB",
    )
    parser.add_argument(
        "--resolution-m",
        type=int,
        default=1000,
        help="Grid resolution in meters",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip DB insert and only write local GeoJSON/Parquet artifacts",
    )
    args = parser.parse_args()

    outputs = build_quebec_offshore_mesh(
        grid_version=args.grid_version,
        resolution_m=args.resolution_m,
        persist_db=not args.no_db,
    )
    print("----- Quebec Offshore Mesh Build -----")
    print(f"grid_version: {outputs['grid_version']}")
    print(f"resolution_m: {outputs['resolution_m']}")
    print(f"offshore_points_count: {outputs['offshore_points_count']}")
    print(f"origin_x: {outputs['origin_x']:.2f}")
    print(f"origin_y: {outputs['origin_y']:.2f}")
    print(f"waters_geojson: {outputs['waters_geojson']}")
    print(f"mesh_parquet: {outputs['mesh_parquet']}")
    print(f"db_persisted: {not args.no_db}")


if __name__ == "__main__":
    main()
