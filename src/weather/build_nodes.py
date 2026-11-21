"""Construye la tabla de nodos: nodos de la malla ERA5 (0.25 grados) de Open-Meteo que
caen dentro de EE. UU. (50 estados + DC), Espana (comunidades autonomas, NUTS-2) y
Paises Bajos (provincias, NUTS-2).

Salida:  nodes.parquet y nodes.csv en la carpeta weather_data.
Uso:     python src/weather/build_nodes.py
"""
from pathlib import Path
import urllib.request

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2] / "data" / "interim" / "weather_data"  # <repo>/data/interim/weather_data
US_ZIP = ROOT / "boundaries" / "us_states" / "cb_2018_us_state_5m.zip"
US_URL = "https://www2.census.gov/geo/tiger/GENZ2018/shp/cb_2018_us_state_5m.zip"
NUTS = ROOT / "boundaries" / "nuts2" / "NUTS_RG_03M_2021_4326_LEVL_2.geojson"
NUTS_URL = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_03M_2021_4326_LEVL_2.geojson"

STEP = 0.25          # resolucion de la malla ERA5 en Open-Meteo
NLAT, NLON = 721, 1440  # la malla va de -90 a 90 y de -180 a 179.75


def fetch(url: str, path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"descargando {path.name}")
        urllib.request.urlretrieve(url, path)


def load_regions() -> gpd.GeoDataFrame:
    fetch(US_URL, US_ZIP)
    fetch(NUTS_URL, NUTS)
    us = gpd.read_file(US_ZIP).to_crs("EPSG:4326")
    us = us[us["STATEFP"].astype(int) <= 56]  # 60 en adelante son territorios
    us = gpd.GeoDataFrame(
        {"country": "US", "region_code": "US-" + us["STUSPS"], "region_name": us["NAME"]},
        geometry=us.geometry, crs="EPSG:4326",
    )
    eu = gpd.read_file(NUTS).to_crs("EPSG:4326")
    eu = eu[eu["CNTR_CODE"].isin(["ES", "NL"])]
    eu = gpd.GeoDataFrame(
        {"country": eu["CNTR_CODE"], "region_code": eu["NUTS_ID"], "region_name": eu["NAME_LATN"]},
        geometry=eu.geometry, crs="EPSG:4326",
    )
    return pd.concat([us, eu], ignore_index=True)


def main() -> None:
    regions = load_regions()

    # Todos los nodos de la malla entre 18 y 72 N (indices enteros -> coordenadas exactas)
    iy = np.arange(round((18 + 90) / STEP), round((72 + 90) / STEP) + 1)
    ix = np.arange(NLON)
    gx, gy = np.meshgrid(ix, iy)
    gx, gy = gx.ravel(), gy.ravel()
    grid = gpd.GeoDataFrame(
        {"iy": gy, "ix": gx, "latitude": gy * STEP - 90, "longitude": gx * STEP - 180},
        geometry=gpd.points_from_xy(gx * STEP - 180, gy * STEP - 90), crs="EPSG:4326",
    )

    # Un nodo pertenece a la region cuyo poligono contiene su centro
    nodes = gpd.sjoin(grid, regions, predicate="within").drop(columns="index_right")
    nodes["assignment"] = "inside"

    # Regiones tan pequenas que ningun nodo cae dentro (DC, Ceuta, Melilla): el nodo mas cercano
    extra = []
    for reg in regions[~regions["region_code"].isin(nodes["region_code"])].itertuples():
        p = reg.geometry.representative_point()
        jy, jx = round((p.y + 90) / STEP), round((p.x + 180) / STEP)
        extra.append({"iy": jy, "ix": jx, "latitude": jy * STEP - 90, "longitude": jx * STEP - 180,
                      "country": reg.country, "region_code": reg.region_code,
                      "region_name": reg.region_name, "assignment": "nearest"})
    nodes = pd.concat([pd.DataFrame(nodes.drop(columns="geometry")), pd.DataFrame(extra)], ignore_index=True)

    nodes["node_id"] = (nodes["iy"] * NLON + nodes["ix"]).astype("int32")
    nodes = nodes.astype({"iy": "int16", "ix": "int16", "latitude": "float32", "longitude": "float32"})
    cols = ["node_id", "latitude", "longitude", "country", "region_code", "region_name", "assignment", "iy", "ix"]
    nodes = nodes[cols].sort_values(["country", "region_code", "node_id"]).reset_index(drop=True)

    nodes.to_parquet(ROOT / "nodes.parquet", index=False)
    nodes.to_csv(ROOT / "nodes.csv", index=False)

    print(f"filas: {len(nodes)} | nodos distintos: {nodes['node_id'].nunique()} | regiones: {nodes['region_code'].nunique()}")
    print(nodes.groupby("country").agg(regiones=("region_code", "nunique"), nodos=("node_id", "nunique")).to_string())
    print("\nasignados por cercania:")
    print(nodes[nodes["assignment"] == "nearest"][["region_code", "region_name", "latitude", "longitude"]].to_string(index=False))


if __name__ == "__main__":
    main()
