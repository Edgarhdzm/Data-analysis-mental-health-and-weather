"""Compara una muestra de nodos de daily/AAAA.parquet con lo que da la API de Open-Meteo.

Pide a la API las mismas variables diarias para unos pocos nodos elegidos al azar y
muestra la diferencia maxima. Gasta unas 10 llamadas de cuota por nodo y anio.

La temperatura se pide con elevation=nan: asi la API devuelve el valor crudo de la
celda, que es lo que hay en los archivos (por defecto la API corrige por altitud).

Uso (desde la raíz del repositorio):
    python src/weather/validate.py --year 2010 --nodes 12
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2] / "data" / "interim" / "weather_data"  # <repo>/data/interim/weather_data
API = "https://archive-api.open-meteo.com/v1/archive"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2010)
    ap.add_argument("--nodes", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    nodes = pd.read_parquet(ROOT / "nodes.parquet").drop_duplicates("node_id")
    per_country = max(1, args.nodes // 3)
    sample = pd.concat([
        g.sample(min(len(g), per_country if c != "US" else args.nodes - 2 * per_country), random_state=args.seed)
        for c, g in nodes.groupby("country")
    ])
    data = pd.read_parquet(ROOT / "daily" / f"{args.year}.parquet")
    variables = [c for c in data.columns if c not in ("node_id", "date")]
    data = data[data["node_id"].isin(sample["node_id"])].set_index(["node_id", "date"])

    worst = {v: 0.0 for v in variables}
    print(f"anio {args.year}: {len(sample)} nodos, variables: {', '.join(variables)}\n")
    for n in sample.itertuples():
        r = requests.get(API, params=dict(
            latitude=float(n.latitude), longitude=float(n.longitude),
            start_date=f"{args.year}-01-01", end_date=f"{args.year}-12-31",
            daily=",".join(variables), models="era5", cell_selection="nearest", elevation="nan",
        ), timeout=120).json()
        if isinstance(r, dict) and r.get("error"):
            raise SystemExit(f"la API respondio: {r['reason']}")
        mine = data.loc[n.node_id]
        diffs = []
        for v in variables:
            d = float(np.nanmax(np.abs(mine[v].to_numpy(dtype=float) - np.array(r["daily"][v], dtype=float))))
            worst[v] = max(worst[v], d)
            diffs.append(f"{v}={d:.3f}")
        print(f"{n.region_code:6s} ({n.latitude:6.2f}, {n.longitude:7.2f})  dif. max: " + "  ".join(diffs))

    print("\nDiferencia maxima en toda la muestra:")
    for v, d in worst.items():
        print(f"  {v:22s} {d:.3f}")


if __name__ == "__main__":
    main()
