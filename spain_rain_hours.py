


import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import unicodedata

# --------------------------------------------------
# 1. CARGAR LOS DATOS
# --------------------------------------------------

df = pd.read_csv("spain_yearly.csv")

# Seleccionar el periodo 2001-2021
df = df[(df["year"] >= 2001) & (df["year"] <= 2021)]

# Comprobar que existen datos para todo el periodo
print("Años disponibles:", df["year"].nunique())
print("Territorios disponibles:", df["region_name"].nunique())

# --------------------------------------------------
# 2. CALCULAR LA MEDIA DE HORAS DE PRECIPITACIÓN
# --------------------------------------------------

media_precipitacion = (
    df.groupby("region_name")["precipitation_hours"]
    .mean()
    .reset_index()
)

media_precipitacion.columns = [
    "comunidad",
    "media_horas_precipitacion"
]

print("\nMedia de horas de precipitación:")
print(media_precipitacion.sort_values(
    "media_horas_precipitacion",
    ascending=False
))

# --------------------------------------------------
# 3. CARGAR EL MAPA DE COMUNIDADES AUTÓNOMAS
# --------------------------------------------------

url = (
    "https://raw.githubusercontent.com/"
    "codeforgermany/click_that_hood/main/public/data/"
    "spain-communities.geojson"
)

mapa = gpd.read_file(url)

# --------------------------------------------------
# 4. NORMALIZAR LOS NOMBRES PARA UNIR LOS DATOS
# --------------------------------------------------

def normalizar(nombre):
    nombre = str(nombre).lower().strip()

    nombre = unicodedata.normalize("NFKD", nombre)
    nombre = "".join(
        c for c in nombre
        if not unicodedata.combining(c)
    )

    return nombre.replace("-", " ").replace("_", " ")

# Los nombres del GeoJSON pueden presentar variantes
# respecto a los del CSV.

equivalencias = {
    "asturias": "principado de asturias",
    "balearic islands": "illes balears",
    "islas baleares": "illes balears",
    "baleares": "illes balears",
    "canary islands": "canarias",
    "castile and leon": "castilla y leon",
    "castilla leon": "castilla y leon",
    "castilla-leon": "castilla y leon",
    "castilla la mancha": "castilla la mancha",
    "castile la mancha": "castilla la mancha",
    "catalonia": "cataluna",
    "valencian community": "comunitat valenciana",
    "valencia": "comunitat valenciana",
    "basque country": "pais vasco",
    "navarre": "comunidad foral de navarra",
    "navarra": "comunidad foral de navarra",
    "la rioja": "la rioja",
    "madrid": "comunidad de madrid",
    "murcia": "region de murcia",
    "ceuta": "ciudad de ceuta",
    "melilla": "ciudad de melilla"
}

# En el GeoJSON de comunidades, el nombre está
# almacenado en la columna 'name'.

mapa["clave"] = mapa["name"].apply(normalizar)
media_precipitacion["clave"] = (
    media_precipitacion["comunidad"].apply(normalizar)
)

# Aplicar equivalencias
media_precipitacion["clave"] = (
    media_precipitacion["clave"].replace(equivalencias)
)

mapa["clave"] = mapa["clave"].replace(equivalencias)

# --------------------------------------------------
# 5. UNIR EL MAPA CON LOS DATOS DE PRECIPITACIÓN
# --------------------------------------------------

mapa_final = mapa.merge(
    media_precipitacion[[
        "clave",
        "media_horas_precipitacion"
    ]],
    on="clave",
    how="left"
)

# Comprobar que todas las comunidades tienen datos
sin_datos = mapa_final[
    mapa_final["media_horas_precipitacion"].isna()
]

if not sin_datos.empty:
    print("\nATENCIÓN: territorios sin correspondencia:")
    print(sin_datos["name"].tolist())

# --------------------------------------------------
# 6. REPRESENTAR EL MAPA COROPLÉTICO
# --------------------------------------------------

fig, ax = plt.subplots(figsize=(12, 10))

mapa_final.plot(
    column="media_horas_precipitacion",
    cmap="Blues",
    linewidth=0.7,
    edgecolor="black",
    legend=True,
    missing_kwds={
        "color": "lightgrey",
        "label": "Sin datos"
    },
    legend_kwds={
        "label": "Media de horas de precipitación",
        "orientation": "vertical",
        "shrink": 0.7
    },
    ax=ax
)

ax.set_title(
    "Media de horas de precipitación por comunidad autónoma\n"
    "Periodo 2001-2021",
    fontsize=16,
    fontweight="bold",
    pad=20
)

ax.set_axis_off()

plt.tight_layout()

# Guardar el mapa
plt.savefig(
    "mapa_precipitaciones_2001_2021.png",
    dpi=300,
    bbox_inches="tight"
)

plt.show()

# --------------------------------------------------
# 7. EXPORTAR LOS RESULTADOS
# --------------------------------------------------

media_precipitacion.drop(columns="clave").to_csv(
    "media_precipitaciones_por_comunidad.csv",
    index=False
)

print("\nAnálisis finalizado correctamente.")