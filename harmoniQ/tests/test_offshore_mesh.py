import asyncio

import geopandas as gpd
import pandas as pd
import pytest
from pyproj import Transformer
from shapely.geometry import Polygon
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from harmoniq.core.offshore import is_offshore_quebec
from harmoniq.db import CRUD, schemas
from harmoniq.scripts.eolien.build_quebec_offshore_mesh import (
    _build_offshore_mesh,
    _select_maritime_polygons,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    engine = engine.execution_options(schema_translate_map={"reseau": None})
    schemas.SQLBase.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session()


def test_select_maritime_polygons_filters_expected_names_and_water_share():
    gdf = gpd.GeoDataFrame(
        {
            "NOM_REG_NA": [
                "Estuaire du Saint-Laurent",
                "Plate-forme de la Côte-Nord",
                "Baie James",
                "Plate-forme et chenal d'Anticosti",
            ],
            "P_TERRE": [0.0, 0.0, 10.0, 50.0],
            "geometry": [
                Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)]),
                Polygon([(1000, 0), (2000, 0), (2000, 1000), (1000, 1000)]),
                Polygon([(0, 1000), (1000, 1000), (1000, 2000), (0, 2000)]),
                Polygon([(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)]),
            ],
        },
        crs="EPSG:32198",
    )

    waters = _select_maritime_polygons(gdf)
    assert not waters.empty

    waters_union = waters.geometry.unary_union
    assert waters_union.contains(gdf.geometry.iloc[0].representative_point())
    assert waters_union.contains(gdf.geometry.iloc[1].representative_point())
    assert not waters_union.contains(gdf.geometry.iloc[2].representative_point())
    assert not waters_union.contains(gdf.geometry.iloc[3].representative_point())


def test_build_offshore_mesh_generates_unique_cells():
    waters = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (2000, 0), (2000, 2000), (0, 2000)])],
        crs="EPSG:32198",
    )
    mesh_df, origin_x, origin_y = _build_offshore_mesh(waters, resolution_m=1000)

    assert origin_x == 0.0
    assert origin_y == 0.0
    assert len(mesh_df) == 4
    assert mesh_df[["ix", "iy"]].drop_duplicates().shape[0] == 4
    assert set(mesh_df["ix"].tolist()) == {0, 1}
    assert set(mesh_df["iy"].tolist()) == {0, 1}


def test_is_offshore_quebec_true_false_and_missing_meta():
    db = _session()
    with pytest.raises(ValueError):
        is_offshore_quebec(latitude=48.0, longitude=-70.0, db=db)

    meta = schemas.QuebecOffshoreMeshMeta(
        grid_version="test_v1",
        resolution_m=1000,
        crs="EPSG:32198",
        origin_x=0.0,
        origin_y=0.0,
        source="test",
        generated_at=pd.Timestamp.utcnow().isoformat(),
    )
    db.add(meta)
    db.add(
        schemas.QuebecOffshoreMeshPoint(
            grid_version="test_v1",
            ix=10,
            iy=20,
            latitude=0.0,
            longitude=0.0,
            resolution_m=1000,
        )
    )
    db.commit()

    to_wgs84 = Transformer.from_crs("EPSG:32198", "EPSG:4326", always_xy=True)
    lon_true, lat_true = to_wgs84.transform(10_500.0, 20_500.0)
    lon_false, lat_false = to_wgs84.transform(30_500.0, 20_500.0)

    assert is_offshore_quebec(
        latitude=lat_true,
        longitude=lon_true,
        db=db,
        grid_version="test_v1",
    )
    assert not is_offshore_quebec(
        latitude=lat_false,
        longitude=lon_false,
        db=db,
        grid_version="test_v1",
    )



