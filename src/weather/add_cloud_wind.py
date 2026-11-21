"""Anade nubosidad y viento a los archivos daily/AAAA.parquet que ya existen.

    cloud_cover_mean       media de las 24 horas de cloud_cover                      (% de cielo cubierto)
    wind_speed_100m_mean   media de las 24 horas de la velocidad del viento a 100 m  (km/h)

La velocidad de cada hora es sqrt(u^2 + v^2), con las componentes wind_u_component_100m y
wind_v_component_100m. El repositorio las guarda en m/s; se pasan a km/h (x 3.6), que es
la unidad que da la API por defecto. Los dias van en hora UTC, como el resto de columnas.

Trabaja por anios y se puede cortar y relanzar: se salta los anios que ya tienen las dos
columnas. Si se corta internet, reintenta durante unos 20 minutos.

Uso (desde la raíz del repositorio):
    caffeinate -i python src/weather/add_cloud_wind.py
    python src/weather/add_cloud_wind.py --years 2010 2011      # solo algunos anios
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

VARIABLES = ["cloud_cover", "wind_u_component_100m", "wind_v_component_100m"]
NEW = ["cloud_cover_mean", "wind_speed_100m_mean"]
MS_TO_KMH = 3.6


def worker(year: int, tiles: list[dict], results: list, errors: list, stats: dict) -> None:
    try:
        fs = BlockFS()
        readers = {v: OmFileReader.from_fsspec(fs, f"{MODEL}/{v}/year_{year}.om") for v in VARIABLES}
        nt = readers["cloud_cover"].shape[2]
        nd = nt // 24
        for t in tiles:
            block = {}
            for v in VARIABLES:
                a = np.asarray(readers[v][t["y0"]:t["y1"] + 1, t["x0"]:t["x1"] + 1, 0:nt])
                block[v] = a[t["jy"], t["jx"], :].reshape(len(t["node_id"]), nd, 24)
            C, U, V = (block[v] for v in VARIABLES)
            speed = np.hypot(U.astype(np.float64), V.astype(np.float64)) * MS_TO_KMH
            results.append({
                "node_id": t["node_id"],
                "cloud_cover_mean": C.mean(axis=2, dtype=np.float64),
                "wind_speed_100m_mean": speed.mean(axis=2),
                "nan": int(np.isnan(C).sum() + np.isnan(U).sum() + np.isnan(V).sum()),
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
    nd = results[0]["cloud_cover_mean"].shape[1]
    stack = lambda k: np.concatenate([r[k] for r in results])[order]

    # Las filas nuevas tienen que ir en el mismo orden que el archivo: nodo y, dentro, fecha
    if not np.array_equal(table["node_id"].to_numpy(), np.repeat(node_id, nd).astype(np.int32)):
        raise ValueError(f"{path.name}: los nodos o los dias no coinciden con los ya guardados")

    for name in NEW:  # por si quedo una columna a medias de un intento anterior
        if name in table.column_names:
            table = table.drop_columns([name])
    table = table.append_column("cloud_cover_mean",
                                pa.array(np.round(stack("cloud_cover_mean"), 1).ravel().astype(np.float32)))
    table = table.append_column("wind_speed_100m_mean",
                                pa.array(np.round(stack("wind_speed_100m_mean"), 2).ravel().astype(np.float32)))
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(path)

    nans = sum(r["nan"] for r in results)
    log(f"{year}: nubosidad y viento anadidos a {table.num_rows:,} filas | {time.time() - t0:.0f} s | "
        f"{stats['bytes'] / 1e6:.0f} MB bajados | {path.stat().st_size / 1e6:.0f} MB en disco | valores vacios: {nans}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="*", default=list(range(2001, 2022)))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    tiles = build_tiles(pd.read_parquet(ROOT / "nodes.parquet"))
    log(f"inicio nubosidad y viento: {len(tiles)} bloques, anios {min(args.years)}-{max(args.years)}")

    for year in args.years:
        path = OUT / f"{year}.parquet"
        if not path.exists():
            log(f"{year}: no existe daily/{year}.parquet; ejecuta antes extract_daily.py")
            sys.exit(1)
        if all(c in pq.ParquetFile(path).schema_arrow.names for c in NEW):
            log(f"{year}: ya tiene nubosidad y viento, se salta")
            continue
        try:
            add_year(year, tiles, args.workers)
        except KeyboardInterrupt:
            log("interrumpido. Vuelve a ejecutar el mismo comando para continuar.")
            sys.exit(1)
        except Exception as e:
            log(f"{year}: ERROR {type(e).__name__}: {e}. Vuelve a ejecutar el mismo comando para continuar.")
            sys.exit(1)
    log("terminado: nubosidad y viento anadidos a todos los anios pedidos")


if __name__ == "__main__":
    main()
