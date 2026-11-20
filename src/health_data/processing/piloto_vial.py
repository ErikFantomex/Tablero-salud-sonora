"""Exportación del piloto regional construida a partir del grafo de la libreta 3.2."""

import json


def exportar_brigada(salida, tramos, nodos, simuladas, ejemplo_cierre):
    import numpy as np
    import pandas as pd
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    from shapely.geometry import mapping

    # La cabecera municipal sirve como base hipotética.
    clave_base = "260690001"
    candidatas = simuladas[simuladas["population"].gt(0)]
    paradas = pd.concat([
        candidatas[candidatas["locality_id"].eq(clave_base)],
        candidatas[candidatas["locality_id"].ne(clave_base)].sort_values(
            ["population", "locality_id"], ascending=[False, True],
        ).head(15),
    ])
    if paradas.empty or paradas.iloc[0]["locality_id"] != clave_base or len(paradas) < 2:
        raise ValueError("El piloto debe incluir la cabecera de Yécora y otras localidades.")
    arcos = tramos[["ID_RED", "origen", "destino", "minutos"]]
    regreso = arcos.loc[tramos["CIRCULA"].eq("Dos sentidos")].rename(
        columns={"origen": "destino", "destino": "origen"},
    )
    arcos = pd.concat([arcos, regreso]).sort_values(["minutos", "ID_RED"]).drop_duplicates(["origen", "destino"])
    grafo = csr_matrix((arcos["minutos"], (arcos["origen"], arcos["destino"])), shape=(len(nodos), len(nodos)))
    id_arco = arcos.set_index(["origen", "destino"])["ID_RED"].to_dict()
    geometria = tramos.to_crs("EPSG:4326").set_index("ID_RED").geometry
    tiempos, previos = dijkstra(grafo, indices=paradas["nodo"].to_numpy(), return_predecessors=True)
    puntos, conexiones, segmentos = {}, {}, {}
    for origen in paradas.itertuples():
        puntos[origen.locality_id] = {
            "nombre": origen.locality_name, "lon": origen.longitude, "lat": origen.latitude,
            "ajuste_m": round(origen.ajuste_m),
        }
    for i, origen in enumerate(paradas.itertuples()):
        for destino in paradas.itertuples():
            minutos = tiempos[i, destino.nodo]
            if origen.locality_id == destino.locality_id or not np.isfinite(minutos):
                continue
            ids = []
            actual = destino.nodo
            while actual != origen.nodo:
                anterior = int(previos[i, actual])
                arco = id_arco[(anterior, actual)]
                clave = str(int(arco))
                if clave not in segmentos:
                    segmentos[clave] = mapping(geometria.loc[arco].simplify(.00007))
                ids.append(clave)
                actual = anterior
            conexiones[f"{origen.locality_id}:{destino.locality_id}"] = {
                "minutos": round(float(minutos), 6), "segmentos": ids[::-1],
            }
    datos = {"base": clave_base, "puntos": puntos, "conexiones": conexiones, "segmentos": segmentos,
             "ejemplo_cierre": ejemplo_cierre}
    salida.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
