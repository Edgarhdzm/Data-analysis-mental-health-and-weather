"""Anade las horas de sol (sunshine_duration) a los archivos daily/AAAA.parquet que ya existen.

    sunshine_duration   segundos de sol en el dia (suma de las 24 horas, dias en hora UTC)

El repositorio de Open-Meteo no guarda sunshine_duration: la API lo calcula a partir de la
radiacion directa (direct_radiation, media de la hora anterior, W/m2). Aqui se repite su calculo
(funcion calculateBackwardsSunshineDuration del codigo de Open-Meteo, archivo SunRiseSet.swift):

  1. la radiacion directa se pasa a radiacion directa normal (DNI) dividiendo por el seno medio
     de la altura del sol en esa hora (solo la parte de la hora con el sol por encima del horizonte);
  2. cuenta como sol la parte de la hora con DNI > 120 W/m2 (definicion de la OMM), con una rampa
     lineal entre 60 y 180 W/m2 porque el dato es una media de una hora.

Comparado con la API (2019, 6 puntos de EE. UU., Espana y Paises Bajos): el total del anio coincide
y la diferencia diaria es menor de 1.5 minutos.

Trabaja por anios y se puede cortar y relanzar: se salta los anios que ya tienen la columna.

Uso (desde la raíz del repositorio):
    caffeinate -i python src/weather/add_sunshine.py
    python src/weather/add_sunshine.py --years 2010 2011      # solo algunos anios
"""
import argparse
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from omfiles import OmFileReader

sys.path.insert(0, str(Path(__file__).resolve().parent))  # para encontrar blockfs.py y extract_daily.py
from blockfs import BlockFS  # noqa: E402
from extract_daily import MODEL, OUT, ROOT, build_tiles, log  # noqa: E402

VARIABLE = "direct_radiation"
NEW = "sunshine_duration"
NLON = 1440

def sun_decl_eqtime(t_unix):
    """Solar declination (deg) and equation of time (hours), NOAA formulas."""
    jd = t_unix / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + T * (36000.76983 + 0.0003032 * T)) % 360
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
    Mr = np.radians(M)
    C = np.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T)) + np.sin(2 * Mr) * (0.019993 - 0.000101 * T) + np.sin(3 * Mr) * 0.000289
    true_long = L0 + C
    omega = 125.04 - 1934.136 * T
    lam = true_long - 0.00569 - 0.00478 * np.sin(np.radians(omega))
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * np.cos(np.radians(omega))
    decl = np.degrees(np.arcsin(np.sin(np.radians(eps)) * np.sin(np.radians(lam))))
    y = np.tan(np.radians(eps / 2)) ** 2
    L0r = np.radians(L0)
    eqt_min = 4 * np.degrees(y * np.sin(2 * L0r) - 2 * e * np.sin(Mr) + 4 * e * y * np.sin(Mr) * np.cos(2 * L0r)
                             - 0.5 * y * y * np.sin(4 * L0r) - 1.25 * e * e * np.sin(2 * Mr))
    return decl, eqt_min / 60

def sunshine_seconds(direct, t_unix, lat, lon, dt=3600.0):
    """Open-Meteo's calculateBackwardsSunshineDuration. direct: W/m2, mean of the hour that ENDS at t_unix.
    direct shape (..., ntime), t_unix shape (ntime,), lat/lon shape (...,) in degrees."""
    direct = np.asarray(direct, dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)[..., None]
    lon = np.asarray(lon, dtype=np.float64)[..., None]
    decl, eqt = sun_decl_eqtime(np.asarray(t_unix, dtype=np.float64))
    ut = (t_unix % 86400) / 3600.0
    t1 = np.radians(90 - decl)
    p1 = np.radians(-15.0 * (ut - 12.0 + eqt))
    p10 = np.radians(-15.0 * (ut - dt / 3600 - 12.0 + eqt))
    t0 = np.radians(90 - lat)
    p0 = np.radians(lon) + 0 * p1
    p0 = np.where(p0 < p1 - np.pi, p0 + 2 * np.pi, p0)
    p0 = np.where(p0 > p1 + np.pi, p0 - 2 * np.pi, p0)
    arg = -(np.cos(t0) * np.cos(t1)) / (np.sin(t0) * np.sin(t1))
    carg = np.where((arg > 1) | (arg < -1), np.pi, np.arccos(np.clip(arg, -1, 1)))
    sunrise, sunset = p0 + carg, p0 - carg
    up = ~((p10 < sunset) | (p1 > sunrise))
    p1_l = np.minimum(sunrise, p10)
    p10_l = np.maximum(sunset, p1)
    dt_bound = dt * np.abs((p1_l - p10_l) / (p10 - p1))
    left = np.sin(t0) * np.sin(t1) * np.sin(p1_l - p0) + p1_l * np.cos(t0) * np.cos(t1)
    right = np.sin(t0) * np.sin(t1) * np.sin(p10_l - p0) + p10_l * np.cos(t0) * np.cos(t1)
    pd_ = p1_l - p10_l
    zz = (left - right) / np.where(pd_ < 0, np.minimum(-0.001, pd_), np.maximum(0.001, pd_))
    with np.errstate(divide="ignore", invalid="ignore"):
        dni = np.where(zz <= 0.0001, direct, direct / zz)
    out = np.minimum(np.maximum(dni - 60, 0) / 120 * dt_bound, dt_bound)
    out = np.where(up & (direct > 0), out, 0.0)
    return np.where(np.isnan(direct), np.nan, out)


def worker(year: int, tiles: list[dict], results: list, errors: list, stats: dict) -> None:
    try:
        fs = BlockFS()
        reader = OmFileReader.from_fsspec(fs, f"{MODEL}/{VARIABLE}/year_{year}.om")
        nt = reader.shape[2]
        nd = nt // 24
        start = np.datetime64(f"{year}-01-01T00:00", "s").astype(np.int64)
        t_unix = start + np.arange(nt, dtype=np.int64) * 3600     # hora de cada valor (fin de la hora media)
        for t in tiles:
            a = np.asarray(reader[t["y0"]:t["y1"] + 1, t["x0"]:t["x1"] + 1, 0:nt])
            direct = a[t["jy"], t["jx"], :]
            lat = (t["node_id"] // NLON) * 0.25 - 90
            lon = (t["node_id"] % NLON) * 0.25 - 180
            sun = sunshine_seconds(direct, t_unix, lat, lon)
            results.append({
                "node_id": t["node_id"],
                NEW: sun.reshape(len(t["node_id"]), nd, 24).sum(axis=2),
                "nan": int(np.isnan(direct).sum()),
            })
        with stats["lock"]:
            stats["bytes"] += fs.http_bytes
    except Exception as e:  # se informa en el hilo principal
        errors.append(e)


def add_year(year: int, tiles: list[dict], workers: int) -> None:
    t0 = time.time()
    path = OUT / f"{year}.parquet"
    table = pq.read_table(path)

    groups = [[] for _ in range(workers)]
    load = [0] * workers
    for t in sorted(tiles, key=lambda t: -t["cells"]):
        i = load.index(min(load))
        groups[i].append(t)
        load[i] += t["cells"]

    results, errors = [], []
    stats = {"bytes": 0, "lock": threading.Lock()}
    threads = [threading.Thread(target=worker, args=(year, g, results, errors, stats)) for g in groups if g]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    if errors:
        raise errors[0]

    node_id = np.concatenate([r["node_id"] for r in results])
    order = np.argsort(node_id)
    node_id = node_id[order]
    nd = results[0][NEW].shape[1]
    stack = lambda k: np.concatenate([r[k] for r in results])[order]

    # Las filas nuevas tienen que ir en el mismo orden que el archivo: nodo y, dentro, fecha
    if not np.array_equal(table["node_id"].to_numpy(), np.repeat(node_id, nd).astype(np.int32)):
        raise ValueError(f"{path.name}: los nodos o los dias no coinciden con los ya guardados")

    if NEW in table.column_names:  # por si quedo a medias de un intento anterior
        table = table.drop_columns([NEW])
    table = table.append_column(NEW, pa.array(np.round(stack(NEW)).ravel().astype(np.float32)))
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(path)

    nans = sum(r["nan"] for r in results)
    log(f"{year}: horas de sol anadidas a {table.num_rows:,} filas | {time.time() - t0:.0f} s | "
        f"{stats['bytes'] / 1e6:.0f} MB bajados | {path.stat().st_size / 1e6:.0f} MB en disco | valores vacios: {nans}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="*", default=list(range(2001, 2022)))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    tiles = build_tiles(pd.read_parquet(ROOT / "nodes.parquet"))
    log(f"inicio horas de sol: {len(tiles)} bloques, anios {min(args.years)}-{max(args.years)}")

    for year in args.years:
        path = OUT / f"{year}.parquet"
        if not path.exists():
            log(f"{year}: no existe daily/{year}.parquet; ejecuta antes extract_daily.py")
            sys.exit(1)
        if NEW in pq.ParquetFile(path).schema_arrow.names:
            log(f"{year}: ya tiene horas de sol, se salta")
            continue
        try:
            add_year(year, tiles, args.workers)
        except KeyboardInterrupt:
            log("interrumpido. Vuelve a ejecutar el mismo comando para continuar.")
            sys.exit(1)
        except Exception as e:
            log(f"{year}: ERROR {type(e).__name__}: {e}. Vuelve a ejecutar el mismo comando para continuar.")
            sys.exit(1)
    log("terminado: horas de sol anadidas a todos los anios pedidos")


if __name__ == "__main__":
    main()
