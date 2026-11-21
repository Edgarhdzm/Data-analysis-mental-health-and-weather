"""Add the suicide rate per 10,000 inhabitants to the raw suicide files.

Inputs:
    data/raw/suicide_by_state_2001_2021.csv          suicide deaths by US state and year (CDC)
    data/raw/datos_ine_suicidio_ccaa_desde2001.csv   suicide deaths by Spanish region and year (INE)
    data/processed/usa_population.csv                population by US state and year
    data/processed/spain_population.csv              population by Spanish region and year
Outputs:
    data/processed/usa_suicide_rate.csv
    data/processed/spain_suicide_rate.csv

Usage (from the repository root):
    python src/compute_suicide_rates.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

# INE number of each autonomous community -> NUTS-2 code used in spain_population.csv
INE_TO_NUTS = {"01": "ES61", "02": "ES24", "03": "ES12", "04": "ES53", "05": "ES70", "06": "ES13",
               "07": "ES41", "08": "ES42", "09": "ES51", "10": "ES52", "11": "ES43", "12": "ES11",
               "13": "ES30", "14": "ES62", "15": "ES22", "16": "ES21", "17": "ES23", "18": "ES63", "19": "ES64"}


def usa() -> None:
    us = pd.read_csv(RAW / "suicide_by_state_2001_2021.csv")
    pop = pd.read_csv(PROCESSED / "usa_population.csv")
    us = us.merge(pop[["region_name", "year", "population"]], left_on=["Location", "Year"], right_on=["region_name", "year"])
    us["suicides_per_10k"] = (us["Deaths"] / us["population"] * 10000).round(3)
    us = us.drop(columns=["region_name", "year", "population"])
    us.to_csv(PROCESSED / "usa_suicide_rate.csv", index=False)
    print("usa_suicide_rate.csv:", len(us), "rows")


def spain() -> None:
    es = pd.read_csv(RAW / "datos_ine_suicidio_ccaa_desde2001.csv", sep="\t", encoding="latin-1")
    es["region_code"] = es["Comunidades y Ciudades Autónomas"].str[:2].map(INE_TO_NUTS)
    pop = pd.read_csv(PROCESSED / "spain_population.csv")
    # Inner join: drops "Extranjero" (no region) and the years without population
    es = es.merge(pop[["region_code", "year", "population"]], left_on=["region_code", "Periodo"], right_on=["region_code", "year"])
    es["suicides_per_10k"] = (es["Total"] / es["population"] * 10000).round(3)
    es = es.drop(columns=["region_code", "year", "population"])
    es.to_csv(PROCESSED / "spain_suicide_rate.csv", index=False)
    print("spain_suicide_rate.csv:", len(es), "rows")


if __name__ == "__main__":
    usa()
    spain()
