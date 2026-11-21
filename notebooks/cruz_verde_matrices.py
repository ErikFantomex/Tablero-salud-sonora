"""Prepara en CSV los tiempos dirigidos para el experimento Cruz Verde."""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree


def ranking_hospitalario(acceso):
    validas = acceso.loc[acceso["population"].gt(0) & np.isfinite(acceso["secondary_time_min"])]
    ponderadas = validas.assign(ponderado=validas["population"] * validas["secondary_time_min"])
    totales = ponderadas.groupby("municipality_name")[["ponderado", "population"]].sum()
    return (totales["ponderado"] / totales["population"]).sort_values(ascending=False, kind="stable")


def calcular_matrices(comparacion=False):
    raiz = Path(__file__).resolve().parents[1]
    ruta_red = raiz / "data/interim/rnc2025.gpkg"
    if comparacion:
        acceso = pd.read_parquet(raiz / "data/processed/accesibilidad_localidades.parquet")
        municipios = {"Sahuaripa": None, "Arivechi": None}
        recorte = (-111.8, 26.95, -107.75, 30.35)
    else:
        acceso = pd.read_parquet(raiz / "datos_mvp/salud/accesibilidad_localidades.parquet")
        municipios = ranking_hospitalario(acceso).head(7).to_dict()
        # Extensión del recorte de la libreta 3.2 para incluir Sáric.
        recorte = (-112.7, 26.95, -107.75, 32.15)
    columnas = ["ID_RED", "ESTATUS", "CIRCULA", "VELOCIDAD", "UNION_INI", "UNION_FIN", "LONGITUD"]
    red = gpd.read_file(ruta_red, layer="red_vial", bbox=recorte, columns=columnas, ignore_geometry=True)
    nodos = gpd.read_file(ruta_red, layer="union_p", bbox=recorte, columns=["ID_UNION"])
    nodos = nodos.dropna(subset=["ID_UNION", "geometry"]).drop_duplicates("ID_UNION").reset_index(drop=True)
    indices = pd.Series(nodos.index, index=nodos["ID_UNION"])
    origen, destino = red["UNION_INI"].map(indices), red["UNION_FIN"].map(indices)
    velocidad, metros = pd.to_numeric(red["VELOCIDAD"], errors="coerce"), pd.to_numeric(red["LONGITUD"], errors="coerce")
    usable = (red["ESTATUS"].eq("Habilitado") & red["CIRCULA"].isin(["Un sentido", "Dos sentidos"])
              & velocidad.gt(0) & metros.gt(0) & origen.notna() & destino.notna() & origen.ne(destino))
    arcos = red.loc[usable, ["ID_RED", "CIRCULA"]].assign(
        origen=origen[usable].astype(int), destino=destino[usable].astype(int),
        minutos=metros[usable] / 1000 / velocidad[usable] * 60,
    )
    activos = np.unique(arcos[["origen", "destino"]].to_numpy())
    regreso = arcos.loc[arcos["CIRCULA"].eq("Dos sentidos")].rename(columns={"origen": "destino", "destino": "origen"})
    arcos = pd.concat([arcos, regreso]).sort_values(["minutos", "ID_RED"]).drop_duplicates(["origen", "destino"])
    grafo = csr_matrix((arcos["minutos"], (arcos["origen"], arcos["destino"])), shape=(len(nodos), len(nodos)))

    proyeccion = "EPSG:32612"
    geometria = nodos.geometry.iloc[activos].to_crs(proyeccion)
    arbol = cKDTree(np.column_stack([geometria.x, geometria.y]))
    grafo_inverso = grafo.T.tocsr()
    for rango, (municipio, acceso_hospital) in enumerate(municipios.items(), start=1):
        resumen = {"rango": rango, "municipio": municipio, "acceso_hospital": acceso_hospital}
        locales = acceso.loc[acceso["municipality_name"].eq(municipio) & acceso["population"].gt(0)]
        locales = locales.dropna(subset=["longitude", "latitude"])
        if locales.empty:
            yield {**resumen, "estado": "Sin localidades con coordenadas"}
            continue
        puntos = gpd.GeoSeries(gpd.points_from_xy(locales["longitude"], locales["latitude"]), crs="EPSG:4326").to_crs(proyeccion)
        ajuste, posicion = arbol.query(np.column_stack([puntos.x, puntos.y]))
        locales = locales.assign(nodo=activos[posicion], ajuste_m=ajuste)
        locales = locales.loc[locales["ajuste_m"].le(5000)]
        cabecera = locales.loc[locales["locality_id"].str.endswith("0001")]
        if len(cabecera) != 1:
            yield {**resumen, "estado": "Sin cabecera con ajuste vial válido"}
            continue
        nodo_base = int(cabecera["nodo"].iloc[0])
        ida = dijkstra(grafo, indices=nodo_base)
        vuelta = dijkstra(grafo_inverso, indices=nodo_base)
        candidatos = locales.loc[locales["nodo"].ne(nodo_base)]
        candidatos = candidatos.loc[np.isfinite(ida[candidatos["nodo"]]) & np.isfinite(vuelta[candidatos["nodo"]])]
        paradas = candidatos.sort_values(["population", "locality_id"], ascending=[False, True]).drop_duplicates("nodo").head(3)
        if len(paradas) < 2:
            yield {**resumen, "estado": f"Solo {len(paradas)} paradas conectadas"}
            continue
        seleccion = pd.concat([cabecera, paradas]).reset_index(drop=True)
        claves = seleccion["nodo"].to_numpy()
        tiempos = dijkstra(grafo, indices=claves)[:, claves]
        for i, origen in seleccion.iterrows():
            for j in range(len(seleccion)):
                yield {**resumen, "estado": "OK", "origen": i + 1, "destino": j + 1,
                       "localidad": origen["locality_name"], "poblacion": origen["population"],
                       "ajuste_m": round(origen["ajuste_m"], 1), "minutos": tiempos[i, j]}


if __name__ == "__main__":
    comparacion = len(sys.argv) > 2 and sys.argv[2] == "comparacion"
    pd.DataFrame(calcular_matrices(comparacion)).to_csv(sys.argv[1], index=False, encoding="utf-8")
