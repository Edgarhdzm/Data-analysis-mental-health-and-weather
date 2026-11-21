"""Download real GDP and the unemployment rate of every US state, 2001-2021, from FRED.

Real GDP: series XXRGSP (millions of chained 2017 dollars), U.S. Bureau of Economic Analysis.
Unemployment: series XXUR, yearly mean of the monthly rate (%), U.S. Bureau of Labor Statistics.
XX is the two-letter state code. https://fred.stlouisfed.org

Inputs:
    data/processed/usa_population.csv   only used for the list of states and their codes
Outputs:
    data/processed/usa_real_gdp.csv
    data/processed/usa_unemployment.csv

Usage (from the repository root, needs internet; about 2 minutes):
    python src/download_economic_data.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}&cosd=2001-01-01&coed=2021-12-31&fq=Annual&fam=avg"


def download(suffix: str, column: str) -> pd.DataFrame:
    states = pd.read_csv(PROCESSED / "usa_population.csv")[["region_code", "region_name"]].drop_duplicates()
    tables = []
    for code, name in zip(states["region_code"], states["region_name"]):
        series = code[3:] + suffix                     # "US-CA" -> "CARGSP" / "CAUR"
        t = pd.read_csv(URL.format(series))
        t["year"] = pd.to_datetime(t["observation_date"]).dt.year
        t = t.rename(columns={series: column})[["year", column]]
        t["region_code"] = code
        t["region_name"] = name
        tables.append(t)
    return pd.concat(tables, ignore_index=True)[["region_code", "region_name", "year", column]]


if __name__ == "__main__":
    gdp = download("RGSP", "real_gdp_millions")
    gdp.to_csv(PROCESSED / "usa_real_gdp.csv", index=False)
    print("usa_real_gdp.csv:", len(gdp), "rows")

    unemployment = download("UR", "unemployment_rate")
    unemployment.to_csv(PROCESSED / "usa_unemployment.csv", index=False)
    print("usa_unemployment.csv:", len(unemployment), "rows")
