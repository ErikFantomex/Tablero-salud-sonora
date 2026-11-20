"""Vista pública del escenario vial y del recorrido de una brigada."""

import json
from itertools import pairwise
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from health_data.red_vial import MAX_PARADAS, minutos_ruta, optimizar_brigada
from health_data.visualization.complementarias import vista_red_vial


@st.cache_data(show_spinner=False)
def leer_brigada(ruta: Path, modificacion_ns: int) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def mapa_brigada(orden, puntos, conexiones, segmentos):
    x, y = [], []
    for a, b in pairwise(orden):
        for clave in conexiones[f"{a}:{b}"]["segmentos"]:
            geo = segmentos[clave]
            lineas = [geo["coordinates"]] if geo["type"] == "LineString" else geo["coordinates"]
            for linea in lineas:
                x.extend([p[0] for p in linea] + [None])
                y.extend([p[1] for p in linea] + [None])
    figura = go.Figure(go.Scatter(x=x, y=y, mode="lines", name="Trayecto por carretera",
                                  line={"color": "#087f73", "width": 3}, hoverinfo="skip"))
    escalas = [puntos[clave] for clave in orden[:-1]]
    figura.add_scatter(
        x=[p["lon"] for p in escalas], y=[p["lat"] for p in escalas],
        mode="markers+text", marker={"size": 20, "color": "#153b43"},
        text=["B", *(str(i) for i in range(1, len(escalas)))], textfont={"color": "white"},
        textposition="middle center", customdata=[p["nombre"] for p in escalas],
        name="Base y paradas", hovertemplate="%{customdata}<extra></extra>",
    )
    figura.update_layout(title="Recorrido optimizado por carretera", height=430, dragmode="pan",
                         margin={"l": 12, "r": 12, "t": 52, "b": 12}, showlegend=False)
    figura.update_xaxes(title="Longitud")
    figura.update_yaxes(title="Latitud", scaleanchor="x", scaleratio=1.13)
    return figura


def simular_brigada(datos: dict) -> None:
    st.subheader("Organiza las visitas de una brigada")
    puntos, conexiones = datos["puntos"], datos["conexiones"]
    clave_base = datos["base"]
    st.caption(f"Base hipotética en {puntos[clave_base]['nombre']}. El recorrido regresa a la base. "
               "Los minutos corresponden a conducción y excluyen las consultas y el acceso desde cada localidad a la red.")
    opciones = [clave for clave in puntos if clave != clave_base]
    conectadas = [clave for clave in opciones if f"{clave_base}:{clave}" in conexiones and f"{clave}:{clave_base}" in conexiones]
    ejemplo = conectadas[1:2] + conectadas[:1] + conectadas[2:3]
    paradas = st.multiselect("Localidades en orden de visita", opciones, default=ejemplo,
                             max_selections=MAX_PARADAS, format_func=lambda clave: puntos[clave]["nombre"],
                             help="El ejemplo inicial sirve para comparar. El orden en que agregas paradas forma tu ruta de referencia.")
    if not paradas:
        st.info("Elige al menos una localidad para calcular el recorrido.")
        return
    entrada = (clave_base, *paradas, clave_base)
    inicial = minutos_ruta(entrada, conexiones)
    orden, minutos = optimizar_brigada(clave_base, paradas, conexiones)
    if orden is None:
        faltan = [puntos[clave]["nombre"] for clave in paradas if clave not in conectadas]
        detalle = f" Revisa estas paradas: {', '.join(faltan)}." if faltan else ""
        st.warning("No hay un recorrido de ida y vuelta para todas las paradas en el recorte." + detalle)
        return
    a, b, c = st.columns(3)
    a.metric("Orden elegido", f"{inicial:.1f} min" if inicial is not None else "Sin ruta")
    b.metric("Orden optimizado", f"{minutos:.1f} min")
    c.metric("Ahorro de conducción", f"{max(inicial - minutos, 0):.1f} min" if inicial is not None else "Sin comparación")
    st.caption("El cálculo prueba todos los órdenes posibles para las paradas elegidas y respeta los sentidos viales.")
    st.plotly_chart(mapa_brigada(orden, puntos, conexiones, datos["segmentos"]), use_container_width=True)
    st.dataframe(pd.DataFrame([
        {"Orden": i if i < len(orden) - 1 else "Regreso", "Localidad": puntos[clave]["nombre"],
         "Minutos desde la parada anterior": round(conexiones[f"{orden[i-1]}:{clave}"]["minutos"], 1) if i else None}
        for i, clave in enumerate(orden)
    ]).assign(Orden=lambda tabla: tabla["Orden"].astype(str)), hide_index=True, use_container_width=True)


def vista_piloto_vial(directorio: Path) -> None:
    st.title("Red vial y brigadas")
    st.caption("Piloto de Yécora · Red Nacional de Caminos 2025. Escenarios de análisis con tiempos estimados.")
    ruta = directorio / "brigada_yecora.json"
    datos = leer_brigada(ruta, ruta.stat().st_mtime_ns) if ruta.is_file() else None
    cierre, brigada = st.tabs(["Cierre de carretera", "Recorrido de brigada"])
    with cierre:
        ejemplo = (datos or {}).get("ejemplo_cierre")
        vista_red_vial(directorio, ejemplo["localidad"] if ejemplo else None)
    with brigada:
        if datos:
            simular_brigada(datos)
        else:
            st.info("Ejecuta la libreta 3.2 para generar la matriz de recorridos de la brigada.")
