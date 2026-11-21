"""Anade la columna daylight_duration (segundos de luz al dia) a los archivos daily/AAAA.parquet.

Las horas de luz de Open-Meteo solo dependen de la latitud y de la fecha (comprobado:
misma latitud y distinta longitud dan exactamente el mismo valor). Su formula es

    cos(H) = -(sin(0.8333 grados) + sin(lat) sin(dec)) / (cos(lat) cos(dec))
    daylight_duration = 2 H / 15 grados * 3600 s

donde dec es la declinacion del sol de ese dia. La declinacion se obtiene UNA vez
pidiendo a la API las horas de luz de la latitud 40 e invirtiendo la formula, y se
guarda en sun_declination.csv. Con ella se calcula cualquier otra latitud sin gastar
cuota (diferencia con la API: menos de 0.2 s).

Uso (desde la raíz del repositorio):
    python src/weather/add_daylight.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

ROOT = Path(__file__).resolve().parents[2] / "data" / "interim" / "weather_data"  # <repo>/data/interim/weather_data
DECL = ROOT / "sun_declination.csv"
API = "https://archive-api.open-meteo.com/v1/archive"
ALPHA = np.radians(0.83333)   # refraccion + radio del sol, como en Open-Meteo
REF_LAT = 40.0
NLON = 1440


def declination_from_daylight(seconds: np.ndarray, lat: float) -> np.ndarray:
    h = seconds / 86400 * np.pi
    t0 = np.radians(lat)
    a, b, c = np.sin(t0), np.cos(h) * np.cos(t0), -np.sin(ALPHA)
    return np.arcsin(c / np.hypot(a, b)) - np.arctan2(b, a)


def daylight_from_declination(dec: np.ndarray, lat: np.ndarray) -> np.ndarray:
    t0 = np.radians(lat)
    arg = -(np.sin(ALPHA) + np.sin(t0) * np.sin(dec)) / (np.cos(t0) * np.cos(dec))
    sec = np.arccos(np.clip(arg, -1, 1)) / np.radians(15) * 2 * 3600
    return np.where(arg > 1, 0.0, np.where(arg < -1, 86400.0, sec))  # noche polar / dia polar


def load_declination() -> tuple[np.datetime64, np.ndarray]:
    if not DECL.exists():
        print("pidiendo a la API las horas de luz de la latitud 40 (2001-2021, unas 55 llamadas)")
        r = requests.get(API, params=dict(latitude=REF_LAT, longitude=-100.0, start_date="2001-01-01",
                                          end_date="2021-12-31", daily="daylight_duration",
                                          models="era5", cell_selection="nearest"), timeout=180).json()
        if isinstance(r, dict) and r.get("error"):
            raise SystemExit(f"la API respondio: {r['reason']}")
        sec = np.array(r["daily"]["daylight_duration"], dtype=float)
        pd.DataFrame({
            "date": r["daily"]["time"],
            "declination_rad": declination_from_daylight(sec, REF_LAT),
            "daylight_duration_lat40": sec,
        }).to_csv(DECL, index=False)
    d = pd.read_csv(DECL)
    days = d["date"].to_numpy(dtype="datetime64[D]")
    if not (np.diff(days) == np.timedelta64(1, "D")).all():
        raise SystemExit("sun_declination.csv tiene huecos; borralo y vuelve a ejecutar")
    return days[0], d["declination_rad"].to_numpy()


def main() -> None:
    first_day, dec = load_declination()
    files = sorted((ROOT / "daily").glob("[0-9][0-9][0-9][0-9].parquet"))
    if not files:
        raise SystemExit("no hay archivos en daily/. Ejecuta antes extract_daily.py")
    for f in files:
        table = pq.read_table(f)
        if "daylight_duration" in table.column_names:
            print(f"{f.name}: ya tiene daylight_duration")
            continue
        lat = (table["node_id"].to_numpy() // NLON) * 0.25 - 90
        day = (table["date"].to_numpy().astype("datetime64[D]") - first_day).astype(int)
        if day.min() < 0 or day.max() >= len(dec):
            raise SystemExit(f"{f.name}: faltan fechas en sun_declination.csv")
        sec = np.round(daylight_from_declination(dec[day], lat), 2).astype(np.float32)
        table = table.append_column("daylight_duration", pa.array(sec))
        tmp = f.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp, compression="zstd")
        tmp.rename(f)
        print(f"{f.name}: anadida daylight_duration ({table.num_rows:,} filas)")


if __name__ == "__main__":
    main()
