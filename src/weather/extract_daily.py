"""Extrae datos diarios por nodo desde el repositorio abierto de Open-Meteo (ERA5, 0.25 grados).

Lee solo las zonas de la malla donde hay nodos (nodes.parquet), resume cada dia y
guarda UN ARCHIVO POR ANIO en daily/AAAA.parquet. Si se corta (internet, cerrar el
portatil, Ctrl+C), al volver a ejecutarlo se salta los anios ya terminados.

Variables que calcula (dias en hora UTC, igual que la API por defecto):
    temperature_2m_mean   media de las 24 horas de temperature_2m            (grados C)
    precipitation_hours   horas con precipitation > 0                        (horas)
    rain_sum              suma de max(precipitation - snowfall_water_eq, 0)  (mm)

Uso (desde la raíz del repositorio):
    caffeinate -i python src/weather/extract_daily.py
    python src/weather/extract_daily.py --years 2010 2011      # solo algunos anios
"""
import argparse
import datetime as dt
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from omfiles import OmFileReader

sys.path.insert(0, str(Path(__file__).resolve().parent))  # para encontrar blockfs.py
from blockfs import BlockFS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "data" / "interim" / "weather_data"  # <repo>/data/interim/weather_data
OUT = ROOT / "daily"
LOG = ROOT / "extract.log"
MODEL = "data/copernicus_era5"
VARIABLES = ["temperature_2m", "precipitation", "snowfall_water_equivalent"]
BAND = 8   # filas de latitud por bloque de lectura
GAP = 24   # columnas vacias a partir de las cuales se parte un bloque


def log(msg: str) -> None:
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def build_tiles(nodes: pd.DataFrame) -> list[dict]:
    """Rectangulos de la malla (filas x columnas) que cubren todos los nodos sin leer de mas."""
    cells = nodes[["node_id", "iy", "ix"]].drop_duplicates("node_id")
    tiles = []
    for band, g in cells.groupby(cells["iy"] // BAND):
        cols = np.sort(g["ix"].unique())
        starts = np.r_[0, np.where(np.diff(cols) > GAP)[0] + 1]
        ends = np.r_[starts[1:], len(cols)]
        for s, e in zip(starts, ends):
            x0, x1 = int(cols[s]), int(cols[e - 1])
            sub = g[(g["ix"] >= x0) & (g["ix"] <= x1)]
            y0, y1 = int(sub["iy"].min()), int(sub["iy"].max())
            tiles.append({
                "y0": y0, "y1": y1, "x0": x0, "x1": x1,
                "node_id": sub["node_id"].to_numpy(),
                "jy": (sub["iy"] - y0).to_numpy(), "jx": (sub["ix"] - x0).to_numpy(),
                "cells": (y1 - y0 + 1) * (x1 - x0 + 1),
            })
    return tiles


def worker(year: int, tiles: list[dict], results: list, errors: list, stats: dict) -> None:
    try:
        fs = BlockFS()
        readers = {v: OmFileReader.from_fsspec(fs, f"{MODEL}/{v}/year_{year}.om") for v in VARIABLES}
        nt = readers["temperature_2m"].shape[2]
        nd = nt // 24
        for t in tiles:
            block = {}
            for v in VARIABLES:
                a = np.asarray(readers[v][t["y0"]:t["y1"] + 1, t["x0"]:t["x1"] + 1, 0:nt])
                block[v] = a[t["jy"], t["jx"], :].reshape(len(t["node_id"]), nd, 24)
            T, P, S = (block[v] for v in VARIABLES)
            results.append({
                "node_id": t["node_id"],
                "temperature_2m_mean": T.mean(axis=2, dtype=np.float64),
                "precipitation_hours": (P > 0).sum(axis=2),
                "rain_sum": np.clip(P.astype(np.float64) - S, 0, None).sum(axis=2),
                "nan": int(np.isnan(T).sum() + np.isnan(P).sum() + np.isnan(S).sum()),
            })
        with stats["lock"]:
            stats["bytes"] += fs.http_bytes
            stats["requests"] += fs.http_requests
    except Exception as e:  # se informa en el hilo principal
        errors.append(e)


def extract_year(year: int, tiles: list[dict], workers: int) -> None:
    t0 = time.time()
    # Reparto equilibrado de los bloques entre los hilos
    groups = [[] for _ in range(workers)]
    load = [0] * workers
    for t in sorted(tiles, key=lambda t: -t["cells"]):
        i = load.index(min(load))
        groups[i].append(t)
        load[i] += t["cells"]

    results, errors = [], []
    stats = {"bytes": 0, "requests": 0, "lock": threading.Lock()}
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
    nd = results[0]["temperature_2m_mean"].shape[1]
    stack = lambda k: np.concatenate([r[k] for r in results])[order]
    first = np.datetime64(f"{year}-01-01")
    dates = np.arange(first, first + np.timedelta64(nd, "D"))

    table = pa.table({
        "node_id": pa.array(np.repeat(node_id, nd).astype(np.int32)),
        "date": pa.array(np.tile(dates, len(node_id)).astype("datetime64[ms]")),  # pandas lo lee como fecha
        "temperature_2m_mean": pa.array(np.round(stack("temperature_2m_mean"), 2).ravel().astype(np.float32)),
        "precipitation_hours": pa.array(stack("precipitation_hours").ravel().astype(np.int8)),
        "rain_sum": pa.array(np.round(stack("rain_sum"), 1).ravel().astype(np.float32)),
    })
    tmp = OUT / f"{year}.parquet.tmp"
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(OUT / f"{year}.parquet")

    nans = sum(r["nan"] for r in results)
    log(f"{year}: {len(node_id)} nodos x {nd} dias = {table.num_rows:,} filas | "
        f"{time.time() - t0:.0f} s | {stats['bytes'] / 1e6:.0f} MB bajados | "
        f"{(OUT / f'{year}.parquet').stat().st_size / 1e6:.0f} MB en disco | valores vacios: {nans}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="*", default=list(range(2001, 2022)))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    nodes = pd.read_parquet(ROOT / "nodes.parquet")
    tiles = build_tiles(nodes)
    n_nodes = nodes["node_id"].nunique()
    log(f"inicio: {n_nodes} nodos en {len(tiles)} bloques ({sum(t['cells'] for t in tiles)} celdas a leer), "
        f"anios {min(args.years)}-{max(args.years)}")

    for year in args.years:
        if (OUT / f"{year}.parquet").exists():
            log(f"{year}: ya estaba hecho, se salta")
            continue
        try:
            extract_year(year, tiles, args.workers)
        except KeyboardInterrupt:
            log("interrumpido. Vuelve a ejecutar el mismo comando para continuar.")
            sys.exit(1)
        except Exception as e:
            log(f"{year}: ERROR {type(e).__name__}: {e}. Vuelve a ejecutar el mismo comando para continuar.")
            sys.exit(1)
    log("terminado: todos los anios pedidos estan en daily/")


if __name__ == "__main__":
    main()
