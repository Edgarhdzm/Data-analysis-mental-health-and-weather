# Mental health and weather

Analysis of suicide rates in the **United States** and **Spain** between **2001 and 2021**, by region (US states and Spanish autonomous communities), and of their relationship with the weather, drug overdoses, population size and density, and the economy.

Weather and population tables are also prepared for the **Netherlands**, but there is no suicide data or analysis for that country yet.

## Research question

Are regional suicide rates related to the weather (temperature, rain, daylight, hours of sun, cloud cover, wind), to drug overdoses, to how many people live in a region and how dispersed they are, or to the economy (GDP)?

The comparisons use **rates** (suicides per 100,000 inhabitants; the processed suicide tables also keep a column per 10,000), not raw counts. The only figure with raw counts is the map of `notebooks/Plots_suicidio_spain.ipynb`, which shows the average number of suicides per year.

## Repository structure

```
Data-analysis-mental-health-and-weather/
├── README.md
├── requirements.txt          <- Python packages needed
├── .gitignore
├── data/
│   ├── raw/                  <- original downloads, not uploaded to GitHub (see "Data")
│   ├── interim/              <- large intermediate files, not uploaded to GitHub
│   │   └── weather_data/     <- daily weather by grid node (Parquet, ~1 GB)
│   ├── processed/            <- clean tables used in the analysis (uploaded)
│   └── geo/                  <- region borders, created by a notebook the first time it runs (not uploaded)
├── notebooks/                <- analysis and figures (Jupyter)
├── src/                      <- Python scripts that create the processed data
│   └── weather/              <- scripts that download and build the weather data
├── figures/                  <- figures written by the notebooks when they run (not uploaded)
└── results/                  <- tables of numbers written by the notebooks when they run (not uploaded)
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

### Processed data (`data/processed/`, in GitHub)

| File | One row per | Created by |
|---|---|---|
| `spain_yearly.csv`, `usa_yearly.csv`, `NL_yearly.csv` | region × year: mean temperature (°C), hours with precipitation, rain (mm), mean daylight (s per day), mean cloud cover (%), mean wind speed at 100 m (km/h), hours of sun in the year | `notebooks/API_Weather.ipynb` |
| `usa_population.csv` | US state × year: population | `notebooks/API_Weather.ipynb` — U.S. Census Bureau, https://www.census.gov/programs-surveys/popest.html |
| `spain_population.csv`, `NL_population.csv` | region × year: population on 1 January | `notebooks/API_Weather.ipynb` — Eurostat `demo_r_d2jan`, https://ec.europa.eu/eurostat/databrowser/view/demo_r_d2jan/default/table |
| `usa_suicide_rate.csv`, `spain_suicide_rate.csv` | region × year: suicides and suicides per 10,000 inhabitants | `src/compute_suicide_rates.py` |
| `drug_overdose_us_2001_2021.csv` | year: overdose deaths and rates per 100,000, total and by sex | `src/extract_overdose_pdf.py` |
| `usa_real_gdp.csv`, `usa_unemployment.csv` | US state × year: real GDP (millions of 2017 dollars) and unemployment rate (%) | `src/download_economic_data.py` — FRED, https://fred.stlouisfed.org |

`usa_unemployment.csv` and the two Dutch tables are not used by any notebook yet.

The hours of sun computed from ERA5 are higher than those measured at weather stations, so they are useful to compare regions, not as absolute values.

Regions: 50 US states + District of Columbia, 17 Spanish autonomous communities + Ceuta and Melilla, 12 Dutch provinces.

### Data downloaded while the notebooks run

The maps need the borders of the regions, which are not in the repository. The notebooks download them when they run, so they need an internet connection: U.S. Census Bureau cartographic boundary files (https://www2.census.gov/geo/tiger/GENZ2018/shp/), Eurostat GISCO NUTS 2021 (https://gisco-services.ec.europa.eu/distribution/v2/nuts/), and public GeoJSON files of the Spanish autonomous communities and the US states.

## Notebooks

| Notebook | What it does | Reads | Writes |
|---|---|---|---|
| `notebooks/API_Weather.ipynb` | Builds the yearly weather tables and the population tables | `data/interim/weather_data/`; Census and Eurostat (internet) | the six `*_yearly.csv` and `*_population.csv` files in `data/processed/` |
| `notebooks/overdose_suicides_usa.ipynb` | Drug overdose deaths vs. suicides in the US: log–log fit, real GDP during the 2007–2011 recession, and maps of the suicide rate by state in four periods | `data/processed/` | nothing (figures are shown in the notebook) |
| `notebooks/Plots_suicidio_spain.ipynb` | Map of the average number of suicides by Spanish autonomous community | `data/processed/spain_suicide_rate.csv` | nothing |
| `notebooks/suicide_rates_vs_population_spain_usa.ipynb` | Suicide rates vs. population size in Spain and the US, with an interactive version of the plots (`plotly`) | the four population and suicide tables | nothing |
| `notebooks/suicide_rates_vs_population_new_plots.ipynb` | Figures and numbers for the paper: suicide rates vs. population size | the four population and suicide tables | `figures/` (PDF and PNG), `results/key_numbers.csv` |
| `notebooks/suicide_population_crm_20261124.ipynb` | Figures and numbers for the paper: suicide rates vs. population density, with maps and area cartograms | the four population and suicide tables | `data/geo/` (borders, first run only), `figures/`, `results/key_numbers.csv` |
| `notebooks/weather_suicide.ipynb` | Maps of every weather variable and of the suicide rate by region (Spain and US), correlation (R²) between two of the tables of regional means, and bivariate maps of suicides and rain | the two yearly weather tables and the two suicide tables of Spain and the US | `figures/weather/` (PNG maps), `results/weather/` (CSV tables of regional means) |

The two notebooks that write `results/key_numbers.csv` use the same file name, so the one that runs last replaces the file of the other.

## Scripts (`src/`)

| Script | What it does |
|---|---|
| `compute_suicide_rates.py` | Adds the suicide rate to the raw suicide files of the US and Spain |
| `extract_overdose_pdf.py` | Extracts the table of overdose deaths per year from the NCHS PDF |
| `download_economic_data.py` | Downloads real GDP and unemployment of every US state from FRED |
| `spain_rain_hours.py` | Map of the hours with precipitation by Spanish autonomous community; writes the map in `figures/` and a table of regional means in `data/processed/` |
| `weather/build_nodes.py`, `extract_daily.py`, `add_daylight.py`, `add_cloud_wind.py`, `add_sunshine.py`, `validate.py`, `blockfs.py` | Build `data/interim/weather_data/` from the Open-Meteo open data, and compare a sample with the Open-Meteo API |

Every script is run from the repository root (for example `python src/compute_suicide_rates.py`) and explains its inputs and outputs in its first lines.

## How to reproduce

1. Clone the repository and install the packages: `pip install -r requirements.txt`
2. Open a notebook from the `notebooks/` folder and use *Run All*. The analysis notebooks only read `data/processed/`, which is in GitHub. The notebooks that draw maps also need an internet connection for the borders.

Optional, only to re-create the processed tables from scratch: download the raw files into `data/raw/` (table above), create the weather data in `data/interim/weather_data/` with the scripts in `src/weather/`, and run the scripts in `src/` and `notebooks/API_Weather.ipynb` (the only notebook that needs the weather data).

### Check of the notebooks

Every notebook was run from start to end on a clean copy of the repository (25 November 2026):

| Notebook | Result of *Run All* |
|---|---|
| `overdose_suicides_usa.ipynb` | Runs |
| `Plots_suicidio_spain.ipynb` | Runs |
| `suicide_rates_vs_population_new_plots.ipynb` | Runs |
| `suicide_population_crm_20261124.ipynb` | Runs |
| `API_Weather.ipynb` | Runs when `data/interim/weather_data/` exists, and re-creates the six tables of `data/processed/` exactly |
| `suicide_rates_vs_population_spain_usa.ipynb` | Runs |
| `weather_suicide.ipynb` | Runs |

## Use of AI

An AI assistant (Claude, by Anthropic) was used to help write and debug the code and to check that the notebooks run; the analysis and its conclusions were reviewed by the team.

## License

GNU General Public License v3.0 (see `LICENSE`).
