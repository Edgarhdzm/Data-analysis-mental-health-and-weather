# Mental health and weather

Analysis of suicide rates in the **United States**, **Spain** and the **Netherlands** between **2001 and 2021**, and of their relationship with weather, drug overdoses, population size and density, and economic indicators.

## Research question

Are regional suicide rates related to the weather (temperature, rain, daylight, hours of sun, cloud cover, wind), to drug overdoses, to how many people live in a region and how dispersed they are, or to the economy (GDP, unemployment, public debt)?

All comparisons use **rates** (suicides per 10,000 or 100,000 inhabitants), never raw counts.

## Repository structure

```
Data-analysis-mental-health-and-weather/
├── README.md
├── requirements.txt          <- Python packages needed
├── .gitignore
├── data/
│   ├── raw/                  <- original downloads, not uploaded to GitHub (see "Data")
│   ├── interim/              <- large intermediate files, not uploaded to GitHub
│   │   └── weather_data/     <- daily weather by grid node (Parquet, ~800 MB)
│   └── processed/            <- clean tables used in the analysis (uploaded)
├── notebooks/                <- analysis and figures (Jupyter)
└── src/                      <- Python scripts that create the processed data
    └── weather/              <- scripts that download and build the weather data
```

The notebooks find the repository folder by themselves and build every path with `pathlib`, so no path depends on a particular computer.

## Data

### Raw data (`data/raw/`, not in GitHub)

These are only needed to re-create the processed tables with the scripts in `src/`; the analysis notebooks do not use them. To re-create the tables, download the files and save them in `data/raw/` with the names below.

| File | Content | Source |
|---|---|---|
| `suicide_by_state_2001_2021.csv` | Suicide deaths by US state and year | CDC, National Center for Health Statistics, *Stats of the States: suicide mortality* — https://www.cdc.gov/nchs/state-stats/deaths/suicide.html |
| `datos_ine_suicidio_ccaa_desde2001.csv` | Suicide deaths by Spanish autonomous community and year (cause 098, both sexes, all ages; tab-separated, Latin-1) | INE, *Estadística de defunciones según la causa de muerte* — https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780&menu=resultados&idp=1254735573175 |
| `drug_overdose_us_2001_2021.pdf` | Drug overdose deaths in the US, 2001–2021 (NCHS Data Brief 457) | CDC, NCHS — https://www.cdc.gov/nchs/products/databriefs/db457.htm |

### Interim data (`data/interim/weather_data/`, not in GitHub)

Daily weather for every node of the 0.25° (about 25 km) **ERA5** reanalysis grid inside the three countries (18,558 nodes), 2001–2021, read from the open-data repository of **Open-Meteo** (https://github.com/open-meteo/open-data, https://open-meteo.com). It is created with the scripts in `src/weather/` (about 3.5 hours; see the docstring of each script). Hours of sun (`sunshine_duration`) are not stored by Open-Meteo: `src/weather/add_sunshine.py` computes them from the direct radiation with the same formula as the Open-Meteo API (checked against the API).

### Processed data (`data/processed/`)

| File | One row per | Created by |
|---|---|---|
| `spain_yearly.csv`, `usa_yearly.csv`, `NL_yearly.csv` | region × year: mean temperature (°C), hours with precipitation, rain (mm), mean daylight (s per day), mean cloud cover (%), mean wind speed at 100 m (km/h), hours of sun in the year | `notebooks/API_Weather.ipynb` |
| `usa_population.csv` | US state × year: population | `notebooks/API_Weather.ipynb` — U.S. Census Bureau, https://www.census.gov/programs-surveys/popest.html |
| `spain_population.csv`, `NL_population.csv` | region × year: population on 1 January | `notebooks/API_Weather.ipynb` — Eurostat `demo_r_d2jan`, https://ec.europa.eu/eurostat/databrowser/view/demo_r_d2jan/default/table |
| `usa_suicide_rate.csv`, `spain_suicide_rate.csv` | region × year: suicides and suicides per 10,000 inhabitants | `src/compute_suicide_rates.py` |
| `drug_overdose_us_2001_2021.csv` | year: overdose deaths and rates, total and by sex | `src/extract_overdose_pdf.py` |
| `usa_real_gdp.csv`, `usa_unemployment.csv` | US state × year: real GDP and unemployment rate | `src/download_economic_data.py` — FRED, https://fred.stlouisfed.org |

The hours of sun computed from ERA5 are higher than those measured at weather stations, so they are useful to compare regions, not as absolute values.

Regions: 50 US states + District of Columbia, 17 Spanish autonomous communities + Ceuta and Melilla, 12 Dutch provinces.

## Notebooks

| Notebook | What it does |
|---|---|
| `API_Weather.ipynb` | Builds the yearly weather and population tables |
| `overdose_suicides_usa.ipynb` | Drug overdose deaths vs. suicides in the US (log–log fit) |
| `suicide_rates_vs_population_spain_usa.ipynb` | Suicide rates vs. population size in Spain and the US |
| `suicide_rates_vs_population_new_plots.ipynb` | Figures and numbers for the paper (population size vs. suicide rates) |
| `Plots_suicidio_spain.ipynb` | Map of the average number of suicides by autonomous community |

Each notebook starts with a description of what it does, its inputs and its outputs.

## How to reproduce

1. Clone the repository and install the packages: `pip install -r requirements.txt`
2. Open the notebooks from the `notebooks/` folder and use *Run All*. All the analysis notebooks only read `data/processed/`, which is in GitHub, so nothing else has to be downloaded.

Optional, only to re-create the processed tables from scratch: download the raw files into `data/raw/` (table above), create the weather data in `data/interim/weather_data/` with the scripts in `src/weather/`, and run the scripts in `src/` and `notebooks/API_Weather.ipynb` (the only notebook that needs the weather data).

## Use of AI

An AI assistant (Claude, by Anthropic) was used to help write and debug the code; the analysis and its conclusions were reviewed by the team.

## License

GNU General Public License v3.0 (see `LICENSE`).
